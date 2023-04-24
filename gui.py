import os
import json
import toml
import time
import uvicorn
import subprocess
import webbrowser
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
from threading import Lock

app = FastAPI()

lock = Lock()


def run_train(toml_path: str):
    print(f"Training started with config file / 训练开始，使用配置文件: {toml_path}")
    args = [
        "accelerate", "launch", "--num_cpu_threads_per_process", "8",
        "./sd-scripts/train_network.py",
        "--config_file", toml_path,
    ]
    try:
        result = subprocess.run(args, shell=True, env=os.environ)
        if result.returncode != 0:
            print(f"Training failed / 训练失败")
        else:
            print(f"Training finished / 训练完成")
    except Exception as e:
        print(f"An error occurred when training / 创建训练进程时出现致命错误: {e}")
    finally:
        lock.release()


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

@app.middleware("http")
async def add_cache_control_header(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "max-age=0"
    return response

@app.get("/")
async def index():
    return FileResponse("./frontend/dist/index.html")


app.mount("/", StaticFiles(directory="frontend/dist"), name="static")

if __name__ == "__main__":
    print("Server started at http://127.0.0.1:28000")
    webbrowser.open(f"http://127.0.0.1:28000")
    uvicorn.run(app, host="127.0.0.1", port=28000, log_level="error")
