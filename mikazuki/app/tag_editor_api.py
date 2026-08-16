from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import Response

from mikazuki.captioning.datasets import CaptionDatasetError
from mikazuki.tag_editor.models import (
    TagEditorApplyRequest,
    TagEditorInspectRequest,
    TagEditorPreviewRequest,
)
from mikazuki.tag_editor.service import (
    TagEditorConflictError,
    TagEditorNotFoundError,
    TagEditorValidationError,
    get_tag_editor_service,
)


router = APIRouter()


@router.post("/datasets/inspect")
async def inspect_tag_editor_dataset(request: TagEditorInspectRequest):
    try:
        return await asyncio.to_thread(get_tag_editor_service().inspect, request)
    except TagEditorConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (CaptionDatasetError, TagEditorValidationError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/datasets/{dataset_id}/items")
async def list_tag_editor_items(
    dataset_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    query: str = Query(default="", max_length=200),
    state: str = Query(default="all", regex="^(all|with|missing|empty|errors|duplicate)$"),
    sort: str = Query(
        default="path_asc",
        regex="^(path_asc|path_desc|caption_asc|modified_desc)$",
    ),
):
    try:
        return await asyncio.to_thread(
            get_tag_editor_service().list_items,
            dataset_id,
            offset=offset,
            limit=limit,
            query=query,
            state=state,
            sort=sort,
        )
    except TagEditorNotFoundError as error:
        raise HTTPException(status_code=410, detail=str(error)) from error
    except TagEditorValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/datasets/{dataset_id}/items/{item_id}")
async def get_tag_editor_item(dataset_id: str, item_id: str):
    try:
        return await asyncio.to_thread(get_tag_editor_service().get_item, dataset_id, item_id)
    except TagEditorNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/datasets/{dataset_id}/items/{item_id}/thumbnail")
async def get_tag_editor_thumbnail(
    dataset_id: str,
    item_id: str,
    size: int = Query(default=512, ge=32, le=2048),
):
    try:
        content = await asyncio.to_thread(
            get_tag_editor_service().thumbnail,
            dataset_id,
            item_id,
            size=size,
        )
    except TagEditorNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except CaptionDatasetError as error:
        raise HTTPException(status_code=400, detail="无法安全生成该图片的缩略图") from error
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/datasets/{dataset_id}/tag-suggestions")
async def suggest_tag_editor_tags(
    dataset_id: str,
    query: str = Query(default="", max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
):
    try:
        return await asyncio.to_thread(
            get_tag_editor_service().suggest_tags,
            dataset_id,
            query=query,
            limit=limit,
        )
    except TagEditorNotFoundError as error:
        raise HTTPException(status_code=410, detail=str(error)) from error


@router.post("/datasets/{dataset_id}/changes/preview")
async def preview_tag_editor_changes(dataset_id: str, request: TagEditorPreviewRequest):
    try:
        return await asyncio.to_thread(get_tag_editor_service().preview, dataset_id, request)
    except TagEditorNotFoundError as error:
        raise HTTPException(status_code=410, detail=str(error)) from error
    except TagEditorConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except TagEditorValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/datasets/{dataset_id}/changes/apply")
async def apply_tag_editor_changes(
    dataset_id: str,
    request: TagEditorApplyRequest,
    background_tasks: BackgroundTasks,
):
    service = get_tag_editor_service()
    try:
        summary = await asyncio.to_thread(service.queue_apply, dataset_id, request)
    except TagEditorNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except TagEditorConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except TagEditorValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    background_tasks.add_task(service.apply_change_set, summary.id)
    return summary


@router.get("/changes")
async def list_tag_editor_changes(limit: int = Query(default=20, ge=1, le=100)):
    return await asyncio.to_thread(get_tag_editor_service().list_changes, limit)


@router.get("/changes/{change_set_id}")
async def get_tag_editor_change(change_set_id: str):
    try:
        return await asyncio.to_thread(get_tag_editor_service().get_change, change_set_id)
    except TagEditorNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/changes/{change_set_id}/results")
async def list_tag_editor_change_results(
    change_set_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return await asyncio.to_thread(
            get_tag_editor_service().list_change_results,
            change_set_id,
            offset=offset,
            limit=limit,
        )
    except TagEditorNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/changes/{change_set_id}/rollback")
async def rollback_tag_editor_change(
    change_set_id: str,
    background_tasks: BackgroundTasks,
):
    service = get_tag_editor_service()
    try:
        summary = await asyncio.to_thread(service.queue_rollback, change_set_id)
    except TagEditorNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except TagEditorConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    background_tasks.add_task(service.rollback_change_set, change_set_id)
    return summary
