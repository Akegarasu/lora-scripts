import argparse
import hashlib
import importlib
import json
import pathlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


TRAINERS = {
    "sd.lora": {
        "title": "SD 1.x / 2.x LoRA",
        "family": "sd",
        "task": "lora",
        "module": "train_network",
        "status": "stable",
        "defaultNetworkModule": "networks.lora",
    },
    "sdxl.lora": {
        "title": "SDXL LoRA",
        "family": "sdxl",
        "task": "lora",
        "module": "sdxl_train_network",
        "status": "stable",
        "defaultNetworkModule": "networks.lora",
    },
    "sd3.lora": {
        "title": "SD3 / SD3.5 LoRA",
        "family": "sd3",
        "task": "lora",
        "module": "sd3_train_network",
        "status": "stable",
        "defaultNetworkModule": "networks.lora_sd3",
    },
    "flux.lora": {
        "title": "FLUX.1 LoRA",
        "family": "flux",
        "task": "lora",
        "module": "flux_train_network",
        "status": "stable",
        "defaultNetworkModule": "networks.lora_flux",
    },
    "chroma.lora": {
        "title": "Chroma LoRA",
        "family": "flux",
        "task": "lora",
        "module": "flux_train_network",
        "status": "experimental",
        "defaultNetworkModule": "networks.lora_flux",
    },
    "lumina.lora": {
        "title": "Lumina LoRA",
        "family": "lumina",
        "task": "lora",
        "module": "lumina_train_network",
        "status": "experimental",
        "defaultNetworkModule": "networks.lora_lumina",
    },
    "hunyuan_image.lora": {
        "title": "HunyuanImage 2.1 LoRA",
        "family": "hunyuan_image",
        "task": "lora",
        "module": "hunyuan_image_train_network",
        "status": "experimental",
        "defaultNetworkModule": "networks.lora_hunyuan_image",
    },
    "anima.lora": {
        "title": "Anima LoRA",
        "family": "anima",
        "task": "lora",
        "module": "anima_train_network",
        "status": "experimental",
        "defaultNetworkModule": "networks.lora_anima",
    },
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, pathlib.Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, set):
        return sorted((_jsonable(v) for v in value), key=str)
    return str(value)


def _scalar_type(action: argparse.Action) -> str:
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return "boolean"
    if action.choices is not None:
        return "enum"
    if action.type is int:
        return "integer"
    if action.type is float:
        return "number"
    if action.type is bool:
        return "boolean"
    if action.type is pathlib.Path:
        return "path"
    if getattr(action.type, "__name__", "") == "int_or_float":
        return "integer_or_number"
    return "string"


def _action_type(action: argparse.Action) -> str:
    is_array = (
        action.nargs in {"*", "+"}
        or (isinstance(action.nargs, int) and action.nargs > 0)
        or isinstance(action, (argparse._AppendAction, argparse._AppendConstAction))
    )
    return "array" if is_array else _scalar_type(action)


def _action_kind(action: argparse.Action) -> str:
    if isinstance(action, argparse._StoreTrueAction):
        return "store_true"
    if isinstance(action, argparse._StoreFalseAction):
        return "store_false"
    if isinstance(action, argparse._AppendConstAction):
        return "append_const"
    if isinstance(action, argparse._AppendAction):
        return "append"
    if isinstance(action, argparse._CountAction):
        return "count"
    if isinstance(action, argparse._StoreConstAction):
        return "store_const"
    return "store"


def _action_name(action: argparse.Action) -> str:
    return action.dest


def _extract_parser(module_name: str, scripts_root: Path) -> argparse.ArgumentParser:
    sys.path.insert(0, str(scripts_root.resolve()))
    module = importlib.import_module(module_name)
    if not hasattr(module, "setup_parser"):
        raise RuntimeError(f"{module_name} does not expose setup_parser()")
    return module.setup_parser()


def _extract_actions(parser: argparse.ArgumentParser, script: str) -> Dict[str, Dict[str, Any]]:
    params: Dict[str, Dict[str, Any]] = {}
    for action in parser._actions:
        if not action.option_strings or action.dest == "help":
            continue
        name = _action_name(action)
        param_type = _action_type(action)
        params[name] = {
            "name": name,
            "flags": list(action.option_strings),
            "type": param_type,
            "itemType": _scalar_type(action) if param_type == "array" else None,
            "default": _jsonable(action.default),
            "choices": _jsonable(list(action.choices)) if action.choices is not None else None,
            "nargs": _jsonable(action.nargs),
            "action": _action_kind(action),
            "required": bool(getattr(action, "required", False)),
            "help": action.help or "",
            "source": {
                "script": f"scripts/dev/{script}.py",
                "module": script,
                "function": "setup_parser",
            },
        }
    return params


def generate_manifest(scripts_root: Path) -> Dict[str, Any]:
    trainers: Dict[str, Dict[str, Any]] = {}
    for trainer_id, trainer in TRAINERS.items():
        module_name = trainer["module"]
        parser = _extract_parser(module_name, scripts_root)
        script = f"scripts/dev/{module_name}.py"
        trainers[trainer_id] = {
            "trainer": {
                "title": trainer["title"],
                "family": trainer["family"],
                "task": trainer["task"],
                "script": script,
                "status": trainer["status"],
                "defaultNetworkModule": trainer["defaultNetworkModule"],
            },
            "script": script,
            "params": _extract_actions(parser, module_name),
        }

    manifest = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "scriptsRoot": str(scripts_root).replace("\\", "/"),
        "sharedParams": {},
        "trainers": trainers,
    }
    semantic_payload = {
        "schemaVersion": manifest["schemaVersion"],
        "trainers": manifest["trainers"],
    }
    manifest["manifestHash"] = hashlib.sha256(
        json.dumps(semantic_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sd-scripts argparse manifest")
    subparsers = parser.add_subparsers(dest="command")
    generate_parser = subparsers.add_parser("generate", help="generate manifest JSON")
    generate_parser.add_argument("--scripts-root", default="scripts/dev")
    generate_parser.add_argument("--output", default="mikazuki/catalog/generated/sd_scripts_manifest.json")
    parser.add_argument("--scripts-root", default="scripts/dev")
    parser.add_argument("--output", default="mikazuki/catalog/generated/sd_scripts_manifest.json")
    args = parser.parse_args()

    manifest = generate_manifest(Path(args.scripts_root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    main()
