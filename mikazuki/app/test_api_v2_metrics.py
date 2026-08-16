import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException

from mikazuki.app import api_v2
from mikazuki.jobs.models import JobRecord


def _job(state: str = "running") -> JobRecord:
    return JobRecord(
        id="job_metrics",
        runId="metrics",
        trainerId="flux.lora",
        state=state,
        createdAt="2026-01-01T00:00:00+00:00",
    )


class _Store:
    def __init__(self, job=None) -> None:
        self.job = job

    def get_job(self, _job_id):
        return self.job


class _SequenceStore:
    def __init__(self, jobs) -> None:
        self.jobs = list(jobs)
        self.index = 0

    def get_job(self, _job_id):
        job = self.jobs[min(self.index, len(self.jobs) - 1)]
        self.index += 1
        return job


class _MetricsService:
    def __init__(self, payload=None) -> None:
        self.payload = payload or {
            "jobId": "job_metrics",
            "cursor": 8,
            "available": True,
            "sourcePath": "logs/metrics",
            "tags": ["loss/current"],
            "series": [
                {
                    "tag": "loss/current",
                    "points": [{"seq": 8, "step": 8, "wallTime": 100.0, "value": 0.5}],
                }
            ],
            "pointCount": 1,
            "errors": [],
        }
        self.calls = []

    def snapshot(self, job, **kwargs):
        self.calls.append((job, kwargs))
        return self.payload


class MetricsApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_metrics_endpoint_passes_cursor_sampling_and_tag_filter(self) -> None:
        service = _MetricsService()
        with (
            patch("mikazuki.app.api_v2.get_job_store", return_value=_Store(_job())),
            patch("mikazuki.app.api_v2.get_job_metrics_service", return_value=service),
        ):
            response = await api_v2.get_job_metrics(
                "job_metrics",
                cursor=5,
                max_points=250,
                tags="loss/current, lr/unet,loss/current",
            )

        self.assertEqual(response["cursor"], 8)
        self.assertEqual(len(service.calls), 1)
        _, kwargs = service.calls[0]
        self.assertEqual(kwargs["cursor"], 5)
        self.assertEqual(kwargs["max_points"], 250)
        self.assertEqual(kwargs["tags"], ["loss/current", "lr/unet"])

    async def test_metrics_endpoint_returns_404_for_missing_job(self) -> None:
        with patch("mikazuki.app.api_v2.get_job_store", return_value=_Store()):
            with self.assertRaises(HTTPException) as raised:
                await api_v2.get_job_metrics("missing", cursor=0, max_points=200, tags=None)
        self.assertEqual(raised.exception.status_code, 404)

    async def test_metric_sse_resumes_from_last_event_id_and_closes_for_terminal_job(self) -> None:
        service = _MetricsService()
        terminal_job = _job(state="succeeded")
        with (
            patch("mikazuki.app.api_v2.get_job_store", return_value=_Store(terminal_job)),
            patch("mikazuki.app.api_v2.get_job_metrics_service", return_value=service),
        ):
            response = await api_v2.get_job_metric_events(
                "job_metrics",
                cursor=None,
                last_event_id="7",
            )
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)

        output = "".join(chunks)
        self.assertEqual(service.calls[0][1]["cursor"], 7)
        self.assertIn("id: 8\nevent: metric", output)
        self.assertIn("event: state", output)
        self.assertIn('"state": "succeeded"', output)
        self.assertIn('"tag": "loss/current"', output)
        self.assertLess(output.index("event: metric"), output.index("event: state"))
        self.assertEqual(response.headers["cache-control"], "no-cache")

    async def test_metric_sse_returns_404_for_missing_job(self) -> None:
        with patch("mikazuki.app.api_v2.get_job_store", return_value=_Store()):
            with self.assertRaises(HTTPException) as raised:
                await api_v2.get_job_metric_events(
                    "missing",
                    cursor=0,
                    last_event_id=None,
                )
        self.assertEqual(raised.exception.status_code, 404)

    async def test_metric_sse_emits_heartbeat_while_job_is_running(self) -> None:
        service = _MetricsService()
        store = _SequenceStore([_job(), _job(), _job(state="succeeded")])
        with (
            patch("mikazuki.app.api_v2.get_job_store", return_value=store),
            patch("mikazuki.app.api_v2.get_job_metrics_service", return_value=service),
            patch(
                "mikazuki.app.api_v2.time",
                new=SimpleNamespace(monotonic=Mock(side_effect=[0.0, 16.0]), time=lambda: 100.0),
            ),
            patch("mikazuki.app.api_v2.asyncio.sleep", new=AsyncMock()),
        ):
            response = await api_v2.get_job_metric_events(
                "job_metrics",
                cursor=0,
                last_event_id=None,
            )
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)

        self.assertIn("event: heartbeat", "".join(chunks))

    def test_cursor_precedence_and_invalid_last_event_id(self) -> None:
        self.assertEqual(api_v2._resolve_metric_cursor(3, "9"), 9)
        self.assertEqual(api_v2._resolve_metric_cursor(3, "invalid"), 3)
        self.assertEqual(api_v2._resolve_metric_cursor(None, "1"), 1)
        self.assertEqual(api_v2._resolve_metric_cursor(None, "9"), 9)
        self.assertEqual(api_v2._resolve_metric_cursor(None, "invalid"), 0)


if __name__ == "__main__":
    unittest.main()
