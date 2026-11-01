from __future__ import annotations

from datetime import datetime
from typing import Optional

from .models import CaptionJobCreateRequest
from .store import CaptionStore


def compact_job_details(
    store: CaptionStore,
    job_id: str,
    request: Optional[CaptionJobCreateRequest] = None,
) -> None:
    """Retain review/raw results; discard successful direct-write payloads."""
    if request is None:
        request = store.get_request(job_id)
    if request is None or request.output.stageBeforeWrite or request.output.saveRawResult:
        return
    store.compact_direct_job_items(job_id)


def finish_canceled_job(
    store: CaptionStore,
    job_id: str,
    *,
    compact_details: bool,
    request: Optional[CaptionJobCreateRequest] = None,
) -> None:
    """Finish item cleanup before publishing the terminal state to observers.

    Generation and the process supervisor compact direct-write details. Review
    commits retain their results, including when canceled between item writes.
    Keep the ledger operations separate and ordered as in normal completion.
    """
    store.cancel_unfinished_items(job_id)
    if compact_details:
        compact_job_details(store, job_id, request)
    store.update_job(
        job_id,
        state="canceled",
        endedAt=datetime.now().astimezone().isoformat(timespec="seconds"),
        message="任务已取消。",
    )
