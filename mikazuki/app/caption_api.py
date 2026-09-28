from __future__ import annotations

import asyncio
import io
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from PIL import Image, ImageOps

from mikazuki.app.events import (
    SSE_HEADERS,
    format_sse as _sse,
    resolve_event_cursor as _event_cursor,
)
from mikazuki.captioning.adapters import get_caption_model_manager
from mikazuki.captioning.catalog import get_caption_model_catalog
from mikazuki.captioning.datasets import (
    CaptionDatasetConflictError,
    CaptionDatasetError,
    CaptionDatasetItemNotFoundError,
    CaptionDatasetNotFoundError,
    get_caption_dataset_registry,
)
from mikazuki.captioning.models import (
    CAPTION_TERMINAL_STATES,
    CaptionCommitRequest,
    CaptionDatasetInspectRequest,
    CaptionJobCreateRequest,
    CaptionJobItemUpdateRequest,
    CaptionJobListResponse,
    CaptionTextUpdateRequest,
)
from mikazuki.captioning.runner import CaptionJobValidationError, get_caption_runner
from mikazuki.captioning.store import CaptionStoreConflict, get_caption_store
from mikazuki.jobs.logs import tail_log


router = APIRouter()


@router.get("/models")
async def list_caption_models():
    return get_caption_model_catalog().response()


@router.post("/models/unload")
async def unload_caption_models():
    await asyncio.to_thread(get_caption_model_manager().unload)
    return {"status": "ok"}


@router.post("/datasets/inspect")
async def inspect_caption_dataset(request: CaptionDatasetInspectRequest):
    try:
        return await asyncio.to_thread(get_caption_dataset_registry().inspect, request)
    except CaptionDatasetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/datasets/{dataset_id}/items")
async def list_caption_dataset_items(
    dataset_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    query: str = Query(default="", max_length=200),
    caption_state: str = Query(default="all", regex="^(all|with|without|error)$"),
):
    try:
        return await asyncio.to_thread(
            get_caption_dataset_registry().list_items,
            dataset_id,
            offset=offset,
            limit=limit,
            query=query,
            caption_state=caption_state,
        )
    except CaptionDatasetNotFoundError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except CaptionDatasetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/datasets/{dataset_id}/items/{item_id}/thumbnail")
async def get_caption_dataset_thumbnail(
    dataset_id: str,
    item_id: str,
    size: int = Query(default=512, ge=32, le=2048),
):
    try:
        content = await asyncio.to_thread(
            get_caption_dataset_registry().thumbnail,
            dataset_id,
            item_id,
            max_size=size,
        )
    except CaptionDatasetNotFoundError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except CaptionDatasetItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaptionDatasetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=content, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@router.put("/datasets/{dataset_id}/items/{item_id}/caption")
async def save_caption_dataset_item(
    dataset_id: str,
    item_id: str,
    request: CaptionTextUpdateRequest,
):
    try:
        return await asyncio.to_thread(
            get_caption_dataset_registry().save_caption,
            dataset_id,
            item_id,
            request,
        )
    except CaptionDatasetNotFoundError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except CaptionDatasetItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaptionDatasetConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CaptionDatasetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/jobs")
async def create_caption_job(request: CaptionJobCreateRequest):
    try:
        return await get_caption_runner().start_job(request)
    except CaptionJobValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/jobs")
async def list_caption_jobs(limit: int = Query(default=50, ge=1, le=200)):
    jobs = await asyncio.to_thread(get_caption_store().list_jobs, limit)
    return CaptionJobListResponse(jobs=jobs)


@router.get("/jobs/{job_id}")
async def get_caption_job(job_id: str):
    job = await asyncio.to_thread(get_caption_store().get_job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Caption 任务不存在")
    return job


@router.get("/jobs/{job_id}/items")
async def list_caption_job_items(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    state: Optional[str] = Query(
        default=None,
        regex="^(pending|running|succeeded|failed|skipped|conflict|canceled)$",
    ),
    query: str = Query(default="", max_length=200),
):
    if get_caption_store().get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Caption 任务不存在")
    return await asyncio.to_thread(
        get_caption_store().list_items,
        job_id,
        offset=offset,
        limit=limit,
        state=state,
        query=query,
    )


@router.get("/jobs/{job_id}/items/{item_id}/thumbnail")
async def get_caption_job_item_thumbnail(
    job_id: str,
    item_id: str,
    size: int = Query(default=512, ge=32, le=2048),
):
    store = get_caption_store()
    row = await asyncio.to_thread(store.get_internal_item, job_id, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Caption 结果不存在")
    source_root = store.get_source_root(job_id)
    if source_root is None:
        raise HTTPException(status_code=404, detail="Caption 数据集根目录不存在")
    try:
        content = await asyncio.to_thread(
            _thumbnail_for_job_item,
            Path(row.image_path),
            source_root,
            size,
        )
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=400, detail=f"无法读取缩略图：{exc}") from exc
    return Response(content=content, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@router.patch("/jobs/{job_id}/items/{item_id}")
async def edit_caption_job_item(
    job_id: str,
    item_id: str,
    request: CaptionJobItemUpdateRequest,
):
    try:
        return await asyncio.to_thread(
            get_caption_store().edit_review_item,
            job_id,
            item_id,
            request.finalText,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Caption 任务或结果不存在") from exc
    except CaptionStoreConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/commit")
async def commit_caption_job(job_id: str, request: CaptionCommitRequest):
    try:
        return await get_caption_runner().commit_job(job_id, request)
    except CaptionJobValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/cancel")
async def cancel_caption_job(job_id: str):
    job = get_caption_runner().cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Caption 任务不存在")
    return job


@router.get("/jobs/{job_id}/logs")
async def get_caption_job_logs(
    job_id: str,
    tail: int = Query(default=500, ge=0, le=5000),
):
    job = get_caption_store().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Caption 任务不存在")
    cursor, lines = await asyncio.to_thread(tail_log, job.logPath, tail=tail)
    return {"jobId": job_id, "cursor": cursor, "lines": lines}


@router.get("/jobs/{job_id}/events")
async def get_caption_job_events(
    job_id: str,
    after: int = Query(default=0, ge=0),
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
):
    if get_caption_store().get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Caption 任务不存在")
    cursor = _event_cursor(after, last_event_id)

    async def stream():
        current = cursor
        last_state = None
        last_heartbeat = time.monotonic()
        first = True
        while True:
            job = get_caption_store().get_job(job_id)
            if job is None:
                yield _sse("state", {"id": job_id, "state": "missing"})
                break
            if first or job.revision > current:
                current = job.revision
                payload = job.dict()
                yield _sse("progress", payload, event_id=current)
                if job.state != last_state:
                    yield _sse("state", payload)
                    last_state = job.state
                first = False
            if job.state in CAPTION_TERMINAL_STATES:
                break
            now = time.monotonic()
            if now - last_heartbeat >= 15:
                yield _sse("heartbeat", {"id": job_id, "revision": current})
                last_heartbeat = now
            await asyncio.sleep(0.75)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


def _thumbnail_for_job_item(path: Path, source_root: Path, size: int) -> bytes:
    resolved = path.resolve(strict=True)
    resolved.relative_to(source_root.resolve())
    with Image.open(resolved) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=86, optimize=True)
        return output.getvalue()
