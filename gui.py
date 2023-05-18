import argparse
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from datetime import datetime
from threading import Lock

import uvicorn
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import starlette.responses as starlette_responses
import toml

parser = argparse.ArgumentParser(description="GUI for stable diffusion training")
parser.add_argument("--host", type=str, default="127.0.0.1")
parser.add_argument("--port", type=int, default=28000, help="Port to run the server on")

def find_windows_git():
    possible_paths = ["git\\bin\\git.exe", "git\\cmd\\git.exe", "Git\\mingw64\\libexec\\git-core\\git.exe"]
    for path in possible_paths:
        if os.path.exists(path):
            return path

def prepare_frontend():
    if not os.path.exists("./frontend/dist"):
        print("Frontend not found, try clone...")
        print("Checking git installation...")
        if not shutil.which("git"):
            if sys.platform == "win32":
                git_path = find_windows_git()

                if git_path is not None:
                    print(f"Git not found, but found git in {git_path}, add it to PATH")
                    os.environ["PATH"] += os.pathsep + os.path.dirname(git_path)
                    return
            else:
                print("Git not found, please install git first")
                sys.exit(1)
        subprocess.run(["git", "submodule", "init"])
        subprocess.run(["git", "submodule", "update"])

def remove_warnings():
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
    if sys.platform == "win32":
        # disable triton on windows
        os.environ["XFORMERS_FORCE_DISABLE_TRITON"] = "1"
    os.environ["BITSANDBYTES_NOWELCOME"] = "1"
    os.environ["PYTHONWARNINGS"] = "ignore::UserWarning"

def run_tensorboard():
    print("Starting tensorboard...")
    subprocess.Popen([sys.executable, "-m", "tensorboard.main", "--logdir", "logs", "--port", "6006"])

remove_warnings()
prepare_frontend()

app = FastAPI()
lock = Lock()

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
    toml_file = f"toml/{timestamp}.toml"
    toml_data = await request.body()
    j = json.loads(toml_data.decode("utf-8"))
    with open(toml_file, "w") as f:
        f.write(toml.dumps(j))
    background_tasks.add_task(run_train, toml_file)
    return {"status": "success"}

@app.get("/")
async def index():
    return FileResponse("./frontend/dist/index.html")


app.mount("/", StaticFiles(directory="frontend/dist"), name="static")

if __name__ == "__main__":
    args, _ = parser.parse_known_args()
    run_tensorboard()
    print(f"Server started at http://{args.host}:{args.port}")
    webbrowser.open(f"http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="error")
