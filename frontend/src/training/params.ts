import { cloneFormModel, type FormModel, type FormValue } from "../schema/adapter"
import { parse } from "smol-toml"

const FLOAT_PARAMS = ["learning_rate", "unet_lr", "text_encoder_lr", "learning_rate_te", "learning_rate_te1", "learning_rate_te2", "sigmoid_scale", "guidance_scale"]
const OPTIONAL_PARAMS = ["vae", "reg_data_dir", "network_weights", "noise_offset", "multires_noise_iterations", "multires_noise_discount", "caption_dropout_rate", "network_dropout", "scale_weight_norms", "gpu_ids"]
const PATH_PARAMS = ["pretrained_model_name_or_path", "vae", "qwen3", "llm_adapter_path", "t5_tokenizer_path", "resume", "train_data_dir", "reg_data_dir", "output_dir", "logging_dir", "network_weights", "sample_prompts"]
const UI_PARAMS = ["lycoris_algo", "conv_dim", "conv_alpha", "dropout", "dylora_unit", "lokr_factor", "train_norm", "down_lr_weight", "mid_lr_weight", "up_lr_weight", "block_lr_zero_threshold", "enable_block_weights", "network_args_custom", "optimizer_args_custom", "enable_base_weight", "prodigy_d0", "prodigy_d_coef", "ui_custom_params"]
const SD_PARAMS = ["v2", "v_parameterization", "scale_v_pred_loss_like_noise_pred", "clip_skip", "learning_rate_te", "stop_text_encoder_training"]
const SDXL_PARAMS = ["learning_rate_te1", "learning_rate_te2"]
const PREVIEW_PARAMS = ["prompt_file", "sample_width", "sample_height", "sample_cfg", "sample_seed", "sample_steps", "sample_sampler", "randomly_choice_prompt", "sample_at_first", "sample_every_n_epochs", "sample_every_n_steps", "positive_prompts", "negative_prompts", "sample_prompts"]

const BASIC_DEFAULTS: FormModel = {
  model_train_type: "sd-lora", enable_bucket: true, min_bucket_reso: 256, max_bucket_reso: 1024,
  save_model_as: "safetensors", network_train_unet_only: false, network_train_text_encoder_only: false,
  learning_rate: 1e-4, network_module: "networks.lora", logging_dir: "./logs", caption_extension: ".txt",
  max_token_length: 255, seed: 1337, prior_loss_weight: 1, clip_skip: 2, save_precision: "fp16",
  persistent_data_loader_workers: true,
}

export interface ParamDiagnostics {
  warnings: string[]
  errors: string[]
}

function values(value: FormValue) {
  return Array.isArray(value) ? value : []
}

function remove(config: FormModel, keys: string[]) {
  keys.forEach((key) => delete config[key])
}

export function buildTrainingConfig(source: FormModel, schemaName: string) {
  const config: FormModel = schemaName === "lora-basic" ? { ...BASIC_DEFAULTS, ...cloneFormModel(source) } : cloneFormModel(source)
  let networkArgs: string[] = []
  let optimizerArgs: string[] = []

  if (config.network_module === "lycoris.kohya") {
    networkArgs.push(`conv_dim=${config.conv_dim}`, `conv_alpha=${config.conv_alpha}`, `dropout=${config.dropout}`, `algo=${config.lycoris_algo}`)
    if (config.lokr_factor) networkArgs.push(`factor=${config.lokr_factor}`)
    if (config.train_norm) networkArgs.push("train_norm=True")
  } else if (config.network_module === "networks.dylora") {
    networkArgs.push(`unit=${config.dylora_unit}`)
  }

  const optimizer = String(config.optimizer_type || "")
  if (optimizer.toLowerCase().startsWith("dada")) {
    if (["DAdaptation", "DAdaptAdam"].includes(optimizer)) optimizerArgs = ["decouple=True", "weight_decay=0.01"]
    config.learning_rate = 1
    config.unet_lr = 1
    config.text_encoder_lr = 1
  } else if (optimizer.toLowerCase() === "prodigy") {
    optimizerArgs = ["decouple=True", "weight_decay=0.01", "use_bias_correction=True", `d_coef=${config.prodigy_d_coef}`]
    if (config.lr_warmup_steps) optimizerArgs.push("safeguard_warmup=True")
    if (config.prodigy_d0) optimizerArgs.push(`d0=${config.prodigy_d0}`)
  }

  if (config.enable_block_weights) {
    networkArgs.push(`down_lr_weight=${config.down_lr_weight}`, `mid_lr_weight=${config.mid_lr_weight}`, `up_lr_weight=${config.up_lr_weight}`, `block_lr_zero_threshold=${config.block_lr_zero_threshold}`)
  }
  if (config.enable_base_weight) {
    if (typeof config.base_weights === "string") config.base_weights = config.base_weights.split(/\r?\n/).filter(Boolean)
    if (typeof config.base_weights_multiplier === "string") config.base_weights_multiplier = config.base_weights_multiplier.split(/\r?\n/).filter(Boolean).map(Number)
  } else {
    remove(config, ["base_weights", "base_weights_multiplier"])
  }

  networkArgs.push(...values(config.network_args).map(String), ...values(config.network_args_custom).map(String))
  optimizerArgs.push(...values(config.optimizer_args).map(String), ...values(config.optimizer_args_custom).map(String))
  if (networkArgs.length) config.network_args = networkArgs
  else delete config.network_args
  if (optimizerArgs.length) config.optimizer_args = optimizerArgs
  else delete config.optimizer_args

  const hasPreview = PREVIEW_PARAMS.some((key) => {
    const value = config[key]
    return value !== undefined && value !== "" && (!Array.isArray(value) || value.length > 0)
  })
  if (hasPreview) config.enable_preview = true
  if (!config.enable_preview) remove(config, PREVIEW_PARAMS)

  for (const key of FLOAT_PARAMS) {
    if (config[key] === undefined) continue
    const parsed = Number.parseFloat(String(config[key]))
    config[key] = Number.isNaN(parsed) ? 0 : parsed
  }
  for (const key of OPTIONAL_PARAMS) {
    const value = config[key]
    if (value === 0 || value === "" || (Array.isArray(value) && !value.length)) delete config[key]
  }
  for (const key of PATH_PARAMS) if (typeof config[key] === "string") config[key] = config[key].replaceAll("\\", "/")

  if (typeof source.ui_custom_params === "string" && source.ui_custom_params.trim()) {
    Object.assign(config, parse(source.ui_custom_params) as FormModel)
  }

  const isSdxl = String(config.model_train_type || "").startsWith("sdxl")
  if (isSdxl && (config.learning_rate_te1 || config.learning_rate_te2)) config.train_text_encoder = true
  remove(config, isSdxl ? SD_PARAMS : SDXL_PARAMS)
  remove(config, UI_PARAMS)

  if (Array.isArray(config.gpu_ids)) {
    config.gpu_ids = config.gpu_ids.map((value) => String(value).match(/GPU (\d+):/)?.[1] || String(value)).filter(Boolean)
  }
  return config
}

export function hydrateImportedConfig(source: FormModel) {
  const config = cloneFormModel(source)
  for (const key of FLOAT_PARAMS) {
    const value = config[key]
    if (typeof value !== "number") continue
    const exponential = value.toExponential()
    config[key] = exponential.length <= 6 ? exponential : String(value)
  }
  if (Array.isArray(config.network_args)) {
    for (const raw of config.network_args) {
      const [key, ...rest] = String(raw).split("=")
      const value = rest.join("=")
      if (!key) continue
      config[key === "algo" ? "lycoris_algo" : key] = value
    }
    delete config.network_args
  }
  if (Array.isArray(config.optimizer_args)) {
    config.optimizer_args_custom = config.optimizer_args
    delete config.optimizer_args
  }
  return config
}

export function checkTrainingConfig(config: FormModel): ParamDiagnostics {
  const warnings: string[] = []
  const errors: string[] = []
  const optimizer = String(config.optimizer_type || "")
  if (optimizer.startsWith("DAdapt") && config.lr_scheduler !== "constant") warnings.push("DAdaptation 系列优化器建议将 lr_scheduler 设置为 constant")
  if (optimizer.toLowerCase().startsWith("prodigy") && (config.unet_lr !== 1 || config.text_encoder_lr !== 1)) warnings.push("Prodigy 建议将 unet_lr、text_encoder_lr 设置为 1")
  if (config.network_module === "networks.oft" && config.model_train_type !== "sdxl-lora") errors.push("OFT 当前仅对 SDXL 可用")
  for (const [left, right] of [["cache_text_encoder_outputs", "shuffle_caption"], ["noise_offset", "multires_noise_iterations"], ["cache_latents", "color_aug"], ["cache_latents", "random_crop"]]) {
    if (config[left] && config[right]) errors.push(`参数 ${left} 与 ${right} 冲突，请只启用其中一个`)
  }
  return { warnings, errors }
}
