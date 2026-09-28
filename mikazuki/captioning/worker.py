from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageOps

from .adapters import get_caption_model_manager
from .datasets import _read_caption_bytes
from .store import CaptionStore
from .writer import (
    CaptionWriteConflict,
    apply_affixes,
    atomic_write_caption,
    merge_caption,
)


def generate_job(job_id: str, store: Optional[CaptionStore] = None) -> None:
    store = store or CaptionStore(reconcile=False)
    job = store.get_job(job_id)
    request = store.get_request(job_id)
    source_root = store.get_source_root(job_id)
    if job is None or request is None or source_root is None:
        raise RuntimeError("Caption 任务或请求快照不存在")

    manager = get_caption_model_manager()
    runtime = request.runtime.copy(update={"keepModelLoaded": True})
    store.update_job(
        job_id,
        state="loading",
        startedAt=job.startedAt or _now(),
        message="正在加载模型并准备推理…",
        errorMessage=None,
    )

    try:
        rows = store.iter_internal_items(job_id, states=("pending",))
        inference_rows = []
        for row in rows:
            if _cancel_requested(store, job_id):
                _finish_canceled(store, job_id, request=request)
                return

            fingerprint = _json_value(row.existing_fingerprint)
            if (
                not request.output.stageBeforeWrite
                and request.output.conflictPolicy == "skip"
                and fingerprint is not None
            ):
                store.update_item(
                    job_id,
                    row.id,
                    state="skipped",
                    finalText=row.existing_text,
                    error="已有 Caption，按跳过策略未执行推理。",
                )
                continue
            inference_rows.append(row)

        first_prediction = True
        for batch_rows in _chunks(inference_rows, request.runtime.batchSize):
            if _cancel_requested(store, job_id):
                _finish_canceled(store, job_id, request=request)
                return

            prepared = []
            for row in batch_rows:
                store.update_item(job_id, row.id, state="running", error=None)
                started = time.perf_counter()
                try:
                    image_path = _validated_image_path(Path(row.image_path), source_root)
                    with Image.open(image_path) as source_image:
                        image = ImageOps.exif_transpose(source_image).convert("RGB")
                    prepared.append((row, image, started))
                except Exception as exc:
                    store.update_item(
                        job_id,
                        row.id,
                        state="failed",
                        error=str(exc),
                        elapsedMs=round((time.perf_counter() - started) * 1000),
                    )
                    print(f"[caption] {row.relative_path}: {exc}", flush=True)

            if not prepared:
                continue

            try:
                outcomes = _predict_batch_isolated(
                    manager,
                    [entry[1] for entry in prepared],
                    request=request,
                    runtime=runtime,
                )
            finally:
                for _, image, _ in prepared:
                    image.close()

            if first_prediction and any(prediction is not None for prediction, _ in outcomes):
                store.update_job(job_id, state="generating", message="正在生成 Caption…")
                first_prediction = False

            for (row, _, started), (prediction, prediction_error) in zip(prepared, outcomes):
                if _cancel_requested(store, job_id):
                    _finish_canceled(store, job_id, request=request)
                    return
                if prediction_error is not None or prediction is None:
                    error = prediction_error or RuntimeError("模型未返回 Caption 结果")
                    store.update_item(
                        job_id,
                        row.id,
                        state="failed",
                        error=str(error),
                        elapsedMs=round((time.perf_counter() - started) * 1000),
                    )
                    print(f"[caption] {row.relative_path}: {error}", flush=True)
                    continue

                try:
                    _save_prediction(
                        job_id=job_id,
                        store=store,
                        source_root=source_root,
                        request=request,
                        row=row,
                        prediction=prediction,
                        started=started,
                    )
                except CaptionWriteConflict as exc:
                    store.update_item(job_id, row.id, state="conflict", error=str(exc))
                except Exception as exc:
                    store.update_item(job_id, row.id, state="failed", error=str(exc))
                    print(f"[caption] {row.relative_path}: {exc}", flush=True)
    finally:
        manager.unload()

    current = store.get_job(job_id)
    if current is None:
        return
    if _cancel_requested(store, job_id):
        _finish_canceled(store, job_id, request=request)
        return
    if current.succeeded == 0 and current.skipped == 0:
        final_state = "failed"
        message = "没有图片成功生成 Caption。"
    elif request.output.stageBeforeWrite:
        final_state = "awaiting_review"
        message = "生成完成，请复核结果后提交写入。"
    elif current.failed or current.conflicts:
        final_state = "partial"
        message = "处理完成，但有部分图片失败或发生写入冲突。"
    else:
        final_state = "succeeded"
        message = "Caption 已生成并写入。"
    _compact_direct_details(store, job_id, request)
    store.update_job(job_id, state=final_state, endedAt=_now(), message=message)


def _chunks(rows: Sequence[Any], batch_size: int) -> Sequence[Sequence[Any]]:
    size = max(1, int(batch_size))
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def _predict_batch_isolated(
    manager: Any,
    images: Sequence[Image.Image],
    *,
    request: Any,
    runtime: Any,
) -> List[Tuple[Optional[Any], Optional[Exception]]]:
    try:
        predictions = manager.predict_batch(
            request.modelId,
            images,
            request.outputMode,
            request.params,
            request.prompt,
            request.postprocess,
            runtime,
        )
        if len(predictions) != len(images):
            raise RuntimeError(
                f"批量推理预期返回 {len(images)} 条结果，实际返回 {len(predictions)} 条"
            )
        return [(prediction, None) for prediction in predictions]
    except Exception as batch_error:
        if len(images) <= 1:
            return [(None, batch_error)]
        print(
            f"[caption] 批量推理失败，将逐图重试定位错误：{batch_error}",
            flush=True,
        )

    outcomes: List[Tuple[Optional[Any], Optional[Exception]]] = []
    for image in images:
        try:
            predictions = manager.predict_batch(
                request.modelId,
                [image],
                request.outputMode,
                request.params,
                request.prompt,
                request.postprocess,
                runtime,
            )
            if len(predictions) != 1:
                raise RuntimeError(
                    f"单图回退预期返回 1 条结果，实际返回 {len(predictions)} 条"
                )
            outcomes.append((predictions[0], None))
        except Exception as exc:
            outcomes.append((None, exc))
    return outcomes


def _save_prediction(
    *,
    job_id: str,
    store: CaptionStore,
    source_root: Path,
    request: Any,
    row: Any,
    prediction: Any,
    started: float,
) -> None:
    fingerprint = _json_value(row.existing_fingerprint)
    generated = prediction.text.strip()
    if request.outputMode != "tags":
        generated = apply_affixes(
            generated,
            request.postprocess.prefix,
            request.postprocess.suffix,
            request.postprocess.separator,
        )
    if not generated:
        raise RuntimeError("模型返回了空 Caption")

    _validate_merge_source(row, source_root, request.output.conflictPolicy)
    final_text, should_write = merge_caption(
        row.existing_text,
        generated,
        exists=fingerprint is not None,
        policy=request.output.conflictPolicy,
        separator=request.postprocess.separator,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    raw = prediction.raw if request.output.saveRawResult else None

    if request.output.stageBeforeWrite:
        store.update_item(
            job_id,
            row.id,
            state="succeeded",
            generatedText=generated,
            finalText=final_text,
            tags=prediction.tags,
            raw=raw,
            elapsedMs=elapsed_ms,
        )
        return

    if not should_write:
        store.update_item(
            job_id,
            row.id,
            state="skipped",
            generatedText=generated,
            finalText=final_text,
            tags=prediction.tags,
            raw=raw,
            elapsedMs=elapsed_ms,
        )
        return

    written_hash = atomic_write_caption(
        job_id=job_id,
        caption_path=Path(row.caption_path),
        allowed_root=source_root,
        relative_path=row.relative_path,
        text=final_text,
        expected_fingerprint=fingerprint,
        backup_existing=request.output.backupExisting,
    )
    store.update_item(
        job_id,
        row.id,
        state="succeeded",
        generatedText=generated,
        finalText=final_text,
        tags=prediction.tags,
        raw=raw,
        written=True,
        writtenHash=written_hash,
        elapsedMs=elapsed_ms,
    )


def commit_job(job_id: str, store: Optional[CaptionStore] = None) -> None:
    store = store or CaptionStore(reconcile=False)
    job = store.get_job(job_id)
    request = store.get_request(job_id)
    source_root = store.get_source_root(job_id)
    if job is None or request is None or source_root is None:
        raise RuntimeError("Caption 任务或请求快照不存在")

    commit = store.get_commit_request(job_id)
    policy = commit.conflictPolicy or request.output.conflictPolicy
    backup_existing = (
        request.output.backupExisting
        if commit.backupExisting is None
        else commit.backupExisting
    )
    store.update_job(
        job_id,
        state="committing",
        endedAt=None,
        message="正在原子写入已确认的 Caption…",
        errorMessage=None,
    )

    rows = store.iter_internal_items(
        job_id,
        states=("succeeded", "conflict", "failed"),
        item_ids=commit.itemIds,
    )
    for row in rows:
        if _cancel_requested(store, job_id):
            _finish_canceled(store, job_id)
            return
        if row.written:
            continue
        if row.state == "failed" and not row.edited:
            continue
        try:
            fingerprint = _json_value(row.existing_fingerprint)
            final_text = row.final_text
            should_write = True
            if not row.edited:
                _validate_merge_source(row, source_root, policy)
                final_text, should_write = merge_caption(
                    row.existing_text,
                    row.generated_text,
                    exists=fingerprint is not None,
                    policy=policy,
                    separator=request.postprocess.separator,
                )
            if not should_write:
                store.update_item(
                    job_id,
                    row.id,
                    state="skipped",
                    finalText=final_text,
                    error=None,
                )
                continue
            written_hash = atomic_write_caption(
                job_id=job_id,
                caption_path=Path(row.caption_path),
                allowed_root=source_root,
                relative_path=row.relative_path,
                text=final_text,
                expected_fingerprint=fingerprint,
                backup_existing=backup_existing,
            )
            store.update_item(
                job_id,
                row.id,
                state="succeeded",
                finalText=final_text,
                error=None,
                written=True,
                writtenHash=written_hash,
            )
        except CaptionWriteConflict as exc:
            store.update_item(job_id, row.id, state="conflict", error=str(exc))
        except Exception as exc:
            store.update_item(job_id, row.id, state="failed", error=str(exc))

    current = store.get_job(job_id)
    if current is None:
        return
    remaining_review = any(
        not row.written
        for row in store.iter_internal_items(job_id, states=("succeeded",))
    )
    if current.failed or current.conflicts:
        final_state = "partial"
        message = "已写入可提交项目，部分图片失败或发生外部修改冲突。"
    elif remaining_review:
        final_state = "awaiting_review"
        message = "已写入所选 Caption，仍有结果等待复核。"
    else:
        final_state = "succeeded"
        message = "已安全写入所选 Caption。"
    store.update_job(job_id, state=final_state, endedAt=_now(), message=message)


def _validate_merge_source(row: Any, source_root: Path, policy: str) -> None:
    # An undecodable caption has an empty text snapshot but nonempty bytes.
    # Policies that retain existing content must not mistake that for empty.
    fingerprint = _json_value(row.existing_fingerprint)
    if (
        policy not in {"append", "prepend", "fill_empty"}
        or row.existing_text
        or not fingerprint
        or not fingerprint.get("size")
    ):
        return
    caption_path = Path(row.caption_path).resolve()
    try:
        caption_path.relative_to(source_root.resolve())
    except ValueError as exc:
        raise CaptionWriteConflict("Caption 输出路径已离开获准的数据集目录。") from exc
    content = _read_caption_bytes(caption_path)
    if content is not None:
        try:
            content.decode("utf-8-sig")
        except UnicodeError as exc:
            raise CaptionWriteConflict(
                "现有 Caption 不是有效的 UTF-8，请先手动修复或明确选择覆盖策略。"
            ) from exc


def _validated_image_path(path: Path, source_root: Path) -> Path:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(source_root.resolve())
    except ValueError as exc:
        raise RuntimeError("图片路径已离开获准的数据集目录") from exc
    if not resolved.is_file():
        raise RuntimeError("图片文件不存在")
    return resolved


def _cancel_requested(store: CaptionStore, job_id: str) -> bool:
    job = store.get_job(job_id)
    return job is None or job.state in {"canceling", "canceled"}


def _finish_canceled(store: CaptionStore, job_id: str, *, request: Any = None) -> None:
    store.cancel_unfinished_items(job_id)
    if request is not None:
        _compact_direct_details(store, job_id, request)
    store.update_job(job_id, state="canceled", endedAt=_now(), message="任务已取消。")


def _compact_direct_details(store: CaptionStore, job_id: str, request: Any) -> None:
    if request.output.stageBeforeWrite or request.output.saveRawResult:
        return
    store.compact_direct_job_items(job_id)


def _json_value(value: Optional[str]) -> Optional[Dict[str, Any]]:
    if not value:
        return None
    payload = json.loads(value)
    return payload if isinstance(payload, dict) else None


def _now() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat(timespec="seconds")


def main() -> None:
    parser = argparse.ArgumentParser(description="Caption job worker")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--action", choices=("generate", "commit"), default="generate")
    args = parser.parse_args()
    if args.action == "commit":
        commit_job(args.job_id)
    else:
        generate_job(args.job_id)


if __name__ == "__main__":
    main()
