from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel

from .paths import app_root


class FileItem(BaseModel):
    name: str
    path: str
    type: str
    size: int = 0


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
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


class BrowsePathError(ValueError):
    """Raised when a requested browse path escapes its configured root."""


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
            )
        )
    return items


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
