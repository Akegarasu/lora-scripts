import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mikazuki.app import api_v2, settings_api
from mikazuki.mcp.integration import MCPService


BASE_URL = "http://127.0.0.1:28473"
PROTOCOL_VERSION = "2025-03-26"
RPC_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": PROTOCOL_VERSION,
}


def make_mcp_app(settings_path):
    @asynccontextmanager
    async def lifespan(app):
        async with app.state.mcp_service.lifespan():
            yield

    app = FastAPI(lifespan=lifespan)
    app.state.mcp_service = MCPService(app, settings_path=settings_path)
    app.include_router(api_v2.router, prefix="/api/v2")
    app.include_router(settings_api.router, prefix="/api/v2/settings")
    app.mount("/mcp", app.state.mcp_service, name="mcp")
    return app


def local_client(app, **kwargs):
    return TestClient(app, base_url=BASE_URL, client=("127.0.0.1", 50000), **kwargs)


def rpc(client, method, params=None, *, headers=None):
    body = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp/", json=body, headers={**RPC_HEADERS, **(headers or {})})


def initialize(client):
    response = rpc(client, "initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "lora-scripts-tests", "version": "1"},
    })
    if response.status_code != 200:
        raise AssertionError(f"MCP initialize failed: {response.status_code} {response.text}")
    notification = client.post("/mcp/", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=RPC_HEADERS)
    if notification.status_code != 202:
        raise AssertionError(f"MCP initialization notification failed: {notification.status_code}")
    return response.json()["result"]


class MCPIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "app-settings.json"
        self.app = make_mcp_app(self.path)

    def test_default_startup_serves_real_jsonrpc_and_reuses_internal_client(self):
        with local_client(self.app) as client:
            settings = client.get("/api/v2/settings/mcp").json()
            self.assertTrue(settings["enabled"])
            self.assertTrue(settings["running"])
            self.assertEqual(settings["endpoint"], BASE_URL + "/mcp/")
            self.assertEqual(settings["transport"], "streamable-http")
            self.assertIsNone(settings["error"])
            self.assertEqual(initialize(client)["protocolVersion"], PROTOCOL_VERSION)
            for _ in range(3):
                tools = rpc(client, "tools/list")
                self.assertEqual(tools.status_code, 200)
                self.assertIn("start_training", {tool["name"] for tool in tools.json()["result"]["tools"]})
                result = rpc(client, "tools/call", {"name": "get_workspace_status", "arguments": {}})
                self.assertEqual(result.status_code, 200)
                payload = result.json()["result"]
                self.assertFalse(payload.get("isError", False))
                self.assertEqual(json.loads(payload["content"][0]["text"])["status"], "ok")
        self.assertFalse(self.app.state.mcp_service.ready)
        self.assertFalse(self.path.exists())

    def test_switch_is_immediate_and_business_api_remains_available(self):
        with local_client(self.app) as client:
            initialize(client)
            response = client.patch("/api/v2/settings/mcp", json={"enabled": False})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["running"])
            self.assertEqual(rpc(client, "tools/list").status_code, 503)
            self.assertEqual(client.get("/mcp/").status_code, 503)
            self.assertEqual(client.get("/api/v2/health").json()["status"], "ok")
            enabled = client.patch("/api/v2/settings/mcp", json={"enabled": True})
            self.assertTrue(enabled.json()["running"])
            initialize(client)
            self.assertEqual(rpc(client, "tools/list").status_code, 200)
            self.assertEqual(client.get("/mcp/").status_code, 405)

    def test_saved_switch_survives_new_lifespan_service_and_process(self):
        self.path.write_text(json.dumps({"mcp": {"enabled": True, "futureSetting": "keep"}, "theme": "dark"}), encoding="utf-8")
        with local_client(self.app) as client:
            self.assertEqual(client.patch("/api/v2/settings/mcp", json={"enabled": False}).status_code, 200)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved, {"mcp": {"enabled": False, "futureSetting": "keep"}, "theme": "dark"})
        with local_client(self.app) as client:
            self.assertFalse(client.get("/api/v2/settings/mcp").json()["running"])
            self.assertEqual(rpc(client, "tools/list").status_code, 503)
        with local_client(make_mcp_app(self.path)) as client:
            self.assertFalse(client.get("/api/v2/settings/mcp").json()["enabled"])
            self.assertTrue(client.patch("/api/v2/settings/mcp", json={"enabled": True}).json()["running"])
            initialize(client)
            self.assertEqual(rpc(client, "tools/list").status_code, 200)
            client.patch("/api/v2/settings/mcp", json={"enabled": False})
        process = subprocess.run(
            [sys.executable, "-c", "from pathlib import Path; import sys; from mikazuki.settings import AppSettings; print(AppSettings(Path(sys.argv[1])).mcp_enabled())", str(self.path)],
            cwd=str(Path(__file__).resolve().parents[3]), capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout.strip(), "False")

    def test_remote_client_cannot_reach_mcp(self):
        with TestClient(self.app, base_url=BASE_URL, client=("192.0.2.10", 50000)) as client:
            self.assertEqual(rpc(client, "tools/list").status_code, 403)

    def test_host_and_origin_validation_preserve_local_access(self):
        with local_client(self.app) as client:
            self.assertEqual(rpc(client, "tools/list", headers={"Host": "foreign.example:28473"}).status_code, 421)
            self.assertEqual(rpc(client, "tools/list", headers={"Origin": "https://foreign.example"}).status_code, 403)
            allowed = rpc(client, "tools/list", headers={"Host": "localhost:28473", "Origin": "http://localhost:28473"})
            self.assertEqual(allowed.status_code, 200)

    def test_custom_loopback_binds_initialize_without_trusting_supplied_hosts(self):
        for host, authority in (("127.0.0.2", "127.0.0.2"), ("::1", "[::1]")):
            with self.subTest(host=host), patch.dict(os.environ, {"MIKAZUKI_BIND_HOST": host}):
                base_url = f"http://{authority}:28473"
                with TestClient(self.app, base_url=base_url, client=(host, 50000)) as client:
                    status = client.get("/api/v2/settings/mcp").json()
                    self.assertTrue(status["running"])
                    self.assertEqual(status["endpoint"], base_url + "/mcp/")
                    self.assertEqual(initialize(client)["protocolVersion"], PROTOCOL_VERSION)
                    self.assertEqual(rpc(client, "tools/list", headers={"Origin": base_url}).status_code, 200)
                    self.assertEqual(rpc(client, "tools/list", headers={"Host": "127.0.0.3:28473"}).status_code, 421)
                    self.assertEqual(rpc(client, "tools/list", headers={"Origin": "http://127.0.0.3:28473"}).status_code, 403)

    def test_binding_status_does_not_advertise_unreachable_loopback_endpoint(self):
        cases = (
            ("192.0.2.10", "", False),
            ("0.0.0.0", "http://127.0.0.1:28473/mcp/", True),
            ("::", "http://[::1]:28473/mcp/", True),
        )
        for bind_host, endpoint, running in cases:
            with self.subTest(bind_host=bind_host), patch.dict(os.environ, {"MIKAZUKI_BIND_HOST": bind_host}):
                with local_client(self.app) as client:
                    status = client.get("/api/v2/settings/mcp").json()
                    self.assertTrue(status["enabled"])
                    self.assertEqual(status["running"], running)
                    self.assertEqual(status["endpoint"], endpoint)
                    if running:
                        self.assertIsNone(status["error"])
                    else:
                        self.assertIn("127.0.0.1", status["error"])
                    self.assertEqual(client.get("/api/v2/health").json()["status"], "ok")

    def test_startup_failure_keeps_settings_and_health_available(self):
        with patch("mikazuki.mcp.server.build_server", side_effect=RuntimeError("fixture SDK failure")):
            with local_client(self.app) as client:
                settings = client.get("/api/v2/settings/mcp").json()
                self.assertTrue(settings["enabled"])
                self.assertFalse(settings["running"])
                self.assertIn("fixture SDK failure", settings["error"])
                self.assertEqual(rpc(client, "tools/list").status_code, 503)
                self.assertEqual(client.get("/api/v2/health").json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
