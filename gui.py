import argparse
import os
import shutil
import subprocess
import sys
import webbrowser

import uvicorn
from typing import List

# from mikazuki.app import app

parser = argparse.ArgumentParser(description="GUI for stable diffusion training")
parser.add_argument("--host", type=str, default="127.0.0.1")
parser.add_argument("--port", type=int, default=28000, help="Port to run the server on")
parser.add_argument("--tensorboard-host", type=str, default="127.0.0.1", help="Port to run the tensorboard")
parser.add_argument("--tensorboard-port", type=int, default=6006, help="Port to run the tensorboard")
parser.add_argument("--dev", action="store_true")


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
    subprocess.Popen([sys.executable, "-m", "tensorboard.main", "--logdir", "logs", "--host", args.tensorboard_host, "--port", str(args.tensorboard_port)])


def check_dirs(dirs: List):
    for d in dirs:
        if not os.path.exists(d):
            os.makedirs(d)


if __name__ == "__main__":
    args, _ = parser.parse_known_args()
    remove_warnings()
    prepare_frontend()
    run_tensorboard()
    check_dirs(["toml/autosave", "logs"])
    print(f"Server started at http://{args.host}:{args.port}")
    if not args.dev:
        webbrowser.open(f"http://{args.host}:{args.port}")
    uvicorn.run("mikazuki.app:app", host=args.host, port=args.port, log_level="error")
