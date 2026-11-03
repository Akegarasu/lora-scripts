import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mikazuki.tests.mcp.test_integration import initialize, local_client, make_mcp_app, rpc


class MCPSettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "settings.json"
        self.app = make_mcp_app(self.path)

    def test_invalid_update_bodies_are_rejected_without_changing_settings(self):
        with local_client(self.app) as client:
            for body in ({}, {"enabled": "false"}, {"enabled": 0}, {"enabled": None}, {"enabled": False, "unexpected": True}):
                with self.subTest(body=body):
                    response = client.patch("/api/v2/settings/mcp", json=body)
                    self.assertEqual(response.status_code, 422)
                    self.assertTrue(client.get("/api/v2/settings/mcp").json()["running"])
            self.assertFalse(self.path.exists())

    def test_failed_settings_write_does_not_flip_live_gate(self):
        self.path.write_text(json.dumps({"mcp": {"enabled": True}}), encoding="utf-8")
        with local_client(self.app) as client:
            with patch.object(self.app.state.mcp_service.settings, "set_mcp_enabled", side_effect=PermissionError("fixture readonly settings")):
                response = client.patch("/api/v2/settings/mcp", json={"enabled": False})
            self.assertEqual(response.status_code, 503)
            self.assertIn("fixture readonly settings", response.json()["detail"])
            self.assertTrue(client.get("/api/v2/settings/mcp").json()["running"])
            self.assertEqual(rpc(client, "tools/list").status_code, 200)
        self.assertTrue(json.loads(self.path.read_text(encoding="utf-8"))["mcp"]["enabled"])

    def test_malformed_settings_fail_closed_without_disabling_business_api(self):
        self.path.write_text('{"mcp":{"enabled":"false"}}', encoding="utf-8")
        original = self.path.read_text(encoding="utf-8")
        with local_client(self.app) as client:
            settings = client.get("/api/v2/settings/mcp").json()
            self.assertFalse(settings["enabled"])
            self.assertFalse(settings["running"])
            self.assertIn("boolean", settings["error"])
            self.assertEqual(rpc(client, "tools/list").status_code, 503)
            self.assertEqual(client.get("/api/v2/health").json()["status"], "ok")
        self.assertEqual(self.path.read_text(encoding="utf-8"), original)

    def test_repaired_settings_can_be_enabled_without_restarting_backend(self):
        self.path.write_text('{"mcp":{"enabled":"broken"}}', encoding="utf-8")
        with local_client(self.app) as client:
            failed = client.get("/api/v2/settings/mcp").json()
            self.assertFalse(failed["running"])
            self.assertIsNotNone(failed["error"])
            self.assertEqual(rpc(client, "tools/list").status_code, 503)
            self.path.write_text('{"mcp":{"enabled":false},"theme":"dark"}', encoding="utf-8")
            enabled = client.patch("/api/v2/settings/mcp", json={"enabled": True})
            self.assertEqual(enabled.status_code, 200)
            self.assertTrue(enabled.json()["running"])
            self.assertIsNone(enabled.json()["error"])
            initialize(client)
            self.assertEqual(rpc(client, "tools/list").status_code, 200)
            self.assertEqual(rpc(client, "tools/call", {"name": "get_workspace_status", "arguments": {}}).status_code, 200)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"mcp": {"enabled": True}, "theme": "dark"})


if __name__ == "__main__":
    unittest.main()
