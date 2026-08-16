import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from .models import ParamDefinition, ParamGroup, TrainerDefinition, TrainerSummary


CATALOG_DIR = Path(__file__).parent
GENERATED_MANIFEST = CATALOG_DIR / "generated" / "sd_scripts_manifest.json"
OVERLAY_DIR = CATALOG_DIR / "overlays"


def _deep_update(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_update(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
    return loaded or {}


def _stable_hash(data: Dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CatalogService:
    def __init__(
        self,
        manifest_path: Optional[Path] = None,
        overlay_dir: Optional[Path] = None,
    ) -> None:
        self.manifest_path = manifest_path or GENERATED_MANIFEST
        self.overlay_dir = overlay_dir or OVERLAY_DIR
        self._manifest: Dict[str, Any] = {}
        self._common_overlay: Dict[str, Any] = {}
        self._trainer_overlays: Dict[str, Dict[str, Any]] = {}
        self._catalog_hash = ""
        self._trainers: Dict[str, TrainerDefinition] = {}
        self.reload()

    def reload(self) -> None:
        self._manifest = _read_json(self.manifest_path)
        self._common_overlay = _read_yaml(self.overlay_dir / "common.yaml")
        self._trainer_overlays = {
            trainer_id: _read_yaml(self.overlay_dir / f"{trainer_id.replace('.', '_')}.yaml")
            for trainer_id in self._manifest.get("trainers", {})
        }
        self._catalog_hash = _stable_hash(
            {
                "manifestHash": self._manifest.get("manifestHash") or _stable_hash(self._manifest),
                "commonOverlay": self._common_overlay,
                "trainerOverlays": self._trainer_overlays,
            }
        )
        self._trainers = self._build_trainers()

    @property
    def manifest_hash(self) -> str:
        return self._catalog_hash

    def list_trainers(self) -> List[TrainerSummary]:
        return [
            TrainerSummary(
                id=trainer.id,
                title=trainer.title,
                family=trainer.family,
                task=trainer.task,
                script=trainer.script,
                status=trainer.status,
                datasetDefaults=copy.deepcopy(trainer.datasetDefaults),
            )
            for trainer in sorted(self._trainers.values(), key=lambda x: (x.family, x.task, x.id))
            if trainer.status != "hidden"
        ]

    def get_trainer(self, trainer_id: str) -> Optional[TrainerDefinition]:
        return self._trainers.get(trainer_id)

    def get_param_groups(self, trainer_id: str, view: str = "recommended") -> List[Dict[str, Any]]:
        trainer = self.get_trainer(trainer_id)
        if trainer is None:
            return []

        visible_params = [p for p in trainer.params.values() if self._include_param(p, view)]
        params_by_group: Dict[str, List[ParamDefinition]] = {}
        for param in visible_params:
            params_by_group.setdefault(param.group or "raw", []).append(param)

        group_defs = {group.id: group for group in trainer.groups}
        raw_group = group_defs.setdefault("raw", ParamGroup(id="raw", title="未分类参数", order=999))

        groups = []
        for group_id, params in params_by_group.items():
            group = group_defs.get(group_id, raw_group if group_id == "raw" else ParamGroup(id=group_id, title=group_id))
            params_sorted = sorted(params, key=lambda p: (self._priority_order(p.priority), p.name))
            groups.append(
                {
                    "id": group.id,
                    "title": group.title,
                    "description": group.description,
                    "order": group.order,
                    "params": [p.dict(exclude_none=True) for p in params_sorted],
                }
            )

        return sorted(groups, key=lambda g: (g["order"], g["id"]))

    def _build_trainers(self) -> Dict[str, TrainerDefinition]:
        shared_params = self._manifest.get("sharedParams", {})
        common_groups = self._load_groups(self._common_overlay)
        trainers: Dict[str, TrainerDefinition] = {}

        for trainer_id, raw_trainer in self._manifest.get("trainers", {}).items():
            overlay = self._load_trainer_overlay(trainer_id)
            trainer_meta = _deep_update(raw_trainer.get("trainer", {}), overlay.get("trainer", {}))

            params = self._expand_params(raw_trainer.get("params", {}), shared_params)
            params = self._merge_param_overlay(params, self._common_overlay.get("params", {}))
            params = self._merge_param_overlay(params, overlay.get("params", {}))

            groups = self._merge_groups(common_groups, self._load_groups(overlay))

            trainer = TrainerDefinition(
                id=trainer_id,
                title=trainer_meta.get("title", trainer_id),
                family=trainer_meta.get("family", raw_trainer.get("family", "unknown")),
                task=trainer_meta.get("task", raw_trainer.get("task", "unknown")),
                script=trainer_meta.get("script", raw_trainer.get("script", "")),
                status=trainer_meta.get("status", raw_trainer.get("status", "stable")),
                supportsDatasetConfig=trainer_meta.get("supportsDatasetConfig", True),
                supportsSamplePrompts=trainer_meta.get("supportsSamplePrompts", True),
                defaultNetworkModule=trainer_meta.get("defaultNetworkModule"),
                datasetDefaults=copy.deepcopy(trainer_meta.get("datasetDefaults", {})),
                params={name: ParamDefinition(**value) for name, value in params.items()},
                groups=groups,
                manifestHash=self.manifest_hash,
            )
            trainers[trainer_id] = trainer

        return trainers

    def _load_trainer_overlay(self, trainer_id: str) -> Dict[str, Any]:
        return self._trainer_overlays.get(trainer_id, {})

    def _expand_params(self, raw_params: Any, shared_params: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        if isinstance(raw_params, list):
            params = {}
            for name in raw_params:
                params[name] = copy.deepcopy(shared_params.get(name, {"name": name, "flags": [f"--{name}"]}))
            return params

        params = {}
        for name, value in raw_params.items():
            base = copy.deepcopy(shared_params.get(name, {"name": name, "flags": [f"--{name}"]}))
            params[name] = _deep_update(base, value or {})
        return params

    def _merge_param_overlay(
        self,
        params: Dict[str, Dict[str, Any]],
        overlay_params: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        merged = copy.deepcopy(params)
        for name, patch in overlay_params.items():
            if name not in merged:
                continue
            base = merged[name]
            merged[name] = _deep_update(base, patch or {})
        return merged

    def _load_groups(self, overlay: Dict[str, Any]) -> List[ParamGroup]:
        return [ParamGroup(**item) for item in overlay.get("groups", [])]

    def _merge_groups(self, base: Iterable[ParamGroup], patch: Iterable[ParamGroup]) -> List[ParamGroup]:
        groups = {group.id: group.dict() for group in base}
        for group in patch:
            groups[group.id] = _deep_update(groups.get(group.id, {}), group.dict())
        return [ParamGroup(**value) for value in groups.values()]

    def _include_param(self, param: ParamDefinition, view: str) -> bool:
        if view == "all":
            return True
        if param.hidden:
            return False
        if view == "required":
            return param.required or param.priority == "required"
        if view == "advanced":
            return param.priority in {"required", "recommended", "advanced", "dangerous", "raw"}
        return param.priority in {"required", "recommended"}

    def _priority_order(self, priority: str) -> int:
        return {
            "required": 0,
            "recommended": 10,
            "advanced": 20,
            "dangerous": 30,
            "raw": 40,
        }.get(priority, 50)


@lru_cache(maxsize=1)
def get_catalog_service() -> CatalogService:
    return CatalogService()
