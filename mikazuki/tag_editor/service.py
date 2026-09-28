from __future__ import annotations

import copy
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import regex as bounded_regex

from mikazuki.captioning.datasets import (
    MAX_CAPTION_BYTES,
    MAX_CAPTION_CHARS,
    CaptionDatasetRecord,
    CaptionDatasetRegistry,
)
from mikazuki.captioning.models import CaptionDatasetInspectRequest
from mikazuki.captioning.writer import (
    CaptionWriteConflict,
    atomic_write_caption,
    file_fingerprint,
)
from mikazuki.storage.paths import app_root

from .models import (
    TagEditorAddOperation,
    TagEditorApplyRequest,
    TagEditorChangeSetListResponse,
    TagEditorChangeSetSummary,
    TagEditorChangeResult,
    TagEditorChangeResultsResponse,
    TagEditorDatasetItem,
    TagEditorDatasetSummary,
    TagEditorDiff,
    TagEditorInspectRequest,
    TagEditorInspectResponse,
    TagEditorItemDetail,
    TagEditorItemsResponse,
    TagEditorNormalizeOperation,
    TagEditorOperation,
    TagEditorPreviewRequest,
    TagEditorPreviewResponse,
    TagEditorPreviewIssue,
    TagEditorRemoveOperation,
    TagEditorReplaceOperation,
    TagEditorScope,
    TagEditorSetOperation,
    TagEditorSort,
    TagEditorTagCount,
    TagEditorTagSuggestionsResponse,
)


MAX_SNAPSHOTS = 8
MAX_CHANGE_SETS = 64
MAX_PREVIEW_TEXT_BYTES = 64 * 1024 * 1024
MAX_COMMON_TAGS = 200
MAX_PUBLIC_TAGS = 500
MAX_LIST_CAPTION_CHARS = 2_000
MAX_LIST_TAGS = 50
MAX_DIFF_CHARS = 4_000
SAFE_CHANGE_ID = re.compile(r"^chg_[A-Za-z0-9_-]{16,80}$")


class TagEditorError(ValueError):
    """Base error for Tag Editor requests."""


class TagEditorNotFoundError(TagEditorError):
    """Raised when an opaque dataset, item, or change-set id has expired."""


class TagEditorConflictError(TagEditorError):
    """Raised when a revision or change-set state is stale."""


class TagEditorValidationError(TagEditorError):
    """Raised when a structured edit cannot be executed safely."""


@dataclass
class TagEditorSnapshot:
    id: str
    source_id: str
    revision: str
    created_at: str
    duplicate_counts: Dict[str, int] = field(default_factory=dict)
    tag_counts: Dict[str, int] = field(default_factory=dict)
    common_tags: List[Tuple[str, int]] = field(default_factory=list)
    active_change_id: Optional[str] = None


@dataclass
class PlannedChange:
    item_id: str
    name: str
    relative_path: str
    before: str
    after: str
    expected_fingerprint: Optional[Dict[str, object]]


@dataclass
class ChangeSetRecord:
    summary: TagEditorChangeSetSummary
    diffs: List[TagEditorDiff] = field(default_factory=list)
    issues: List[TagEditorPreviewIssue] = field(default_factory=list)
    changes: List[PlannedChange] = field(default_factory=list)


class TagEditorService:
    def __init__(
        self,
        *,
        registry: Optional[CaptionDatasetRegistry] = None,
        history_root: Optional[Path] = None,
        max_snapshots: int = MAX_SNAPSHOTS,
        max_change_sets: int = MAX_CHANGE_SETS,
    ) -> None:
        if max_snapshots < 1 or max_change_sets < 1:
            raise ValueError("snapshot and change-set limits must be positive")
        self._registry = registry or CaptionDatasetRegistry(max_snapshots=max_snapshots)
        self._history_root = (
            Path(history_root).expanduser().resolve()
            if history_root is not None
            else (app_root() / "config" / "tag-editor-changes").resolve()
        )
        self._max_snapshots = max_snapshots
        self._max_change_sets = max_change_sets
        self._snapshots: "OrderedDict[str, TagEditorSnapshot]" = OrderedDict()
        self._changes: "OrderedDict[str, ChangeSetRecord]" = OrderedDict()
        self._lock = threading.RLock()

    def inspect(self, request: TagEditorInspectRequest) -> TagEditorInspectResponse:
        with self._lock:
            active = [item for item in self._snapshots.values() if item.active_change_id]
            if len(active) >= self._max_snapshots:
                raise TagEditorConflictError("已有过多数据集正在写入，请等待变更批次完成后再扫描")
            for item in active:
                self._registry.get_snapshot(item.source_id)
        source = self._registry.inspect(CaptionDatasetInspectRequest(**request.dict()))
        snapshot = TagEditorSnapshot(
            id=source.dataset.id,
            source_id=source.dataset.id,
            revision=_opaque_id("rev"),
            created_at=source.dataset.createdAt,
        )
        self._refresh_indexes(snapshot)
        with self._lock:
            self._snapshots[snapshot.id] = snapshot
            self._snapshots.move_to_end(snapshot.id)
            while len(self._snapshots) > self._max_snapshots:
                removable = next(
                    (
                        key
                        for key, item in self._snapshots.items()
                        if not item.active_change_id and key != snapshot.id
                    ),
                    None,
                )
                if removable is None:
                    break
                self._snapshots.pop(removable)

        source_snapshot = self._registry.get_snapshot(snapshot.source_id)
        first = list(source_snapshot.items.values())[: request.initialLimit]
        return TagEditorInspectResponse(
            dataset=self._dataset_summary(snapshot),
            items=[self._public_item(snapshot, record) for record in first],
            commonTags=self._common_tags(snapshot),
        )

    def get_item(self, dataset_id: str, item_id: str) -> TagEditorItemDetail:
        snapshot = self._get_snapshot(dataset_id)
        record = self._record(snapshot, item_id)
        return self._public_item(snapshot, record, detail=True)

    def list_items(
        self,
        dataset_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        query: str = "",
        state: str = "all",
        sort: TagEditorSort = "path_asc",
    ) -> TagEditorItemsResponse:
        if offset < 0:
            raise TagEditorValidationError("分页起点不能小于 0")
        if limit < 1 or limit > 500:
            raise TagEditorValidationError("每页数量必须在 1 到 500 之间")
        if state not in {"all", "with", "missing", "empty", "errors", "duplicate"}:
            raise TagEditorValidationError("未知的 Caption 状态筛选")

        snapshot = self._get_snapshot(dataset_id)
        records = self._filter_records(snapshot, query=query, state=state)
        records = _sort_records(records, sort)
        return TagEditorItemsResponse(
            datasetId=dataset_id,
            revision=snapshot.revision,
            total=len(records),
            offset=offset,
            limit=limit,
            items=[
                self._public_item(snapshot, record)
                for record in records[offset: offset + limit]
            ],
        )

    def thumbnail(self, dataset_id: str, item_id: str, *, size: int = 512) -> bytes:
        snapshot = self._get_snapshot(dataset_id)
        self._record(snapshot, item_id)
        return self._registry.thumbnail(snapshot.source_id, item_id, max_size=size)

    def suggest_tags(
        self,
        dataset_id: str,
        *,
        query: str = "",
        limit: int = 50,
    ) -> TagEditorTagSuggestionsResponse:
        if limit < 1 or limit > 200:
            raise TagEditorValidationError("补全数量必须在 1 到 200 之间")
        snapshot = self._get_snapshot(dataset_id)
        needle = query.strip().casefold()
        matches = [
            (text, count)
            for text, count in snapshot.tag_counts.items()
            if not needle or needle in text.casefold()
        ]
        matches.sort(key=lambda item: (-item[1], item[0].casefold(), item[0]))
        return TagEditorTagSuggestionsResponse(
            datasetId=dataset_id,
            query=query,
            suggestions=[
                TagEditorTagCount(text=text, count=count)
                for text, count in matches[:limit]
            ],
        )

    def preview(
        self,
        dataset_id: str,
        request: TagEditorPreviewRequest,
    ) -> TagEditorPreviewResponse:
        snapshot = self._get_snapshot(dataset_id)
        with self._lock:
            if request.revision != snapshot.revision:
                raise TagEditorConflictError("数据集版本已变化，请刷新后重新预览")
            if snapshot.active_change_id:
                raise TagEditorConflictError("当前数据集正在应用另一个变更批次")

        compiled = _compile_operations(request.operations)
        records = self._resolve_scope(snapshot, request.scope)
        changes: List[PlannedChange] = []
        diffs: List[TagEditorDiff] = []
        issues: List[TagEditorPreviewIssue] = []
        conflicts = 0
        unchanged = 0
        preview_bytes = 0

        for record in records:
            if not record.writable:
                conflicts += 1
                _add_preview_issue(issues, record, record.error or "项目当前不可写")
                continue
            if (record.caption_truncated or record.error_code == "caption.invalid") and not isinstance(
                request.operations[0], TagEditorSetOperation
            ):
                conflicts += 1
                _add_preview_issue(
                    issues,
                    record,
                    "正文被截断或编码无效，必须使用显式整段替换",
                )
                continue

            protected_source = record.caption_truncated or record.error_code == "caption.invalid"
            try:
                if protected_source:
                    stable_fingerprint = file_fingerprint(record.caption_path)
                    if record.caption_path.is_symlink() or stable_fingerprint != record.fingerprint:
                        raise TagEditorConflictError("Caption 已被外部修改")
                    before = record.existing_text[:MAX_CAPTION_CHARS]
                else:
                    before, stable_fingerprint = _stable_text(record)
            except TagEditorConflictError:
                conflicts += 1
                _add_preview_issue(issues, record, "Caption 已在扫描后被外部修改")
                continue
            try:
                after = _apply_operations(before, request.operations, compiled)
                _validate_output_text(after)
            except TimeoutError as error:
                raise TagEditorValidationError(
                    "正则替换超过 100 毫秒执行上限，请简化表达式或缩小范围"
                ) from error
            except (UnicodeError, ValueError) as error:
                raise TagEditorValidationError(
                    f"无法处理 {record.relative_path}：{error}"
                ) from error
            if after == before:
                unchanged += 1
                continue

            preview_bytes += len(before.encode("utf-8")) + len(after.encode("utf-8"))
            if preview_bytes > MAX_PREVIEW_TEXT_BYTES:
                raise TagEditorValidationError(
                    "本次预览的正文超过 64 MB，请缩小筛选范围后分批处理"
                )
            change = PlannedChange(
                item_id=record.id,
                name=record.name,
                relative_path=record.relative_path,
                before=before,
                after=after,
                expected_fingerprint=copy.deepcopy(stable_fingerprint),
            )
            changes.append(change)
            if len(diffs) < request.sampleLimit:
                diffs.append(
                    TagEditorDiff(
                        itemId=record.id,
                        name=record.name,
                        relativePath=record.relative_path,
                        before=before,
                        after=after,
                        beforeTruncated=len(before) > MAX_DIFF_CHARS,
                        afterTruncated=len(after) > MAX_DIFF_CHARS,
                    )
                )

        change_id = _opaque_id("chg")
        message = _preview_message(len(records), len(changes), unchanged, conflicts)
        summary = TagEditorChangeSetSummary(
            id=change_id,
            datasetId=dataset_id,
            datasetPath=self._registry.get_snapshot(snapshot.source_id).displayPath,
            revision=snapshot.revision,
            state="previewed",
            message=message,
            matched=len(records),
            changed=len(changes),
            unchanged=unchanged,
            conflicts=conflicts,
            createdAt=_now(),
        )
        with self._lock:
            self._changes[change_id] = ChangeSetRecord(
                summary=summary,
                diffs=diffs,
                issues=issues,
                changes=changes,
            )
            self._changes.move_to_end(change_id)
            self._trim_changes()
        bounded_diffs = [
            TagEditorDiff(
                **{
                    **diff.dict(),
                    "before": diff.before[:MAX_DIFF_CHARS],
                    "after": diff.after[:MAX_DIFF_CHARS],
                }
            )
            for diff in diffs
        ]
        return TagEditorPreviewResponse(
            **summary.dict(),
            diffs=bounded_diffs,
            issues=issues[: request.sampleLimit],
        )

    def queue_apply(
        self,
        dataset_id: str,
        request: TagEditorApplyRequest,
    ) -> TagEditorChangeSetSummary:
        with self._lock:
            snapshot = self._get_snapshot(dataset_id)
            change = self._get_change(request.changeSetId, load_persisted=False)
            summary = change.summary
            if summary.datasetId != dataset_id:
                raise TagEditorNotFoundError("变更集不属于当前数据集")
            if summary.revision != request.revision or snapshot.revision != request.revision:
                raise TagEditorConflictError("数据集版本已变化，请重新预览")
            if summary.state != "previewed":
                raise TagEditorConflictError("这个变更集已经提交或不再可应用")
            if not change.changes:
                raise TagEditorValidationError("预览没有产生可应用的改动")
            if snapshot.active_change_id:
                raise TagEditorConflictError("当前数据集已有正在应用的变更批次")

            summary.state = "queued"
            summary.message = "变更已进入安全写入队列"
            summary.backupExisting = request.backupExisting
            snapshot.active_change_id = summary.id
            self._persist_summary(summary)
            return summary.copy(deep=True)

    def apply_change_set(self, change_set_id: str) -> TagEditorChangeSetSummary:
        try:
            return self._apply_change_set(change_set_id)
        except TagEditorError:
            raise
        except Exception as error:
            with self._lock:
                change = self._changes.get(change_set_id)
                if change is None:
                    raise
                summary = change.summary
                snapshot = self._snapshots.get(summary.datasetId)
                recovered = 0
                if snapshot is not None:
                    source = self._registry.get_snapshot(snapshot.source_id)
                    for planned in change.changes:
                        record = source.items.get(planned.item_id)
                        fingerprint = file_fingerprint(record.caption_path) if record else None
                        if fingerprint and fingerprint.get("sha256") == _text_hash(planned.after):
                            _refresh_record(record, planned.after)
                            recovered += 1
                    self._refresh_indexes(snapshot)
                    snapshot.revision = _opaque_id("rev")
                    snapshot.active_change_id = None
                    summary.resultRevision = snapshot.revision
                summary.applied = max(summary.applied, recovered)
                summary.failed = max(summary.failed, summary.changed - summary.applied)
                summary.state = "partial" if summary.applied else "failed"
                summary.message = f"变更执行异常中止（{type(error).__name__}）"
                summary.canRollback = False
                summary.endedAt = _now()
                self._persist_summary(summary)
                return summary.copy(deep=True)

    def _apply_change_set(self, change_set_id: str) -> TagEditorChangeSetSummary:
        with self._lock:
            change = self._get_change(change_set_id, load_persisted=False)
            summary = change.summary
            if summary.state != "queued":
                raise TagEditorConflictError("变更集未处于可执行队列")
            snapshot = self._get_snapshot(summary.datasetId)
            summary.state = "applying"
            summary.message = "正在核对指纹并写入 Caption"
            summary.startedAt = _now()
            self._persist_summary(summary)

        source = self._registry.get_snapshot(snapshot.source_id)
        change_root = self._change_root(summary.id, create=True)
        manifest_path = change_root / "manifest.jsonl"
        applied_records: List[Tuple[CaptionDatasetRecord, PlannedChange]] = []
        runtime_conflicts = 0
        failed = 0

        try:
            with manifest_path.open("a", encoding="utf-8") as manifest:
                for issue in change.issues:
                    _append_manifest(
                        manifest,
                        {
                            "event": "conflict",
                            "itemId": issue.itemId,
                            "relativePath": issue.relativePath,
                            "error": issue.error,
                            "createdAt": _now(),
                        },
                    )
                for planned in change.changes:
                    record = source.items.get(planned.item_id)
                    if record is None or not record.writable:
                        runtime_conflicts += 1
                        _append_manifest(
                            manifest,
                            _manifest_event("conflict", planned, error="项目已失效或不可写"),
                        )
                        continue
                    current = file_fingerprint(record.caption_path)
                    if current != planned.expected_fingerprint:
                        runtime_conflicts += 1
                        _append_manifest(
                            manifest,
                            _manifest_event("conflict", planned, error="Caption 已被外部修改"),
                        )
                        continue

                    backup_path = None
                    try:
                        _require_within(record.caption_path.resolve(strict=False), source.datasetPath)
                        if current is not None and summary.backupExisting:
                            backup_path = _backup_path(change_root, source.datasetPath, record.caption_path)
                            _copy_backup(record.caption_path, backup_path)
                        intent = _manifest_event(
                            "intent",
                            planned,
                            caption_path=record.caption_path,
                            source_root=source.datasetPath,
                            before_fingerprint=current,
                            backup_path=backup_path,
                        )
                        _append_manifest(manifest, intent)
                        atomic_write_caption(
                            job_id=summary.id,
                            caption_path=record.caption_path,
                            allowed_root=source.datasetPath,
                            relative_path=record.relative_path,
                            text=planned.after,
                            expected_fingerprint=current,
                            backup_existing=False,
                        )
                        after_fingerprint = file_fingerprint(record.caption_path)
                        _append_manifest(
                            manifest,
                            _manifest_event(
                                "applied",
                                planned,
                                caption_path=record.caption_path,
                                source_root=source.datasetPath,
                                before_fingerprint=current,
                                after_fingerprint=after_fingerprint,
                                backup_path=backup_path,
                            ),
                        )
                        applied_records.append((record, planned))
                    except CaptionWriteConflict as error:
                        runtime_conflicts += 1
                        _append_manifest(
                            manifest,
                            _manifest_event("conflict", planned, error=str(error)),
                        )
                    except (OSError, UnicodeError, ValueError) as error:
                        failed += 1
                        _append_manifest(
                            manifest,
                            _manifest_event("failed", planned, error=str(error)),
                        )
        except OSError as error:
            failed += max(0, len(change.changes) - len(applied_records) - runtime_conflicts)
            summary.message = f"写入清单失败：{error}"

        with self._lock:
            for record, planned in applied_records:
                _refresh_record(record, planned.after)
            summary.applied = len(applied_records)
            summary.conflicts += runtime_conflicts
            summary.failed = failed
            summary.endedAt = _now()
            if summary.applied == summary.changed and summary.conflicts == 0 and failed == 0:
                summary.state = "completed"
                summary.message = f"已安全写入 {summary.applied} 个 Caption"
            elif summary.applied > 0:
                summary.state = "partial"
                summary.message = (
                    f"已写入 {summary.applied} 项；"
                    f"{summary.conflicts} 项冲突，{summary.failed} 项失败"
                )
            else:
                summary.state = "failed"
                summary.message = (
                    f"没有文件被写入；{summary.conflicts} 项冲突，{summary.failed} 项失败"
                )
            summary.canRollback = summary.applied > 0 and (
                summary.backupExisting
                or all(planned.expected_fingerprint is None for _, planned in applied_records)
            )
            self._refresh_indexes(snapshot)
            snapshot.revision = _opaque_id("rev")
            snapshot.active_change_id = None
            summary.resultRevision = snapshot.revision
            self._persist_summary(summary)
            return summary.copy(deep=True)

    def get_change(self, change_set_id: str) -> TagEditorChangeSetSummary:
        with self._lock:
            return self._get_change(change_set_id).summary.copy(deep=True)

    def list_changes(self, limit: int = 20) -> TagEditorChangeSetListResponse:
        if limit < 1 or limit > 100:
            raise TagEditorValidationError("变更历史数量必须在 1 到 100 之间")
        summaries: Dict[str, TagEditorChangeSetSummary] = {}
        with self._lock:
            for change in self._changes.values():
                summaries[change.summary.id] = change.summary.copy(deep=True)
        if self._history_root.is_dir():
            for path in self._history_root.glob("chg_*/summary.json"):
                try:
                    summary = self._load_summary(path.parent.name)
                    if summary is not None:
                        summaries.setdefault(summary.id, summary)
                except (OSError, ValueError, TypeError, TagEditorError):
                    continue
        ordered = sorted(summaries.values(), key=lambda item: item.createdAt, reverse=True)
        return TagEditorChangeSetListResponse(changes=ordered[:limit])

    def list_change_results(
        self,
        change_set_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> TagEditorChangeResultsResponse:
        if offset < 0 or limit < 1 or limit > 500:
            raise TagEditorValidationError("变更结果分页参数无效")
        self._get_change(change_set_id)
        entries = _load_result_manifest(self._change_root(change_set_id) / "manifest.jsonl")
        page = entries[offset: offset + limit]
        return TagEditorChangeResultsResponse(
            changeSetId=change_set_id,
            total=len(entries),
            offset=offset,
            limit=limit,
            items=[TagEditorChangeResult.parse_obj(entry) for entry in page],
        )

    def queue_rollback(self, change_set_id: str) -> TagEditorChangeSetSummary:
        with self._lock:
            change = self._get_change(change_set_id)
            summary = change.summary
            if summary.state not in {"completed", "partial", "rollback_partial"}:
                raise TagEditorConflictError("只有已应用的变更批次可以回滚")
            if not summary.canRollback:
                raise TagEditorConflictError("该批次没有完整备份，不能自动回滚")
            summary.state = "rolling_back"
            summary.message = "正在核对写入后的指纹并回滚"
            summary.rolledBack = 0
            summary.rollbackConflicts = 0
            self._persist_summary(summary)
            return summary.copy(deep=True)

    def rollback_change_set(self, change_set_id: str) -> TagEditorChangeSetSummary:
        with self._lock:
            change = self._get_change(change_set_id)
            summary = change.summary
            if summary.state != "rolling_back":
                raise TagEditorConflictError("变更集未处于回滚状态")

        change_root = self._change_root(change_set_id)
        applied = _load_applied_manifest(change_root / "manifest.jsonl")
        rolled_back = 0
        conflicts = 0
        failures = 0
        manifest_path = change_root / "manifest.jsonl"
        with manifest_path.open("a", encoding="utf-8") as manifest:
            for entry in reversed(applied):
                try:
                    caption_path = Path(entry["captionPath"])
                    source_root = Path(entry["sourceRoot"]).resolve()
                    _require_within(caption_path.resolve(strict=False), source_root)
                    if caption_path.is_symlink() or file_fingerprint(caption_path) != entry.get("afterFingerprint"):
                        conflicts += 1
                        _append_manifest(
                            manifest,
                            {
                                "event": "rollback_conflict",
                                "itemId": entry.get("itemId"),
                                "relativePath": entry.get("relativePath"),
                                "error": "Caption 在应用后被外部修改",
                            },
                        )
                        continue

                    before_fingerprint = entry.get("beforeFingerprint")
                    if before_fingerprint is None:
                        _archive_created_file(change_root, source_root, caption_path)
                    else:
                        backup_value = entry.get("backupPath")
                        if not backup_value:
                            conflicts += 1
                            continue
                        backup_path = Path(backup_value).resolve()
                        _require_within(backup_path, change_root.resolve())
                        if file_fingerprint(backup_path) != before_fingerprint:
                            conflicts += 1
                            continue
                        _atomic_restore(caption_path, backup_path.read_bytes())
                    rolled_back += 1
                    _append_manifest(
                        manifest,
                        {
                            "event": "rolled_back",
                            "itemId": entry.get("itemId"),
                            "relativePath": entry.get("relativePath"),
                        },
                    )
                except (KeyError, OSError, ValueError):
                    failures += 1

        with self._lock:
            summary.rolledBack = rolled_back
            summary.rollbackConflicts = conflicts + failures
            summary.endedAt = _now()
            if rolled_back == len(applied) and not conflicts and not failures:
                summary.state = "rolled_back"
                summary.message = f"已回滚 {rolled_back} 个 Caption"
                summary.canRollback = False
            else:
                summary.state = "rollback_partial"
                summary.message = (
                    f"已回滚 {rolled_back} 项；{conflicts + failures} 项因外部修改或备份问题未回滚"
                )
            snapshot = self._snapshots.get(summary.datasetId)
            if snapshot is not None:
                self._rescan_snapshot_records(snapshot)
                self._refresh_indexes(snapshot)
                snapshot.revision = _opaque_id("rev")
                summary.resultRevision = snapshot.revision
            self._persist_summary(summary)
            return summary.copy(deep=True)

    def _get_snapshot(self, dataset_id: str) -> TagEditorSnapshot:
        with self._lock:
            snapshot = self._snapshots.get(dataset_id)
            if snapshot is None:
                raise TagEditorNotFoundError("Tag Editor 数据集快照不存在或已过期，请重新扫描")
            self._snapshots.move_to_end(dataset_id)
            return snapshot

    def _record(self, snapshot: TagEditorSnapshot, item_id: str) -> CaptionDatasetRecord:
        source = self._registry.get_snapshot(snapshot.source_id)
        record = source.items.get(item_id)
        if record is None:
            raise TagEditorNotFoundError("数据集项目不存在")
        return record

    def _dataset_summary(self, snapshot: TagEditorSnapshot) -> TagEditorDatasetSummary:
        source = self._registry.get_snapshot(snapshot.source_id)
        records = list(source.items.values())
        with_caption = sum(1 for item in records if item.caption_exists)
        empty = sum(1 for item in records if item.caption_exists and not item.existing_text.strip())
        errors = sum(1 for item in records if item.error)
        duplicates = sum(1 for item in records if snapshot.duplicate_counts.get(item.id, 0) > 1)
        return TagEditorDatasetSummary(
            id=snapshot.id,
            revision=snapshot.revision,
            root=source.rootName,
            path=source.displayPath,
            recursive=source.recursive,
            captionExtension=source.captionExtension,
            total=len(records),
            withCaption=with_caption,
            missing=len(records) - with_caption,
            empty=empty,
            errors=errors,
            duplicates=duplicates,
            truncated=source.truncated,
            createdAt=snapshot.created_at,
        )

    def _public_item(
        self,
        snapshot: TagEditorSnapshot,
        record: CaptionDatasetRecord,
        *,
        detail: bool = False,
    ) -> TagEditorDatasetItem:
        preview_text = record.existing_text[:MAX_CAPTION_CHARS]
        caption_text = preview_text if detail else preview_text[:MAX_LIST_CAPTION_CHARS]
        tags = _split_tags(preview_text)
        model = TagEditorItemDetail if detail else TagEditorDatasetItem
        return model(
            id=record.id,
            name=record.name,
            relativePath=record.relative_path,
            width=record.width,
            height=record.height,
            captionExists=record.caption_exists,
            captionText=caption_text,
            captionPreviewTruncated=(
                record.caption_truncated or (not detail and len(record.existing_text) > MAX_LIST_CAPTION_CHARS)
            ),
            sourceTruncated=record.caption_truncated,
            writable=record.writable,
            error=_public_record_error(record),
            errorCode=record.error_code,
            duplicateCount=snapshot.duplicate_counts.get(record.id, 0),
            tags=tags[: (MAX_PUBLIC_TAGS if detail else MAX_LIST_TAGS)],
            thumbnailUrl=(
                f"/api/v2/tag-editor/datasets/{snapshot.id}/items/{record.id}/thumbnail"
            ),
        )

    def _common_tags(self, snapshot: TagEditorSnapshot) -> List[TagEditorTagCount]:
        return [TagEditorTagCount(text=text, count=count) for text, count in snapshot.common_tags]

    def _refresh_indexes(self, snapshot: TagEditorSnapshot) -> None:
        source = self._registry.get_snapshot(snapshot.source_id)
        duplicate_groups: Counter[str] = Counter(
            _duplicate_key(record.existing_text)
            for record in source.items.values()
            if _duplicate_key(record.existing_text)
        )
        snapshot.duplicate_counts = {
            record.id: duplicate_groups.get(_duplicate_key(record.existing_text), 0)
            for record in source.items.values()
        }
        tags = Counter()
        for record in source.items.values():
            tags.update(set(_split_tags(record.existing_text[:MAX_CAPTION_CHARS])))
        snapshot.tag_counts = dict(tags)
        snapshot.common_tags = sorted(
            tags.items(), key=lambda item: (-item[1], item[0].casefold(), item[0])
        )[:MAX_COMMON_TAGS]

    def _filter_records(
        self,
        snapshot: TagEditorSnapshot,
        *,
        query: str,
        state: str,
    ) -> List[CaptionDatasetRecord]:
        source = self._registry.get_snapshot(snapshot.source_id)
        needle = query.strip().casefold()
        records = []
        for record in source.items.values():
            if not _matches_state(record, state, snapshot.duplicate_counts.get(record.id, 0)):
                continue
            if needle and needle not in "\n".join(
                (record.name, record.relative_path, record.existing_text)
            ).casefold():
                continue
            records.append(record)
        return records

    def _resolve_scope(
        self,
        snapshot: TagEditorSnapshot,
        scope: TagEditorScope,
    ) -> List[CaptionDatasetRecord]:
        source = self._registry.get_snapshot(snapshot.source_id)
        known_ids = set(source.items)
        unknown = (set(scope.includeIds) | set(scope.exclusions)).difference(known_ids)
        if unknown:
            raise TagEditorValidationError("选择中包含已失效的项目，请刷新数据集")
        if scope.mode == "include":
            included = set(scope.includeIds)
            return [record for record in source.items.values() if record.id in included]
        exclusions = set(scope.exclusions)
        return [
            record
            for record in self._filter_records(snapshot, query=scope.query, state=scope.state)
            if record.id not in exclusions
        ]

    def _trim_changes(self) -> None:
        attempts = 0
        while len(self._changes) > self._max_change_sets and attempts < len(self._changes):
            key, change = next(iter(self._changes.items()))
            if change.summary.state in {"queued", "applying", "rolling_back"}:
                self._changes.move_to_end(key)
                attempts += 1
                continue
            self._changes.pop(key)

    def _get_change(self, change_id: str, *, load_persisted: bool = True) -> ChangeSetRecord:
        change = self._changes.get(change_id)
        if change is not None:
            self._changes.move_to_end(change_id)
            return change
        if load_persisted:
            summary = self._load_summary(change_id)
            if summary is not None:
                change = ChangeSetRecord(summary=summary)
                self._changes[change_id] = change
                self._trim_changes()
                return change
        raise TagEditorNotFoundError("变更集不存在或预览已过期")

    def _change_root(self, change_id: str, *, create: bool = False) -> Path:
        if not SAFE_CHANGE_ID.fullmatch(change_id):
            raise TagEditorNotFoundError("变更集 id 无效")
        root = (self._history_root / change_id).resolve()
        _require_within(root, self._history_root)
        if create:
            root.mkdir(parents=True, exist_ok=True)
        return root

    def _persist_summary(self, summary: TagEditorChangeSetSummary) -> None:
        root = self._change_root(summary.id, create=True)
        _atomic_json(root / "summary.json", summary.dict())

    def _load_summary(self, change_id: str) -> Optional[TagEditorChangeSetSummary]:
        path = self._change_root(change_id) / "summary.json"
        if not path.is_file():
            return None
        try:
            summary = TagEditorChangeSetSummary.parse_obj(
                json.loads(path.read_text(encoding="utf-8"))
            )
            if summary.state in {"queued", "applying", "rolling_back"}:
                summary.state = "interrupted"
                summary.message = "服务重启中断了这个变更批次；请核对文件后重新扫描"
                summary.endedAt = _now()
                self._persist_summary(summary)
            return summary
        except (OSError, ValueError, TypeError):
            return None

    def _rescan_snapshot_records(self, snapshot: TagEditorSnapshot) -> None:
        source = self._registry.get_snapshot(snapshot.source_id)
        for record in source.items.values():
            try:
                if not record.caption_path.exists():
                    record.caption_exists = False
                    record.existing_text = ""
                    record.caption_truncated = False
                    record.fingerprint = None
                    continue
                content = record.caption_path.read_bytes()
                text = content.decode("utf-8-sig")
                record.caption_exists = True
                record.existing_text = text
                record.caption_truncated = len(text) > MAX_CAPTION_CHARS
                record.fingerprint = file_fingerprint(record.caption_path)
                if record.error_code == "caption.invalid":
                    record.error = None
                    record.error_code = None
                    record.writable = True
            except (OSError, UnicodeError) as error:
                record.error = f"Caption 无法读取：{error}"
                record.error_code = "caption.invalid"
                record.fingerprint = file_fingerprint(record.caption_path)


def _compile_operations(
    operations: Sequence[TagEditorOperation],
) -> Dict[int, Any]:
    compiled: Dict[int, Any] = {}
    for index, operation in enumerate(operations):
        if not isinstance(operation, TagEditorReplaceOperation):
            continue
        pattern = operation.search if operation.useRegex else re.escape(operation.search)
        if operation.useRegex:
            _validate_regex(pattern)
        if operation.wholeWord:
            pattern = rf"(?<!\w)(?:{pattern})(?!\w)"
        flags = 0 if operation.matchCase else bounded_regex.IGNORECASE
        try:
            compiled[index] = bounded_regex.compile(pattern, flags)
        except bounded_regex.error as error:
            raise TagEditorValidationError(f"正则表达式无效：{error}") from error
    return compiled


def _validate_regex(pattern: str) -> None:
    if len(pattern) > 500:
        raise TagEditorValidationError("正则表达式不能超过 500 个字符")
    blocked = ("(?R", "(?0", "(?P=", "(?<=", "(?<!")
    if any(token in pattern for token in blocked) or re.search(r"\\[1-9]", pattern):
        raise TagEditorValidationError("正则表达式包含不受支持的递归、回溯引用或后向断言")
    nested_quantifier = re.compile(r"\((?:[^()\\]|\\.)*[*+{](?:[^()\\]|\\.)*\)[*+{]")
    repeated_wildcard = re.compile(r"(?:\.\*|\.\+)[*+{]")
    if nested_quantifier.search(pattern) or repeated_wildcard.search(pattern):
        raise TagEditorValidationError("正则表达式包含可能导致过度回溯的嵌套量词")


def _apply_operations(
    initial: str,
    operations: Sequence[TagEditorOperation],
    compiled: Dict[int, Any],
) -> str:
    text = initial
    for index, operation in enumerate(operations):
        if isinstance(operation, TagEditorSetOperation):
            text = operation.text
        elif isinstance(operation, TagEditorAddOperation):
            text = _apply_add(text, operation)
        elif isinstance(operation, TagEditorRemoveOperation):
            text = _apply_remove(text, operation)
        elif isinstance(operation, TagEditorReplaceOperation):
            text = compiled[index].sub(operation.replacement, text, timeout=0.1)
        elif isinstance(operation, TagEditorNormalizeOperation):
            text = _apply_normalize(text, operation)
    return text


def _apply_add(text: str, operation: TagEditorAddOperation) -> str:
    if operation.mode == "text":
        added = operation.separator.join(operation.values)
        parts = (added, text) if operation.position == "start" else (text, added)
        return operation.separator.join(part for part in parts if part)
    existing = _split_tags(text)
    additions = list(operation.values)
    combined = additions + existing if operation.position == "start" else existing + additions
    if operation.deduplicate:
        combined = _deduplicate(combined, case_sensitive=False)
    return operation.separator.join(combined)


def _apply_remove(text: str, operation: TagEditorRemoveOperation) -> str:
    if operation.mode == "tags" and operation.wholeWord:
        needles = {
            value if operation.matchCase else value.casefold()
            for value in operation.values
        }
        return operation.separator.join(
            tag
            for tag in _split_tags(text)
            if (tag if operation.matchCase else tag.casefold()) not in needles
        )
    result = text
    flags = 0 if operation.matchCase else re.IGNORECASE
    for value in operation.values:
        pattern = re.escape(value)
        if operation.wholeWord:
            pattern = rf"(?<!\w){pattern}(?!\w)"
        result = re.sub(pattern, "", result, flags=flags)
    return result


def _apply_normalize(text: str, operation: TagEditorNormalizeOperation) -> str:
    if operation.mode == "text":
        if not operation.trim:
            return text
        return "\n".join(line.strip() for line in text.strip().splitlines())
    tags = _split_tags(text)
    if operation.trim:
        tags = [tag.strip() for tag in tags if tag.strip()]
    if operation.replaceUnderscore:
        tags = [tag.replace("_", " ") for tag in tags]
    if operation.deduplicate:
        tags = _deduplicate(tags, case_sensitive=operation.caseSensitive)
    if operation.sort == "alphabetical":
        tags.sort(key=(None if operation.caseSensitive else str.casefold))
    elif operation.sort == "natural":
        tags.sort(key=lambda value: _natural_key(value, operation.caseSensitive))
    return operation.separator.join(tags)


def _split_tags(text: str) -> List[str]:
    return [part.strip() for part in re.split(r"[,\r\n]+", text) if part.strip()]


def _deduplicate(values: Iterable[str], *, case_sensitive: bool) -> List[str]:
    result = []
    seen = set()
    for value in values:
        key = value if case_sensitive else value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _natural_key(value: str, case_sensitive: bool):
    normalized = value if case_sensitive else value.casefold()
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", normalized)]


def _matches_state(record: CaptionDatasetRecord, state: str, duplicate_count: int) -> bool:
    if state == "all":
        return True
    if state == "with":
        return record.caption_exists
    if state == "missing":
        return not record.caption_exists
    if state == "empty":
        return record.caption_exists and not record.existing_text.strip()
    if state == "errors":
        return bool(record.error)
    if state == "duplicate":
        return duplicate_count > 1
    return False


def _public_record_error(record: CaptionDatasetRecord) -> Optional[str]:
    if not record.error:
        return None
    if record.error_code == "image.invalid":
        return "图片无法读取或格式不受支持"
    if record.error_code == "caption.invalid":
        return "Caption 无法按 UTF-8 安全读取；可使用整段替换进行修复"
    return record.error


def _sort_records(records: List[CaptionDatasetRecord], sort: TagEditorSort):
    if sort == "path_desc":
        return sorted(records, key=lambda item: item.relative_path.casefold(), reverse=True)
    if sort == "caption_asc":
        return sorted(records, key=lambda item: (item.existing_text.casefold(), item.relative_path.casefold()))
    if sort == "modified_desc":
        return sorted(
            records,
            key=lambda item: int((item.fingerprint or {}).get("mtimeNs", 0)),
            reverse=True,
        )
    return sorted(records, key=lambda item: (item.relative_path.casefold(), item.relative_path))


def _duplicate_key(text: str) -> str:
    return text.strip()


def _stable_text(
    record: CaptionDatasetRecord,
) -> Tuple[str, Optional[Dict[str, object]]]:
    if record.caption_path.is_symlink():
        raise TagEditorConflictError("符号链接 Caption 不可编辑")
    before = file_fingerprint(record.caption_path)
    if before != record.fingerprint:
        raise TagEditorConflictError("Caption 已在扫描后被外部修改")
    if before is None:
        return "", None
    try:
        content = record.caption_path.read_bytes()
        text = content.decode("utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise TagEditorConflictError(f"Caption 无法稳定读取：{error}") from error
    after = file_fingerprint(record.caption_path)
    if after != before:
        raise TagEditorConflictError("Caption 在读取期间发生变化")
    return text, after


def _validate_output_text(text: str) -> None:
    if len(text) > MAX_CAPTION_CHARS:
        raise ValueError(f"Caption 不能超过 {MAX_CAPTION_CHARS:,} 个字符")
    if len(text.encode("utf-8")) > MAX_CAPTION_BYTES:
        raise ValueError(f"Caption UTF-8 内容不能超过 {MAX_CAPTION_BYTES:,} 字节")


def _preview_message(matched: int, changed: int, unchanged: int, conflicts: int) -> str:
    if matched == 0:
        return "当前作用域没有匹配项目，请调整筛选或选择"
    if changed == 0 and conflicts:
        return f"没有可应用的改动；{conflicts} 项存在截断、编码、路径或外部修改冲突"
    if changed == 0:
        return f"已检查 {matched} 项，操作没有改变任何 Caption"
    return f"命中 {matched} 项，将修改 {changed} 项；{unchanged} 项不变，{conflicts} 项冲突"


def _add_preview_issue(
    issues: List[TagEditorPreviewIssue],
    record: CaptionDatasetRecord,
    error: str,
) -> None:
    issues.append(
        TagEditorPreviewIssue(
            itemId=record.id,
            name=record.name,
            relativePath=record.relative_path,
            error=error,
        )
    )


def _refresh_record(record: CaptionDatasetRecord, text: str) -> None:
    record.caption_exists = True
    record.existing_text = text
    record.caption_truncated = False
    record.fingerprint = file_fingerprint(record.caption_path)
    if record.error_code == "caption.invalid":
        record.error = None
        record.error_code = None
        record.writable = True


def _backup_path(change_root: Path, dataset_root: Path, caption_path: Path) -> Path:
    relative = caption_path.resolve(strict=False).relative_to(dataset_root.resolve())
    path = (change_root / "backups" / relative).resolve()
    _require_within(path, change_root / "backups")
    return path


def _copy_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as reader, target.open("xb") as writer:
        shutil.copyfileobj(reader, writer, length=1024 * 1024)
        writer.flush()
        os.fsync(writer.fileno())
    shutil.copystat(source, target, follow_symlinks=False)


def _manifest_event(
    event: str,
    planned: PlannedChange,
    *,
    caption_path: Optional[Path] = None,
    source_root: Optional[Path] = None,
    before_fingerprint=None,
    after_fingerprint=None,
    backup_path: Optional[Path] = None,
    error: Optional[str] = None,
) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "event": event,
        "itemId": planned.item_id,
        "relativePath": planned.relative_path,
        "beforeFingerprint": before_fingerprint,
        "afterFingerprint": after_fingerprint,
        "beforeHash": _text_hash(planned.before),
        "afterHash": _text_hash(planned.after),
        "createdAt": _now(),
    }
    if caption_path is not None:
        payload["captionPath"] = str(caption_path)
    if source_root is not None:
        payload["sourceRoot"] = str(source_root)
    if backup_path is not None:
        payload["backupPath"] = str(backup_path)
    if error:
        payload["error"] = error
    return payload


def _append_manifest(handle, payload: Dict[str, object]) -> None:
    handle.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def _load_applied_manifest(path: Path) -> List[Dict[str, object]]:
    if not path.is_file():
        raise TagEditorConflictError("变更清单不存在，无法自动回滚")
    applied: Dict[str, Dict[str, object]] = {}
    rolled_back = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except (TypeError, ValueError):
            continue
        item_id = entry.get("itemId")
        if entry.get("event") == "applied" and item_id:
            applied[str(item_id)] = entry
        elif entry.get("event") == "rolled_back" and item_id:
            rolled_back.add(str(item_id))
    return [entry for item_id, entry in applied.items() if item_id not in rolled_back]


def _load_result_manifest(path: Path) -> List[Dict[str, object]]:
    if not path.is_file():
        return []
    results: "OrderedDict[str, Dict[str, object]]" = OrderedDict()
    state_events = {
        "applied": "applied",
        "conflict": "conflict",
        "failed": "failed",
        "rolled_back": "rolled_back",
        "rollback_conflict": "rollback_conflict",
    }
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except (TypeError, ValueError):
            continue
        event = state_events.get(str(entry.get("event")))
        item_id = entry.get("itemId")
        if not event or not item_id:
            continue
        item_id = str(item_id)
        results[item_id] = {
            "itemId": item_id,
            "relativePath": str(entry.get("relativePath") or ""),
            "state": event,
            "error": entry.get("error"),
        }
    return list(results.values())


def _archive_created_file(change_root: Path, source_root: Path, caption_path: Path) -> None:
    relative = caption_path.resolve().relative_to(source_root.resolve())
    archive = (change_root / "rollback-created" / relative).resolve()
    _require_within(archive, change_root / "rollback-created")
    archive.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(caption_path, archive)
    except OSError:
        _copy_backup(caption_path, archive)
        caption_path.unlink()


def _atomic_restore(path: Path, content: bytes) -> None:
    temporary: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".rollback.tmp",
            dir=str(path.parent),
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, payload: Dict[str, object]) -> None:
    temporary: Optional[Path] = None
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _text_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()




def _require_within(path: Path, root: Path) -> None:
    try:
        path.resolve(strict=False).relative_to(root.resolve())
    except ValueError as error:
        raise TagEditorConflictError("文件路径已经离开获准的数据集目录") from error


def _opaque_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(18)}"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


_service: Optional[TagEditorService] = None
_service_lock = threading.Lock()


def get_tag_editor_service() -> TagEditorService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = TagEditorService()
    return _service
