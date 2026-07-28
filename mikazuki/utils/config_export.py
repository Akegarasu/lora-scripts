"""GUI export normalization: clean network_args via adapter, keep importable GUI fields."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from mikazuki.anima_backend.adapter import adapt_anima_config
from mikazuki.utils.config_args import normalize_custom_args
from mikazuki.utils.config_import import (
    _hydrate_lycoris_ui_fields_from_network_args,
    _looks_like_sd_scripts_toml,
    validate_config_import,
)
from mikazuki.utils.train_utils import ensure_enable_preview_flag, fix_config_types

ANIMA_EXPORT_TRAIN_TYPES = frozenset({"anima-lora", "sd3-lora"})
ANIMA_FINETUNE_TRAIN_TYPES = frozenset({"anima-finetune"})
_ADAPTER_UNKNOWN_FIELD_WARNING = "Unknown field passed through to sd-scripts: "

_GUI_STRIP_KEYS = frozenset({
    "gpu_ids",
    "network_args_custom",
    "optimizer_args_custom",
    "_training_warnings",
})


def _is_invalid_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "undefined", "null", "nan"}:
        return True
    return False


def _sanitize_generic_export(config: dict) -> None:
    keys_to_remove = [k for k, v in config.items() if _is_invalid_value(v)]
    for key in keys_to_remove:
        config.pop(key, None)
    for key in ("network_args", "optimizer_args"):
        if isinstance(config.get(key), list):
            from mikazuki.utils.config_args import normalize_kv_arg_list

            config[key] = normalize_kv_arg_list(config[key])


def _ensure_gui_identity_fields(config: dict, *, page_train_type: str) -> None:
    model_train_type = str(
        config.get("model_train_type") or page_train_type or ""
    ).strip()
    if model_train_type:
        config["model_train_type"] = model_train_type

    if config.get("lora_type"):
        return

    lycoris_algo = config.get("lycoris_algo")
    if isinstance(lycoris_algo, str) and lycoris_algo.strip():
        config["lora_type"] = lycoris_algo.strip().lower()
        return

    network_args = config.get("network_args")
    if isinstance(network_args, list):
        for item in network_args:
            if isinstance(item, str) and item.strip().lower().startswith("algo="):
                config["lora_type"] = item.split("=", 1)[1].strip().lower()
                return


def _export_warnings(warnings: list[str]) -> list[str]:
    # GUI exports intentionally retain fields that are not direct sd-scripts args.
    return [
        warning
        for warning in warnings
        if not warning.startswith(_ADAPTER_UNKNOWN_FIELD_WARNING)
    ]


def normalize_config_for_export(
    config: dict,
    *,
    page_train_type: str,
) -> tuple[dict[str, Any], list[str]]:
    """
    Build a GUI-importable config for download TOML.

    Uses adapt_anima_config only to normalize network_args (same as training),
    while preserving model_train_type / lora_type and other GUI fields.
    """
    cfg = deepcopy(config)
    for key in _GUI_STRIP_KEYS:
        cfg.pop(key, None)

    model_train_type = str(
        config.get("model_train_type") or page_train_type or ""
    ).strip()
    if not model_train_type:
        model_train_type = page_train_type

    fix_config_types(cfg)
    normalize_custom_args(cfg)
    ensure_enable_preview_flag(cfg)
    _ensure_gui_identity_fields(cfg, page_train_type=model_train_type)

    if model_train_type in ANIMA_FINETUNE_TRAIN_TYPES:
        adapted, warnings = adapt_anima_config(deepcopy(cfg), finetune=True)
        if adapted.get("network_args"):
            cfg["network_args"] = adapted["network_args"]
        _hydrate_lycoris_ui_fields_from_network_args(cfg)
        _ensure_gui_identity_fields(cfg, page_train_type=model_train_type)
        return cfg, _export_warnings(warnings)

    if model_train_type in ANIMA_EXPORT_TRAIN_TYPES:
        adapted, warnings = adapt_anima_config(deepcopy(cfg), finetune=False)
        if adapted.get("network_args"):
            cfg["network_args"] = adapted["network_args"]
        elif "network_args" in cfg:
            cfg.pop("network_args", None)
        _hydrate_lycoris_ui_fields_from_network_args(cfg)
        _ensure_gui_identity_fields(cfg, page_train_type=model_train_type)
        return cfg, _export_warnings(warnings)

    _sanitize_generic_export(cfg)
    cfg["model_train_type"] = model_train_type
    return cfg, []


def assert_gui_export_importable(config: dict, *, page_train_type: str) -> None:
    """Test helper: exported GUI config must not be rejected as sd-scripts TOML."""
    if _looks_like_sd_scripts_toml(config):
        raise AssertionError("export looks like sd-scripts TOML, not GUI format")
    result = validate_config_import(page_train_type, config)
    if result.get("result") == "reject":
        raise AssertionError(result.get("errors"))
