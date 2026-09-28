import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mikazuki.jobs.models import JobRecord
from mikazuki.jobs.store import JobStore


def _job(*, state: str = "queued") -> JobRecord:
    return JobRecord(
        id="job_run_persistence",
        runId="run_persistence",
        trainerId="flux.lora",
        state=state,
        command=["accelerate", "launch"],
        artifacts={"trainConfig": "config/runs/run_persistence/train.toml"},
        createdAt="2026-08-15T12:00:00+08:00",
    )


class JobStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "runs"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_terminal_job_history_is_loaded_from_run_manifest(self) -> None:
        store = JobStore(self.root)
        store.create_job(_job())
        store.update_job(
            "job_run_persistence",
            state="succeeded",
            endedAt="2026-08-15T12:30:00+08:00",
            exitCode=0,
        )

        restarted = JobStore(self.root)
        loaded = restarted.get_job("job_run_persistence")

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.state, "succeeded")
        self.assertEqual(loaded.exitCode, 0)
        self.assertTrue((self.root / "run_persistence" / "job.json").is_file())

    def test_nonterminal_job_is_failed_after_service_restart(self) -> None:
        store = JobStore(self.root)
        store.create_job(_job(state="running"))

        restarted = JobStore(self.root)
        loaded = restarted.get_job("job_run_persistence")

        self.assertEqual(loaded.state, "failed")
        self.assertIsNotNone(loaded.endedAt)
        self.assertIn("服务重启", loaded.errorMessage)

        restarted_again = JobStore(self.root)
        self.assertEqual(restarted_again.get_job("job_run_persistence").state, "failed")

    def test_corrupt_manifest_does_not_hide_valid_history(self) -> None:
        store = JobStore(self.root)
        store.create_job(_job(state="succeeded"))
        corrupt_dir = self.root / "corrupt"
        corrupt_dir.mkdir()
        (corrupt_dir / "job.json").write_text("{broken", encoding="utf-8")

        with self.assertLogs("sd-trainer", level="WARNING"):
            restarted = JobStore(self.root)

        self.assertEqual([job.id for job in restarted.list_jobs()], ["job_run_persistence"])
        self.assertEqual((corrupt_dir / "job.json").read_text(encoding="utf-8"), "{broken")

    def test_failed_create_does_not_leave_an_unpersisted_job(self) -> None:
        store = JobStore(self.root)
        with patch.object(store, "_persist_job", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.create_job(_job())

        self.assertEqual(store.list_jobs(), [])

    def test_failed_update_keeps_last_persisted_state(self) -> None:
        store = JobStore(self.root)
        job = _job(state="succeeded")
        store.create_job(job)
        with patch.object(store, "_persist_job", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.update_job(job.id, state="failed")

        self.assertEqual(store.get_job(job.id).state, "succeeded")
        self.assertEqual(JobStore(self.root).get_job(job.id).state, "succeeded")


if __name__ == "__main__":
    unittest.main()
