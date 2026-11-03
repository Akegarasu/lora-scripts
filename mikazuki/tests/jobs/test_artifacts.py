import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mikazuki.jobs.artifacts import JobArtifactError, read_job_artifacts
from mikazuki.jobs.models import JobRecord


class JobArtifactsTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "runs"
        self.run_dir = self.root / "run_test"
        self.run_dir.mkdir(parents=True)
        self.job = JobRecord(
            id="job_test", runId="run_test", trainerId="sdxl.lora",
            state="succeeded", createdAt="2026-01-01T00:00:00+00:00",
        )
        self.draft = {"trainerId": "sdxl.lora", "name": "示例"}
        (self.run_dir / "draft.json").write_text(json.dumps(self.draft), encoding="utf-8")
        (self.run_dir / "train.toml").write_text('[training]\nseed = 42\n', encoding="utf-8")

    def test_reads_saved_inputs_and_only_known_artifacts(self) -> None:
        (self.run_dir / "dataset.toml").write_text('[general]\ncaption_extension = ".txt"\n', encoding="utf-8")
        (self.run_dir / "sample_prompts.txt").write_bytes("示例 prompt\n".encode("utf-8"))
        (self.run_dir / "private.txt").write_text("not an artifact", encoding="utf-8")
        self.job.artifacts = {"draft": "../private.txt", "trainConfig": "../private.txt"}

        result = read_job_artifacts(self.job, root=self.root)

        self.assertEqual(result["jobId"], self.job.id)
        self.assertEqual(result["draft"], self.draft)
        self.assertIn("seed = 42", result["trainConfig"])
        self.assertIn("caption_extension", result["datasetConfig"])
        self.assertEqual(result["samplePrompts"], "示例 prompt\n")
        self.assertNotIn("not an artifact", str(result))

    def test_missing_optional_files_are_null_but_required_files_raise(self) -> None:
        result = read_job_artifacts(self.job, root=self.root)
        self.assertIsNone(result["datasetConfig"])
        self.assertIsNone(result["samplePrompts"])
        (self.run_dir / "train.toml").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "train.toml"):
            read_job_artifacts(self.job, root=self.root)

    def test_rejects_portable_traversal_and_absolute_run_ids(self) -> None:
        for run_id in ("../outside", "..", r"..\outside", "/outside", r"C:\outside", "run_test/other", "run:test", ""):
            with self.subTest(run_id=run_id):
                self.job.runId = run_id
                with self.assertRaises(JobArtifactError):
                    read_job_artifacts(self.job, root=self.root)

    def test_rejects_oversized_files_and_invalid_text(self) -> None:
        path = self.run_dir / "sample_prompts.txt"
        path.write_bytes(b"x" * 65)
        with patch("mikazuki.jobs.artifacts.MAX_ARTIFACT_BYTES", 64):
            with self.assertRaisesRegex(JobArtifactError, "artifact limit"):
                read_job_artifacts(self.job, root=self.root)
        path.write_bytes(b"\xff")
        with self.assertRaisesRegex(JobArtifactError, "UTF-8"):
            read_job_artifacts(self.job, root=self.root)

    def test_rejects_invalid_draft_and_directory_in_place_of_artifact(self) -> None:
        path = self.run_dir / "draft.json"
        for content in ("{broken", "[]", '{"learning_rate": NaN}', '{"learning_rate": 1e999}'):
            with self.subTest(content=content):
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(JobArtifactError):
                    read_job_artifacts(self.job, root=self.root)
        path.write_text("{}", encoding="utf-8")
        (self.run_dir / "dataset.toml").mkdir()
        with self.assertRaisesRegex(JobArtifactError, "regular file"):
            read_job_artifacts(self.job, root=self.root)

    def test_rejects_artifact_symlink_even_within_run(self) -> None:
        try:
            (self.run_dir / "sample_prompts.txt").symlink_to(self.run_dir / "train.toml")
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"symlinks are unavailable: {error}")
        with self.assertRaisesRegex(JobArtifactError, "symbolic link"):
            read_job_artifacts(self.job, root=self.root)

    def test_rejects_resolved_path_redirection_without_symlink_privileges(self) -> None:
        original_resolve = Path.resolve
        for redirected_path in (self.run_dir, self.run_dir / "sample_prompts.txt"):
            with self.subTest(redirected_path=redirected_path):
                def redirected_resolve(path, *args, **kwargs):
                    if path == redirected_path:
                        return self.root / "other_run" / path.name
                    return original_resolve(path, *args, **kwargs)

                with patch.object(Path, "resolve", redirected_resolve):
                    with self.assertRaises(JobArtifactError):
                        read_job_artifacts(self.job, root=self.root)

    def test_rejects_run_directory_redirect_to_another_run(self) -> None:
        try:
            (self.root / "redirect").symlink_to(self.run_dir, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"directory symlinks are unavailable: {error}")
        self.job.runId = "redirect"
        with self.assertRaisesRegex(JobArtifactError, "redirect"):
            read_job_artifacts(self.job, root=self.root)


if __name__ == "__main__":
    unittest.main()
