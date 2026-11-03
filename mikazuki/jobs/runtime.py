"""Cheap launch-time checks, kept separate from portable configuration export."""

from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from typing import List, Optional

import toml
from packaging.version import InvalidVersion, Version

from mikazuki.compiler.models import ValidationMessage


def validate_training_runtime(trainer_id: str, train_config: Optional[str]) -> List[ValidationMessage]:
    if trainer_id != "moss_image.lora":
        return []

    errors = []
    # These are the standard dependencies, including the Qwen3.5 text model used by
    # the lazy upstream loader. Do not import torch or allocate GPU memory in
    # the web server merely to inspect dependency versions.
    for package, minimum in (("torch", "2.6.0"), ("transformers", "5.17.0")):
        try:
            installed = version(package)
            ready = Version(installed) >= Version(minimum)
        except PackageNotFoundError:
            installed, ready = "未安装", False
        except InvalidVersion:
            ready = False
        if not ready:
            errors.append(ValidationMessage(
                severity="error",
                code="runtime.moss_dependency",
                field="trainerId",
                message=(
                    f"MOSS-Image 需要 {package}>={minimum}，当前为 {installed}。"
                    "请按 docs/human/moss-image.md 更新 requirements.txt 中的依赖后重启 GUI。"
                ),
            ))

    values = {}
    for section in toml.loads(train_config or "").values():
        if isinstance(section, dict):
            values.update(section)
    if values.get("convrot_int8_bwd") == "int8" and find_spec("triton") is None:
        errors.append(ValidationMessage(
            severity="error",
            code="runtime.moss_triton",
            field="params.convrot_int8_bwd",
            message=(
                "ConvRot INT8 反向计算需要 Triton（Windows 使用 triton-windows）和 CUDA。"
                "请安装与 PyTorch 匹配的版本，或使用 bf16 反向计算。"
            ),
        ))
    return errors
