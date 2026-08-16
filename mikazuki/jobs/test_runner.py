import asyncio
import os
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch

from mikazuki.catalog.models import TrainerDefinition
from mikazuki.compiler.compiler import _build_command
from mikazuki.compiler.models import CompileArtifacts, CompileResult, TrainDraft
from mikazuki.jobs.models import JobRecord
from mikazuki.jobs.runner import JobRunner


class MemoryJobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, JobRecord] = {}
        self._lock = threading.RLock()
        self.queued = threading.Event()

    def create_job(self, job: JobRecord) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def update_job(self, job_id: str, **fields: Any) -> Optional[JobRecord]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            data = job.dict()
            data.update(fields)
            updated = JobRecord(**data)
            self._jobs[job_id] = updated
            if fields.get("state") == "queued":
                self.queued.set()
            return updated


def make_job(job_id: str = "job_test", state: str = "queued") -> JobRecord:
    return JobRecord(
        id=job_id,
        runId="run_test",
        trainerId="flux.lora",
        state=state,
        command=["python", "train.py"],
        createdAt="2026-01-01T00:00:00+00:00",
    )


class RunnerCommandAndEnvironmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryJobStore()
        self.runner = JobRunner(store=self.store, max_concurrent=1)  # type: ignore[arg-type]
        self.draft = TrainDraft(
            trainerId="flux.lora",
            runtime={
                "gpuIds": [" 0", "1 "],
                "numCpuThreadsPerProcess": 6,
            },
        )

    def test_build_command_includes_runtime_and_windows_multi_gpu_flags(self) -> None:
        trainer = TrainerDefinition(
            id="flux.lora",
            title="FLUX",
            family="flux",
            task="lora",
            script="scripts/dev/flux_train_network.py",
        )
        train_path = Path("output") / "train.toml"

        with (
            patch("mikazuki.compiler.compiler.sys.executable", "C:/Python/python.exe"),
            patch("mikazuki.compiler.compiler.sys.platform", "win32"),
        ):
            command = _build_command(trainer, train_path, self.draft)

        self.assertEqual(command[:7], [
            "C:/Python/python.exe",
            "-m",
            "accelerate.commands.launch",
            "--num_cpu_threads_per_process",
            "6",
            "--quiet",
            "--rdzv_backend",
        ])
        self.assertIn("c10d", command)
        self.assertIn("--multi_gpu", command)
        self.assertEqual(command[command.index("--num_processes") + 1], "2")
        self.assertEqual(command[-3:-1], ["scripts/dev/flux_train_network.py", "--config_file"])
        self.assertTrue(command[-1].endswith("/output/train.toml"))

    def test_build_command_forces_one_process_for_one_selected_gpu(self) -> None:
        trainer = TrainerDefinition(
            id="flux.lora",
            title="FLUX",
            family="flux",
            task="lora",
            script="scripts/dev/flux_train_network.py",
        )
        draft = TrainDraft(
            trainerId="flux.lora",
            runtime={"gpuIds": ["2"], "numCpuThreadsPerProcess": 4},
        )

        command = _build_command(trainer, Path("output") / "train.toml", draft)

        self.assertNotIn("--multi_gpu", command)
        self.assertEqual(command[command.index("--num_processes") + 1], "1")

    def test_build_env_uses_normalized_gpu_ids_and_hides_unrelated_values(self) -> None:
        with (
            patch.dict(os.environ, {"SECRET_TOKEN": "secret"}, clear=True),
            patch("mikazuki.jobs.runner.sys.platform", "win32"),
        ):
            env = self.runner._build_env(self.draft)

        self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "0,1")
        self.assertEqual(env["USE_LIBUV"], "0")
        self.assertEqual(env["ACCELERATE_DISABLE_RICH"], "1")
        self.assertEqual(env["PYTHONUNBUFFERED"], "1")
        self.assertEqual(env["SECRET_TOKEN"], "secret")
        self.assertNotIn("SECRET_TOKEN", self.runner._public_env(env))


class RunnerQueuedTerminationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryJobStore()
        self.runner = JobRunner(store=self.store, max_concurrent=1)  # type: ignore[arg-type]

    def test_terminating_queued_job_never_starts_a_process(self) -> None:
        job = make_job()
        self.store.create_job(job)
        self.assertTrue(self.runner._slot.acquire(blocking=False))

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "job.log"
            with patch("mikazuki.jobs.runner.subprocess.Popen") as popen:
                worker = threading.Thread(
                    target=self.runner._run_sync,
                    args=(job.id, job.command, {}, log_path),
                    daemon=True,
                )
                worker.start()
                try:
                    self.assertTrue(self.store.queued.wait(timeout=2))
                    terminating = self.runner.terminate_job(job.id)
                    self.assertIsNotNone(terminating)
                    assert terminating is not None
                    self.assertEqual(terminating.state, "terminating")
                finally:
                    self.runner._slot.release()

                worker.join(timeout=2)
                self.assertFalse(worker.is_alive())
                popen.assert_not_called()

        finished = self.store.get_job(job.id)
        self.assertIsNotNone(finished)
        assert finished is not None
        self.assertEqual(finished.state, "terminated")
        self.assertIsNotNone(finished.endedAt)
        self.assertIsNone(finished.startedAt)

    def test_already_canceled_job_never_starts_a_process(self) -> None:
        job = make_job(job_id="job_canceled", state="canceled")
        self.store.create_job(job)

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("mikazuki.jobs.runner.subprocess.Popen") as popen:
                self.runner._run_sync(job.id, job.command, {}, Path(temp_dir) / "job.log")
                popen.assert_not_called()

        finished = self.store.get_job(job.id)
        self.assertIsNotNone(finished)
        assert finished is not None
        self.assertEqual(finished.state, "canceled")
        self.assertIsNotNone(finished.endedAt)


class RunnerStartChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryJobStore()
        self.runner = JobRunner(store=self.store, max_concurrent=1)  # type: ignore[arg-type]

    def test_start_job_persists_queued_record_and_schedules_worker(self) -> None:
        draft = TrainDraft(trainerId="flux.lora", name="chain_test")
        compiled = CompileResult(
            runId="run_chain",
            trainerId="flux.lora",
            manifestHash="catalog-hash",
            artifacts=CompileArtifacts(trainConfig="config/runs/run_chain/train.toml"),
            command=["python", "scripts/dev/flux_train_network.py", "--config_file", "train.toml"],
        )

        async def exercise():
            with (
                patch("mikazuki.jobs.runner.compile_draft", return_value=compiled),
                patch.object(self.runner, "_run_sync") as run_sync,
            ):
                result = await self.runner.start_job(draft)
                pending = tuple(self.runner._tasks)
                if pending:
                    await asyncio.gather(*pending)
                return result, run_sync

        result, run_sync = asyncio.run(exercise())

        self.assertIsNotNone(result.job)
        assert result.job is not None
        self.assertEqual(result.job.state, "queued")
        self.assertIsNotNone(self.store.get_job(result.job.id))
        run_sync.assert_called_once()
        self.assertEqual(run_sync.call_args.args[:2], (result.job.id, compiled.command))

    def test_worker_launches_process_and_records_success(self) -> None:
        job = make_job(job_id="job_success")
        self.store.create_job(job)

        class FakeProcess:
            pid = 12345
            stdout = iter(["training started\n", "training finished\n"])

            def wait(self) -> int:
                return 0

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "job.log"
            with patch("mikazuki.jobs.runner.subprocess.Popen", return_value=FakeProcess()) as popen:
                self.runner._run_sync(job.id, job.command, {}, log_path)

            popen.assert_called_once()
            self.assertIn("training started", log_path.read_text(encoding="utf-8"))

        finished = self.store.get_job(job.id)
        self.assertIsNotNone(finished)
        assert finished is not None
        self.assertEqual(finished.state, "succeeded")
        self.assertEqual(finished.exitCode, 0)
        self.assertIsNotNone(finished.startedAt)
        self.assertIsNotNone(finished.endedAt)


if __name__ == "__main__":
    unittest.main()
