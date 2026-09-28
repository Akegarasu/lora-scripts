from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from mikazuki.jobs.resources import get_gpu_lease
from mikazuki.storage.paths import app_root
from mikazuki.tasks import kill_proc_tree

from .catalog import CaptionModelCatalog, get_caption_model_catalog
from .datasets import (
    CaptionDatasetError,
    CaptionDatasetRegistry,
    get_caption_dataset_registry,
)
from .models import (
    CAPTION_TERMINAL_STATES,
    CaptionCommitRequest,
    CaptionJobCreateRequest,
    CaptionJobSummary,
)
from .store import CaptionStore, CaptionStoreConflict, get_caption_store


class CaptionJobValidationError(ValueError):
    pass


class CaptionRunner:
    """Queues isolated caption worker processes and shares the training GPU lease."""

    def __init__(
        self,
        *,
        store: Optional[CaptionStore] = None,
        datasets: Optional[CaptionDatasetRegistry] = None,
        catalog: Optional[CaptionModelCatalog] = None,
    ) -> None:
        self.store = store or get_caption_store()
        self.datasets = datasets or get_caption_dataset_registry()
        self.catalog = catalog or get_caption_model_catalog()
        self._gpu_lease = get_gpu_lease()
        self._processes: Dict[str, subprocess.Popen] = {}
        self._process_lock = threading.RLock()
        self._tasks: set[asyncio.Task] = set()

    async def start_job(self, request: CaptionJobCreateRequest) -> CaptionJobSummary:
        model = self.catalog.get(request.modelId)
        if model is None:
            raise CaptionJobValidationError(f"Caption 模型不存在：{request.modelId}")
        if model.status in {"unavailable", "misconfigured"}:
            raise CaptionJobValidationError(model.statusReason or "Caption 模型当前不可用")
        if request.outputMode not in model.outputModes:
            raise CaptionJobValidationError(
                f"模型 {request.modelId} 不支持 {request.outputMode} 输出"
            )
        if not model.capabilities.devices:
            raise CaptionJobValidationError(model.statusReason or "Caption 模型没有可用的推理设备")
        if (
            request.runtime.device != "auto"
            and request.runtime.device not in model.capabilities.devices
        ):
            raise CaptionJobValidationError(
                f"模型 {request.modelId} 当前不支持 {request.runtime.device} 推理"
            )
        if request.runtime.device == "cpu" and request.runtime.dtype == "float16":
            raise CaptionJobValidationError("CPU Caption 推理不能使用 float16")
        if not model.capabilities.batch and request.runtime.batchSize != 1:
            raise CaptionJobValidationError("该模型不支持批量推理，请将批次大小设为 1")
        if (
            model.capabilities.prompt
            and request.prompt.language not in model.capabilities.languages
        ):
            supported = "、".join(model.capabilities.languages)
            raise CaptionJobValidationError(f"该模型仅支持以下输出语言：{supported}")
        try:
            validated_params = self.catalog.validate_params(request.modelId, request.params)
            if validated_params.get("minPixels", 0) > validated_params.get("maxPixels", float("inf")):
                raise ValueError("最小视觉像素不能高于最大视觉像素")
            request = request.copy(update={"params": validated_params})
        except ValueError as exc:
            raise CaptionJobValidationError(str(exc)) from exc

        try:
            snapshot = self.datasets.get_snapshot(request.datasetId)
            records = self.datasets.select_records(request.datasetId, request.itemIds)
        except CaptionDatasetError as exc:
            raise CaptionJobValidationError(str(exc)) from exc
        if not records:
            raise CaptionJobValidationError("没有选择可处理的图片")

        job_id = f"caption_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        log_path = app_root() / "logs" / "caption-jobs" / f"{job_id}.log"
        summary = CaptionJobSummary(
            id=job_id,
            name=request.name,
            modelId=model.id,
            modelTitle=model.title,
            outputMode=request.outputMode,
            state="queued",
            reviewMode=request.output.stageBeforeWrite,
            message="任务已进入 Caption 队列。",
            revision=1,
            datasetId=request.datasetId,
            logPath=_display_path(log_path),
            total=len(records),
            createdAt=_now(),
        )
        items = [
            {
                "id": record.id,
                "name": record.name,
                "relative_path": record.relative_path,
                "image_path": record.image_path,
                "caption_path": record.caption_path,
                "existing_text": record.existing_text,
                "existing_fingerprint": record.fingerprint,
                "source_root": snapshot.source_root,
                "state": "pending" if record.writable else "failed",
                "error": record.error,
            }
            for record in records
        ]
        created = self.store.create_job(summary, request, items)
        self._schedule(job_id, action="generate", use_gpu=request.runtime.device != "cpu")
        return created

    async def commit_job(
        self,
        job_id: str,
        request: CaptionCommitRequest,
    ) -> CaptionJobSummary:
        with self._process_lock:
            job = self.store.get_job(job_id)
            if job is None:
                raise CaptionJobValidationError("Caption 任务不存在")
            process = self._processes.get(job_id)
            if process is not None and process.poll() is None:
                raise CaptionJobValidationError("任务仍在运行")
            try:
                updated = self.store.queue_commit(job_id, request)
            except CaptionStoreConflict as exc:
                raise CaptionJobValidationError(str(exc)) from exc
        self._schedule(job_id, action="commit", use_gpu=False)
        return updated

    def cancel_job(self, job_id: str) -> Optional[CaptionJobSummary]:
        with self._process_lock:
            job = self.store.get_job(job_id)
            if job is None:
                return None
            if job.state in CAPTION_TERMINAL_STATES:
                return job
            self.store.update_job(job_id, state="canceling", message="正在取消 Caption 任务…")
            process = self._processes.get(job_id)

        if process is not None and process.poll() is None:
            try:
                kill_proc_tree(process.pid, including_parent=True)
            except Exception as exc:
                self.store.update_job(job_id, errorMessage=str(exc))
        else:
            self.store.cancel_unfinished_items(job_id)
            self._compact_direct_details(job_id)
            self.store.update_job(job_id, state="canceled", endedAt=_now(), message="任务已取消。")
        return self.store.get_job(job_id)

    def _schedule(self, job_id: str, *, action: str, use_gpu: bool) -> None:
        task = asyncio.create_task(
            asyncio.to_thread(self._run_process, job_id, action, use_gpu)
        )
        self._tasks.add(task)
        task.add_done_callback(lambda completed: self._finish_task(job_id, completed))

    def _finish_task(self, job_id: str, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self.store.update_job(
                job_id,
                state="failed",
                endedAt=_now(),
                message="Caption worker 运行失败。",
                errorMessage=str(error),
            )

    def _run_process(self, job_id: str, action: str, use_gpu: bool) -> None:
        acquired = False
        process: Optional[subprocess.Popen] = None
        if use_gpu:
            acquired = self._gpu_lease.acquire(blocking=False)
            if not acquired:
                self.store.update_job(job_id, message="正在等待 GPU 资源…")
                self._gpu_lease.acquire()
                acquired = True

        try:
            current = self.store.get_job(job_id)
            if current is None:
                return
            if current.state in {"canceling", "canceled"}:
                self.store.cancel_unfinished_items(job_id)
                self._compact_direct_details(job_id)
                self.store.update_job(job_id, state="canceled", endedAt=_now(), message="任务已取消。")
                return

            log_path = Path(current.logPath) if current.logPath else app_root() / "logs" / "caption-jobs" / f"{job_id}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                sys.executable,
                "-m",
                "mikazuki.captioning.worker",
                "--job-id",
                job_id,
                "--action",
                action,
            ]
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            with log_path.open("a", encoding="utf-8", errors="replace") as log_file:
                log_file.write(f"$ {' '.join(command)}\n")
                log_file.flush()
                with self._process_lock:
                    latest = self.store.get_job(job_id)
                    if latest is None or latest.state in {"canceling", "canceled"}:
                        return
                    process = subprocess.Popen(
                        command,
                        cwd=str(app_root()),
                        env=env,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                    self._processes[job_id] = process
                exit_code = process.wait()

            latest = self.store.get_job(job_id)
            if latest is None:
                return
            if latest.state == "canceling":
                self.store.cancel_unfinished_items(job_id)
                self._compact_direct_details(job_id)
                self.store.update_job(job_id, state="canceled", endedAt=_now(), message="任务已取消。")
            elif exit_code != 0 and latest.state not in CAPTION_TERMINAL_STATES:
                self.store.update_job(
                    job_id,
                    state="failed",
                    endedAt=_now(),
                    message="Caption worker 异常退出。",
                    errorMessage=f"worker exit code: {exit_code}",
                )
        finally:
            try:
                if process is not None and process.poll() is None:
                    kill_proc_tree(process.pid, including_parent=True)
                    process.wait()
            finally:
                with self._process_lock:
                    self._processes.pop(job_id, None)
                if acquired:
                    self._gpu_lease.release()

    def _compact_direct_details(self, job_id: str) -> None:
        request = self.store.get_request(job_id)
        if request is None:
            return
        if request.output.stageBeforeWrite or request.output.saveRawResult:
            return
        self.store.compact_direct_job_items(job_id)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _display_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


@lru_cache(maxsize=1)
def get_caption_runner() -> CaptionRunner:
    return CaptionRunner()
