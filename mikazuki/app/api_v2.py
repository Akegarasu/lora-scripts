import asyncio
import json
import os
import platform
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from mikazuki.catalog import get_catalog_service
from mikazuki.compiler import TrainDraft, compile_draft
from mikazuki.frontend_release import release_version_payload
from mikazuki.jobs import get_job_runner, get_job_store
from mikazuki.jobs.logs import read_log_from, tail_log
from mikazuki.jobs.metrics import get_job_metrics_service, parse_tag_filter
from mikazuki.jobs.models import TERMINAL_STATES
from mikazuki.storage.files import (
    IMAGE_EXTENSIONS,
    IMAGE_MEDIA_TYPES,
    BrowsePathError,
    FileManagerLaunchError,
    FileManagerUnavailableError,
    SafetensorsMetadataError,
    UnsupportedFileTypeError,
    file_manager_capability,
    list_files,
    read_safetensors_metadata,
    resolve_output_file,
    show_output_in_file_manager,
)

router = APIRouter()


@router.get("/health")
async def health():
    release = release_version_payload()
    return {
        "status": "ok",
        **release,
        "python": platform.python_version(),
        "devMode": os.environ.get("MIKAZUKI_DEV", "0") == "1",
    }


@router.get("/trainers")
async def list_trainers():
    catalog = get_catalog_service()
    return {
        "trainers": [item.dict() for item in catalog.list_trainers()],
        "manifestHash": catalog.manifest_hash,
    }


@router.get("/trainers/{trainer_id}")
async def get_trainer(trainer_id: str):
    trainer = get_catalog_service().get_trainer(trainer_id)
    if trainer is None:
        raise HTTPException(status_code=404, detail="trainer not found")
    return trainer.dict(exclude_none=True)


@router.get("/trainers/{trainer_id}/params")
async def get_trainer_params(
    trainer_id: str,
    view: str = Query(default="recommended", regex="^(required|recommended|advanced|all)$"),
):
    catalog = get_catalog_service()
    trainer = catalog.get_trainer(trainer_id)
    if trainer is None:
        raise HTTPException(status_code=404, detail="trainer not found")
    return {
        "trainerId": trainer_id,
        "view": view,
        "groups": catalog.get_param_groups(trainer_id, view=view),
        "manifestHash": catalog.manifest_hash,
    }


@router.post("/compile")
async def compile_train_draft(
    draft: TrainDraft,
    persist: bool = Query(default=True),
    validate_paths: bool = Query(default=True),
):
    result = compile_draft(draft, persist=persist, validate_paths=validate_paths)
    if result.errors and any(item.code == "trainer.not_found" for item in result.errors):
        raise HTTPException(status_code=404, detail=result.errors[0].message)
    return result.dict(exclude_none=True)


@router.post("/jobs")
async def create_job(
    draft: TrainDraft,
    validate_paths: bool = Query(default=True),
):
    result = await get_job_runner().start_job(draft, validate_paths=validate_paths)
    payload = result.dict(exclude_none=True)
    if result.compile.errors:
        return JSONResponse(status_code=400, content=payload)
    return payload


@router.get("/jobs")
async def list_jobs(limit: int = Query(default=50, ge=1, le=200)):
    jobs = get_job_store().list_jobs(limit=limit)
    return {"jobs": [job.dict(exclude_none=True) for job in jobs]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = get_job_store().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.dict(exclude_none=True)


@router.get("/jobs/{job_id}/logs")
async def get_job_logs(job_id: str, tail: int = Query(default=500, ge=0, le=5000)):
    job = get_job_store().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    cursor, lines = tail_log(job.logPath or "", tail=tail)
    return {"jobId": job_id, "cursor": cursor, "lines": lines}


@router.get("/jobs/{job_id}/metrics")
async def get_job_metrics(
    job_id: str,
    cursor: int = Query(default=0, ge=0),
    max_points: int = Query(default=2000, ge=2, le=20000),
    tags: Optional[str] = Query(default=None),
):
    job = get_job_store().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return await asyncio.to_thread(
        get_job_metrics_service().snapshot,
        job,
        cursor=cursor,
        max_points=max_points,
        tags=parse_tag_filter(tags),
    )


@router.get("/jobs/{job_id}/metric-events")
async def get_job_metric_events(
    job_id: str,
    cursor: Optional[int] = Query(default=None, ge=0),
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
):
    if get_job_store().get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")

    initial_cursor = _resolve_metric_cursor(cursor, last_event_id)

    async def metric_event_stream():
        current_cursor = initial_cursor
        last_state = None
        first_snapshot = True
        last_heartbeat = time.monotonic()

        while True:
            job = get_job_store().get_job(job_id)
            if job is None:
                yield _format_sse("state", {"jobId": job_id, "state": "missing"})
                break

            snapshot = await asyncio.to_thread(
                get_job_metrics_service().snapshot,
                job,
                cursor=current_cursor,
                max_points=2000,
            )
            if first_snapshot or snapshot.get("pointCount", 0) > 0:
                current_cursor = int(snapshot.get("cursor", current_cursor))
                yield _format_sse("metric", snapshot, event_id=current_cursor)
                first_snapshot = False

            if job.state != last_state:
                yield _format_sse(
                    "state",
                    {
                        "jobId": job.id,
                        "state": job.state,
                        "cursor": current_cursor,
                        "endedAt": job.endedAt,
                        "exitCode": job.exitCode,
                        "errorMessage": job.errorMessage,
                    },
                )
                last_state = job.state

            if job.state in TERMINAL_STATES:
                break

            now = time.monotonic()
            if now - last_heartbeat >= 15:
                yield _format_sse(
                    "heartbeat",
                    {"jobId": job.id, "cursor": current_cursor, "timestamp": time.time()},
                )
                last_heartbeat = now
            await asyncio.sleep(1)

    return StreamingResponse(
        metric_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/jobs/{job_id}/events")
async def get_job_events(job_id: str):
    if get_job_store().get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def event_stream():
        cursor = 0
        last_state = None
        while True:
            job = get_job_store().get_job(job_id)
            if job is None:
                yield "event: state\ndata: {\"state\":\"missing\"}\n\n"
                break

            if job.state != last_state:
                payload = json.dumps(job.dict(exclude_none=True), ensure_ascii=False)
                yield f"event: state\ndata: {payload}\n\n"
                last_state = job.state

            cursor, lines = read_log_from(job.logPath or "", cursor=cursor)
            for line in lines:
                payload = json.dumps({"line": line, "cursor": cursor}, ensure_ascii=False)
                yield f"event: log\ndata: {payload}\n\n"

            if job.state in TERMINAL_STATES:
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _resolve_metric_cursor(
    cursor: Optional[int],
    last_event_id: Optional[str],
) -> int:
    # EventSource retains the original query string when it reconnects but
    # advances Last-Event-ID after every received metric frame. Prefer that
    # header whenever it is valid to avoid replaying from the initial cursor.
    if last_event_id is not None:
        try:
            resumed_cursor = int(last_event_id)
            if resumed_cursor >= 0:
                return resumed_cursor
        except (TypeError, ValueError):
            pass
    if cursor is not None:
        return max(0, cursor)
    return 0


def _format_sse(event: str, payload, *, event_id: Optional[int] = None) -> str:
    parts = []
    if event_id is not None:
        parts.append(f"id: {event_id}")
    parts.append(f"event: {event}")
    parts.append(f"data: {json.dumps(payload, ensure_ascii=False, allow_nan=False)}")
    return "\n".join(parts) + "\n\n"


@router.post("/jobs/{job_id}/terminate")
async def terminate_job(job_id: str):
    job = get_job_runner().terminate_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.dict(exclude_none=True)


@router.get("/files")
async def browse_files(
    kind: str = Query(default="file"),
    root: str = Query(default="workspace"),
    path: str = Query(default=""),
):
    try:
        items = list_files(kind=kind, root=root, path=path or None)
    except BrowsePathError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"items": [item.dict() for item in items]}


@router.get("/files/file-manager-capability")
async def get_file_manager_capability():
    return file_manager_capability()


@router.post("/files/reveal")
async def reveal_output_path(path: str = Query(min_length=1)):
    try:
        resolved = show_output_in_file_manager(path)
    except BrowsePathError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except FileManagerUnavailableError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except FileManagerLaunchError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"status": "opened", "path": str(resolved).replace("\\", "/")}


@router.get("/files/content")
async def read_output_file(path: str = Query(min_length=1)):
    try:
        resolved = resolve_output_file(path, extensions=IMAGE_EXTENSIONS)
    except BrowsePathError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except UnsupportedFileTypeError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error

    media_type = IMAGE_MEDIA_TYPES[resolved.suffix.lower()]
    return FileResponse(resolved, media_type=media_type)


@router.get("/files/safetensors-metadata")
async def get_safetensors_metadata(path: str = Query(min_length=1)):
    try:
        return read_safetensors_metadata(path)
    except BrowsePathError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except UnsupportedFileTypeError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except SafetensorsMetadataError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/devices/gpus")
async def list_gpus():
    import torch

    if not torch.cuda.is_available():
        return {"gpus": [], "error": "torch cuda is not available"}

    gpus = []
    for index in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(index)
        free, total = torch.cuda.mem_get_info(index)
        gpus.append(
            {
                "id": str(index),
                "name": torch.cuda.get_device_name(index),
                "vramTotal": int(total or props.total_memory),
                "vramFree": int(free),
            }
        )
    return {"gpus": gpus}
