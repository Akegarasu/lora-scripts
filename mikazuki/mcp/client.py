from __future__ import annotations

import base64
import json as json_module
from typing import Any
from urllib.parse import urlsplit

import httpx
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ImageContent


class BackendClient:
    """Bounded HTTP calls to one backend, without retries or environment proxies."""

    MAX_JSON_BYTES = 16 * 1024 * 1024
    MAX_IMAGE_BYTES = 16 * 1024 * 1024

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:28000",
        *,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be an HTTP(S) origin, e.g. http://127.0.0.1:28000")
        if not 0 < timeout <= 600:
            raise ValueError("timeout must be greater than 0 and at most 600 seconds")
        self.base_url = base_url.rstrip("/")
        self._owned = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout, trust_env=False, follow_redirects=False,
        )

    async def close(self) -> None:
        if self._owned:
            await self._client.aclose()

    async def _read(
        self, method: str, path: str, *, params: dict | None = None,
        json: Any = None, max_bytes: int,
    ) -> tuple[bytes, str]:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("backend path must be an absolute API path")
        try:
            async with self._client.stream(
                method, self.base_url + path, params=params, json=json,
            ) as response:
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > max_bytes:
                        raise ToolError("Backend response exceeds 16 MiB; narrow the query or read a thumbnail." + _uncertain_action(method))
                if not 200 <= response.status_code < 300:
                    detail = bytes(chunks).decode("utf-8", errors="replace")[:16000]
                    raise ToolError(f"Backend HTTP {response.status_code}: {detail}")
                return bytes(chunks), response.headers.get("content-type", "").split(";", 1)[0].lower()
        except httpx.RequestError as exc:
            raise ToolError(
                f"Cannot reach Mikazuki at {self.base_url}: {type(exc).__name__}. "
                "Start one backend process and check its address." + _uncertain_action(method)
            ) from exc

    async def request(
        self, method: str, path: str, *, params: dict | None = None, json: Any = None,
    ) -> dict:
        data, _ = await self._read(method, path, params=params, json=json, max_bytes=self.MAX_JSON_BYTES)
        try:
            payload = json_module.loads(data)
        except (ValueError, UnicodeError) as exc:
            raise ToolError("Backend returned non-JSON content; check the backend URL and version." + _uncertain_action(method)) from exc
        if not isinstance(payload, dict):
            raise ToolError("Backend returned an unexpected JSON shape (expected object)." + _uncertain_action(method))
        return payload

    async def image(self, path: str, *, params: dict | None = None) -> ImageContent:
        data, media_type = await self._read("GET", path, params=params, max_bytes=self.MAX_IMAGE_BYTES)
        if media_type not in {
            "image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp", "image/avif",
        }:
            raise ToolError(f"Backend did not return a supported image: {media_type}")
        return ImageContent(type="image", data=base64.b64encode(data).decode("ascii"), mimeType=media_type)


def _uncertain_action(method: str) -> str:
    return (
        " The action may have been accepted; inspect the job queue or change history before retrying."
        if method != "GET" else ""
    )
