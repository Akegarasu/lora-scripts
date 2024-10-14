import argparse
import copy
import math
import random
from typing import Any, Optional

import torch
from accelerate import Accelerator
from library.device_utils import init_ipex, clean_memory_on_device

init_ipex()

from library import flux_models, flux_train_utils, flux_utils, sd3_train_utils, strategy_base, strategy_flux, train_util
import train_network
from library.utils import setup_logging

setup_logging()
import logging

logger = logging.getLogger(__name__)


class FluxNetworkTrainer(train_network.NetworkTrainer):
    def __init__(self):
        super().__init__()
        self.sample_prompts_te_outputs = None
        self.is_schnell: Optional[bool] = None

    def assert_extra_args(self, args, train_dataset_group):
        super().assert_extra_args(args, train_dataset_group)
        # sdxl_train_util.verify_sdxl_training_args(args)

        if args.fp8_base_unet:
            args.fp8_base = True  # if fp8_base_unet is enabled, fp8_base is also enabled for FLUX.1

        if args.cache_text_encoder_outputs_to_disk and not args.cache_text_encoder_outputs:
            logger.warning(
                "cache_text_encoder_outputs_to_disk is enabled, so cache_text_encoder_outputs is also enabled / cache_text_encoder_outputs_to_diskが有効になっているため、cache_text_encoder_outputsも有効になります"
            )
            args.cache_text_encoder_outputs = True

        if args.cache_text_encoder_outputs:
            assert (
                train_dataset_group.is_text_encoder_output_cacheable()
            ), "when caching Text Encoder output, either caption_dropout_rate, shuffle_caption, token_warmup_step or caption_tag_dropout_rate cannot be used / Text Encoderの出力をキャッシュするときはcaption_dropout_rate, shuffle_caption, token_warmup_step, caption_tag_dropout_rateは使えません"

        # prepare CLIP-L/T5XXL training flags
        self.train_clip_l = not args.network_train_unet_only
        self.train_t5xxl = False  # default is False even if args.network_train_unet_only is False

        if args.max_token_length is not None:
            logger.warning("max_token_length is not used in Flux training / max_token_lengthはFluxのトレーニングでは使用されません")

        assert not args.split_mode or not args.cpu_offload_checkpointing, (
            "split_mode and cpu_offload_checkpointing cannot be used together"
            " / split_modeとcpu_offload_checkpointingは同時に使用できません"
        )

        train_dataset_group.verify_bucket_reso_steps(32)  # TODO check this

    def load_target_model(self, args, weight_dtype, accelerator):
        # currently offload to cpu for some models

        # if the file is fp8 and we are using fp8_base, we can load it as is (fp8)
        loading_dtype = None if args.fp8_base else weight_dtype

        # if we load to cpu, flux.to(fp8) takes a long time, so we should load to gpu in future
        self.is_schnell, model = flux_utils.load_flow_model(
            args.pretrained_model_name_or_path, loading_dtype, "cpu", disable_mmap=args.disable_mmap_load_safetensors
        )
        if args.fp8_base:
            # check dtype of model
            if model.dtype == torch.float8_e4m3fnuz or model.dtype == torch.float8_e5m2 or model.dtype == torch.float8_e5m2fnuz:
                raise ValueError(f"Unsupported fp8 model dtype: {model.dtype}")
            elif model.dtype == torch.float8_e4m3fn:
                logger.info("Loaded fp8 FLUX model")

        if args.split_mode:
            model = self.prepare_split_model(model, weight_dtype, accelerator)

        clip_l = flux_utils.load_clip_l(args.clip_l, weight_dtype, "cpu", disable_mmap=args.disable_mmap_load_safetensors)
        clip_l.eval()

        # if the file is fp8 and we are using fp8_base (not unet), we can load it as is (fp8)
        if args.fp8_base and not args.fp8_base_unet:
            loading_dtype = None  # as is
        else:
            loading_dtype = weight_dtype

        # loading t5xxl to cpu takes a long time, so we should load to gpu in future
        t5xxl = flux_utils.load_t5xxl(args.t5xxl, loading_dtype, "cpu", disable_mmap=args.disable_mmap_load_safetensors)
        t5xxl.eval()
        if args.fp8_base and not args.fp8_base_unet:
            # check dtype of model
            if t5xxl.dtype == torch.float8_e4m3fnuz or t5xxl.dtype == torch.float8_e5m2 or t5xxl.dtype == torch.float8_e5m2fnuz:
                raise ValueError(f"Unsupported fp8 model dtype: {t5xxl.dtype}")
            elif t5xxl.dtype == torch.float8_e4m3fn:
                logger.info("Loaded fp8 T5XXL model")

        ae = flux_utils.load_ae(args.ae, weight_dtype, "cpu", disable_mmap=args.disable_mmap_load_safetensors)

        return flux_utils.MODEL_VERSION_FLUX_V1, [clip_l, t5xxl], ae, model

    def prepare_split_model(self, model, weight_dtype, accelerator):
        from accelerate import init_empty_weights

        logger.info("prepare split model")
        with init_empty_weights():
            flux_upper = flux_models.FluxUpper(model.params)
            flux_lower = flux_models.FluxLower(model.params)
        sd = model.state_dict()

        # lower (trainable)
        logger.info("load state dict for lower")
        flux_lower.load_state_dict(sd, strict=False, assign=True)
        flux_lower.to(dtype=weight_dtype)

        # upper (frozen)
        logger.info("load state dict for upper")
        flux_upper.load_state_dict(sd, strict=False, assign=True)

        logger.info("prepare upper model")
        target_dtype = torch.float8_e4m3fn if args.fp8_base else weight_dtype
        flux_upper.to(accelerator.device, dtype=target_dtype)
        flux_upper.eval()

        if args.fp8_base:
            # this is required to run on fp8
            flux_upper = accelerator.prepare(flux_upper)

        flux_upper.to("cpu")

        self.flux_upper = flux_upper
        del model  # we don't need model anymore
        clean_memory_on_device(accelerator.device)

        logger.info("split model prepared")

        return flux_lower

    def get_tokenize_strategy(self, args):
        _, is_schnell, _ = flux_utils.check_flux_state_dict_diffusers_schnell(args.pretrained_model_name_or_path)

        if args.t5xxl_max_token_length is None:
            if is_schnell:
                t5xxl_max_token_length = 256
            else:
                t5xxl_max_token_length = 512
        else:
            t5xxl_max_token_length = args.t5xxl_max_token_length

        logger.info(f"t5xxl_max_token_length: {t5xxl_max_token_length}")
        return strategy_flux.FluxTokenizeStrategy(t5xxl_max_token_length, args.tokenizer_cache_dir)

    def get_tokenizers(self, tokenize_strategy: strategy_flux.FluxTokenizeStrategy):
        return [tokenize_strategy.clip_l, tokenize_strategy.t5xxl]

    def get_latents_caching_strategy(self, args):
        latents_caching_strategy = strategy_flux.FluxLatentsCachingStrategy(args.cache_latents_to_disk, args.vae_batch_size, False)
        return latents_caching_strategy

    def get_text_encoding_strategy(self, args):
        return strategy_flux.FluxTextEncodingStrategy(apply_t5_attn_mask=args.apply_t5_attn_mask)

    def post_process_network(self, args, accelerator, network, text_encoders, unet):
        # check t5xxl is trained or not
        self.train_t5xxl = network.train_t5xxl

        if self.train_t5xxl and args.cache_text_encoder_outputs:
            raise ValueError(
                "T5XXL is trained, so cache_text_encoder_outputs cannot be used / T5XXL学習時はcache_text_encoder_outputsは使用できません"
            )

    def get_models_for_text_encoding(self, args, accelerator, text_encoders):
        if args.cache_text_encoder_outputs:
            if self.train_clip_l and not self.train_t5xxl:
                return text_encoders[0:1]  # only CLIP-L is needed for encoding because T5XXL is cached
            else:
                return None  # no text encoders are needed for encoding because both are cached
        else:
            return text_encoders  # both CLIP-L and T5XXL are needed for encoding

    def get_text_encoders_train_flags(self, args, text_encoders):
        return [self.train_clip_l, self.train_t5xxl]

    def get_text_encoder_outputs_caching_strategy(self, args):
        if args.cache_text_encoder_outputs:
            # if the text encoders is trained, we need tokenization, so is_partial is True
            return strategy_flux.FluxTextEncoderOutputsCachingStrategy(
                args.cache_text_encoder_outputs_to_disk,
                None,
                False,
                is_partial=self.train_clip_l or self.train_t5xxl,
                apply_t5_attn_mask=args.apply_t5_attn_mask,
            )
        else:
            return None

    def cache_text_encoder_outputs_if_needed(
        self, args, accelerator: Accelerator, unet, vae, text_encoders, dataset: train_util.DatasetGroup, weight_dtype
    ):
        if args.cache_text_encoder_outputs:
            if not args.lowram:
                # メモリ消費を減らす
                logger.info("move vae and unet to cpu to save memory")
                org_vae_device = vae.device
                org_unet_device = unet.device
                vae.to("cpu")
                unet.to("cpu")
                clean_memory_on_device(accelerator.device)

            # When TE is not be trained, it will not be prepared so we need to use explicit autocast
            logger.info("move text encoders to gpu")
            text_encoders[0].to(accelerator.device, dtype=weight_dtype)  # always not fp8
            text_encoders[1].to(accelerator.device)

            if text_encoders[1].dtype == torch.float8_e4m3fn:
                # if we load fp8 weights, the model is already fp8, so we use it as is
                self.prepare_text_encoder_fp8(1, text_encoders[1], text_encoders[1].dtype, weight_dtype)
            else:
                # otherwise, we need to convert it to target dtype
                text_encoders[1].to(weight_dtype)

            with accelerator.autocast():
                dataset.new_cache_text_encoder_outputs(text_encoders, accelerator.is_main_process)

            # cache sample prompts
            if args.sample_prompts is not None:
                logger.info(f"cache Text Encoder outputs for sample prompt: {args.sample_prompts}")

                tokenize_strategy: strategy_flux.FluxTokenizeStrategy = strategy_base.TokenizeStrategy.get_strategy()
                text_encoding_strategy: strategy_flux.FluxTextEncodingStrategy = strategy_base.TextEncodingStrategy.get_strategy()

                prompts = sd3_train_utils.load_prompts(args.sample_prompts)
                sample_prompts_te_outputs = {}  # key: prompt, value: text encoder outputs
                with accelerator.autocast(), torch.no_grad():
                    for prompt_dict in prompts:
                        for p in [prompt_dict.get("prompt", ""), prompt_dict.get("negative_prompt", "")]:
                            if p not in sample_prompts_te_outputs:
                                logger.info(f"cache Text Encoder outputs for prompt: {p}")
                                tokens_and_masks = tokenize_strategy.tokenize(p)
                                sample_prompts_te_outputs[p] = text_encoding_strategy.encode_tokens(
                                    tokenize_strategy, text_encoders, tokens_and_masks, args.apply_t5_attn_mask
                                )
                self.sample_prompts_te_outputs = sample_prompts_te_outputs

            accelerator.wait_for_everyone()

            # move back to cpu
            if not self.is_train_text_encoder(args):
                logger.info("move CLIP-L back to cpu")
                text_encoders[0].to("cpu")
            logger.info("move t5XXL back to cpu")
            text_encoders[1].to("cpu")
            clean_memory_on_device(accelerator.device)

            if not args.lowram:
                logger.info("move vae and unet back to original device")
                vae.to(org_vae_device)
                unet.to(org_unet_device)
        else:
            # Text Encoderから毎回出力を取得するので、GPUに乗せておく
            text_encoders[0].to(accelerator.device, dtype=weight_dtype)
            text_encoders[1].to(accelerator.device)

    # def call_unet(self, args, accelerator, unet, noisy_latents, timesteps, text_conds, batch, weight_dtype):
    #     noisy_latents = noisy_latents.to(weight_dtype)  # TODO check why noisy_latents is not weight_dtype

    #     # get size embeddings
    #     orig_size = batch["original_sizes_hw"]
    #     crop_size = batch["crop_top_lefts"]
    #     target_size = batch["target_sizes_hw"]
    #     embs = sdxl_train_util.get_size_embeddings(orig_size, crop_size, target_size, accelerator.device).to(weight_dtype)

    #     # concat embeddings
    #     encoder_hidden_states1, encoder_hidden_states2, pool2 = text_conds
    #     vector_embedding = torch.cat([pool2, embs], dim=1).to(weight_dtype)
    #     text_embedding = torch.cat([encoder_hidden_states1, encoder_hidden_states2], dim=2).to(weight_dtype)

    #     noise_pred = unet(noisy_latents, timesteps, text_embedding, vector_embedding)
    #     return noise_pred

    def sample_images(self, accelerator, args, epoch, global_step, device, ae, tokenizer, text_encoder, flux):
        text_encoders = text_encoder  # for compatibility
        text_encoders = self.get_models_for_text_encoding(args, accelerator, text_encoders)

        if not args.split_mode:
            flux_train_utils.sample_images(
                accelerator, args, epoch, global_step, flux, ae, text_encoders, self.sample_prompts_te_outputs
            )
            return

        class FluxUpperLowerWrapper(torch.nn.Module):
            def __init__(self, flux_upper: flux_models.FluxUpper, flux_lower: flux_models.FluxLower, device: torch.device):
                super().__init__()
                self.flux_upper = flux_upper
                self.flux_lower = flux_lower
                self.target_device = device

            def prepare_block_swap_before_forward(self):
                pass

            def forward(self, img, img_ids, txt, txt_ids, timesteps, y, guidance=None, txt_attention_mask=None):
                self.flux_lower.to("cpu")
                clean_memory_on_device(self.target_device)
                self.flux_upper.to(self.target_device)
                img, txt, vec, pe = self.flux_upper(img, img_ids, txt, txt_ids, timesteps, y, guidance, txt_attention_mask)
                self.flux_upper.to("cpu")
                clean_memory_on_device(self.target_device)
                self.flux_lower.to(self.target_device)
                return self.flux_lower(img, txt, vec, pe, txt_attention_mask)

        wrapper = FluxUpperLowerWrapper(self.flux_upper, flux, accelerator.device)
        clean_memory_on_device(accelerator.device)
        flux_train_utils.sample_images(
            accelerator, args, epoch, global_step, wrapper, ae, text_encoders, self.sample_prompts_te_outputs
        )
        clean_memory_on_device(accelerator.device)

    def get_noise_scheduler(self, args: argparse.Namespace, device: torch.device) -> Any:
        noise_scheduler = sd3_train_utils.FlowMatchEulerDiscreteScheduler(num_train_timesteps=1000, shift=args.discrete_flow_shift)
        self.noise_scheduler_copy = copy.deepcopy(noise_scheduler)
        return noise_scheduler

    def encode_images_to_latents(self, args, accelerator, vae, images):
        return vae.encode(images)

    def shift_scale_latents(self, args, latents):
        return latents

    def get_noise_pred_and_target(
        self,
        args,
        accelerator,
        noise_scheduler,
        latents,
        batch,
        text_encoder_conds,
        unet: flux_models.Flux,
        network,
        weight_dtype,
        train_unet,
    ):
        # Sample noise that we'll add to the latents
        noise = torch.randn_like(latents)
        bsz = latents.shape[0]

        # get noisy model input and timesteps
        noisy_model_input, timesteps, sigmas = flux_train_utils.get_noisy_model_input_and_timesteps(
            args, noise_scheduler, latents, noise, accelerator.device, weight_dtype
        )

        # pack latents and get img_ids
        packed_noisy_model_input = flux_utils.pack_latents(noisy_model_input)  # b, c, h*2, w*2 -> b, h*w, c*4
        packed_latent_height, packed_latent_width = noisy_model_input.shape[2] // 2, noisy_model_input.shape[3] // 2
        img_ids = flux_utils.prepare_img_ids(bsz, packed_latent_height, packed_latent_width).to(device=accelerator.device)

        # get guidance
        # ensure guidance_scale in args is float
        guidance_vec = torch.full((bsz,), float(args.guidance_scale), device=accelerator.device)

        # ensure the hidden state will require grad
        if args.gradient_checkpointing:
            noisy_model_input.requires_grad_(True)
            for t in text_encoder_conds:
                if t.dtype.is_floating_point:
                    t.requires_grad_(True)
            img_ids.requires_grad_(True)
            guidance_vec.requires_grad_(True)

        # Predict the noise residual
        l_pooled, t5_out, txt_ids, t5_attn_mask = text_encoder_conds
        if not args.apply_t5_attn_mask:
            t5_attn_mask = None

        if not args.split_mode:
            # normal forward
            with accelerator.autocast():
                # YiYi notes: divide it by 1000 for now because we scale it by 1000 in the transformer model (we should not keep it but I want to keep the inputs same for the model for testing)
                model_pred = unet(
                    img=packed_noisy_model_input,
                    img_ids=img_ids,
                    txt=t5_out,
                    txt_ids=txt_ids,
                    y=l_pooled,
                    timesteps=timesteps / 1000,
                    guidance=guidance_vec,
                    txt_attention_mask=t5_attn_mask,
                )
        else:
            # split forward to reduce memory usage
            assert network.train_blocks == "single", "train_blocks must be single for split mode"
            with accelerator.autocast():
                # move flux lower to cpu, and then move flux upper to gpu
                unet.to("cpu")
                clean_memory_on_device(accelerator.device)
                self.flux_upper.to(accelerator.device)

                # upper model does not require grad
                with torch.no_grad():
                    intermediate_img, intermediate_txt, vec, pe = self.flux_upper(
                        img=packed_noisy_model_input,
                        img_ids=img_ids,
                        txt=t5_out,
                        txt_ids=txt_ids,
                        y=l_pooled,
                        timesteps=timesteps / 1000,
                        guidance=guidance_vec,
                        txt_attention_mask=t5_attn_mask,
                    )

                # move flux upper back to cpu, and then move flux lower to gpu
                self.flux_upper.to("cpu")
                clean_memory_on_device(accelerator.device)
                unet.to(accelerator.device)

                # lower model requires grad
                intermediate_img.requires_grad_(True)
                intermediate_txt.requires_grad_(True)
                vec.requires_grad_(True)
                pe.requires_grad_(True)
                model_pred = unet(img=intermediate_img, txt=intermediate_txt, vec=vec, pe=pe, txt_attention_mask=t5_attn_mask)

        # unpack latents
        model_pred = flux_utils.unpack_latents(model_pred, packed_latent_height, packed_latent_width)

        # apply model prediction type
        model_pred, weighting = flux_train_utils.apply_model_prediction_type(args, model_pred, noisy_model_input, sigmas)

        # flow matching loss: this is different from SD3
        target = noise - latents

        return model_pred, target, timesteps, None, weighting

    def post_process_loss(self, loss, args, timesteps, noise_scheduler):
        return loss

    def get_sai_model_spec(self, args):
        return train_util.get_sai_model_spec(None, args, False, True, False, flux="dev")

    def update_metadata(self, metadata, args):
        metadata["ss_apply_t5_attn_mask"] = args.apply_t5_attn_mask
        metadata["ss_weighting_scheme"] = args.weighting_scheme
        metadata["ss_logit_mean"] = args.logit_mean
        metadata["ss_logit_std"] = args.logit_std
        metadata["ss_mode_scale"] = args.mode_scale
        metadata["ss_guidance_scale"] = args.guidance_scale
        metadata["ss_timestep_sampling"] = args.timestep_sampling
        metadata["ss_sigmoid_scale"] = args.sigmoid_scale
        metadata["ss_model_prediction_type"] = args.model_prediction_type
        metadata["ss_discrete_flow_shift"] = args.discrete_flow_shift

    def is_text_encoder_not_needed_for_training(self, args):
        return args.cache_text_encoder_outputs and not self.is_train_text_encoder(args)

    def prepare_text_encoder_grad_ckpt_workaround(self, index, text_encoder):
        if index == 0:  # CLIP-L
            return super().prepare_text_encoder_grad_ckpt_workaround(index, text_encoder)
        else:  # T5XXL
            text_encoder.encoder.embed_tokens.requires_grad_(True)

    def prepare_text_encoder_fp8(self, index, text_encoder, te_weight_dtype, weight_dtype):
        if index == 0:  # CLIP-L
            logger.info(f"prepare CLIP-L for fp8: set to {te_weight_dtype}, set embeddings to {weight_dtype}")
            text_encoder.to(te_weight_dtype)  # fp8
            text_encoder.text_model.embeddings.to(dtype=weight_dtype)
        else:  # T5XXL

            def prepare_fp8(text_encoder, target_dtype):
                def forward_hook(module):
                    def forward(hidden_states):
                        hidden_gelu = module.act(module.wi_0(hidden_states))
                        hidden_linear = module.wi_1(hidden_states)
                        hidden_states = hidden_gelu * hidden_linear
                        hidden_states = module.dropout(hidden_states)

                        hidden_states = module.wo(hidden_states)
                        return hidden_states

                    return forward

                for module in text_encoder.modules():
                    if module.__class__.__name__ in ["T5LayerNorm", "Embedding"]:
                        # print("set", module.__class__.__name__, "to", target_dtype)
                        module.to(target_dtype)
                    if module.__class__.__name__ in ["T5DenseGatedActDense"]:
                        # print("set", module.__class__.__name__, "hooks")
                        module.forward = forward_hook(module)

            if flux_utils.get_t5xxl_actual_dtype(text_encoder) == torch.float8_e4m3fn and text_encoder.dtype == weight_dtype:
                logger.info(f"T5XXL already prepared for fp8")
            else:
                logger.info(f"prepare T5XXL for fp8: set to {te_weight_dtype}, set embeddings to {weight_dtype}, add hooks")
                text_encoder.to(te_weight_dtype)  # fp8
                prepare_fp8(text_encoder, weight_dtype)


def setup_parser() -> argparse.ArgumentParser:
    parser = train_network.setup_parser()
    flux_train_utils.add_flux_train_arguments(parser)

    parser.add_argument(
        "--split_mode",
        action="store_true",
        help="[EXPERIMENTAL] use split mode for Flux model, network arg `train_blocks=single` is required"
        + "/[実験的] Fluxモデルの分割モードを使用する。ネットワーク引数`train_blocks=single`が必要",
    )
    return parser


if __name__ == "__main__":
    parser = setup_parser()

    args = parser.parse_args()
    train_util.verify_command_line_training_args(args)
    args = train_util.read_config_from_file(args, parser)

    trainer = FluxNetworkTrainer()
    trainer.train(args)
