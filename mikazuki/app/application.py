import os

import starlette.responses as starlette_responses
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mikazuki.app.api import router as api_router
from mikazuki.app.proxy import router as proxy_router

app = FastAPI()
app.include_router(proxy_router)


# fix mimetype error in some fucking systems
_origin_guess_type = starlette_responses.guess_type


def _hooked_guess_type(*args, **kwargs):
    url = args[0]
    r = _origin_guess_type(*args, **kwargs)
    if url.endswith(".js"):
        r = ("application/javascript", None)
    elif url.endswith(".css"):
        r = ("text/css", None)
    return r


starlette_responses.guess_type = _hooked_guess_type


cors_config = os.environ.get("MIKAZUKI_APP_CORS", "")
if cors_config != "":
    if cors_config == "1":
        cors_config = ["http://localhost:8004"]
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
    response.headers["Cache-Control"] = "max-age=0"
    return response

app.include_router(api_router, prefix="/api")


@app.get("/")
async def index():
    return FileResponse("./frontend/dist/index.html")


app.mount("/", StaticFiles(directory="frontend/dist"), name="static")
