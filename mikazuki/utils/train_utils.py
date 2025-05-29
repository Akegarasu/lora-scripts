from enum import Enum
import glob
import os
import re
import shutil
import sys
import json
from typing import Dict

from mikazuki.log import log

python_bin = sys.executable


class ModelType(Enum):
    UNKNOWN = -1
    SD15 = 1
    SD2 = 2
    SDXL = 3
    SD3 = 4
    FLUX = 5
    LUMINA = 6
    LoRA = 10


MODEL_SIGNATURE = [
    {
        "type": ModelType.LUMINA,
        "signature": [
            "cap_embedder.0.weight",
            "context_refiner.0.attention.k_norm.weight",
        ]
    },
    {
        "type": ModelType.FLUX,
        "signature": [
            "double_blocks.0.img_mlp.0.weight",
            "guidance_in.in_layer.weight"
            "model.diffusion_model.double_blocks",
            "double_blocks.0.img_attn.norm.query_norm.scale",
        ]
    },
    {
        "type": ModelType.SD3,
        "signature": [
            "model.diffusion_model.x_embedder.proj.weight",
            "model.diffusion_model.joint_blocks.0.context_block.attn.proj.weight"
        ]
    },
    {
        "type": ModelType.SDXL,
        "signature": [
            "conditioner.embedders.1.model.transformer.resblocks",
        ]
    },
    {
        "type": ModelType.SD15,
        "signature": [
            "model.diffusion_model",
            "cond_stage_model.transformer.text_model",
        ]
    },
    {
        "type": ModelType.LoRA,
        "signature": [
            "lora_te_text_model_encoder",
            "lora_unet_up_blocks"
            "lora_unet_input_blocks_4_1_transformer_blocks_0_attn1_to_k.alpha",
            "lora_unet_input_blocks_4_1_transformer_blocks_0_attn1_to_k.lora_up.weight",

            # more common signature
            "lora_unet",
            "lora_te",
            "lora_A.weight",
        ]
    }
]


def is_promopt_like(s):
    for p in ["--n", "--s", "--l", "--d"]:
        if p in s:
            return True
    return False


def match_model_type_legacy(sig_content: bytes):
    if b"model.diffusion_model.double_blocks" in sig_content or b"double_blocks.0.img_attn.norm.query_norm.scale" in sig_content:
        return ModelType.FLUX

    if b"model.diffusion_model.x_embedder.proj.weight" in sig_content:
        return ModelType.SD3

    if b"conditioner.embedders.1.model.transformer.resblocks" in sig_content:
        return ModelType.SDXL

    if b"model.diffusion_model" in sig_content or b"cond_stage_model.transformer.text_model" in sig_content:
        return ModelType.SD15

    if b"lora_unet" in sig_content or b"lora_te" in sig_content:
        return ModelType.LoRA

    return ModelType.UNKNOWN


def read_safetensors_metadata(path) -> Dict:
    if not os.path.exists(path):
        log.error(f"Can't find safetensors metadata file {path}")
        return None

    with open(path, "rb") as f:
        meta_length = int.from_bytes(f.read(8), "little")
        meta = f.read(meta_length)
        return json.loads(meta)


def guess_model_type(path):
    if path.endswith("safetensors"):
        metadata = read_safetensors_metadata(path)
        model_keys = "\n".join(metadata.keys())
        for m in MODEL_SIGNATURE:
            if any([k in model_keys for k in m["signature"]]):
                return m["type"]

        return ModelType.UNKNOWN

    if path.endswith("pt") or path.endswith("ckpt"):
        with open(path, "rb") as f:
            content = f.read(1024 * 1000)
            return match_model_type_legacy(content)


def validate_model(model_name: str, training_type: str = "sd-lora"):
    if os.path.exists(model_name):
        if os.path.isdir(model_name):
            files = os.listdir(model_name)
            if "model_index.json" in files or "unet" in model_name:
                return True, "ok"
            else:
                log.warning("Can't find model, is this a huggingface model folder?")
                return True, "ok"

        model_type = ModelType.UNKNOWN

        try:
            model_type = guess_model_type(model_name)
        except Exception as e:
            log.warning(f"model file {model_name} can't open: {e}")
            return True, ""

        if model_type == ModelType.UNKNOWN:
            log.error(f"Can't match model type from {model_name}")

        if model_type not in [ModelType.SD15, ModelType.SD2, ModelType.SD3, ModelType.SDXL, ModelType.FLUX, ModelType.LUMINA]:
            return False, "Pretrained model is not a Stable Diffusion, Flux or Lumina checkpoint / 校验失败：底模不是 Stable Diffusion, Flux 或 Lumina 模型"

        if model_type == ModelType.SDXL and training_type == "sd-lora":
            return False, "Pretrained model is SDXL, but you are training with SD1.5 LoRA / 校验失败：你选择的是 SD1.5 LoRA 训练，但预训练模型是 SDXL。请前往专家模式选择正确的模型种类。"

        return True, "ok"

    # huggingface model repo
    if model_name.count("/") == 1 \
            and not model_name[0] in [".", "/"] \
            and not model_name.split(".")[-1] in ["pt", "pth", "ckpt", "safetensors"]:
        return True, "ok"

    return False, "model not found"


def validate_data_dir(path):
    if not os.path.exists(path):
        log.error(f"Data dir {path} not exists, check your params")
        return False

    dir_content = os.listdir(path)

    if len(dir_content) == 0:
        log.error(f"Data dir {path} is empty, check your params")

    subdirs = [f for f in dir_content if os.path.isdir(os.path.join(path, f))]

    if len(subdirs) == 0:
        log.warning(f"No subdir found in data dir")

    ok_dir = [d for d in subdirs if re.findall(r"^\d+_.+", d)]

    if len(ok_dir) > 0:
        log.info(f"Found {len(ok_dir)} legal dataset")
        return True

    if len(ok_dir) == 0:
        log.warning(f"No leagal dataset found. Try find avaliable images")
        imgs = get_total_images(path, False)
        captions = glob.glob(path + '/*.txt')
        log.info(f"{len(imgs)} images found, {len(captions)} captions found")
        if len(imgs) > 0:
            num_repeat = suggest_num_repeat(len(imgs))
            dataset_path = os.path.join(path, f"{num_repeat}_zkz")
            os.makedirs(dataset_path)
            for i in imgs:
                shutil.move(i, dataset_path)
            if len(captions) > 0:
                for c in captions:
                    shutil.move(c, dataset_path)
            log.info(f"Auto dataset created {dataset_path}")
        else:
            log.error("No image found in data dir")
            return False

    return True


def suggest_num_repeat(img_count):
    if img_count <= 10:
        return 7
    elif 10 < img_count <= 50:
        return 5
    elif 50 < img_count <= 100:
        return 3

    return 1


def check_training_params(data):
    potential_path = [
        "train_data_dir", "reg_data_dir", "output_dir"
    ]
    file_paths = [
        "sample_prompts"
    ]
    for p in potential_path:
        if p in data and not os.path.exists(data[p]):
            return False

    for f in file_paths:
        if f in data and not os.path.exists(data[f]):
            return False
    return True


def get_total_images(path, recursive=True):
    if recursive:
        image_files = glob.glob(path + '/**/*.jpg', recursive=True)
        image_files += glob.glob(path + '/**/*.jpeg', recursive=True)
        image_files += glob.glob(path + '/**/*.png', recursive=True)
    else:
        image_files = glob.glob(path + '/*.jpg')
        image_files += glob.glob(path + '/*.jpeg')
        image_files += glob.glob(path + '/*.png')
    return image_files


def fix_config_types(config: dict):
    keep_float_params = ["guidance_scale", "sigmoid_scale", "discrete_flow_shift"]
    for k in keep_float_params:
        if k in config:
            config[k] = float(config[k])
