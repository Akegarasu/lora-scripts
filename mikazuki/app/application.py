import mimetypes
import os
import sys
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from mikazuki.app.api_v2 import router as api_v2_router
from mikazuki.app.caption_api import router as caption_api_router
from mikazuki.app.tag_editor_api import router as tag_editor_api_router

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
FRONTEND_DIST = Path("frontend/dist")


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as ex:
            if ex.status_code == 404:
                return await super().get_response("index.html", scope)
            else:
                raise ex


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if sys.platform == "win32" and os.environ.get("MIKAZUKI_DEV", "0") != "1":
        webbrowser.open(f'http://{os.environ["MIKAZUKI_HOST"]}:{os.environ["MIKAZUKI_PORT"]}')
    yield


app = FastAPI(lifespan=lifespan)


cors_config = os.environ.get("MIKAZUKI_APP_CORS", "")
if cors_config != "":
    if cors_config == "1":
        cors_config = ["http://localhost:8004", "*"]
    else:
        cors_config = cors_config.split(";")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_config,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def add_cache_control_header(request, call_next):
    response = await call_next(request)
    if "Cache-Control" not in response.headers:
        response.headers["Cache-Control"] = "max-age=0"
    return response

app.include_router(api_v2_router, prefix="/api/v2")
app.include_router(caption_api_router, prefix="/api/v2/caption")
app.include_router(tag_editor_api_router, prefix="/api/v2/tag-editor")


@app.get("/")
async def index():
    index_file = FRONTEND_DIST / "index.html"
    if not index_file.exists():
        return JSONResponse(
            status_code=503,
            content={"status": "frontend_not_built", "message": "frontend/dist/index.html does not exist"},
        )
    return FileResponse(index_file)


@app.get("/favicon.ico", response_class=FileResponse)
async def favicon():
    return FileResponse("assets/favicon.ico")

if FRONTEND_DIST.exists():
    app.mount("/", SPAStaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")
