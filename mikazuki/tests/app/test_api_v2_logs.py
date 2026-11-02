import threading
import unittest
from unittest.mock import Mock, patch

from mikazuki.app import api_v2
from mikazuki.jobs.models import JobRecord


class JobLogsApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.job = JobRecord(
            id="job_logs", runId="logs", trainerId="sd.lora",
            state="succeeded", createdAt="2026-01-01T00:00:00+00:00",
        )

    async def test_job_without_a_log_path_has_empty_logs_and_terminal_events(self) -> None:
        store = Mock()
        store.get_job.return_value = self.job
        with patch.object(api_v2, "get_job_store", return_value=store):
            logs = await api_v2.get_job_logs(self.job.id, tail=500)
            response = await api_v2.get_job_events(self.job.id)
            events = [chunk async for chunk in response.body_iterator]

        self.assertEqual(logs, {"jobId": self.job.id, "cursor": 0, "lines": []})
        self.assertEqual(len(events), 1)
        self.assertIn('"state": "succeeded"', events[0])

    async def test_log_reads_run_outside_the_server_event_loop(self) -> None:
        event_loop_thread = threading.get_ident()
        worker_threads = []

        def read_log(*args, **kwargs):
            worker_threads.append(threading.get_ident())
            return 5, ["done"]

        store = Mock()
        store.get_job.return_value = self.job
        with (
            patch.object(api_v2, "get_job_store", return_value=store),
            patch.object(api_v2, "tail_log", side_effect=read_log),
            patch.object(api_v2, "read_log_from", side_effect=read_log),
        ):
            logs = await api_v2.get_job_logs(self.job.id, tail=1)
            response = await api_v2.get_job_events(self.job.id)
            events = [chunk async for chunk in response.body_iterator]

        self.assertEqual(logs["lines"], ["done"])
        self.assertIn('"line": "done"', events[1])
        self.assertEqual(len(worker_threads), 2)
        self.assertTrue(all(thread != event_loop_thread for thread in worker_threads))


if __name__ == "__main__":
    unittest.main()
