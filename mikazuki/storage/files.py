import ctypes
import json
import os
import platform
import shutil
import subprocess
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
    "models": app_root() / "models",
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


class FileManagerUnavailableError(RuntimeError):
    """Raised when the backend has no usable graphical file manager."""


class FileManagerLaunchError(RuntimeError):
    """Raised when a validated output path cannot be shown by the file manager."""


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


def file_manager_capability() -> Dict[str, object]:
    """Describe whether this backend process can reach a graphical file manager."""
    system = platform.system().lower()
    if system == "windows":
        if not _windows_has_interactive_desktop():
            return _unavailable_file_manager(system, "当前后端运行环境没有可用的图形化桌面")
        executable = shutil.which("explorer.exe")
        name = "Windows 文件资源管理器"
    elif system == "darwin":
        if not _darwin_has_interactive_desktop():
            return _unavailable_file_manager(system, "当前后端运行环境没有可用的图形化桌面")
        executable = shutil.which("open")
        name = "Finder"
    elif system == "linux":
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return _unavailable_file_manager(system, "当前后端运行环境没有可用的图形化桌面")
        executable = shutil.which("xdg-open")
        name = "系统文件管理器"
    else:
        return _unavailable_file_manager(system or "unknown", "当前系统不支持在文件管理器中显示")

    if not executable:
        return _unavailable_file_manager(system, "未找到可用的系统文件管理器")
    return {
        "available": True,
        "platform": system,
        "fileManager": name,
        "reason": None,
    }


def show_output_in_file_manager(path: str) -> Path:
    """Reveal a file or directory beneath output using the local graphical shell."""
    capability = file_manager_capability()
    if not capability["available"]:
        raise FileManagerUnavailableError(str(capability.get("reason") or "文件管理器不可用"))

    resolved = resolve_output_path(path)
    command = _file_manager_command(str(capability["platform"]), resolved)
    try:
        options: Dict[str, object] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            options["creationflags"] = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            )
        else:
            options["start_new_session"] = True
        subprocess.Popen(command, **options)
    except OSError as error:
        raise FileManagerLaunchError(f"无法启动系统文件管理器：{error}") from error
    return resolved


def resolve_output_path(path: str) -> Path:
    """Resolve an existing file or directory beneath the managed output root."""
    base = ROOTS["output"].resolve()
    resolved = _resolve_path(base, path)
    if not resolved.exists():
        raise FileNotFoundError("output path not found")
    return resolved


def resolve_output_file(path: str, *, extensions: Optional[Set[str]] = None) -> Path:
    """Resolve a regular file beneath output, optionally enforcing suffixes."""
    resolved = resolve_output_path(path)
    if not resolved.is_file():
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


def _unavailable_file_manager(system: str, reason: str) -> Dict[str, object]:
    return {
        "available": False,
        "platform": system,
        "fileManager": None,
        "reason": reason,
    }


def _windows_has_interactive_desktop() -> bool:
    if os.environ.get("SESSIONNAME", "").strip().lower() == "services":
        return False
    try:
        class UserObjectFlags(ctypes.Structure):
            _fields_ = [
                ("fInherit", ctypes.c_int),
                ("fReserved", ctypes.c_int),
                ("dwFlags", ctypes.c_uint32),
            ]

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetProcessWindowStation.restype = ctypes.c_void_p
        window_station = user32.GetProcessWindowStation()
        if not window_station:
            return False
        flags = UserObjectFlags()
        required = ctypes.c_uint32()
        succeeded = user32.GetUserObjectInformationW(
            window_station,
            1,  # UOI_FLAGS
            ctypes.byref(flags),
            ctypes.sizeof(flags),
            ctypes.byref(required),
        )
        return bool(succeeded and flags.dwFlags & 0x0001)  # WSF_VISIBLE
    except (AttributeError, OSError):
        return False


def _darwin_has_interactive_desktop() -> bool:
    try:
        return os.stat("/dev/console").st_uid != 0
    except OSError:
        return False


def _file_manager_command(system: str, path: Path) -> List[str]:
    if system == "windows":
        if path.is_dir():
            return ["explorer.exe", str(path)]
        return ["explorer.exe", "/select,", str(path)]
    if system == "darwin":
        return ["open", "-R", str(path)]
    if system == "linux":
        return ["xdg-open", str(path if path.is_dir() else path.parent)]
    raise FileManagerUnavailableError("当前系统不支持在文件管理器中显示")


def _display_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def _format_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")
