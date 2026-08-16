from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from mikazuki.storage.paths import app_root


class CaptionWriteConflict(RuntimeError):
    """Raised when a caption changed after dataset inspection."""


def file_fingerprint(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return None
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "size": stat.st_size,
        "mtimeNs": stat.st_mtime_ns,
        "sha256": digest.hexdigest(),
    }


def merge_caption(
    existing: str,
    generated: str,
    *,
    exists: bool,
    policy: str,
    separator: str,
) -> Tuple[str, bool]:
    existing = existing.strip()
    generated = generated.strip()
    if policy == "skip" and exists:
        return existing, False
    if policy == "fill_empty" and exists and existing:
        return existing, False
    if policy == "overwrite" or not existing:
        return generated, True
    if policy == "prepend":
        return _join_nonempty((generated, existing), separator), True
    if policy == "append":
        return _join_nonempty((existing, generated), separator), True
    if policy in {"skip", "fill_empty"}:
        return generated, True
    raise ValueError(f"未知 Caption 冲突策略：{policy}")


def apply_affixes(text: str, prefix: str, suffix: str, separator: str) -> str:
    return _join_nonempty((prefix.strip(), text.strip(), suffix.strip()), separator)


def atomic_write_caption(
    *,
    job_id: str,
    caption_path: Path,
    allowed_root: Path,
    relative_path: str,
    text: str,
    expected_fingerprint: Optional[Dict[str, Any]],
    backup_existing: bool,
) -> str:
    caption_path = caption_path.resolve()
    try:
        caption_path.relative_to(allowed_root.resolve())
    except ValueError as exc:
        raise CaptionWriteConflict("Caption 输出路径已离开获准的数据集目录。") from exc
    current = file_fingerprint(caption_path)
    if current != expected_fingerprint:
        raise CaptionWriteConflict("Caption 在扫描后被其他程序修改，已停止覆盖。")

    encoded = text.encode("utf-8")
    next_hash = hashlib.sha256(encoded).hexdigest()
    if current is not None and current.get("sha256") == next_hash:
        return next_hash

    caption_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Optional[Path] = None
    if current is not None and backup_existing:
        backup_path = _backup_path(job_id, relative_path, caption_path.suffix)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(caption_path, backup_path)

    temporary_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{caption_path.name}.",
            suffix=".tmp",
            dir=str(caption_path.parent),
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, caption_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    if backup_path is not None:
        _append_backup_manifest(
            job_id,
            {
                "relativePath": relative_path,
                "captionPath": str(caption_path).replace("\\", "/"),
                "backupPath": str(backup_path).replace("\\", "/"),
                "before": current,
                "after": {"sha256": next_hash, "size": len(encoded)},
            },
        )
    return next_hash


def _backup_path(job_id: str, relative_image_path: str, caption_extension: str) -> Path:
    relative = Path(relative_image_path)
    safe_parts = [part for part in relative.parts if part not in {"", ".", ".."}]
    if not safe_parts:
        safe_parts = ["caption"]
    relative_caption = Path(*safe_parts).with_suffix(caption_extension)
    return app_root() / "config" / "caption-backups" / job_id / relative_caption


def _append_backup_manifest(job_id: str, payload: Dict[str, Any]) -> None:
    path = app_root() / "config" / "caption-backups" / job_id / "manifest.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        handle.flush()


def _join_nonempty(parts, separator: str) -> str:
    return separator.join(part for part in parts if part)
