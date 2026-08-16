import unittest

from pydantic import ValidationError

from mikazuki.compiler.models import RuntimeDraft


class RuntimeDraftTests(unittest.TestCase):
    def test_cpu_thread_count_must_be_positive(self) -> None:
        with self.assertRaises(ValidationError):
            RuntimeDraft(numCpuThreadsPerProcess=0)

    def test_gpu_ids_are_trimmed_and_empty_values_are_removed(self) -> None:
        runtime = RuntimeDraft(gpuIds=[" 0 ", "", "  ", "2"])

        self.assertEqual(runtime.gpuIds, ["0", "2"])

    def test_gpu_ids_reject_duplicates_after_normalization(self) -> None:
        with self.assertRaisesRegex(ValidationError, r"duplicate value: 1"):
            RuntimeDraft(gpuIds=["1", " 1 "])

    def test_gpu_ids_do_not_turn_null_into_a_device_name(self) -> None:
        with self.assertRaises(ValidationError):
            RuntimeDraft(gpuIds=[None])

    def test_gpu_ids_reject_comma_separated_values(self) -> None:
        with self.assertRaisesRegex(ValidationError, r"invalid device identifier"):
            RuntimeDraft(gpuIds=["0,1"])


if __name__ == "__main__":
    unittest.main()
