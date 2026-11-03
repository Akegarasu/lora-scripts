import asyncio
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mikazuki.tests.mcp.test_client import PNG


class MCPStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_discovery_calls_images_and_tool_errors(self):
        requests = []

        class BackendFixture(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                status = 200
                if self.path == "/api/v2/jobs/job_missing":
                    status = 404
                    body = json.dumps({"detail": "job not found"}).encode()
                    content_type = "application/json"
                elif self.path.startswith("/api/v2/files/content?"):
                    body = PNG
                    content_type = "image/png"
                else:
                    body = json.dumps({"status": "ok", "version": "fixture"}).encode()
                    content_type = "application/json"
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                pass

        backend = ThreadingHTTPServer(("127.0.0.1", 0), BackendFixture)
        worker = threading.Thread(target=backend.serve_forever, daemon=True)
        worker.start()
        root = Path(__file__).resolve().parents[3]
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mikazuki.mcp", "--base-url", f"http://127.0.0.1:{backend.server_port}"],
            cwd=str(root),
            env={
                "HTTP_PROXY": "http://127.0.0.1:1",
                "HTTPS_PROXY": "http://127.0.0.1:1",
                "ALL_PROXY": "http://127.0.0.1:1",
                "NO_PROXY": "",
                "PYTHONIOENCODING": "utf-8",
            },
        )
        try:
            with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr:
                with self.assertNoLogs("mcp.client.stdio", level="ERROR"), anyio.fail_after(30):
                    async with stdio_client(parameters, errlog=stderr) as (reader, writer):
                        async with ClientSession(reader, writer) as session:
                            initialized = await session.initialize()
                            self.assertIsNotNone(initialized.capabilities.tools)
                            tools = await session.list_tools()
                            self.assertIn("start_training", {tool.name for tool in tools.tools})
                            status = await session.call_tool("get_workspace_status", {})
                            self.assertFalse(status.isError)
                            self.assertIn("ok", " ".join(block.text for block in status.content if block.type == "text"))
                            image = await session.call_tool("read_output_image", {"path": "sample.png"})
                            self.assertFalse(image.isError)
                            self.assertTrue(any(block.type == "image" for block in image.content))
                            invalid = await session.call_tool("browse_files", {"limit": 0})
                            self.assertTrue(invalid.isError)
                            missing = await session.call_tool("get_training_job", {"job_id": "job_missing"})
                            self.assertTrue(missing.isError)
                            error_text = " ".join(block.text for block in missing.content if block.type == "text")
                            self.assertIn("404", error_text)
                            self.assertIn("job not found", error_text)
                stderr.seek(0)
                self.assertNotIn("Failed to parse JSONRPC message", stderr.read())
            self.assertIn("/api/v2/health", requests)
        finally:
            await asyncio.to_thread(backend.shutdown)
            backend.server_close()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
