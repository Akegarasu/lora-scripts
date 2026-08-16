from __future__ import annotations

import io
import os
import secrets
import tempfile
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from itertools import islice
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from PIL import Image, ImageOps, UnidentifiedImageError

from mikazuki.storage.files import ROOTS
from mikazuki.storage.paths import app_root

from .models import (
    CaptionDatasetInspectRequest,
    CaptionDatasetInspectResponse,
    CaptionDatasetItem,
    CaptionDatasetItemsResponse,
    CaptionDatasetSummary,
    CaptionTextUpdateRequest,
)
from .writer import file_fingerprint


IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp"})
ALLOWED_ROOTS = frozenset({"train", "datasets", "workspace"})
MAX_CAPTION_CHARS = 100_000
MAX_CAPTION_BYTES = 1_000_000
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500
DEFAULT_SNAPSHOT_LIMIT = 16


class CaptionDatasetError(ValueError):
    """Base error for safe caption dataset access."""


class CaptionDatasetPathError(CaptionDatasetError):
    """Raised when a requested path is invalid or escapes its allowed root."""


class CaptionDatasetNotFoundError(CaptionDatasetError):
    """Raised when an opaque dataset snapshot is missing or expired."""


class CaptionDatasetItemNotFoundError(CaptionDatasetError):
    """Raised when an opaque item id does not belong to a dataset snapshot."""


class CaptionDatasetConflictError(CaptionDatasetError):
    """Raised when a caption changed after inspection or cannot be written safely."""


@dataclass
class CaptionDatasetRecord:
    id: str
    image_path: Path
    caption_path: Path
    relative_path: str
    width: Optional[int] = None
    height: Optional[int] = None
    caption_exists: bool = False
    existing_text: str = ""
    caption_truncated: bool = False
    fingerprint: Optional[Dict[str, object]] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    writable: bool = True

    @property
    def name(self) -> str:
        return self.image_path.name


@dataclass
class CaptionDatasetSnapshot:
    id: str
    rootName: str
    rootPath: Path
    datasetPath: Path
    displayPath: str
    recursive: bool
    captionExtension: str
    createdAt: str
    truncated: bool = False
    items: "OrderedDict[str, CaptionDatasetRecord]" = field(default_factory=OrderedDict)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def source_path(self) -> Path:
        """Canonical selected dataset directory used as the item safety root."""
        return self.datasetPath

    @property
    def source_root(self) -> Path:
        """Alias suitable for persisting on caption job items."""
        return self.datasetPath

    @property
    def allowed_root(self) -> Path:
        """Canonical configured root (train/datasets/workspace)."""
        return self.rootPath


class CaptionDatasetRegistry:
    def __init__(
        self,
        *,
        roots: Optional[Dict[str, Path]] = None,
        max_snapshots: int = DEFAULT_SNAPSHOT_LIMIT,
        backup_root: Optional[Path] = None,
    ) -> None:
        if max_snapshots < 1:
            raise ValueError("max_snapshots must be at least 1")

        configured_roots = roots or {name: ROOTS[name] for name in ALLOWED_ROOTS}
        missing_roots = ALLOWED_ROOTS.difference(configured_roots)
        if missing_roots:
            missing = ", ".join(sorted(missing_roots))
            raise ValueError(f"missing caption dataset roots: {missing}")

        self._roots = {
            name: Path(configured_roots[name]).expanduser().resolve()
            for name in ALLOWED_ROOTS
        }
        self._max_snapshots = max_snapshots
        self._backup_root = (
            Path(backup_root).expanduser().resolve()
            if backup_root is not None
            else (app_root() / "config" / "caption-backups" / "manual").resolve()
        )
        self._snapshots: "OrderedDict[str, CaptionDatasetSnapshot]" = OrderedDict()
        self._lock = threading.RLock()

    def inspect(self, request: CaptionDatasetInspectRequest) -> CaptionDatasetInspectResponse:
        root_path, dataset_path, display_path = self._resolve_dataset_path(request.root, request.path)
        image_paths, truncated = _enumerate_images(
            dataset_path,
            recursive=request.recursive,
            max_images=request.maxImages,
        )

        dataset_id = _opaque_id("ds")
        snapshot = CaptionDatasetSnapshot(
            id=dataset_id,
            rootName=request.root,
            rootPath=root_path,
            datasetPath=dataset_path,
            displayPath=display_path,
            recursive=request.recursive,
            captionExtension=request.captionExtension,
            createdAt=_now(),
            truncated=truncated,
        )

        records = [
            self._inspect_item(snapshot, image_path)
            for image_path in image_paths
        ]
        _mark_caption_collisions(records)
        for record in records:
            snapshot.items[record.id] = record

        with self._lock:
            self._snapshots[dataset_id] = snapshot
            self._snapshots.move_to_end(dataset_id)
            while len(self._snapshots) > self._max_snapshots:
                self._snapshots.popitem(last=False)

        return CaptionDatasetInspectResponse(
            dataset=self._summary(snapshot),
            items=[
                self._public_item(snapshot, item)
                for item in islice(snapshot.items.values(), request.initialLimit)
            ],
        )

    def get_snapshot(self, dataset_id: str) -> CaptionDatasetSnapshot:
        with self._lock:
            snapshot = self._snapshots.get(dataset_id)
            if snapshot is None:
                raise CaptionDatasetNotFoundError("caption dataset snapshot not found or expired")
            self._snapshots.move_to_end(dataset_id)
            return snapshot

    def get_record(self, dataset_id: str, item_id: str) -> CaptionDatasetRecord:
        snapshot = self.get_snapshot(dataset_id)
        record = snapshot.items.get(item_id)
        if record is None:
            raise CaptionDatasetItemNotFoundError("caption dataset item not found")
        return record

    def get_item(self, dataset_id: str, item_id: str) -> CaptionDatasetItem:
        snapshot = self.get_snapshot(dataset_id)
        record = self._record_from_snapshot(snapshot, item_id)
        return self._public_item(snapshot, record)

    def resolve_image(self, dataset_id: str, item_id: str) -> Path:
        snapshot = self.get_snapshot(dataset_id)
        record = self._record_from_snapshot(snapshot, item_id)
        self._validate_current_image(snapshot, record)
        return record.image_path

    def select_records(
        self,
        dataset_id: str,
        item_ids: Optional[Sequence[str]] = None,
    ) -> List[CaptionDatasetRecord]:
        snapshot = self.get_snapshot(dataset_id)
        if item_ids is None:
            return list(snapshot.items.values())

        selected: List[CaptionDatasetRecord] = []
        seen = set()
        for item_id in item_ids:
            if item_id in seen:
                continue
            selected.append(self._record_from_snapshot(snapshot, item_id))
            seen.add(item_id)
        return selected

    def list_items(
        self,
        dataset_id: str,
        *,
        offset: int = 0,
        limit: int = DEFAULT_PAGE_LIMIT,
        query: str = "",
        caption_state: str = "all",
    ) -> CaptionDatasetItemsResponse:
        if offset < 0:
            raise CaptionDatasetError("offset must be zero or greater")
        if limit < 1 or limit > MAX_PAGE_LIMIT:
            raise CaptionDatasetError(f"limit must be between 1 and {MAX_PAGE_LIMIT}")

        snapshot = self.get_snapshot(dataset_id)
        normalized_state = _normalize_caption_state(caption_state)
        normalized_query = query.strip().casefold()
        records = [
            item
            for item in snapshot.items.values()
            if _matches_caption_state(item, normalized_state)
            and _matches_query(item, normalized_query)
        ]
        page = records[offset: offset + limit]
        return CaptionDatasetItemsResponse(
            datasetId=dataset_id,
            total=len(records),
            offset=offset,
            limit=limit,
            items=[self._public_item(snapshot, item) for item in page],
        )

    def thumbnail(self, dataset_id: str, item_id: str, *, max_size: int = 512) -> bytes:
        if max_size < 32 or max_size > 2048:
            raise CaptionDatasetError("max_size must be between 32 and 2048")

        snapshot = self.get_snapshot(dataset_id)
        record = self._record_from_snapshot(snapshot, item_id)
        self._validate_current_image(snapshot, record)

        try:
            with Image.open(record.image_path) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=86, optimize=True)
                return output.getvalue()
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
            raise CaptionDatasetError(f"unable to create thumbnail: {error}") from error

    def save_caption(
        self,
        dataset_id: str,
        item_id: str,
        request: CaptionTextUpdateRequest,
    ) -> CaptionDatasetItem:
        with self._lock:
            snapshot = self.get_snapshot(dataset_id)
            record = self._record_from_snapshot(snapshot, item_id)
            if not record.writable:
                raise CaptionDatasetConflictError(record.error or "caption item is not writable")

            self._validate_current_image(snapshot, record)
            self._validate_caption_target(snapshot, record)
            current_bytes = _read_caption_bytes(record.caption_path)
            current_fingerprint = file_fingerprint(record.caption_path)
            if current_fingerprint != record.fingerprint:
                raise CaptionDatasetConflictError(
                    "caption changed after dataset inspection; refresh before saving"
                )

            new_bytes = request.text.encode("utf-8")
            if current_bytes == new_bytes:
                self._refresh_record_caption(record, new_bytes)
                return self._public_item(snapshot, record)

            if request.backupExisting and current_bytes is not None:
                self._backup_caption(snapshot, record, current_bytes)

            _atomic_write(record.caption_path, new_bytes)
            self._refresh_record_caption(record, new_bytes)
            return self._public_item(snapshot, record)

    def _resolve_dataset_path(self, root_name: str, requested_path: str) -> tuple[Path, Path, str]:
        if root_name not in ALLOWED_ROOTS:
            raise CaptionDatasetPathError("unsupported caption dataset root")

        root_path = self._roots[root_name]
        normalized_path = requested_path.strip()
        candidate = Path(normalized_path).expanduser() if normalized_path else root_path
        if not candidate.is_absolute():
            candidate = root_path / candidate
        dataset_path = candidate.resolve()
        _require_within(dataset_path, root_path)

        if not dataset_path.exists():
            raise CaptionDatasetPathError("caption dataset path does not exist")
        if not dataset_path.is_dir():
            raise CaptionDatasetPathError("caption dataset path must be a directory")

        relative = dataset_path.relative_to(root_path)
        display_path = "." if not relative.parts else relative.as_posix()
        return root_path, dataset_path, display_path

    def _inspect_item(
        self,
        snapshot: CaptionDatasetSnapshot,
        image_path: Path,
    ) -> CaptionDatasetRecord:
        relative_path = image_path.relative_to(snapshot.datasetPath).as_posix()
        caption_path = image_path.with_suffix(snapshot.captionExtension)
        record = CaptionDatasetRecord(
            id=_opaque_id("item"),
            image_path=image_path,
            caption_path=caption_path,
            relative_path=relative_path,
        )

        try:
            self._validate_current_image(snapshot, record)
            with Image.open(image_path) as image:
                record.width, record.height = image.size
        except (CaptionDatasetError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
            _set_record_error(record, "image.invalid", f"图片无法读取：{error}", writable=False)

        try:
            self._validate_caption_target(snapshot, record)
            text, exists, truncated, fingerprint = _read_caption(caption_path)
            record.existing_text = text
            record.caption_exists = exists
            record.caption_truncated = truncated
            record.fingerprint = fingerprint
        except UnicodeError as error:
            record.caption_exists = caption_path.is_file()
            record.fingerprint = file_fingerprint(caption_path)
            _set_record_error(
                record,
                "caption.invalid",
                f"Caption 不是有效的 UTF-8：{error}",
                writable=True,
            )
        except (CaptionDatasetError, OSError) as error:
            record.caption_exists = caption_path.exists()
            _set_record_error(record, "caption.invalid", f"Caption 无法读取：{error}", writable=False)

        return record

    def _validate_current_image(
        self,
        snapshot: CaptionDatasetSnapshot,
        record: CaptionDatasetRecord,
    ) -> None:
        if record.image_path.is_symlink():
            raise CaptionDatasetPathError("symbolic-link images are not allowed")
        resolved = record.image_path.resolve()
        _require_within(resolved, snapshot.datasetPath)
        if resolved != record.image_path.resolve(strict=False) or not resolved.is_file():
            raise CaptionDatasetPathError("image is no longer a regular file")

    def _validate_caption_target(
        self,
        snapshot: CaptionDatasetSnapshot,
        record: CaptionDatasetRecord,
    ) -> None:
        if record.caption_path.is_symlink():
            raise CaptionDatasetPathError("symbolic-link captions are not allowed")
        parent = record.caption_path.parent.resolve()
        _require_within(parent, snapshot.datasetPath)
        if not parent.is_dir():
            raise CaptionDatasetPathError("caption parent directory does not exist")

    def _record_from_snapshot(
        self,
        snapshot: CaptionDatasetSnapshot,
        item_id: str,
    ) -> CaptionDatasetRecord:
        record = snapshot.items.get(item_id)
        if record is None:
            raise CaptionDatasetItemNotFoundError("caption dataset item not found")
        return record

    def _summary(self, snapshot: CaptionDatasetSnapshot) -> CaptionDatasetSummary:
        with_caption = sum(1 for item in snapshot.items.values() if item.caption_exists)
        return CaptionDatasetSummary(
            id=snapshot.id,
            root=snapshot.rootName,
            path=snapshot.displayPath,
            recursive=snapshot.recursive,
            captionExtension=snapshot.captionExtension,
            total=snapshot.total,
            withCaption=with_caption,
            withoutCaption=snapshot.total - with_caption,
            truncated=snapshot.truncated,
            createdAt=snapshot.createdAt,
        )

    def _public_item(
        self,
        snapshot: CaptionDatasetSnapshot,
        record: CaptionDatasetRecord,
    ) -> CaptionDatasetItem:
        item = CaptionDatasetItem(
            id=record.id,
            name=record.image_path.name,
            relativePath=record.relative_path,
            width=record.width,
            height=record.height,
            captionExists=record.caption_exists,
            captionText=record.existing_text,
            captionTruncated=record.caption_truncated,
            writable=record.writable,
            error=record.error,
            errorCode=record.error_code,
            thumbnailUrl=(
                f"/api/v2/caption/datasets/{snapshot.id}/items/{record.id}/thumbnail"
            ),
        )
        return item

    def _backup_caption(
        self,
        snapshot: CaptionDatasetSnapshot,
        record: CaptionDatasetRecord,
        content: bytes,
    ) -> Path:
        relative_caption = record.caption_path.relative_to(snapshot.datasetPath)
        backup_dir = self._backup_root / snapshot.id / relative_caption.parent
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f%z")
        backup_path = backup_dir / (
            f"{relative_caption.name}.{stamp}-{secrets.token_hex(4)}.bak"
        )
        with backup_path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return backup_path

    def _refresh_record_caption(self, record: CaptionDatasetRecord, content: bytes) -> None:
        text = content.decode("utf-8")
        record.caption_exists = True
        record.existing_text = text[:MAX_CAPTION_CHARS]
        record.caption_truncated = len(text) > MAX_CAPTION_CHARS
        record.fingerprint = file_fingerprint(record.caption_path)
        if record.error_code == "caption.invalid":
            record.error = None
            record.error_code = None
            record.writable = True


def _enumerate_images(
    dataset_path: Path,
    *,
    recursive: bool,
    max_images: int,
) -> tuple[List[Path], bool]:
    images: List[Path] = []
    truncated = False

    def visit(directory: Path) -> None:
        nonlocal truncated
        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda path: (path.name.casefold(), path.name),
            )
        except OSError:
            return

        for entry in entries:
            if truncated:
                return
            if entry.name.startswith(".") or entry.is_symlink():
                continue
            try:
                if entry.is_dir():
                    if recursive:
                        visit(entry)
                    continue
                if not entry.is_file() or entry.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
            except OSError:
                continue

            if len(images) >= max_images:
                truncated = True
                return
            images.append(entry.resolve())

    visit(dataset_path)
    images.sort(
        key=lambda path: (
            path.relative_to(dataset_path).as_posix().casefold(),
            path.relative_to(dataset_path).as_posix(),
        )
    )
    return images, truncated


def _read_caption(
    path: Path,
) -> tuple[str, bool, bool, Optional[Dict[str, object]]]:
    if not path.exists():
        return "", False, False, None
    if not path.is_file():
        raise OSError("caption path is not a regular file")

    if path.stat().st_size > MAX_CAPTION_BYTES:
        raise OSError(f"caption exceeds the {MAX_CAPTION_BYTES}-byte safety limit")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        text = handle.read(MAX_CAPTION_CHARS + 1)
    truncated = len(text) > MAX_CAPTION_CHARS
    return text[:MAX_CAPTION_CHARS], True, truncated, file_fingerprint(path)


def _read_caption_bytes(path: Path) -> Optional[bytes]:
    if not path.exists():
        return None
    if not path.is_file():
        raise OSError("caption path is not a regular file")
    if path.stat().st_size > MAX_CAPTION_BYTES:
        raise OSError(f"caption exceeds the {MAX_CAPTION_BYTES}-byte safety limit")
    return path.read_bytes()


def _mark_caption_collisions(records: Iterable[CaptionDatasetRecord]) -> None:
    by_caption_path: Dict[str, List[CaptionDatasetRecord]] = {}
    for record in records:
        portable_key = record.caption_path.as_posix().casefold()
        by_caption_path.setdefault(portable_key, []).append(record)

    for collision in by_caption_path.values():
        if len(collision) < 2:
            continue
        names = ", ".join(item.relative_path for item in collision)
        message = f"多个图片会写入同一个 Caption 文件：{names}"
        for item in collision:
            _set_record_error(item, "caption.path_collision", message, writable=False)


def _set_record_error(
    record: CaptionDatasetRecord,
    code: str,
    message: str,
    *,
    writable: bool,
) -> None:
    if record.error:
        record.error = f"{record.error}；{message}"
        record.error_code = f"{record.error_code},{code}"
    else:
        record.error = message
        record.error_code = code
    if not writable:
        record.writable = False


def _matches_query(record: CaptionDatasetRecord, query: str) -> bool:
    if not query:
        return True
    return query in "\n".join(
        (record.relative_path, record.image_path.name, record.existing_text)
    ).casefold()


def _normalize_caption_state(state: str) -> str:
    aliases = {
        "all": "all",
        "with": "with_caption",
        "with_caption": "with_caption",
        "without": "without_caption",
        "without_caption": "without_caption",
        "error": "errors",
        "errors": "errors",
    }
    normalized = aliases.get(state.strip().lower())
    if normalized is None:
        raise CaptionDatasetError(
            "caption_state must be all, with_caption, without_caption, or errors"
        )
    return normalized


def _matches_caption_state(record: CaptionDatasetRecord, state: str) -> bool:
    if state == "all":
        return True
    if state == "with_caption":
        return record.caption_exists
    if state == "without_caption":
        return not record.caption_exists
    return record.error is not None


def _atomic_write(path: Path, content: bytes) -> None:
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def _require_within(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as error:
        raise CaptionDatasetPathError("requested path is outside the selected root") from error


def _opaque_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(18)}"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


_registry: Optional[CaptionDatasetRegistry] = None
_registry_lock = threading.Lock()


def get_caption_dataset_registry() -> CaptionDatasetRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = CaptionDatasetRegistry()
    return _registry
