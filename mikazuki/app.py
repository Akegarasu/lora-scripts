import json
import os
import shlex
import subprocess
import sys
from datetime import datetime
from threading import Lock

import starlette.responses as starlette_responses
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import mikazuki.utils as utils
import toml
from mikazuki.models import TaggerInterrogateRequest
from mikazuki.tagger.interrogator import (available_interrogators,
                                          on_interrogate)

app = FastAPI()
lock = Lock()
avaliable_scripts = [
    "networks/extract_lora_from_models.py",
    "networks/extract_lora_from_dylora.py"
]
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


def run_train(toml_path: str):
    print(f"Training started with config file / 训练开始，使用配置文件: {toml_path}")
    args = [
        sys.executable, "-m", "accelerate.commands.launch", "--num_cpu_threads_per_process", "8",
        "./sd-scripts/train_network.py",
        "--config_file", toml_path,
    ]
    try:
        result = subprocess.run(args, env=os.environ)
        if result.returncode != 0:
            print(f"Training failed / 训练失败")
        else:
            print(f"Training finished / 训练完成")
    except Exception as e:
        print(f"An error occurred when training / 创建训练进程时出现致命错误: {e}")
    finally:
        lock.release()


@app.middleware("http")
async def add_cache_control_header(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "max-age=0"
    return response


@app.post("/api/run")
async def create_toml_file(request: Request, background_tasks: BackgroundTasks):
    acquired = lock.acquire(blocking=False)

    if not acquired:
        print("Training is already running / 已有正在进行的训练")
        return {"status": "fail", "detail": "Training is already running"}

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    toml_file = os.path.join(os.getcwd(), f"toml", "autosave", f"{timestamp}.toml")
    toml_data = await request.body()
    j = json.loads(toml_data.decode("utf-8"))
    with open(toml_file, "w") as f:
        f.write(toml.dumps(j))
    background_tasks.add_task(run_train, toml_file)
    return {"status": "success"}


@app.post("/api/run_script")
async def run_script(request: Request, background_tasks: BackgroundTasks):
    paras = await request.body()
    j = json.loads(paras.decode("utf-8"))
    script_name = j["script_name"]
    if script_name not in avaliable_scripts:
        return {"status": "fail"}
    del j["script_name"]
    result = []
    for k, v in j.items():
        result.append(f"--{k}")
        if not isinstance(v, bool):
            value = str(v)
            if " " in value:
                value = f'"{v}"'
            result.append(value)
    script_args = " ".join(result)
    cmd = f"{utils.python_bin} {script_name} {script_args}"
    background_tasks.add_task(utils.run, cmd)
    return {"status": "success"}


@app.post("/api/interrogate")
async def run_interrogate(req: TaggerInterrogateRequest, background_tasks: BackgroundTasks):
    interrogator = available_interrogators.get(req.interrogator_model, available_interrogators["wd14-convnextv2-v2"])
    background_tasks.add_task(on_interrogate,
                              image=None,
                              batch_input_glob=req.path,
                              batch_input_recursive=False,
                              batch_output_dir="",
                              batch_output_filename_format="[name].[output_extension]",
                              batch_output_action_on_conflict=req.batch_output_action_on_conflict,
                              batch_remove_duplicated_tag=True,
                              batch_output_save_json=False,
                              interrogator=interrogator,
                              threshold=req.threshold,
                              additional_tags=req.additional_tags,
                              exclude_tags=req.exclude_tags,
                              sort_by_alphabetical_order=False,
                              add_confident_as_weight=False,
                              replace_underscore=req.replace_underscore,
                              replace_underscore_excludes=req.replace_underscore_excludes,
                              escape_tag=req.escape_tag,
                              unload_model_after_running=True
                              )
    return {"status": "success"}


@app.get("/")
async def index():
    return FileResponse("./frontend/dist/index.html")


app.mount("/", StaticFiles(directory="frontend/dist"), name="static")

