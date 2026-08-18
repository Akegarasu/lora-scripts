import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from mikazuki.app import api_v2
from mikazuki.storage.files import (
    BrowsePathError,
    FileManagerLaunchError,
    FileManagerUnavailableError,
)


class FilesApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_reports_file_manager_capability(self) -> None:
        capability = {
            "available": True,
            "platform": "windows",
            "fileManager": "Windows 文件资源管理器",
            "reason": None,
        }
        with patch("mikazuki.app.api_v2.file_manager_capability", return_value=capability):
            response = await api_v2.get_file_manager_capability()

        self.assertEqual(capability, response)

    async def test_reveals_a_validated_output_path(self) -> None:
        target = Path("C:/workspace/output/model.safetensors")
        with patch("mikazuki.app.api_v2.show_output_in_file_manager", return_value=target):
            response = await api_v2.reveal_output_path(str(target))

        self.assertEqual("opened", response["status"])
        self.assertEqual(target.as_posix(), response["path"])

    async def test_reveal_maps_boundary_and_environment_errors(self) -> None:
        cases = (
            (BrowsePathError("outside"), 400),
            (FileNotFoundError("missing"), 404),
            (FileManagerUnavailableError("headless"), 409),
            (FileManagerLaunchError("failed"), 503),
        )
        for error, expected_status in cases:
            with self.subTest(error=type(error).__name__):
                with patch("mikazuki.app.api_v2.show_output_in_file_manager", side_effect=error):
                    with self.assertRaises(HTTPException) as raised:
                        await api_v2.reveal_output_path("output/model.safetensors")
                self.assertEqual(expected_status, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
