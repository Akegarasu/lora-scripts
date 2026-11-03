"""Streamable HTTP MCP attached to the GUI's existing ASGI application."""

import ipaddress
import os
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from starlette.responses import JSONResponse, Response

from mikazuki.log import log
from mikazuki.settings import AppSettings


class MCPService:
    def __init__(self, app, *, settings_path: Path | None = None) -> None:
        self.app = app
        self.settings = AppSettings(settings_path)
        self.enabled = True
        self.ready = False
        self.error: str | None = None
        self._http_app = None
        self._security = None
        self._bind_host: str | None = None

    @asynccontextmanager
    async def lifespan(self):
        # Rebuild per application lifespan: SDK session managers are single-use.
        self.ready = False
        self.error = None
        self._bind_host = os.environ.get("MIKAZUKI_BIND_HOST")
        try:
            self.enabled = self.settings.mcp_enabled()
        except (OSError, ValueError) as exc:
            self.enabled = False
            self.error = f"无法读取 MCP 设置：{exc}"

        async with AsyncExitStack() as stack:
            try:
                import httpx
                from mcp.server.transport_security import TransportSecuritySettings

                from .client import BackendClient
                from .server import build_server

                # Internal API calls stay in this process and do not depend on GUI
                # bind address, fallback port, network proxies or a second runner.
                http = await stack.enter_async_context(httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=self.app),
                    timeout=30.0, trust_env=False, follow_redirects=False,
                ))
                backend = BackendClient("http://127.0.0.1", client=http)
                server = build_server(client=backend)
                server.settings.stateless_http = True
                server.settings.json_response = True
                server.settings.streamable_http_path = "/"
                server.settings.transport_security = TransportSecuritySettings(
                    allowed_hosts=["127.0.0.1", "localhost", "[::1]", "127.0.0.1:*", "localhost:*", "[::1]:*"],
                    allowed_origins=["http://127.0.0.1", "http://localhost", "http://[::1]", "http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
                )
                self._security = server.settings.transport_security
                self._http_app = server.streamable_http_app()
                await stack.enter_async_context(server.session_manager.run())
                self.ready = True
            except Exception as exc:
                # A broken optional environment must not prevent the GUI from opening
                # its settings page. Normal project installation includes the SDK.
                self.error = f"MCP 启动失败：{exc}。请安装 requirements/mcp.txt 后重启服务。"
                log.warning(self.error)
                await stack.aclose()

            try:
                yield
            finally:
                self.ready = False
                self._http_app = None
                self._security = None

    def set_enabled(self, enabled: bool) -> None:
        # Persist before changing the live gate; a failed write must not flip it.
        self.settings.set_mcp_enabled(enabled)
        self.enabled = enabled
        if self.ready:
            # A repaired settings file no longer blocks a successfully started SDK.
            self.error = None

    def status(self, request) -> dict:
        server = request.scope.get("server")
        port = server[1] if server and server[1] else request.url.port or 80
        host = self._bind_host or (server[0] if server else "127.0.0.1")
        if host == "0.0.0.0":
            host = "127.0.0.1"
        elif host == "::":
            host = "::1"
        supported = host == "localhost" or _loopback(host)
        display_host = f"[{host}]" if ":" in host else host
        error = self.error
        if not supported and not error:
            error = "MCP 需要本机回环监听地址；请使用 --host 127.0.0.1 或 --listen 启动 GUI。"
        return {
            "enabled": self.enabled,
            "running": self.enabled and self.ready and error is None,
            "transport": "streamable-http",
            "endpoint": f"http://{display_host}:{port}/mcp/" if supported else "",
            "error": error,
        }

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            return
        peer = (scope.get("client") or ("", 0))[0]
        if not _loopback(peer):
            response = JSONResponse({"detail": "MCP 仅允许本机连接。"}, status_code=403)
        elif not self.enabled:
            response = JSONResponse({"detail": "MCP 已关闭，可在设置 → 后端服务中开启。"}, status_code=503)
        elif not self.ready or self.error:
            response = JSONResponse({"detail": self.error or "MCP 尚未就绪。"}, status_code=503)
        elif scope["method"] != "POST":
            # This server uses JSON request/response only. Do not leave GET SSE
            # streams alive across a settings toggle or application shutdown.
            response = Response(status_code=405, headers={"Allow": "POST"})
        else:
            # Trust the actual accepted socket address, never a supplied Host or
            # Origin header. This also supports other valid loopback binds.
            bound_host = (scope.get("server") or ("", 0))[0]
            if self._security is not None and _loopback(bound_host):
                authority = f"[{bound_host}]" if ":" in bound_host else bound_host
                for allowed in (authority, f"{authority}:*"):
                    if allowed not in self._security.allowed_hosts:
                        self._security.allowed_hosts.append(allowed)
                        self._security.allowed_origins.append(f"http://{allowed}")
            await self._http_app(scope, receive, send)
            return
        await response(scope, receive, send)


def _loopback(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
        return (getattr(address, "ipv4_mapped", None) or address).is_loopback
    except ValueError:
        return False
