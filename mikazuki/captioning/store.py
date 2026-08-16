from __future__ import annotations

import json
import threading
from collections import Counter
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Type

from peewee import (
    BooleanField,
    CharField,
    CompositeKey,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
    fn,
)

from mikazuki.storage.paths import caption_db_path

from .models import (
    CaptionCommitRequest,
    CaptionJobCreateRequest,
    CaptionJobItem,
    CaptionJobItemsResponse,
    CaptionJobSummary,
    CaptionTag,
)


ACTIVE_STATES = {
    "created",
    "queued",
    "running",
    "loading",
    "generating",
    "committing",
    "canceling",
}
PROCESSED_STATES = {"succeeded", "failed", "skipped", "conflict", "canceled"}
STATE_COUNTERS = {
    "succeeded": "succeeded",
    "failed": "failed",
    "skipped": "skipped",
    "conflict": "conflicts",
}
SQL_BATCH_SIZE = 500


class CaptionStoreConflict(RuntimeError):
    """Raised when a review mutation loses the job-state race."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _create_models(database: SqliteDatabase) -> Tuple[Type[Model], Type[Model]]:
    bound_database = database

    class StoredModel(Model):
        class Meta:
            database = bound_database

    class CaptionJobRow(StoredModel):
        id = CharField(primary_key=True)
        name = TextField(null=True)
        model_id = CharField()
        model_title = TextField()
        output_mode = CharField()
        state = CharField()
        review_mode = BooleanField(default=False)
        details_state = CharField(default="available")
        message = TextField(default="")
        revision = IntegerField(default=0)
        dataset_id = CharField()
        source_root = TextField()
        log_path = TextField()
        request_json = TextField()
        commit_json = TextField(null=True)
        total = IntegerField(default=0)
        processed = IntegerField(default=0)
        succeeded = IntegerField(default=0)
        failed = IntegerField(default=0)
        skipped = IntegerField(default=0)
        conflicts = IntegerField(default=0)
        written = IntegerField(default=0)
        created_at = CharField()
        started_at = CharField(null=True)
        ended_at = CharField(null=True)
        error_message = TextField(null=True)

        class Meta:
            table_name = "caption_jobs"
            indexes = ((("created_at",), False),)

    class CaptionItemRow(StoredModel):
        job_id = CharField()
        id = CharField()
        item_index = IntegerField()
        name = TextField()
        relative_path = TextField()
        image_path = TextField()
        caption_path = TextField()
        state = CharField()
        existing_text = TextField(default="")
        existing_fingerprint = TextField(null=True)
        generated_text = TextField(default="")
        final_text = TextField(default="")
        tags_json = TextField(default="[]")
        raw_json = TextField(null=True)
        error = TextField(null=True)
        written = BooleanField(default=False)
        edited = BooleanField(default=False)
        elapsed_ms = IntegerField(null=True)
        written_hash = TextField(null=True)

        class Meta:
            table_name = "caption_items"
            primary_key = CompositeKey("job_id", "id")
            indexes = (
                (("job_id", "item_index"), False),
                (("job_id", "state"), False),
            )

    return CaptionJobRow, CaptionItemRow


class CaptionStore:
    """SQLite-backed IPC ledger for isolated Caption workers."""

    def __init__(self, db_path: Optional[Path] = None, *, reconcile: bool = True) -> None:
        self.db_path = (db_path or caption_db_path()).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._database = SqliteDatabase(
            str(self.db_path),
            timeout=30,
            pragmas={"journal_mode": "wal", "busy_timeout": 30_000},
        )
        self._Job, self._Item = _create_models(self._database)
        with self._database:
            self._database.create_tables([self._Job, self._Item])
        if reconcile:
            self.reconcile_interrupted_jobs()

    def create_job(
        self,
        summary: CaptionJobSummary,
        request: CaptionJobCreateRequest,
        items: Sequence[Dict[str, Any]],
    ) -> CaptionJobSummary:
        stats = _item_stats(items)
        item_rows = [
            {
                "job_id": summary.id,
                "id": item["id"],
                "item_index": index,
                "name": item["name"],
                "relative_path": item["relative_path"],
                "image_path": str(item["image_path"]),
                "caption_path": str(item["caption_path"]),
                "state": item.get("state", "pending"),
                "existing_text": item.get("existing_text", ""),
                "existing_fingerprint": _json_dump(item.get("existing_fingerprint")),
                "error": item.get("error"),
            }
            for index, item in enumerate(items)
        ]
        with self._lock, self._database:
            job = self._Job.create(
                id=summary.id,
                name=summary.name,
                model_id=summary.modelId,
                model_title=summary.modelTitle,
                output_mode=summary.outputMode,
                state=summary.state,
                review_mode=request.output.stageBeforeWrite,
                details_state=summary.detailsState,
                message=summary.message,
                revision=summary.revision,
                dataset_id=summary.datasetId,
                source_root=str(items[0]["source_root"]),
                log_path=summary.logPath,
                request_json=request.json(ensure_ascii=False),
                total=len(items),
                processed=stats["processed"],
                succeeded=stats["succeeded"],
                failed=stats["failed"],
                skipped=stats["skipped"],
                conflicts=stats["conflicts"],
                written=stats["written"],
                created_at=summary.createdAt,
                started_at=summary.startedAt,
                ended_at=summary.endedAt,
                error_message=summary.errorMessage,
            )
            for batch in _chunks(item_rows, SQL_BATCH_SIZE):
                self._Item.insert_many(batch).execute()
            return self._row_to_summary(job)

    def get_job(self, job_id: str) -> Optional[CaptionJobSummary]:
        with self._lock, self._database:
            row = self._Job.get_or_none(self._Job.id == job_id)
            return self._row_to_summary(row) if row is not None else None

    def list_jobs(self, limit: int = 50) -> List[CaptionJobSummary]:
        with self._lock, self._database:
            rows = (
                self._Job.select()
                .order_by(self._Job.created_at.desc())
                .limit(limit)
            )
            return [self._row_to_summary(row) for row in rows]

    def get_request(self, job_id: str) -> Optional[CaptionJobCreateRequest]:
        with self._lock, self._database:
            row = self._Job.get_or_none(self._Job.id == job_id)
            if row is None:
                return None
            return CaptionJobCreateRequest.parse_raw(row.request_json)

    def get_source_root(self, job_id: str) -> Optional[Path]:
        with self._lock, self._database:
            row = self._Job.get_or_none(self._Job.id == job_id)
            if row is None:
                return None
            return Path(row.source_root).resolve()

    def queue_commit(
        self,
        job_id: str,
        request: CaptionCommitRequest,
    ) -> CaptionJobSummary:
        with (
            self._lock,
            self._database.connection_context(),
            self._database.atomic("IMMEDIATE"),
        ):
            row = self._Job.get_by_id(job_id)
            if not row.review_mode:
                raise CaptionStoreConflict("直接写入任务没有可提交的复核结果")
            if row.state not in {"awaiting_review", "partial", "failed"}:
                raise CaptionStoreConflict("只有已生成并等待复核的任务可以提交")
            (
                self._Job.update(
                    commit_json=request.json(ensure_ascii=False),
                    state="queued",
                    ended_at=None,
                    message="写入任务已进入队列。",
                    error_message=None,
                    revision=self._Job.revision + 1,
                )
                .where(self._Job.id == job_id)
                .execute()
            )
            row = self._Job.get_by_id(job_id)
            return self._row_to_summary(row)

    def get_commit_request(self, job_id: str) -> CaptionCommitRequest:
        with self._lock, self._database:
            row = self._Job.get_by_id(job_id)
            if row.commit_json is None:
                return CaptionCommitRequest()
            return CaptionCommitRequest.parse_raw(row.commit_json)

    def update_job(self, job_id: str, **fields: Any) -> Optional[CaptionJobSummary]:
        columns = {
            "state": "state",
            "detailsState": "details_state",
            "message": "message",
            "startedAt": "started_at",
            "endedAt": "ended_at",
            "errorMessage": "error_message",
        }
        values = {columns[name]: value for name, value in fields.items()}
        with self._lock, self._database:
            updated = (
                self._Job.update(**values, revision=self._Job.revision + 1)
                .where(self._Job.id == job_id)
                .execute()
            )
            if not updated:
                return None
            row = self._Job.get_by_id(job_id)
            return self._row_to_summary(row)

    def list_items(
        self,
        job_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        state: Optional[str] = None,
        query: str = "",
    ) -> CaptionJobItemsResponse:
        condition = self._Item.job_id == job_id
        if state:
            condition &= self._Item.state == state
        if query.strip():
            condition &= self._Item.relative_path.contains(query.strip())
        with self._lock, self._database:
            base_query = self._Item.select().where(condition)
            total = base_query.count()
            rows = (
                base_query
                .order_by(self._Item.item_index)
                .limit(limit)
                .offset(offset)
            )
            return CaptionJobItemsResponse(
                jobId=job_id,
                total=total,
                offset=offset,
                limit=limit,
                items=[self._row_to_item(row) for row in rows],
            )

    def get_item(self, job_id: str, item_id: str) -> Optional[CaptionJobItem]:
        row = self.get_internal_item(job_id, item_id)
        return self._row_to_item(row) if row is not None else None

    def get_internal_item(self, job_id: str, item_id: str) -> Optional[Model]:
        with self._lock, self._database:
            return self._Item.get_or_none(
                (self._Item.job_id == job_id) & (self._Item.id == item_id)
            )

    def iter_internal_items(
        self,
        job_id: str,
        *,
        states: Optional[Sequence[str]] = None,
        item_ids: Optional[Sequence[str]] = None,
    ) -> List[Model]:
        if item_ids == []:
            return []
        condition = self._Item.job_id == job_id
        if states:
            condition &= self._Item.state.in_(states)
        with self._lock, self._database:
            if item_ids is None:
                return list(
                    self._Item.select()
                    .where(condition)
                    .order_by(self._Item.item_index)
                )
            rows = []
            unique_ids = list(dict.fromkeys(item_ids))
            for batch in _chunks(unique_ids, SQL_BATCH_SIZE):
                rows.extend(
                    self._Item.select().where(
                        condition & self._Item.id.in_(batch)
                    )
                )
            return sorted(rows, key=lambda row: row.item_index)

    def update_item(self, job_id: str, item_id: str, **fields: Any) -> Optional[CaptionJobItem]:
        columns = {
            "state": "state",
            "generatedText": "generated_text",
            "finalText": "final_text",
            "tags": "tags_json",
            "raw": "raw_json",
            "error": "error",
            "written": "written",
            "edited": "edited",
            "elapsedMs": "elapsed_ms",
            "writtenHash": "written_hash",
            "existingText": "existing_text",
            "existingFingerprint": "existing_fingerprint",
        }
        values: Dict[str, Any] = {}
        for name, value in fields.items():
            column = columns[name]
            if name == "tags":
                value = json.dumps([item.dict() for item in value], ensure_ascii=False)
            elif name in {"raw", "existingFingerprint"}:
                value = _json_dump(value)
            values[column] = value

        with (
            self._lock,
            self._database.connection_context(),
            self._database.atomic("IMMEDIATE"),
        ):
            row = self._Item.get_or_none(
                (self._Item.job_id == job_id) & (self._Item.id == item_id)
            )
            if row is None:
                return None
            previous = _counter_values(row.state, row.written)
            (
                self._Item.update(**values)
                .where(
                    (self._Item.job_id == job_id) & (self._Item.id == item_id)
                )
                .execute()
            )
            row = self._Item.get_by_id((job_id, item_id))
            current = _counter_values(row.state, row.written)
            self._update_counters(job_id, previous, current)
            return self._row_to_item(row)

    def compact_direct_job_items(self, job_id: str) -> int:
        with self._lock, self._database:
            count = (
                self._Item.update(
                    existing_text="",
                    existing_fingerprint=None,
                    generated_text="",
                    final_text="",
                    tags_json="[]",
                    raw_json=None,
                    written_hash=None,
                    edited=False,
                )
                .where(
                    (self._Item.job_id == job_id)
                    & self._Item.state.in_(("succeeded", "skipped"))
                )
                .execute()
            )
            (
                self._Job.update(
                    details_state="compacted",
                    revision=self._Job.revision + 1,
                )
                .where(self._Job.id == job_id)
                .execute()
            )
            return count

    def edit_review_item(self, job_id: str, item_id: str, final_text: str) -> CaptionJobItem:
        with (
            self._lock,
            self._database.connection_context(),
            self._database.atomic("IMMEDIATE"),
        ):
            job = self._Job.get_or_none(self._Job.id == job_id)
            if job is None:
                raise KeyError(job_id)
            if not job.review_mode:
                raise CaptionStoreConflict("直接写入任务不支持任务内人工修订")
            if job.state not in {"awaiting_review", "partial", "failed"}:
                raise CaptionStoreConflict("任务尚未进入可复核状态")
            item = self._Item.get_or_none(
                (self._Item.job_id == job_id) & (self._Item.id == item_id)
            )
            if item is None:
                raise KeyError(item_id)
            if item.written:
                raise CaptionStoreConflict("该 Caption 已写入，不能在当前任务中再次编辑")
            if item.state not in {"succeeded", "failed", "conflict"}:
                raise CaptionStoreConflict("该结果当前不可编辑")
            (
                self._Item.update(final_text=final_text, edited=True)
                .where(
                    (self._Item.job_id == job_id) & (self._Item.id == item_id)
                )
                .execute()
            )
            (
                self._Job.update(revision=self._Job.revision + 1)
                .where(self._Job.id == job_id)
                .execute()
            )
            item = self._Item.get_by_id((job_id, item_id))
            return self._row_to_item(item)

    def cancel_unfinished_items(self, job_id: str) -> None:
        with self._lock, self._database:
            condition = (
                (self._Item.job_id == job_id)
                & self._Item.state.in_(("pending", "running"))
            )
            count = (
                self._Item.update(
                    state="canceled",
                    error=fn.COALESCE(self._Item.error, "任务已取消"),
                )
                .where(condition)
                .execute()
            )
            if count == 0:
                return
            (
                self._Job.update(
                    processed=self._Job.processed + count,
                    revision=self._Job.revision + 1,
                )
                .where(self._Job.id == job_id)
                .execute()
            )

    def reconcile_interrupted_jobs(self) -> int:
        with (
            self._lock,
            self._database.connection_context(),
            self._database.atomic("IMMEDIATE"),
        ):
            jobs = list(
                self._Job.select(self._Job.id)
                .where(self._Job.state.in_(ACTIVE_STATES))
            )
            if not jobs:
                return 0
            ended_at = _now()
            for job in jobs:
                running = (
                    self._Item.select()
                    .where(
                        (self._Item.job_id == job.id)
                        & (self._Item.state == "running")
                    )
                    .count()
                )
                (
                    self._Item.update(
                        state="failed",
                        error=fn.COALESCE(
                            self._Item.error,
                            "服务重启中断了该图片的处理",
                        ),
                    )
                    .where(
                        (self._Item.job_id == job.id)
                        & (self._Item.state == "running")
                    )
                    .execute()
                )
                (
                    self._Job.update(
                        state="interrupted",
                        message="服务重启中断了任务，可重新创建任务处理未完成项目。",
                        ended_at=fn.COALESCE(self._Job.ended_at, ended_at),
                        processed=self._Job.processed + running,
                        failed=self._Job.failed + running,
                        revision=self._Job.revision + 1,
                    )
                    .where(self._Job.id == job.id)
                    .execute()
                )
            return len(jobs)

    def _update_counters(
        self,
        job_id: str,
        previous: Dict[str, int],
        current: Dict[str, int],
    ) -> None:
        values: Dict[str, Any] = {"revision": self._Job.revision + 1}
        for name in current:
            delta = current[name] - previous[name]
            if delta:
                values[name] = getattr(self._Job, name) + delta
        self._Job.update(**values).where(self._Job.id == job_id).execute()

    def _row_to_summary(self, row: Model) -> CaptionJobSummary:
        return CaptionJobSummary(
            id=row.id,
            name=row.name,
            modelId=row.model_id,
            modelTitle=row.model_title,
            outputMode=row.output_mode,
            state=row.state,
            reviewMode=row.review_mode,
            detailsState=row.details_state,
            message=row.message,
            revision=row.revision,
            datasetId=row.dataset_id,
            logPath=row.log_path,
            total=row.total,
            processed=row.processed,
            succeeded=row.succeeded,
            failed=row.failed,
            skipped=row.skipped,
            conflicts=row.conflicts,
            written=row.written,
            createdAt=row.created_at,
            startedAt=row.started_at,
            endedAt=row.ended_at,
            errorMessage=row.error_message,
        )

    def _row_to_item(self, row: Model) -> CaptionJobItem:
        return CaptionJobItem(
            id=row.id,
            index=row.item_index,
            name=row.name,
            relativePath=row.relative_path,
            state=row.state,
            existingText=row.existing_text,
            generatedText=row.generated_text,
            finalText=row.final_text,
            tags=[CaptionTag.parse_obj(item) for item in json.loads(row.tags_json)],
            error=row.error,
            written=row.written,
            edited=row.edited,
            elapsedMs=row.elapsed_ms,
            thumbnailUrl=f"/api/v2/caption/jobs/{row.job_id}/items/{row.id}/thumbnail",
        )


def _counter_values(state: str, written: bool) -> Dict[str, int]:
    values = {
        "processed": int(state in PROCESSED_STATES),
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "conflicts": 0,
        "written": int(written),
    }
    counter = STATE_COUNTERS.get(state)
    if counter is not None:
        values[counter] = 1
    return values


def _item_stats(items: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    states = Counter(item.get("state", "pending") for item in items)
    return {
        "processed": sum(states[state] for state in PROCESSED_STATES),
        "succeeded": states["succeeded"],
        "failed": states["failed"],
        "skipped": states["skipped"],
        "conflicts": states["conflict"],
        "written": sum(int(bool(item.get("written"))) for item in items),
    }


def _json_dump(value: Any) -> Optional[str]:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def _chunks(values: Sequence[Any], size: int) -> List[Sequence[Any]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


@lru_cache(maxsize=1)
def get_caption_store() -> CaptionStore:
    return CaptionStore()
