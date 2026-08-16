import argparse
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List

import toml

from .inspector import TRAINERS, _extract_parser


class ConfigValidationError(ValueError):
    pass


def validate_config(trainer_id: str, config_path: Path, scripts_root: Path = Path("scripts/dev")) -> Dict[str, Any]:
    trainer = TRAINERS.get(trainer_id)
    if trainer is None:
        raise ConfigValidationError(f"unknown trainer: {trainer_id}")

    path = config_path.resolve()
    if not path.is_file():
        raise ConfigValidationError(f"config file not found: {path}")

    parser = _extract_parser(trainer["module"], scripts_root)
    known_params = {
        action.dest
        for action in parser._actions
        if action.option_strings and action.dest != "help"
    }
    flattened = _flatten_toml(toml.load(path))
    unknown = sorted(set(flattened) - known_params)
    if unknown:
        raise ConfigValidationError(f"unknown config keys: {', '.join(unknown)}")

    # sd-scripts' read_config_from_file reads sys.argv a second time so that
    # explicit CLI flags override TOML. Give it the same minimal command that
    # the job runner will use, without leaking this helper's own CLI flags.
    with _argv([trainer["module"], "--config_file", str(path)]):
        args = parser.parse_args()
        from library import args as args_util

        loaded = args_util.read_config_from_file(args, parser)

    return {
        "trainerId": trainer_id,
        "config": str(path).replace("\\", "/"),
        "parameterCount": len(flattened),
        "parameters": sorted(flattened),
        "loaded": {
            key: _jsonable(getattr(loaded, key))
            for key in flattened
            if hasattr(loaded, key)
        },
    }


def _flatten_toml(config: Dict[str, Any]) -> Dict[str, Any]:
    flattened: Dict[str, Any] = {}
    for key, value in config.items():
        if isinstance(value, dict):
            flattened.update(value)
        else:
            flattened[key] = value
    return flattened


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


@contextmanager
def _argv(args: List[str]) -> Iterator[None]:
    previous = sys.argv
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = previous


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a generated TOML with the real sd-scripts parser")
    parser.add_argument("--trainer", required=True, choices=sorted(TRAINERS))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--scripts-root", type=Path, default=Path("scripts/dev"))
    args = parser.parse_args()

    try:
        result = validate_config(args.trainer, args.config, args.scripts_root)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from exc

    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
