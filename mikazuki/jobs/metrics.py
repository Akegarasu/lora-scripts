from __future__ import annotations

import math
import os
import struct
import threading
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from tensorboardX.proto.event_pb2 import Event

from mikazuki.storage.paths import app_root

from .models import JobRecord


EVENT_FILE_PREFIX = "events.out.tfevents."
MAX_EVENT_RECORD_BYTES = 256 * 1024 * 1024
MAX_RETAINED_POINTS_PER_TAG = 50_000
COMPACT_POINTS_PER_TAG_AT = 75_000
DEFAULT_READER_CACHE_SIZE = 32


@dataclass(frozen=True)
class MetricPoint:
    seq: int
    step: int
    wall_time: float
    value: Optional[float]
    non_finite: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "seq": self.seq,
            "step": self.step,
            "wallTime": self.wall_time,
            "value": self.value,
        }
        if self.non_finite is not None:
            payload["nonFinite"] = self.non_finite
        return payload


@dataclass(frozen=True)
class MetricsSource:
    root: Optional[Path]
    prefix: str = ""
    error: Optional[str] = None
    recursive: bool = True


@dataclass
class _EventFileState:
    offset: int = 0
    size: int = 0


def parse_tag_filter(tags: Optional[str | Sequence[str]]) -> Optional[List[str]]:
    """Normalize comma-separated or repeated metric tag filters."""

    if tags is None:
        return None
    raw_values = [tags] if isinstance(tags, str) else list(tags)
    result: List[str] = []
    seen = set()
    for raw in raw_values:
        for item in str(raw).split(","):
            tag = item.strip()
            if tag and tag not in seen:
                result.append(tag)
                seen.add(tag)
    return result or None


def resolve_metrics_source(job: JobRecord) -> MetricsSource:
    """Resolve a job's event root from v2 compile artifacts."""

    artifacts = job.artifacts
    root_value = _first_text(artifacts, "loggingDir")
    prefix = _first_text(artifacts, "logPrefix") or ""

    if root_value is None:
        return MetricsSource(root=None, prefix=prefix)

    try:
        root = _absolute_path(root_value)
    except (OSError, TypeError, ValueError) as exc:
        return MetricsSource(root=None, prefix=prefix, error=f"训练指标目录无效：{exc}")
    return MetricsSource(root=root, prefix=prefix)


class JobMetricsReader:
    """Incrementally reads scalar summaries for one training job."""

    def __init__(self, job: JobRecord) -> None:
        self.job_id = job.id
        self.run_id = job.runId
        self.source = resolve_metrics_source(job)
        self._file_states: Dict[str, _EventFileState] = {}
        self._series: Dict[str, List[MetricPoint]] = {}
        self._next_seq = 1
        self._errors: List[str] = []
        if self.source.error:
            self._add_error(self.source.error)
        self._lock = threading.RLock()
        self._source_path: Optional[Path] = self.source.root

    def snapshot(
        self,
        *,
        cursor: int = 0,
        max_points: int = 2000,
        tags: Optional[str | Sequence[str]] = None,
    ) -> Dict[str, Any]:
        cursor = max(0, int(cursor or 0))
        max_points = max(2, int(max_points or 2))
        requested_tags = parse_tag_filter(tags)

        with self._lock:
            self._refresh()
            latest_cursor = self._next_seq - 1
            available_tags = sorted(self._series)
            selected_tags = requested_tags if requested_tags is not None else available_tags
            series_payload = []
            point_count = 0

            for tag in selected_tags:
                points = self._series.get(tag)
                if points is None:
                    continue
                delta = [point for point in points if point.seq > cursor]
                point_count += len(delta)
                sampled = downsample_metric_points(delta, max_points)
                series_payload.append(
                    {
                        "tag": tag,
                        "points": [point.as_dict() for point in sampled],
                    }
                )

            return {
                "jobId": self.job_id,
                "cursor": latest_cursor,
                "available": bool(self._series),
                "sourcePath": _display_path(self._source_path),
                "tags": available_tags,
                "series": series_payload,
                "pointCount": point_count,
                "errors": list(self._errors),
            }

    def _refresh(self) -> None:
        files, source_path = _discover_event_files(self.source)
        touched_tags = set()
        if source_path is not None:
            self._source_path = source_path

        for path in files:
            key = _display_path(path) or str(path)
            state = self._file_states.setdefault(key, _EventFileState())
            try:
                file_size = path.stat().st_size
                if state.offset > file_size:
                    # Event writers normally append, but a replaced file must
                    # be readable again rather than staying permanently stale.
                    state.offset = 0
                records, next_offset, errors = _read_tfrecords(path, state.offset)
                state.offset = next_offset
                state.size = file_size
                for error in errors:
                    self._add_error(f"{path.name}: {error}")
            except OSError as exc:
                self._add_error(f"无法读取指标文件 {path.name}：{exc}")
                continue

            for _, payload in records:
                try:
                    event = Event.FromString(payload)
                    scalar_values = _scalar_values(event)
                except Exception as exc:
                    self._add_error(f"{path.name}: 无法解析事件记录：{exc}")
                    continue

                for tag, raw_value in scalar_values:
                    value, non_finite = _normalize_number(raw_value)
                    point = MetricPoint(
                        seq=self._next_seq,
                        step=int(getattr(event, "step", 0)),
                        wall_time=float(getattr(event, "wall_time", 0.0)),
                        value=value,
                        non_finite=non_finite,
                    )
                    self._series.setdefault(tag, []).append(point)
                    touched_tags.add(tag)
                    self._next_seq += 1

        # Keep long-running jobs bounded while preserving the global shape,
        # endpoints and spikes. Compaction only runs after a generous buffer
        # is reached so ordinary incremental refreshes stay inexpensive.
        for tag in touched_tags:
            points = self._series.get(tag, [])
            if len(points) > COMPACT_POINTS_PER_TAG_AT:
                self._series[tag] = downsample_metric_points(
                    points,
                    MAX_RETAINED_POINTS_PER_TAG,
                )

    def _add_error(self, message: str) -> None:
        clean = str(message).strip()
        if not clean or clean in self._errors:
            return
        self._errors.append(clean)
        if len(self._errors) > 20:
            del self._errors[:-20]


class JobMetricsService:
    """Thread-safe reader cache shared by REST and SSE requests."""

    def __init__(self, max_readers: int = DEFAULT_READER_CACHE_SIZE) -> None:
        self._readers: OrderedDict[str, JobMetricsReader] = OrderedDict()
        self._max_readers = max(1, int(max_readers))
        self._lock = threading.RLock()

    def snapshot(
        self,
        job: JobRecord,
        *,
        cursor: int = 0,
        max_points: int = 2000,
        tags: Optional[str | Sequence[str]] = None,
    ) -> Dict[str, Any]:
        reader = self._reader_for(job)
        return reader.snapshot(cursor=cursor, max_points=max_points, tags=tags)

    def clear(self, job_id: Optional[str] = None) -> None:
        with self._lock:
            if job_id is None:
                self._readers.clear()
            else:
                self._readers.pop(job_id, None)

    def _reader_for(self, job: JobRecord) -> JobMetricsReader:
        source = resolve_metrics_source(job)
        with self._lock:
            reader = self._readers.get(job.id)
            if reader is None or reader.source != source:
                reader = JobMetricsReader(job)
                self._readers[job.id] = reader
            self._readers.move_to_end(job.id)
            while len(self._readers) > self._max_readers:
                self._readers.popitem(last=False)
            return reader


@lru_cache(maxsize=1)
def get_job_metrics_service() -> JobMetricsService:
    return JobMetricsService()


def downsample_metric_points(points: Sequence[MetricPoint], limit: int) -> List[MetricPoint]:
    """Largest-Triangle-Three-Buckets sampling preserving endpoints/spikes."""

    length = len(points)
    if limit <= 0 or length <= limit:
        return list(points)
    if limit == 1:
        return [points[-1]]
    if limit == 2:
        return [points[0], points[-1]]

    sampled: List[MetricPoint] = [points[0]]
    every = (length - 2) / float(limit - 2)
    anchor_index = 0

    for bucket in range(limit - 2):
        average_start = int(math.floor((bucket + 1) * every)) + 1
        average_end = int(math.floor((bucket + 2) * every)) + 1
        average_end = min(average_end, length)
        average_bucket = points[average_start:average_end]
        if average_bucket:
            average_x = sum(point.seq for point in average_bucket) / len(average_bucket)
            finite_values = [point.value for point in average_bucket if point.value is not None]
            average_y = sum(finite_values) / len(finite_values) if finite_values else 0.0
        else:
            average_x = float(points[-1].seq)
            average_y = _point_y(points[-1])

        range_start = int(math.floor(bucket * every)) + 1
        range_end = int(math.floor((bucket + 1) * every)) + 1
        range_end = min(range_end, length - 1)
        anchor = points[anchor_index]
        anchor_y = _point_y(anchor)
        max_area = -1.0
        selected_index = range_start

        for index in range(range_start, max(range_start + 1, range_end)):
            point = points[index]
            area = abs(
                (anchor.seq - average_x) * (_point_y(point) - anchor_y)
                - (anchor.seq - point.seq) * (average_y - anchor_y)
            )
            if area > max_area:
                max_area = area
                selected_index = index

        sampled.append(points[selected_index])
        anchor_index = selected_index

    sampled.append(points[-1])
    return sampled


def _point_y(point: MetricPoint) -> float:
    return point.value if point.value is not None else 0.0


def _discover_event_files(source: MetricsSource) -> Tuple[List[Path], Optional[Path]]:
    root = source.root
    if root is None or not root.exists():
        return [], root
    if root.is_file():
        if root.name.startswith(EVENT_FILE_PREFIX):
            return [root], root.parent
        return [], root

    if not source.recursive and not source.prefix:
        try:
            files = sorted(
                (
                    child
                    for child in root.iterdir()
                    if child.is_file() and child.name.startswith(EVENT_FILE_PREFIX)
                ),
                key=lambda item: item.as_posix(),
            )
        except OSError:
            return [], root
        return files, root

    search_roots: List[Path]
    if source.prefix:
        search_roots = _prefix_search_roots(root, source.prefix)
    else:
        search_roots = [root]

    files: List[Path] = []
    for search_root in sorted(set(search_roots), key=lambda item: item.as_posix()):
        try:
            files.extend(
                path
                for path in search_root.rglob(f"{EVENT_FILE_PREFIX}*")
                if path.is_file()
            )
        except OSError:
            continue
    files = sorted(set(files), key=lambda item: item.as_posix())

    if len(search_roots) == 1:
        source_path: Optional[Path] = search_roots[0]
    elif search_roots:
        try:
            source_path = Path(os.path.commonpath([str(path) for path in search_roots]))
        except ValueError:
            source_path = root
    else:
        source_path = root
    return files, source_path


def _prefix_search_roots(root: Path, prefix: str) -> List[Path]:
    """Return direct, in-root run directories matching a managed prefix."""

    if not prefix or not root.is_dir():
        return []
    candidates: List[Path] = []
    if root.name.startswith(prefix):
        candidates.append(root)
    try:
        candidates.extend(
            child
            for child in root.iterdir()
            if child.is_dir()
            and not child.is_symlink()
            and child.name.startswith(prefix)
        )
    except OSError:
        return []

    try:
        resolved_root = root.resolve()
    except OSError:
        return []
    safe: List[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(resolved_root)
        except (OSError, ValueError):
            continue
        safe.append(resolved)
    return sorted(set(safe), key=lambda item: item.as_posix())


def _read_tfrecords(path: Path, offset: int) -> Tuple[List[Tuple[int, bytes]], int, List[str]]:
    records: List[Tuple[int, bytes]] = []
    errors: List[str] = []
    with path.open("rb") as handle:
        handle.seek(max(0, offset))
        next_offset = handle.tell()

        while True:
            record_offset = handle.tell()
            header = handle.read(12)
            if not header:
                break
            if len(header) < 12:
                handle.seek(record_offset)
                break

            length_bytes = header[:8]
            expected_header_crc = struct.unpack("<I", header[8:])[0]
            if _masked_crc32c(length_bytes) != expected_header_crc:
                errors.append(f"TFRecord 头校验失败（offset={record_offset}）")
                handle.seek(0, os.SEEK_END)
                next_offset = handle.tell()
                break

            length = struct.unpack("<Q", length_bytes)[0]
            if length > MAX_EVENT_RECORD_BYTES:
                errors.append(f"TFRecord 长度异常：{length} bytes（offset={record_offset}）")
                handle.seek(0, os.SEEK_END)
                next_offset = handle.tell()
                break

            payload = handle.read(length)
            footer = handle.read(4)
            if len(payload) < length or len(footer) < 4:
                handle.seek(record_offset)
                break

            expected_payload_crc = struct.unpack("<I", footer)[0]
            if _masked_crc32c(payload) != expected_payload_crc:
                errors.append(f"TFRecord 数据校验失败（offset={record_offset}）")
            else:
                records.append((record_offset, payload))
            next_offset = handle.tell()

        next_offset = max(next_offset, handle.tell()) if handle.tell() >= offset else next_offset
    return records, next_offset, errors


def _scalar_values(event: Any) -> Iterable[Tuple[str, float]]:
    summary = getattr(event, "summary", None)
    if summary is None:
        return []
    values: List[Tuple[str, float]] = []
    for item in getattr(summary, "value", []):
        value_kind = item.WhichOneof("value")
        scalar: Optional[float] = None
        if value_kind == "simple_value":
            scalar = float(item.simple_value)
        elif value_kind == "tensor":
            scalar = _tensor_scalar(item.tensor)

        if scalar is not None:
            values.append((str(item.tag), scalar))
    return values


def _tensor_scalar(tensor: Any) -> Optional[float]:
    dtype = int(getattr(tensor, "dtype", 0))
    for field in (
        "float_val",
        "double_val",
        "int_val",
        "int64_val",
        "uint32_val",
        "uint64_val",
        "bool_val",
    ):
        values = getattr(tensor, field, None)
        if values:
            return float(values[0])

    half_values = getattr(tensor, "half_val", None)
    if half_values:
        bits = int(half_values[0]) & 0xFFFF
        if dtype == 14:  # DT_BFLOAT16
            return float(struct.unpack("<f", struct.pack("<I", bits << 16))[0])
        return float(struct.unpack("<e", struct.pack("<H", bits))[0])

    content = bytes(getattr(tensor, "tensor_content", b""))
    if not content:
        return None
    formats = {
        1: "<f",   # DT_FLOAT
        2: "<d",   # DT_DOUBLE
        3: "<i",   # DT_INT32
        4: "<B",   # DT_UINT8
        5: "<h",   # DT_INT16
        6: "<b",   # DT_INT8
        9: "<q",   # DT_INT64
        10: "<?",  # DT_BOOL
        17: "<H",  # DT_UINT16
        19: "<e",  # DT_HALF
        22: "<I",  # DT_UINT32
        23: "<Q",  # DT_UINT64
    }
    if dtype == 14 and len(content) >= 2:  # DT_BFLOAT16
        bits = struct.unpack("<H", content[:2])[0] << 16
        return float(struct.unpack("<f", struct.pack("<I", bits))[0])
    format_code = formats.get(dtype)
    if format_code is None or len(content) < struct.calcsize(format_code):
        return None
    return float(struct.unpack(format_code, content[: struct.calcsize(format_code)])[0])


def _normalize_number(value: float) -> Tuple[Optional[float], Optional[str]]:
    number = float(value)
    if math.isfinite(number):
        return number, None
    if math.isnan(number):
        return None, "nan"
    return None, "+inf" if number > 0 else "-inf"


def _first_text(values: Mapping[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = values.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _absolute_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = app_root() / path
    return path.resolve()


def _display_path(path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    try:
        return str(path.resolve()).replace("\\", "/")
    except OSError:
        return str(path).replace("\\", "/")


@lru_cache(maxsize=1)
def _crc32c_table() -> Tuple[int, ...]:
    table = []
    for index in range(256):
        value = index
        for _ in range(8):
            value = (value >> 1) ^ (0x82F63B78 if value & 1 else 0)
        table.append(value & 0xFFFFFFFF)
    return tuple(table)


def _crc32c(data: bytes) -> int:
    value = 0xFFFFFFFF
    table = _crc32c_table()
    for byte in data:
        value = table[(value ^ byte) & 0xFF] ^ (value >> 8)
    return (value ^ 0xFFFFFFFF) & 0xFFFFFFFF


def _masked_crc32c(data: bytes) -> int:
    value = _crc32c(data)
    return (((value >> 15) | ((value << 17) & 0xFFFFFFFF)) + 0xA282EAD8) & 0xFFFFFFFF
