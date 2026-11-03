import base64
import json
import unittest

import httpx

from mikazuki.mcp.client import BackendClient


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6"
    "lZQAAAAASUVORK5CYII="
)


class BackendClientTests(unittest.IsolatedAsyncioTestCase):
    async def make_backend(self, handler):
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http.aclose)
        backend = BackendClient("http://127.0.0.1:28000", client=http)
        self.addAsyncCleanup(backend.close)
        return backend

    async def test_http_validation_details_are_preserved_and_submit_is_not_retried(self):
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(422, json={"detail": [{"loc": ["body", "trainerId"], "msg": "unknown trainer"}]})

        backend = await self.make_backend(handle)
        with self.assertRaises(Exception) as raised:
            await backend.request("POST", "/api/v2/jobs", json={"trainerId": "unknown"})
        message = str(raised.exception)
        self.assertIn("422", message)
        self.assertIn("trainerId", message)
        self.assertIn("unknown trainer", message)
        self.assertEqual(len(requests), 1)

    async def test_timed_out_submission_is_not_retried(self):
        requests = []

        def handle(request):
            requests.append(request)
            raise httpx.ReadTimeout("timeout", request=request)

        backend = await self.make_backend(handle)
        with self.assertRaises(Exception):
            await backend.request("POST", "/api/v2/jobs", json={"trainerId": "sd.lora"})
        self.assertEqual(len(requests), 1)

    async def test_image_is_returned_as_mcp_image_content(self):
        backend = await self.make_backend(
            lambda request: httpx.Response(200, content=PNG, headers={"Content-Type": "image/png"})
        )
        image = await backend.image("/api/v2/files/content", params={"path": "sample.png"})
        self.assertEqual(image.type, "image")
        self.assertEqual(image.mimeType, "image/png")
        self.assertEqual(base64.b64decode(image.data), PNG)

    async def test_image_endpoint_rejects_html_instead_of_encoding_error_page(self):
        backend = await self.make_backend(
            lambda request: httpx.Response(200, text="<html>wrong server</html>", headers={"Content-Type": "text/html"})
        )
        with self.assertRaises(Exception):
            await backend.image("/api/v2/files/content", params={"path": "sample.png"})

    async def test_json_endpoint_rejects_frontend_html(self):
        backend = await self.make_backend(
            lambda request: httpx.Response(200, text="<html>frontend</html>", headers={"Content-Type": "text/html"})
        )
        with self.assertRaises(Exception):
            await backend.request("GET", "/api/v2/health")

    async def test_backend_redirect_is_not_followed(self):
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(307, headers={"Location": "http://unrelated.example/private"})

        backend = await self.make_backend(handle)
        with self.assertRaises(Exception) as raised:
            await backend.request("GET", "/api/v2/health")
        self.assertIn("307", str(raised.exception))
        self.assertEqual(len(requests), 1)

    async def test_oversized_responses_fail_instead_of_flooding_context(self):
        backend = await self.make_backend(
            lambda request: httpx.Response(200, json={"text": "x" * 128})
        )
        backend.MAX_JSON_BYTES = 64
        with self.assertRaises(Exception) as raised:
            await backend.request("GET", "/api/v2/jobs")
        self.assertIn("exceeds", str(raised.exception))

    async def test_uncertain_mutation_responses_advise_inspection_before_retry(self):
        for content in (b"invalid JSON", b"[]", json.dumps({"text": "x" * 128}).encode()):
            with self.subTest(content=content[:20]):
                requests = []

                def handle(request):
                    requests.append(request)
                    return httpx.Response(200, content=content, headers={"Content-Type": "application/json"})

                backend = await self.make_backend(handle)
                backend.MAX_JSON_BYTES = 64
                with self.assertRaises(Exception) as raised:
                    await backend.request("POST", "/api/v2/jobs", json={"trainerId": "sd.lora"})
                self.assertIn("may have been accepted", str(raised.exception))
                self.assertIn("before retrying", str(raised.exception))
                self.assertEqual(len(requests), 1)

    async def test_request_preserves_unicode_json_and_query(self):
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(200, json={"ok": True})

        backend = await self.make_backend(handle)
        payload = {"trainerId": "sd.lora", "name": "角色一", "dataset": {"root": "train/角色"}}
        self.assertEqual(
            await backend.request("POST", "/api/v2/compile", params={"persist": False}, json=payload),
            {"ok": True},
        )
        request = requests[0]
        self.assertEqual(request.url.host, "127.0.0.1")
        self.assertEqual(request.url.path, "/api/v2/compile")
        self.assertEqual(request.url.params["persist"], "false")
        self.assertEqual(json.loads(request.content), payload)


if __name__ == "__main__":
    unittest.main()
