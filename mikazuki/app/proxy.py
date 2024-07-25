import asyncio
import os

import httpx
import starlette
import websockets
from fastapi import APIRouter, Request, WebSocket
from httpx import ConnectError
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import PlainTextResponse, StreamingResponse

from mikazuki.log import log

router = APIRouter()


def reverse_proxy_maker(url_type: str, full_path: bool = False):
    if url_type == "tensorboard":
        host = os.environ.get("MIKAZUKI_TENSORBOARD_HOST", "127.0.0.1")
        port = os.environ.get("MIKAZUKI_TENSORBOARD_PORT", "6006")
    elif url_type == "tageditor":
        host = os.environ.get("MIKAZUKI_TAGEDITOR_HOST", "127.0.0.1")
        port = os.environ.get("MIKAZUKI_TAGEDITOR_PORT", "28001")

    client = httpx.AsyncClient(base_url=f"http://{host}:{port}/", proxies={}, trust_env=False, timeout=360)

    async def _reverse_proxy(request: Request):
        if full_path:
            url = httpx.URL(path=request.url.path, query=request.url.query.encode("utf-8"))
        else:
            url = httpx.URL(
                path=request.path_params.get("path", ""),
                query=request.url.query.encode("utf-8")
            )
        rp_req = client.build_request(
            request.method, url,
            headers=request.headers.raw,
            content=request.stream() if request.method != "GET" else None
        )
        try:
            rp_resp = await client.send(rp_req, stream=True)
        except ConnectError:
            return PlainTextResponse(
                content="The requested service not started yet or service started fail. This may cost a while when you first time startup\n请求的服务尚未启动或启动失败。若是第一次启动，可能需要等待一段时间后再刷新网页。",
                status_code=502
            )
        return StreamingResponse(
            rp_resp.aiter_raw(),
            status_code=rp_resp.status_code,
            headers=rp_resp.headers,
            background=BackgroundTask(rp_resp.aclose),
        )

    return _reverse_proxy


async def proxy_ws_forward(ws_a: WebSocket, ws_b: websockets.WebSocketClientProtocol):
    while True:
        try:
            data = await ws_a.receive_text()
            await ws_b.send(data)
        except starlette.websockets.WebSocketDisconnect as e:
            break
        except Exception as e:
            log.error(f"Error when proxy data client -> backend: {e}")
            break


async def proxy_ws_reverse(ws_a: WebSocket, ws_b: websockets.WebSocketClientProtocol):
    while True:
        try:
            data = await ws_b.recv()
            await ws_a.send_text(data)
        except websockets.exceptions.ConnectionClosedOK as e:
            break
        except Exception as e:
            log.error(f"Error when proxy data backend -> client: {e}")
            break


@router.websocket("/proxy/tageditor/queue/join")
async def websocket_a(ws_a: WebSocket):
    # for temp use
    ws_b_uri = "ws://127.0.0.1:28001/queue/join"
    await ws_a.accept()
    async with websockets.connect(ws_b_uri, timeout=360, ping_timeout=None) as ws_b_client:
        fwd_task = asyncio.create_task(proxy_ws_forward(ws_a, ws_b_client))
        rev_task = asyncio.create_task(proxy_ws_reverse(ws_a, ws_b_client))
        await asyncio.gather(fwd_task, rev_task)

router.add_route("/proxy/tensorboard/{path:path}", reverse_proxy_maker("tensorboard"), ["GET", "POST"])
router.add_route("/font-roboto/{path:path}", reverse_proxy_maker("tensorboard", full_path=True), ["GET", "POST"])
router.add_route("/proxy/tageditor/{path:path}", reverse_proxy_maker("tageditor"), ["GET", "POST"])
