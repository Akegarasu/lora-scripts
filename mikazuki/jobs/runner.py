import asyncio
import os
import subprocess
import sys
import threading
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from mikazuki.compiler import TrainDraft, compile_draft
from mikazuki.storage.paths import app_root, jobs_log_dir
from mikazuki.tasks import kill_proc_tree

from .models import JobRecord, JobStartResult, TERMINAL_STATES
from .resources import get_gpu_lease
from .store import JobStore, get_job_store


class JobRunner:
    def __init__(self, store: Optional[JobStore] = None, max_concurrent: int = 1) -> None:
        self.store = store or get_job_store()
        self.max_concurrent = max_concurrent
        self._slot = get_gpu_lease(max_concurrent)
        self._processes: Dict[str, subprocess.Popen] = {}
        self._process_lock = threading.Lock()
        self._tasks: set[asyncio.Task] = set()

    async def start_job(self, draft: TrainDraft, *, validate_paths: bool = True) -> JobStartResult:
        compiled = compile_draft(draft, persist=True, validate_paths=validate_paths)
        if compiled.errors or compiled.runId is None:
            return JobStartResult(compile=compiled)

        created_at = _now()
        job_id = f"job_{compiled.runId}"
        log_path = jobs_log_dir() / f"{job_id}.log"
        artifacts = compiled.artifacts.dict(exclude_none=True)
        env = self._build_env(draft)

        job = JobRecord(
            id=job_id,
            runId=compiled.runId,
            trainerId=draft.trainerId,
            name=draft.name,
            state="queued",
            command=compiled.command,
            env=self._public_env(env),
            artifacts=artifacts,
            logPath=_display_path(log_path),
            createdAt=created_at,
        )
        self.store.create_job(job)
        task = asyncio.create_task(
            asyncio.to_thread(self._run_sync, job_id, compiled.command, env, log_path)
        )
        self._tasks.add(task)
        task.add_done_callback(lambda completed: self._finish_task(job_id, completed))
        return JobStartResult(job=job, compile=compiled)

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
                errorMessage=str(error),
            )

    def terminate_job(self, job_id: str) -> Optional[JobRecord]:
        with self._process_lock:
            job = self.store.get_job(job_id)
            if job is None:
                return None
            if job.state in TERMINAL_STATES:
                return job

            self.store.update_job(job_id, state="terminating")
            process = self._processes.get(job_id)

        if process is not None and process.poll() is None:
            try:
                kill_proc_tree(process.pid, including_parent=True)
            except Exception as exc:
                self.store.update_job(job_id, errorMessage=str(exc))
        return self.store.get_job(job_id)

    def _run_sync(self, job_id: str, command: list, env: Dict[str, str], log_path: Path) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        acquired = self._slot.acquire(blocking=False)
        if not acquired:
            with self._process_lock:
                current = self.store.get_job(job_id)
                if current is not None and current.state not in TERMINAL_STATES | {"terminating"}:
                    self.store.update_job(job_id, state="queued")
            self._slot.acquire()

        try:
            with self._process_lock:
                if self._finish_if_not_startable(job_id):
                    return

            with log_path.open("a", encoding="utf-8", errors="replace") as log_file:
                log_file.write(f"$ {' '.join(command)}\n")
                log_file.flush()

                process = None
                try:
                    with self._process_lock:
                        if self._finish_if_not_startable(job_id):
                            log_file.write("[runner] job canceled before process start\n")
                            return
                        process = subprocess.Popen(
                            command,
                            cwd=str(app_root()),
                            env=env,
                            stdout=log_file,
                            stderr=subprocess.STDOUT,
                        )
                        self._processes[job_id] = process
                        self.store.update_job(job_id, state="running", startedAt=_now())

                    exit_code = process.wait()
                    current = self.store.get_job(job_id)
                    if current is not None and current.state == "terminating":
                        final_state = "terminated"
                    else:
                        final_state = "succeeded" if exit_code == 0 else "failed"
                    self.store.update_job(job_id, state=final_state, endedAt=_now(), exitCode=exit_code)
                except Exception as exc:
                    error = str(exc)
                    if process is not None and process.poll() is None:
                        try:
                            kill_proc_tree(process.pid, including_parent=True)
                            process.wait()
                        except Exception as cleanup_error:
                            error = f"{error}; process cleanup failed: {cleanup_error}"
                    self.store.update_job(job_id, state="failed", endedAt=_now(), errorMessage=error)
                    log_file.write(f"\n[runner] {error}\n")
        finally:
            with self._process_lock:
                self._processes.pop(job_id, None)
            self._slot.release()

    def _finish_if_not_startable(self, job_id: str) -> bool:
        current = self.store.get_job(job_id)
        if current is None:
            return True
        if current.state not in TERMINAL_STATES | {"terminating"}:
            return False

        if current.state == "terminating":
            self.store.update_job(job_id, state="terminated", endedAt=current.endedAt or _now())
        elif current.state == "canceled" and current.endedAt is None:
            self.store.update_job(job_id, state="canceled", endedAt=_now())
        return True

    def _build_env(self, draft: TrainDraft) -> Dict[str, str]:
        env = os.environ.copy()
        env["ACCELERATE_DISABLE_RICH"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONWARNINGS"] = "ignore::FutureWarning,ignore::UserWarning"
        if draft.runtime.gpuIds:
            env["CUDA_VISIBLE_DEVICES"] = ",".join(draft.runtime.gpuIds)
        if sys.platform == "win32" and len(draft.runtime.gpuIds) > 1:
            env["USE_LIBUV"] = "0"
        return env

    def _public_env(self, env: Dict[str, str]) -> Dict[str, str]:
        keys = ["CUDA_VISIBLE_DEVICES", "ACCELERATE_DISABLE_RICH", "PYTHONUNBUFFERED", "USE_LIBUV"]
        return {key: env[key] for key in keys if key in env}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _display_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


@lru_cache(maxsize=1)
def get_job_runner() -> JobRunner:
    return JobRunner()
