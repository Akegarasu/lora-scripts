import threading
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from mikazuki.app import api_v2
from mikazuki.jobs.artifacts import JobArtifactError
from mikazuki.jobs.models import JobRecord


class JobArtifactsApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.job = JobRecord(
            id="job_test", runId="run_test", trainerId="sdxl.lora",
            state="succeeded", createdAt="2026-01-01T00:00:00+00:00",
        )
        self.store = Mock()
        self.store.get_job.return_value = self.job
        patcher = patch.object(api_v2, "get_job_store", return_value=self.store)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_returns_artifacts_without_blocking_event_loop(self) -> None:
        event_loop_thread = threading.get_ident()
        reader_threads = []
        payload = {"jobId": self.job.id, "draft": {"trainerId": "sdxl.lora"}}

        def read(job):
            self.assertEqual(job, self.job)
            reader_threads.append(threading.get_ident())
            return payload

        with patch.object(api_v2, "read_job_artifacts", side_effect=read):
            result = await api_v2.get_job_artifacts(self.job.id)
        self.assertEqual(result, payload)
        self.assertEqual(len(reader_threads), 1)
        self.assertNotEqual(reader_threads[0], event_loop_thread)

    async def test_missing_job_never_reads_files(self) -> None:
        self.store.get_job.return_value = None
        with patch.object(api_v2, "read_job_artifacts") as reader:
            with self.assertRaises(HTTPException) as caught:
                await api_v2.get_job_artifacts("missing")
        self.assertEqual(caught.exception.status_code, 404)
        reader.assert_not_called()

    async def test_maps_missing_invalid_and_unreadable_artifacts(self) -> None:
        for error, status in (
            (FileNotFoundError("required job artifact is missing: draft.json"), 404),
            (JobArtifactError("train.toml exceeds the 1 MiB artifact limit"), 422),
            (PermissionError("permission denied"), 503),
        ):
            with self.subTest(error=error):
                with patch.object(api_v2, "read_job_artifacts", side_effect=error):
                    with self.assertRaises(HTTPException) as caught:
                        await api_v2.get_job_artifacts(self.job.id)
                self.assertEqual(caught.exception.status_code, status)


if __name__ == "__main__":
    unittest.main()
