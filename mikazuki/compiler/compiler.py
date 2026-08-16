import json
import secrets
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import toml

from mikazuki.catalog import get_catalog_service
from mikazuki.catalog.models import ParamDefinition, TrainerDefinition
from mikazuki.storage.paths import app_root

from .dataset import build_simple_dataset
from .models import CompileArtifacts, CompileResult, TrainDraft, ValidationMessage
from .sample_prompts import format_sample_prompts


MANAGED_PARAMS = {
    "config_file",
    "output_config",
    "dataset_config",
    "sample_prompts",
    "output_name",
    "train_data_dir",
    "reg_data_dir",
    "in_json",
    "resolution",
    "caption_extension",
    "caption_extention",
    "dataset_repeats",
    "enable_bucket",
    "min_bucket_reso",
    "max_bucket_reso",
    "bucket_reso_steps",
    "bucket_no_upscale",
    "keep_tokens",
    "train_batch_size",
    "shuffle_caption",
    "sample_every_n_epochs",
    "sample_every_n_steps",
    "sample_sampler",
}
MODEL_FILE_SUFFIXES = {".safetensors", ".ckpt", ".pt", ".pth", ".bin"}


def compile_draft(
    draft: TrainDraft,
    *,
    persist: bool = True,
    validate_paths: bool = True,
    base_dir: Optional[Path] = None,
) -> CompileResult:
    root = base_dir or app_root()
    catalog = get_catalog_service()
    trainer = catalog.get_trainer(draft.trainerId)
    if trainer is None:
        return CompileResult(
            trainerId=draft.trainerId,
            manifestHash=catalog.manifest_hash,
            errors=[
                ValidationMessage(
                    severity="error",
                    code="trainer.not_found",
                    field="trainerId",
                    message=f"未知训练器：{draft.trainerId}",
                )
            ],
        )

    warnings: List[ValidationMessage] = []
    errors: List[ValidationMessage] = []

    run_id = _new_run_id()
    run_dir = root / "config" / "runs" / run_id

    values = _build_param_values(trainer, draft, warnings, errors)
    _apply_derived_values(values, warnings)
    _normalize_path_values(trainer, values, root)
    logging_dir, log_prefix = _configure_run_logging(
        trainer,
        values,
        root=root,
        run_id=run_id,
        warnings=warnings,
    )
    errors.extend(_validate_output_name(draft.name))
    dataset_toml = None
    dataset_path = None
    if trainer.supportsDatasetConfig:
        dataset_config, dataset_errors = _build_dataset_config(
            trainer,
            draft,
            validate_paths=validate_paths,
            base_dir=root,
        )
        errors.extend(dataset_errors)
        if dataset_config is not None:
            dataset_toml = toml.dumps(dataset_config)
            dataset_path = run_dir / "dataset.toml"
            values["dataset_config"] = _display_path(dataset_path)

    sample_text = None
    sample_path = None
    if draft.sample.enabled:
        sample_text = format_sample_prompts(draft.sample)
        if sample_text:
            sample_path = run_dir / "sample_prompts.txt"
            values["sample_prompts"] = _display_path(sample_path)
            if draft.sample.everyNEpochs is not None:
                _set_structured_param(
                    trainer,
                    values,
                    "sample_every_n_epochs",
                    draft.sample.everyNEpochs,
                    "sample.everyNEpochs",
                    errors,
                )
            if draft.sample.everyNSteps is not None:
                _set_structured_param(
                    trainer,
                    values,
                    "sample_every_n_steps",
                    draft.sample.everyNSteps,
                    "sample.everyNSteps",
                    errors,
                )
            if draft.sample.sampler:
                _set_structured_param(
                    trainer,
                    values,
                    "sample_sampler",
                    draft.sample.sampler,
                    "sample.sampler",
                    errors,
                )
            if (
                draft.sample.everyNEpochs is not None
                and draft.sample.everyNSteps is not None
            ):
                errors.append(
                    ValidationMessage(
                        severity="error",
                        code="sample.schedule.conflict",
                        field="sample.everyNSteps",
                        message="Epoch 采样间隔会覆盖 Step 采样间隔；请只保留一种。",
                    )
                )
            elif (
                draft.sample.everyNEpochs is None
                and draft.sample.everyNSteps is None
                and not values.get("sample_at_first")
            ):
                errors.append(
                    ValidationMessage(
                        severity="error",
                        code="sample.schedule.required",
                        field="sample.everyNEpochs",
                        message="已启用训练中采样，请设置 Epoch 或 Step 采样间隔。",
                    )
                )
        else:
            errors.append(
                ValidationMessage(
                    severity="error",
                    code="sample.prompts.required",
                    field="sample.prompts",
                    message="已启用训练中采样，请至少填写一条 Prompt。",
                )
            )

    errors.extend(_validate_required_params(trainer, values))
    path_errors, path_warnings = _validate_path_params(
        trainer,
        values,
        validate_paths=validate_paths,
        base_dir=root,
    )
    errors.extend(path_errors)
    warnings.extend(path_warnings)
    errors.extend(_validate_conflicts(trainer, draft, values))

    train_config = _build_train_config(trainer, values)
    train_toml = toml.dumps(train_config)
    train_path = run_dir / "train.toml"
    command_path = run_dir / "command.json"
    draft_path = run_dir / "draft.json"
    command = _build_command(trainer, train_path, draft)

    artifacts = CompileArtifacts()
    if not errors and persist:
        run_dir.mkdir(parents=True, exist_ok=True)
        _write_text(train_path, train_toml)
        if dataset_toml and dataset_path:
            _write_text(dataset_path, dataset_toml)
        if sample_text and sample_path:
            _write_text(sample_path, sample_text)
        _write_text(draft_path, draft.json(ensure_ascii=False, indent=2))
        _write_text(
            command_path,
            json.dumps({"command": command, "cwd": _display_path(root)}, ensure_ascii=False, indent=2),
        )

        artifacts = CompileArtifacts(
            draft=_display_path(draft_path),
            trainConfig=_display_path(train_path),
            datasetConfig=_display_path(dataset_path) if dataset_path else None,
            samplePrompts=_display_path(sample_path) if sample_path else None,
            command=_display_path(command_path),
            loggingDir=logging_dir,
            logPrefix=log_prefix,
        )

    return CompileResult(
        runId=run_id if not errors else None,
        trainerId=draft.trainerId,
        manifestHash=catalog.manifest_hash,
        artifacts=artifacts,
        command=command,
        trainConfig=train_toml,
        datasetConfig=dataset_toml,
        samplePrompts=sample_text,
        warnings=warnings,
        errors=errors,
    )


def _new_run_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"


def _build_param_values(
    trainer: TrainerDefinition,
    draft: TrainDraft,
    warnings: List[ValidationMessage],
    errors: Optional[List[ValidationMessage]] = None,
) -> Dict[str, Any]:
    errors = errors if errors is not None else []
    values: Dict[str, Any] = {}
    for name, param in trainer.params.items():
        default = param.effectiveDefault if param.effectiveDefault is not None else None
        if default is not None:
            normalized, issue = _normalize_param_value(param, default, f"defaults.{name}")
            if issue is not None:
                errors.append(issue)
            elif not _should_omit_value(param, normalized):
                values[name] = normalized

    if trainer.defaultNetworkModule and not values.get("network_module"):
        values["network_module"] = trainer.defaultNetworkModule

    for source_name, raw_values in (("modelAssets", draft.modelAssets), ("params", draft.params)):
        for name, value in raw_values.items():
            if name in MANAGED_PARAMS:
                if value is not None and value != "" and value is not False:
                    warnings.append(
                        ValidationMessage(
                            severity="warning",
                            code="param.managed",
                            field=f"{source_name}.{name}",
                            message=f"参数由编译器管理，已忽略草稿中的值：{name}",
                        )
                    )
                continue

            param = trainer.params.get(name)
            if param is None:
                errors.append(
                    ValidationMessage(
                        severity="error",
                        code="param.unknown",
                        field=f"{source_name}.{name}",
                        message=f"参数不在当前训练器的 argparse 定义中：{name}",
                    )
                )
                continue

            normalized, issue = _normalize_param_value(param, value, f"{source_name}.{name}")
            if issue is not None:
                errors.append(issue)
                values.pop(name, None)
                continue
            if _should_omit_value(param, normalized):
                # An explicit empty/false value must be able to disable an
                # overlay effectiveDefault that was inserted above.
                values.pop(name, None)
            else:
                values[name] = normalized

    # The product default is epoch-based, while sd-scripts also accepts an
    # explicit step limit. Once a caller removes the epoch field and sets
    # max_train_steps, do not silently put the overlay epoch default back.
    if (
        values.get("max_train_steps") is not None
        and "max_train_epochs" not in draft.params
        and "max_train_epochs" not in draft.modelAssets
    ):
        values.pop("max_train_epochs", None)

    if draft.name and draft.name.strip():
        values["output_name"] = draft.name.strip()
    return {name: value for name, value in values.items() if not _should_omit_value(trainer.params.get(name), value)}


def _set_structured_param(
    trainer: TrainerDefinition,
    values: Dict[str, Any],
    name: str,
    value: Any,
    field: str,
    errors: List[ValidationMessage],
) -> None:
    param = trainer.params.get(name)
    if param is None:
        errors.append(
            ValidationMessage(
                severity="error",
                code="param.unsupported",
                field=field,
                message=f"当前训练器不支持参数：{name}",
            )
        )
        return
    normalized, issue = _normalize_param_value(param, value, field)
    if issue is not None:
        errors.append(issue)
        return
    if _should_omit_value(param, normalized):
        values.pop(name, None)
    else:
        values[name] = normalized


def _normalize_path_values(trainer: TrainerDefinition, values: Dict[str, Any], root: Path) -> None:
    for name, value in list(values.items()):
        param = trainer.params.get(name)
        if param is not None and param.control == "modelSource" and isinstance(value, str):
            if _looks_like_local_model_reference(value, root):
                values[name] = _normalize_path(value, root)
            continue
        if param is None or not _is_path_param(param):
            continue
        if isinstance(value, str):
            values[name] = _normalize_path(value, root)
        elif isinstance(value, list):
            values[name] = [
                _normalize_path(item, root) if isinstance(item, str) else item
                for item in value
            ]


def _configure_run_logging(
    trainer: TrainerDefinition,
    values: Dict[str, Any],
    *,
    root: Path,
    run_id: str,
    warnings: List[ValidationMessage],
) -> Tuple[Optional[str], Optional[str]]:
    """Give every compiled run an isolated local event directory.

    sd-scripts creates a timestamped child below ``logging_dir`` and prefixes
    that child with ``log_prefix``. Keeping both values deterministic here lets
    the jobs API discover only the event files owned by this run without
    depending on the timestamp chosen inside the upstream process.
    """
    if "logging_dir" not in trainer.params:
        return None, None

    configured_root = values.get("logging_dir")
    logging_root = Path(str(configured_root)) if configured_root else root / "logs"
    if not logging_root.is_absolute():
        logging_root = root / logging_root

    logging_dir = logging_root / "jobs" / f"job_{run_id}" / "events"
    values["logging_dir"] = _display_path(logging_dir)

    log_prefix: Optional[str] = None
    if "log_prefix" in trainer.params:
        if values.get("log_prefix"):
            warnings.append(
                ValidationMessage(
                    severity="warning",
                    code="logging.log_prefix.managed",
                    field="params.log_prefix",
                    message="日志目录前缀由任务中心管理，已替换为本次任务的唯一前缀。",
                )
            )
        log_prefix = f"{run_id}-"
        values["log_prefix"] = log_prefix

    # sd-scripts only accepts one of tensorboard/wandb/all. Selecting `all`
    # is therefore the supported way to keep a local TensorBoard-compatible
    # event writer alongside an explicitly requested W&B run.
    if values.get("log_with") == "wandb":
        values["log_with"] = "all"
        warnings.append(
            ValidationMessage(
                severity="warning",
                code="logging.local_events.enabled",
                field="params.log_with",
                message="已在 W&B 之外同时启用本地事件日志，供任务中心展示训练曲线。",
            )
        )

    return values["logging_dir"], log_prefix


def _build_dataset_config(
    trainer: TrainerDefinition,
    draft: TrainDraft,
    *,
    validate_paths: bool,
    base_dir: Optional[Path] = None,
) -> Tuple[Optional[Dict[str, Any]], List[ValidationMessage]]:
    if not draft.dataset:
        return None, [
            ValidationMessage(
                severity="error",
                code="dataset.required",
                field="dataset",
                message="训练草稿缺少数据集配置。",
            )
        ]

    dataset_values = _dataset_values(trainer, draft)
    mode = dataset_values.get("mode", "simple")
    if mode != "simple":
        return None, [
            ValidationMessage(
                severity="error",
                code="dataset.mode.unsupported",
                field="dataset.mode",
                message="当前阶段只支持 simple 数据集模式。",
            )
        ]
    return build_simple_dataset(dataset_values, validate_paths=validate_paths, base_dir=base_dir)


def _dataset_values(trainer: TrainerDefinition, draft: TrainDraft) -> Dict[str, Any]:
    values = dict(trainer.datasetDefaults)
    values.update(draft.dataset or {})
    return values


def _normalize_param_value(
    param: ParamDefinition,
    value: Any,
    field: str,
) -> Tuple[Any, Optional[ValidationMessage]]:
    if value is None:
        return None, None

    try:
        if param.type == "array":
            if isinstance(value, str):
                raw_items = [item.strip() for item in value.splitlines() if item.strip()]
            elif isinstance(value, (list, tuple)):
                raw_items = list(value)
            else:
                raise ValueError("expected an array")

            item_type = param.itemType or "string"
            normalized = [_cast_scalar(item_type, item) for item in raw_items]
            if param.choices is not None and not param.extra.get("allowCustomChoice"):
                normalized = [_match_choice(item, param.choices) for item in normalized]
            return normalized, _validate_numeric_bounds(param, normalized, field)

        normalized = _cast_scalar(param.type, value)
        if param.choices is not None and normalized != "" and not param.extra.get("allowCustomChoice"):
            normalized = _match_choice(normalized, param.choices)
        return normalized, _validate_numeric_bounds(param, normalized, field)
    except (TypeError, ValueError) as exc:
        return value, ValidationMessage(
            severity="error",
            code="param.invalid",
            field=field,
            message=f"参数值无效：{param.label or param.name}（{exc}）",
        )


def _cast_scalar(param_type: str, value: Any) -> Any:
    if value == "":
        return ""
    if param_type == "integer":
        if isinstance(value, bool):
            raise ValueError("需要整数")
        number = float(value)
        if not number.is_integer():
            raise ValueError("需要整数")
        return int(number)
    if param_type == "number":
        if isinstance(value, bool):
            raise ValueError("需要数字")
        return float(value)
    if param_type == "integer_or_number":
        if isinstance(value, bool):
            raise ValueError("需要整数步数、0–1 比例或百分比")
        if isinstance(value, str) and value.strip().endswith("%"):
            percentage = float(value.strip()[:-1])
            return percentage / 100.0
        number = float(value)
        if number >= 1:
            if not number.is_integer():
                raise ValueError("大于等于 1 时需要整数步数")
            return int(number)
        return number
    if param_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in {0, 1}:
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        raise ValueError("需要布尔值")
    if param_type in {"string", "path", "enum"}:
        if isinstance(value, (dict, list, tuple, set)):
            raise ValueError("需要单个值")
        return str(value)
    return value


def _match_choice(value: Any, choices: List[Any]) -> Any:
    for choice in choices:
        if value == choice or str(value) == str(choice):
            return choice
    available = "、".join(str(choice) for choice in choices if choice is not None)
    raise ValueError(f"可选值为：{available}")


def _validate_numeric_bounds(
    param: ParamDefinition,
    value: Any,
    field: str,
) -> Optional[ValidationMessage]:
    values = value if isinstance(value, list) else [value]
    numeric_values = [item for item in values if isinstance(item, (int, float)) and not isinstance(item, bool)]
    if param.min is not None and any(item < param.min for item in numeric_values):
        return ValidationMessage(
            severity="error",
            code="param.min",
            field=field,
            message=f"{param.label or param.name} 不能小于 {param.min:g}。",
        )
    if param.max is not None and any(item > param.max for item in numeric_values):
        return ValidationMessage(
            severity="error",
            code="param.max",
            field=field,
            message=f"{param.label or param.name} 不能大于 {param.max:g}。",
        )
    return None


def _should_omit_value(param: Optional[ParamDefinition], value: Any) -> bool:
    if value is None or value == "" or value == [] or value == {}:
        return True
    if param is not None and param.omitIfZero and value == 0:
        return True
    if (
        isinstance(value, bool)
        and value is False
        and param is not None
        and param.action in {"store_true", "_StoreTrueAction"}
    ):
        return True
    return False


def _validate_required_params(trainer: TrainerDefinition, values: Dict[str, Any]) -> List[ValidationMessage]:
    errors: List[ValidationMessage] = []
    for name, param in trainer.params.items():
        if param.hidden:
            continue
        if not param.required and param.priority != "required":
            continue
        if _should_omit_value(param, values.get(name)):
            errors.append(
                ValidationMessage(
                    severity="error",
                    code="param.required",
                    field=f"params.{name}",
                    message=f"缺少必填参数：{param.label or name}",
                )
            )
    return errors


def _validate_output_name(name: Optional[str]) -> List[ValidationMessage]:
    value = (name or "").strip()
    if not value:
        return [
            ValidationMessage(
                severity="error",
                code="output.name.required",
                field="name",
                message="输出名称不能为空。",
            )
        ]

    invalid_chars = '<>:"/\\|?*'
    windows_reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
    stem = value.split(".", 1)[0].upper()
    if (
        len(value) > 128
        or value.endswith((".", " "))
        or stem in windows_reserved
        or any(ord(char) < 32 or char in invalid_chars for char in value)
    ):
        return [
            ValidationMessage(
                severity="error",
                code="output.name.invalid",
                field="name",
                message="输出名称必须是 1–128 个字符的安全文件名，不能包含路径或系统保留字符。",
            )
        ]
    return []


def _validate_path_params(
    trainer: TrainerDefinition,
    values: Dict[str, Any],
    *,
    validate_paths: bool,
    base_dir: Path,
) -> Tuple[List[ValidationMessage], List[ValidationMessage]]:
    if not validate_paths:
        return [], []

    errors: List[ValidationMessage] = []
    warnings: List[ValidationMessage] = []
    generated_paths = {"dataset_config", "sample_prompts"}

    for name, value in values.items():
        param = trainer.params.get(name)
        if param is None or name in generated_paths:
            continue
        if param.control == "modelSource":
            if isinstance(value, str) and _looks_like_local_model_reference(value, base_dir):
                path = Path(value)
                if not path.exists():
                    errors.append(
                        ValidationMessage(
                            severity="error",
                            code="path.missing",
                            field=f"params.{name}",
                            message=f"本地模型路径不存在：{value}",
                        )
                    )
            continue
        if not _is_path_param(param):
            continue

        raw_paths = value if isinstance(value, list) else [value]
        for raw_path in raw_paths:
            if not isinstance(raw_path, str):
                continue
            _validate_single_path(param, name, raw_path, errors, warnings)

    return errors, warnings


def _validate_single_path(
    param: ParamDefinition,
    name: str,
    value: str,
    errors: List[ValidationMessage],
    warnings: List[ValidationMessage],
) -> None:
    path = Path(value)
    is_folder = param.control == "folder" or param.fileKind == "folder" or name in {"output_dir", "logging_dir"}
    allows_file_or_folder = param.control == "fileOrFolder"
    is_required = param.required or param.priority == "required"
    can_create_folder = name in {"output_dir", "logging_dir"}

    if not path.exists():
        # The managed per-job event directory is intentionally created by the
        # tracker when training starts. Reporting it on every compile would
        # turn the expected pre-run state into a permanent warning.
        if name == "logging_dir":
            return
        message = f"路径不存在：{param.label or name} -> {value}"
        target = warnings if can_create_folder or (is_folder and not is_required) else errors
        target.append(
            ValidationMessage(
                severity="warning" if target is warnings else "error",
                code="path.missing",
                field=f"params.{name}",
                message=message,
            )
        )
        return

    if is_folder and not path.is_dir():
        errors.append(
            ValidationMessage(
                severity="error",
                code="path.not_folder",
                field=f"params.{name}",
                message=f"需要目录路径：{param.label or name} -> {value}",
            )
        )
    elif not is_folder and not allows_file_or_folder and path.is_dir():
        errors.append(
            ValidationMessage(
                severity="error",
                code="path.not_file",
                field=f"params.{name}",
                message=f"需要文件路径：{param.label or name} -> {value}",
            )
        )



def _apply_derived_values(values: Dict[str, Any], warnings: List[ValidationMessage]) -> None:
    derived_pairs = (
        ("cache_latents_to_disk", "cache_latents"),
        ("cache_text_encoder_outputs_to_disk", "cache_text_encoder_outputs"),
        ("fp8_base_unet", "fp8_base"),
        ("unsloth_offload_checkpointing", "gradient_checkpointing"),
    )
    for trigger, target in derived_pairs:
        if values.get(trigger) and not values.get(target):
            values[target] = True
            warnings.append(
                ValidationMessage(
                    severity="warning",
                    code=f"param.derived.{target}",
                    field=f"params.{trigger}",
                    message=f"已根据 {trigger} 自动启用 {target}。",
                )
            )


def _validate_conflicts(
    trainer: TrainerDefinition,
    draft: TrainDraft,
    values: Dict[str, Any],
) -> List[ValidationMessage]:
    errors: List[ValidationMessage] = []
    dataset_values = _dataset_values(trainer, draft)

    def add(code: str, field: str, message: str) -> None:
        errors.append(
            ValidationMessage(
                severity="error",
                code=code,
                field=field,
                message=message,
            )
        )

    if values.get("network_train_unet_only") and values.get("network_train_text_encoder_only"):
        add(
            "param.conflict.network_target",
            "params.network_train_unet_only",
            "不能同时选择“仅训练 U-Net / DiT”和“仅训练文本编码器”。",
        )

    if values.get("max_train_epochs") is not None and values.get("max_train_steps") is not None:
        add(
            "param.conflict.training_duration",
            "params.max_train_steps",
            "max_train_epochs 会覆盖 max_train_steps；请只保留一种训练时长。",
        )

    if values.get("train_inpainting") and values.get("cache_latents"):
        add(
            "param.conflict.train_inpainting_cache",
            "params.train_inpainting",
            "train_inpainting 需要逐步读取原图，不能与 cache_latents 同时启用。",
        )

    if values.get("cache_latents"):
        for name in ("color_aug", "random_crop"):
            if values.get(name):
                add(
                    "param.conflict.cache_latents",
                    f"params.{name}",
                    f"cache_latents 不能与 {name} 同时启用。",
                )

    if values.get("cache_text_encoder_outputs"):
        caption_values = {
            "shuffle_caption": bool(values.get("shuffle_caption"))
            or bool(dataset_values.get("shuffleCaption")),
            "caption_dropout_rate": values.get("caption_dropout_rate"),
            "caption_tag_dropout_rate": values.get("caption_tag_dropout_rate"),
            "token_warmup_step": values.get("token_warmup_step"),
        }
        if trainer.id == "anima.lora":
            caption_values.pop("caption_dropout_rate")
        for name, value in caption_values.items():
            if value:
                field = "dataset.shuffleCaption" if name == "shuffle_caption" and dataset_values.get("shuffleCaption") else f"params.{name}"
                add(
                    "param.conflict.cache_text_encoder_outputs",
                    field,
                    f"cache_text_encoder_outputs 不能与 {name} 同时启用。",
                )

    if values.get("adaptive_noise_scale") is not None and values.get("noise_offset") is None:
        add(
            "param.requires.noise_offset",
            "params.adaptive_noise_scale",
            "adaptive_noise_scale 需要同时设置 noise_offset。",
        )

    if values.get("scale_v_pred_loss_like_noise_pred") and not values.get("v_parameterization"):
        add(
            "param.requires.v_parameterization",
            "params.scale_v_pred_loss_like_noise_pred",
            "scale_v_pred_loss_like_noise_pred 仅可在 v_parameterization 开启时使用。",
        )

    if values.get("v_pred_like_loss") and values.get("v_parameterization"):
        add(
            "param.conflict.v_pred_like_loss",
            "params.v_pred_like_loss",
            "v_pred_like_loss 不能与 v_parameterization 同时启用。",
        )

    if values.get("full_fp16") and values.get("mixed_precision") != "fp16":
        add(
            "param.requires.full_fp16",
            "params.full_fp16",
            "full_fp16 要求 mixed_precision 为 fp16。",
        )
    if values.get("full_bf16") and values.get("mixed_precision") != "bf16":
        add(
            "param.requires.full_bf16",
            "params.full_bf16",
            "full_bf16 要求 mixed_precision 为 bf16。",
        )
    if (values.get("fp8_base") or values.get("fp8_base_unet")) and values.get("mixed_precision") == "no":
        add(
            "param.requires.fp8_precision",
            "params.fp8_base",
            "FP8 训练要求 mixed_precision 使用 fp16 或 bf16。",
        )

    if values.get("log_with") in {"tensorboard", "all"} and not values.get("logging_dir"):
        add(
            "param.requires.logging_dir",
            "params.logging_dir",
            "使用 TensorBoard 日志时必须设置 logging_dir。",
        )

    if values.get("fused_backward_pass"):
        if str(values.get("optimizer_type", "")).lower() != "adafactor":
            add(
                "param.requires.fused_backward_optimizer",
                "params.optimizer_type",
                "fused_backward_pass 仅支持 Adafactor 优化器。",
            )
        if values.get("gradient_accumulation_steps", 1) != 1:
            add(
                "param.requires.fused_backward_accumulation",
                "params.gradient_accumulation_steps",
                "fused_backward_pass 要求 gradient_accumulation_steps 为 1。",
            )

    if values.get("dim_from_weights") and not values.get("network_weights"):
        add(
            "param.requires.network_weights",
            "params.dim_from_weights",
            "dim_from_weights 需要先设置 network_weights。",
        )

    if values.get("blocks_to_swap", 0) and values.get("cpu_offload_checkpointing"):
        add(
            "param.conflict.block_swap_cpu_offload",
            "params.blocks_to_swap",
            "blocks_to_swap 不能与 cpu_offload_checkpointing 同时启用。",
        )

    if values.get("unsloth_offload_checkpointing") and (
        values.get("cpu_offload_checkpointing") or values.get("blocks_to_swap", 0)
    ):
        add(
            "param.conflict.unsloth_offload",
            "params.unsloth_offload_checkpointing",
            "Unsloth offload checkpointing 不能与 CPU offload 或 block swap 同时启用。",
        )

    if trainer.id == "sdxl.lora" and values.get("v2"):
        add("param.unsupported.sdxl_v2", "params.v2", "SDXL 训练不支持 v2 参数。")

    if trainer.id == "sdxl.lora" and values.get("cache_text_encoder_outputs") and not values.get("network_train_unet_only"):
        add(
            "param.requires.sdxl_unet_only",
            "params.cache_text_encoder_outputs",
            "SDXL 缓存文本编码器输出时必须仅训练 U-Net。",
        )

    if trainer.id == "anima.lora" and values.get("cache_text_encoder_outputs") and not values.get("network_train_unet_only"):
        add(
            "param.requires.anima_unet_only",
            "params.cache_text_encoder_outputs",
            "Anima 缓存文本编码器输出时必须仅训练 DiT。",
        )

    if trainer.id == "chroma.lora" and not values.get("apply_t5_attn_mask"):
        add(
            "param.requires.chroma_t5_mask",
            "params.apply_t5_attn_mask",
            "Chroma 训练必须启用 T5 注意力掩码。",
        )

    network_args = [str(item).lower() for item in values.get("network_args", [])]
    trains_t5 = any(item.split("=", 1)[0] == "train_t5xxl" and item.endswith("=true") for item in network_args)
    if trainer.family in {"flux", "sd3"} and trains_t5 and values.get("cache_text_encoder_outputs"):
        add(
            "param.conflict.train_t5_cache",
            "params.network_args",
            "训练 T5-XXL 时不能缓存文本编码器输出。",
        )

    bucket_alignment = {
        "sd": 64,
        "sdxl": 32,
        "sd3": 32,
        "flux": 32,
        "hunyuan_image": 32,
        "lumina": 16,
        "anima": 16,
    }.get(trainer.family)
    if bucket_alignment and dataset_values.get("enableBucket", True):
        bucket_step = dataset_values.get("bucketResoSteps", 64)
        try:
            if int(bucket_step) % bucket_alignment != 0:
                add(
                    "dataset.bucket_step.model_alignment",
                    "dataset.bucketResoSteps",
                    f"{trainer.family.upper()} 的 bucket 步长必须能被 {bucket_alignment} 整除。",
                )
        except (TypeError, ValueError):
            pass

    return errors


def _is_path_param(param: ParamDefinition) -> bool:
    return (
        param.type == "path"
        or param.control in {"path", "file", "folder", "fileOrFolder"}
        or param.fileKind is not None
    )


def _looks_like_local_model_reference(value: str, root: Path) -> bool:
    raw = value.strip()
    if not raw:
        return False
    path = Path(raw).expanduser()
    return (
        path.is_absolute()
        or raw.startswith(("./", ".\\", "../", "..\\", "~"))
        or "\\" in raw
        or ("/" not in raw and path.suffix.lower() in MODEL_FILE_SUFFIXES)
        or (root / path).exists()
    )


def _normalize_path(value: str, root: Path) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return _display_path(path)


def _build_train_config(trainer: TrainerDefinition, values: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for name, value in values.items():
        param = trainer.params.get(name)
        group = param.group if param is not None else "raw"
        if group == "raw":
            group = "advanced"
        groups.setdefault(group, {})[name] = value
    return groups


def _build_command(trainer: TrainerDefinition, train_path: Path, draft: TrainDraft) -> List[str]:
    command = [
        sys.executable,
        "-m",
        "accelerate.commands.launch",
        "--num_cpu_threads_per_process",
        str(draft.runtime.numCpuThreadsPerProcess),
        "--quiet",
    ]
    if len(draft.runtime.gpuIds) == 1:
        command.extend(["--num_processes", "1"])
    elif len(draft.runtime.gpuIds) > 1:
        if sys.platform == "win32":
            command.extend(["--rdzv_backend", "c10d"])
        command.extend(["--multi_gpu", "--num_processes", str(len(draft.runtime.gpuIds))])
    command.extend([trainer.script, "--config_file", _display_path(train_path)])
    return command


def _display_path(path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    return str(path.resolve()).replace("\\", "/")


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
