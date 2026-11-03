"""Read bounded, known training artifacts without trusting manifest file paths."""

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Optional

from mikazuki.storage.paths import runs_dir

from .models import JobRecord


MAX_ARTIFACT_BYTES = 1024 * 1024
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class JobArtifactError(ValueError):
    """The stored artifact is unsafe, oversized, or invalid."""


def read_job_artifacts(job: JobRecord, *, root: Optional[Path] = None) -> Dict[str, Any]:
    """Return the saved input and compiled text for one job; never create a store.

    Paths recorded in ``job.artifacts`` are deliberately ignored. Only four fixed
    files in this run's own directory are readable, at most 1 MiB per file.
    """
    if not _RUN_ID.fullmatch(job.runId):
        raise JobArtifactError("invalid training run identifier")

    try:
        base = (root or runs_dir()).resolve()
        candidate = base / job.runId
        run_dir = candidate.resolve()
    except RuntimeError as error:
        raise JobArtifactError("training run directory cannot be resolved") from error
    if candidate.is_symlink() or run_dir != candidate or run_dir.parent != base:
        raise JobArtifactError("training run directory must not redirect outside its own path")

    draft_text = _read_text(run_dir, "draft.json", required=True)
    try:
        draft = json.loads(draft_text, parse_constant=_reject_nonfinite_json, parse_float=_finite_json_float)
    except (ValueError, RecursionError) as error:
        raise JobArtifactError("draft.json is not valid JSON") from error
    if not isinstance(draft, dict):
        raise JobArtifactError("draft.json must contain a JSON object")

    return {
        "jobId": job.id,
        "runId": job.runId,
        "draft": draft,
        "trainConfig": _read_text(run_dir, "train.toml", required=True),
        "datasetConfig": _read_text(run_dir, "dataset.toml"),
        "samplePrompts": _read_text(run_dir, "sample_prompts.txt"),
    }


def _read_text(run_dir: Path, filename: str, *, required: bool = False) -> Optional[str]:
    path = run_dir / filename
    try:
        redirected = path.is_symlink() or path.resolve() != path
    except RuntimeError as error:
        raise JobArtifactError(f"{filename} cannot be resolved") from error
    if redirected:
        raise JobArtifactError(f"{filename} must not be a symbolic link or redirected path")
    try:
        if path.exists() and not path.is_file():
            raise JobArtifactError(f"{filename} must be a regular file")
        with path.open("rb") as handle:
            content = handle.read(MAX_ARTIFACT_BYTES + 1)
    except FileNotFoundError as error:
        if required:
            raise FileNotFoundError(f"required job artifact is missing: {filename}") from error
        return None

    if len(content) > MAX_ARTIFACT_BYTES:
        raise JobArtifactError(f"{filename} exceeds the 1 MiB artifact limit")
    try:
        return content.decode("utf-8-sig")
    except UnicodeError as error:
        raise JobArtifactError(f"{filename} is not valid UTF-8") from error


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _finite_json_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("JSON number is outside the finite float range")
    return result
