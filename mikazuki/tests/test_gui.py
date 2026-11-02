import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

import gui


class GuiLaunchTests(unittest.TestCase):
    def setUp(self):
        patches = ExitStack()
        self.addCleanup(patches.close)
        self.frontend = patches.enter_context(patch.object(gui, "ensure_frontend_release"))
        self.frontend.return_value = SimpleNamespace(required_version="2.0.0", status="current", source="")
        self.prepare = patches.enter_context(patch.object(gui, "prepare_environment"))
        self.available = patches.enter_context(patch.object(gui, "check_port_available", return_value=True))
        self.serve = patches.enter_context(patch("uvicorn.run"))
        patches.enter_context(patch.object(gui, "log"))
        patches.enter_context(patch.dict(os.environ, {}, clear=True))

    def test_launch_parses_arguments_without_module_global(self):
        with patch.object(gui.sys, "argv", ["gui.py", "--skip-frontend-download"]):
            gui.launch()

        self.assertTrue(self.frontend.call_args.kwargs["skip_download"])
        self.prepare.assert_called_once_with(disable_auto_mirror=False, prepare_onnxruntime=True)
        self.assertEqual(self.serve.call_args.kwargs["host"], "127.0.0.1")
        self.assertEqual(self.serve.call_args.kwargs["port"], 28000)

    def test_listen_and_fallback_port_preserve_callers_arguments(self):
        args = gui.parser.parse_args(["--listen", "--port", "28001", "--skip-prepare-environment"])
        self.available.return_value = False
        with patch.object(gui, "find_available_port", return_value=30001):
            gui.launch(args)

        self.assertEqual((args.host, args.port), ("127.0.0.1", 28001))
        self.assertEqual(self.serve.call_args.kwargs["host"], "0.0.0.0")
        self.assertEqual(self.serve.call_args.kwargs["port"], 30001)
        self.assertEqual(os.environ["MIKAZUKI_HOST"], "127.0.0.1")
        self.assertEqual(os.environ["MIKAZUKI_PORT"], "30001")
        self.prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
