import unittest
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

from mikazuki.jobs.runtime import validate_training_runtime
from mikazuki.tests.jobs.test_runner import MemoryJobStore
from mikazuki.jobs.runner import JobRunner
from mikazuki.compiler.models import CompileResult, TrainDraft


class TrainingRuntimeTests(unittest.TestCase):
    def test_old_environment_does_not_block_existing_trainers(self):
        with patch("mikazuki.jobs.runtime.version", side_effect=PackageNotFoundError):
            self.assertEqual(validate_training_runtime("flux.lora", None), [])

    def test_old_moss_environment_has_actionable_dependency_errors(self):
        with patch("mikazuki.jobs.runtime.version", side_effect=lambda name: {
            "torch": "2.4.1+cu121", "transformers": "4.54.1",
        }[name]):
            errors = validate_training_runtime("moss_image.lora", None)
        self.assertEqual(len(errors), 2)
        self.assertTrue(all(error.code == "runtime.moss_dependency" for error in errors))
        self.assertIn("docs/moss-image-training.md", errors[0].message)

    def test_bf16_convrot_fallback_does_not_require_triton(self):
        with (
            patch("mikazuki.jobs.runtime.version", side_effect=lambda name: {
                "torch": "2.7.0+cu128", "transformers": "5.17.0",
            }[name]),
            patch("mikazuki.jobs.runtime.find_spec", return_value=None),
        ):
            self.assertEqual(validate_training_runtime("moss_image.lora", '[memory]\nconvrot_int8 = true'), [])
            errors = validate_training_runtime("moss_image.lora", '[memory]\nconvrot_int8_bwd = "int8"')
        self.assertEqual([e.code for e in errors], ["runtime.moss_triton"])


class RuntimeLaunchTests(unittest.IsolatedAsyncioTestCase):
    async def test_moss_dependency_failure_never_queues_a_process(self):
        store = MemoryJobStore()
        runner = JobRunner(store=store)
        compiled = CompileResult(trainerId="moss_image.lora", manifestHash="test", runId="test")
        with (
            patch("mikazuki.jobs.runner.compile_draft", return_value=compiled),
            patch("mikazuki.jobs.runtime.version", side_effect=PackageNotFoundError),
            patch("mikazuki.jobs.runner.subprocess.Popen") as process,
        ):
            result = await runner.start_job(TrainDraft(trainerId="moss_image.lora"))
        self.assertIsNone(result.job)
        self.assertEqual(len(result.compile.errors), 2)
        self.assertFalse(store._jobs)
        process.assert_not_called()
