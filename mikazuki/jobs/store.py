import threading
from functools import lru_cache
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from mikazuki.storage.paths import runs_dir

from .models import JobRecord


class JobStore:
    """Training job registry backed by each run's artifact directory.

    Only the server process updates training state, so a per-run JSON manifest
    preserves history without a second database.
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = (root or runs_dir()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, JobRecord] = {}
        self._lock = threading.RLock()
        self._load_jobs()

    def create_job(self, job: JobRecord) -> None:
        with self._lock:
            self._jobs[job.id] = job
            self._persist_job(job)

    def update_job(self, job_id: str, **fields: Any) -> Optional[JobRecord]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            data = job.dict()
            data.update(fields)
            updated = JobRecord(**data)
            self._jobs[job_id] = updated
            self._persist_job(updated)
            return updated

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 50) -> List[JobRecord]:
        with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda job: job.createdAt,
                reverse=True,
            )
            return jobs[:limit]

    def _load_jobs(self) -> None:
        for path in self.root.glob("*/job.json"):
            job = JobRecord.parse_raw(path.read_text(encoding="utf-8"))
            if job.state not in {"succeeded", "failed", "terminated", "canceled"}:
                job = job.copy(
                    update={
                        "state": "failed",
                        "endedAt": job.endedAt or _now(),
                        "errorMessage": "服务重启中断了训练任务。",
                    }
                )
                self._persist_job(job)
            self._jobs[job.id] = job

    def _persist_job(self, job: JobRecord) -> None:
        path = self.root / job.runId / "job.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(".json.tmp")
        temporary_path.write_text(
            job.json(ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(path)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@lru_cache(maxsize=1)
def get_job_store() -> JobStore:
    return JobStore()
