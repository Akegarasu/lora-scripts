import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

from pydantic import BaseModel

from .paths import app_root


class FileItem(BaseModel):
    name: str
    path: str
    type: str
    size: int = 0
    modifiedAt: str


ROOTS: Dict[str, Path] = {
    "models": app_root() / "sd-models",
    "sd-models": app_root() / "sd-models",
    "datasets": app_root() / "train",
    "train": app_root() / "train",
    "outputs": app_root() / "output",
    "output": app_root() / "output",
    "logs": app_root() / "logs",
    "workspace": app_root(),
}

MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".pth"}
IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".avif": "image/avif",
}
IMAGE_EXTENSIONS = set(IMAGE_MEDIA_TYPES)
SAFETENSORS_HEADER_LIMIT = 16 * 1024 * 1024


class BrowsePathError(ValueError):
    """Raised when a requested browse path escapes its configured root."""


class UnsupportedFileTypeError(ValueError):
    """Raised when a file is outside the allowlist for a read endpoint."""


class SafetensorsMetadataError(ValueError):
    """Raised when a safetensors header is missing, invalid, or too large."""


def list_files(kind: str = "file", root: str = "workspace", path: Optional[str] = None) -> List[FileItem]:
    base = ROOTS.get(root, ROOTS["workspace"]).resolve()
    target = _resolve_path(base, path)
    if not target.exists() or not target.is_dir():
        return []

    items: List[FileItem] = []
    for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.name.startswith("."):
            continue
        if not _include_item(child, kind):
            continue
        stat = child.stat()
        items.append(
            FileItem(
                name=child.name,
                path=_display_path(child),
                type="dir" if child.is_dir() else "file",
                size=0 if child.is_dir() else stat.st_size,
                modifiedAt=_format_timestamp(stat.st_mtime),
            )
        )
    return items


def resolve_output_file(path: str, *, extensions: Optional[Set[str]] = None) -> Path:
    """Resolve a regular file beneath output, optionally enforcing suffixes."""
    base = ROOTS["output"].resolve()
    resolved = _resolve_path(base, path)
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError("output file not found")
    if extensions is not None and resolved.suffix.lower() not in extensions:
        raise UnsupportedFileTypeError("unsupported output file type")
    return resolved


def read_safetensors_metadata(path: str) -> Dict[str, object]:
    """Read only the bounded JSON header of a safetensors output file."""
    resolved = resolve_output_file(path, extensions={".safetensors"})
    file_stat = resolved.stat()

    with resolved.open("rb") as file:
        length_bytes = file.read(8)
        if len(length_bytes) != 8:
            raise SafetensorsMetadataError("invalid safetensors header")
        header_length = int.from_bytes(length_bytes, byteorder="little", signed=False)
        if header_length <= 0 or header_length > SAFETENSORS_HEADER_LIMIT:
            raise SafetensorsMetadataError("safetensors header size is invalid or exceeds the limit")
        if header_length > max(0, file_stat.st_size - 8):
            raise SafetensorsMetadataError("safetensors header is truncated")
        header_bytes = file.read(header_length)

    try:
        header = json.loads(header_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SafetensorsMetadataError("invalid safetensors metadata JSON") from error
    if not isinstance(header, dict):
        raise SafetensorsMetadataError("invalid safetensors metadata object")

    raw_metadata = header.get("__metadata__", {})
    metadata = (
        {str(key): str(value) for key, value in raw_metadata.items()}
        if isinstance(raw_metadata, dict)
        else {}
    )
    return {
        "name": resolved.name,
        "path": _display_path(resolved),
        "size": file_stat.st_size,
        "modifiedAt": _format_timestamp(file_stat.st_mtime),
        "tensorCount": sum(1 for key in header if key != "__metadata__"),
        "metadata": metadata,
    }


def _resolve_path(base: Path, path: Optional[str]) -> Path:
    if not path:
        return base
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as error:
        raise BrowsePathError("requested path is outside the selected root") from error
    return resolved


def _include_item(path: Path, kind: str) -> bool:
    if path.is_dir():
        return True
    suffix = path.suffix.lower()
    if kind in {"model", "lora", "vae"}:
        return suffix in MODEL_EXTENSIONS
    if kind == "dataset":
        return suffix in IMAGE_EXTENSIONS
    if kind == "folder":
        return False
    return True


def _display_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def _format_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")
