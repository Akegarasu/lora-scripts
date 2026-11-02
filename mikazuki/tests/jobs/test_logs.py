import tempfile
import unittest
from pathlib import Path

from mikazuki.jobs.logs import read_log_from, tail_log


class JobLogTests(unittest.TestCase):
    def test_tail_returns_requested_lines_and_a_resumable_utf8_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "training.log"
            path.write_bytes("first\r\n第二行\r\nlast\n".encode("utf-8"))

            cursor, lines = tail_log(str(path), tail=2)
            self.assertEqual(lines, ["第二行", "last"])
            self.assertEqual(read_log_from(str(path), cursor), (cursor, []))

            with path.open("ab") as handle:
                handle.write("追加\n".encode("utf-8"))
            next_cursor, appended = read_log_from(str(path), cursor)
            self.assertGreater(next_cursor, cursor)
            self.assertEqual(appended, ["追加"])

    def test_zero_tail_keeps_all_lines_including_unterminated_final_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "training.log"
            path.write_bytes(b"first\n\nlast")

            self.assertEqual(tail_log(str(path), tail=0), (11, ["first", "", "last"]))
            self.assertEqual(tail_log(str(path), tail=1), (11, ["last"]))

    def test_absent_or_directory_log_paths_return_empty_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for path in ("", directory, str(Path(directory) / "missing.log")):
                with self.subTest(path=path):
                    self.assertEqual(tail_log(path), (0, []))
                    self.assertEqual(read_log_from(path, cursor=23), (23, []))


if __name__ == "__main__":
    unittest.main()
