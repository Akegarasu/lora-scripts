import math
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tensorboardX.proto.event_pb2 import Event

from mikazuki.jobs.metrics import (
    JobMetricsReader,
    JobMetricsService,
    MetricPoint,
    _masked_crc32c,
    downsample_metric_points,
    parse_tag_filter,
    resolve_metrics_source,
)
from mikazuki.jobs.models import JobRecord


def _job(root: Path, prefix: str = "run_test-") -> JobRecord:
    return JobRecord(
        id="job_run_test",
        runId="run_test",
        trainerId="flux.lora",
        state="running",
        artifacts={"loggingDir": str(root), "logPrefix": prefix},
        createdAt="2026-01-01T00:00:00+00:00",
    )


def _scalar_event(tag: str, value: float, step: int, wall_time: float = 100.0) -> bytes:
    event = Event(wall_time=wall_time, step=step)
    event.summary.value.add(tag=tag, simple_value=value)
    return event.SerializeToString()


def _tensor_event(tag: str, value: float, step: int) -> bytes:
    event = Event(wall_time=101.0, step=step)
    summary = event.summary.value.add(tag=tag)
    summary.tensor.dtype = 1  # DT_FLOAT
    summary.tensor.float_val.append(value)
    return event.SerializeToString()


def _record(payload: bytes) -> bytes:
    length = struct.pack("<Q", len(payload))
    return (
        length
        + struct.pack("<I", _masked_crc32c(length))
        + payload
        + struct.pack("<I", _masked_crc32c(payload))
    )


class JobMetricsReaderTests(unittest.TestCase):
    def test_incremental_read_keeps_partial_record_for_next_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / "run_test-20260101000000" / "network_train"
            run_dir.mkdir(parents=True)
            event_path = run_dir / "events.out.tfevents.test"
            first_record = _record(_scalar_event("loss/current", 0.8, 1))
            second_record = _record(_scalar_event("loss/current", 0.6, 2))
            split = len(second_record) // 2
            event_path.write_bytes(first_record + second_record[:split])

            reader = JobMetricsReader(_job(root))
            first = reader.snapshot(max_points=100)

            self.assertEqual(first["cursor"], 1)
            self.assertEqual(first["tags"], ["loss/current"])
            self.assertEqual(first["series"][0]["points"][0]["step"], 1)

            with event_path.open("ab") as handle:
                handle.write(second_record[split:])

            second = reader.snapshot(cursor=first["cursor"], max_points=100)
            self.assertEqual(second["cursor"], 2)
            self.assertEqual(second["pointCount"], 1)
            self.assertEqual(second["series"][0]["points"][0]["step"], 2)
            self.assertAlmostEqual(second["series"][0]["points"][0]["value"], 0.6)

            unchanged = reader.snapshot(cursor=second["cursor"], max_points=100)
            self.assertEqual(unchanged["pointCount"], 0)
            self.assertEqual(unchanged["series"][0]["points"], [])

    def test_prefix_prevents_reading_another_jobs_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = root / "run_test-20260101000000" / "network_train"
            unrelated = root / "run_other-20260101000001" / "network_train"
            expected.mkdir(parents=True)
            unrelated.mkdir(parents=True)
            (expected / "events.out.tfevents.a").write_bytes(
                _record(_scalar_event("loss/current", 1.0, 1))
            )
            (unrelated / "events.out.tfevents.b").write_bytes(
                _record(_scalar_event("private/other-job", 9.0, 1))
            )

            snapshot = JobMetricsReader(_job(root)).snapshot(max_points=100)

            self.assertEqual(snapshot["tags"], ["loss/current"])
            self.assertNotIn("private/other-job", snapshot["tags"])
            self.assertTrue(snapshot["sourcePath"].replace("\\", "/").endswith("run_test-20260101000000"))

    def test_tensor_scalar_and_non_finite_values_are_json_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / "run_test-20260101000000" / "network_train"
            run_dir.mkdir(parents=True)
            (run_dir / "events.out.tfevents.a").write_bytes(
                _record(_tensor_event("lr/unet", 0.0001, 3))
                + _record(_scalar_event("loss/current", math.nan, 3))
            )

            snapshot = JobMetricsReader(_job(root)).snapshot(max_points=100)
            series = {item["tag"]: item["points"] for item in snapshot["series"]}

            self.assertAlmostEqual(series["lr/unet"][0]["value"], 0.0001)
            self.assertIsNone(series["loss/current"][0]["value"])
            self.assertEqual(series["loss/current"][0]["nonFinite"], "nan")

    def test_corrupt_record_is_reported_without_crashing_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / "run_test-20260101000000"
            run_dir.mkdir()
            (run_dir / "events.out.tfevents.bad").write_bytes(b"not-a-valid-tfrecord")

            snapshot = JobMetricsReader(_job(root)).snapshot(max_points=100)

            self.assertFalse(snapshot["available"])
            self.assertEqual(snapshot["tags"], [])
            self.assertTrue(any("TFRecord" in error for error in snapshot["errors"]))

    def test_resolve_source_uses_v2_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job = JobRecord(
                id="job_source",
                runId="source",
                trainerId="sd.lora",
                artifacts={"loggingDir": str(root), "logPrefix": "run-"},
                createdAt="2026-01-01T00:00:00+00:00",
            )
            source = resolve_metrics_source(job)
            self.assertEqual(source.root, root.resolve())
            self.assertEqual(source.prefix, "run-")

    def test_long_series_is_compacted_without_losing_cursor_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / "run_test-20260101000000"
            run_dir.mkdir()
            event_path = run_dir / "events.out.tfevents.compact"
            event_path.write_bytes(
                b"".join(
                    _record(_scalar_event("loss/current", float(step), step))
                    for step in range(1, 7)
                )
            )

            with (
                patch("mikazuki.jobs.metrics.COMPACT_POINTS_PER_TAG_AT", 5),
                patch("mikazuki.jobs.metrics.MAX_RETAINED_POINTS_PER_TAG", 3),
            ):
                snapshot = JobMetricsReader(_job(root)).snapshot(max_points=100)

            points = snapshot["series"][0]["points"]
            self.assertEqual(snapshot["cursor"], 6)
            self.assertEqual(len(points), 3)
            self.assertEqual(points[0]["step"], 1)
            self.assertEqual(points[-1]["step"], 6)

    def test_service_evicts_least_recently_used_reader(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = JobMetricsService(max_readers=2)
            jobs = [
                JobRecord(
                    id=f"job_{index}",
                    runId=f"run_{index}",
                    trainerId="sd.lora",
                    artifacts={"loggingDir": str(root / str(index))},
                    createdAt="2026-01-01T00:00:00+00:00",
                )
                for index in range(3)
            ]

            service.snapshot(jobs[0])
            service.snapshot(jobs[1])
            service.snapshot(jobs[0])
            service.snapshot(jobs[2])

            self.assertEqual(list(service._readers), ["job_0", "job_2"])


class MetricUtilityTests(unittest.TestCase):
    def test_lttb_downsample_preserves_endpoints_and_spike(self) -> None:
        points = [
            MetricPoint(seq=index + 1, step=index, wall_time=float(index), value=50.0 if index == 50 else 1.0)
            for index in range(100)
        ]

        sampled = downsample_metric_points(points, 12)

        self.assertEqual(len(sampled), 12)
        self.assertEqual(sampled[0], points[0])
        self.assertEqual(sampled[-1], points[-1])
        self.assertIn(points[50], sampled)

    def test_tag_filter_is_trimmed_ordered_and_deduplicated(self) -> None:
        self.assertEqual(
            parse_tag_filter(["loss/current, lr/unet", "loss/current", "  loss/average  "]),
            ["loss/current", "lr/unet", "loss/average"],
        )
        self.assertIsNone(parse_tag_filter(" , "))


if __name__ == "__main__":
    unittest.main()
