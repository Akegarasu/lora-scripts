import os
import unittest
from unittest.mock import patch

from mikazuki.proxy_utils import tageditor_ws_uri


class TageditorProxyTest(unittest.TestCase):
    def test_websocket_uses_default_service(self):
        environment = {key: value for key, value in os.environ.items() if key not in {"MIKAZUKI_TAGEDITOR_HOST", "MIKAZUKI_TAGEDITOR_PORT"}}
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(tageditor_ws_uri(), "ws://127.0.0.1:28001/queue/join")

    def test_websocket_honors_configured_service(self):
        with patch.dict(os.environ, {"MIKAZUKI_TAGEDITOR_HOST": "tag-editor", "MIKAZUKI_TAGEDITOR_PORT": "28123"}):
            self.assertEqual(tageditor_ws_uri(), "ws://tag-editor:28123/queue/join")


if __name__ == "__main__":
    unittest.main()
