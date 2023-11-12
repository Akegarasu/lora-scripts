import os
import httpx
from fastapi import Request
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import StreamingResponse
from fastapi import APIRouter

router = APIRouter()

def reverse_proxy_maker(url_type: str):
    if url_type == "tensorboard":
        host = os.environ.get("MIKAZUKI_TENSORBOARD_HOST", "127.0.0.1")
        port = os.environ.get("MIKAZUKI_TENSORBOARD_PORT", "6006")
        client = httpx.AsyncClient(base_url=f"http://{host}:{port}/")
    elif url_type == "tageditor":
        client = httpx.AsyncClient(base_url="http://127.0.0.1:28001/")

    async def _reverse_proxy(request: Request):
        url = httpx.URL(path=request.path_params.get("path", ""),
                        query=request.url.query.encode("utf-8"))
        rp_req = client.build_request(request.method, url,
                                    headers=request.headers.raw,
                                    content=request.stream())
        rp_resp = await client.send(rp_req, stream=True)
        return StreamingResponse(
            rp_resp.aiter_raw(),
            status_code=rp_resp.status_code,
            headers=rp_resp.headers,
            background=BackgroundTask(rp_resp.aclose),
        )

    return _reverse_proxy


router.add_route("/tensorboard/{path:path}", reverse_proxy_maker("tensorboard"), ["GET", "POST"])
router.add_route("/tageditor/{path:path}", reverse_proxy_maker("tageditor"), ["GET", "POST"])
