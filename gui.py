import argparse
import subprocess
import sys
import webbrowser

import uvicorn

from mikazuki.launch_utils import (check_dirs, prepare_frontend,
                                   remove_warnings, smart_pip_mirror,
                                   validate_requirements)
from mikazuki.log import log, setup_logging

parser = argparse.ArgumentParser(description="GUI for stable diffusion training")
parser.add_argument("--host", type=str, default="127.0.0.1")
parser.add_argument("--port", type=int, default=28000, help="Port to run the server on")
parser.add_argument("--skip-prepare-environment", action="store_true")
parser.add_argument("--tensorboard-host", type=str, default="127.0.0.1", help="Port to run the tensorboard")
parser.add_argument("--tensorboard-port", type=int, default=6006, help="Port to run the tensorboard")
parser.add_argument("--dev", action="store_true")


def run_tensorboard():
    log.info("Starting tensorboard...")
    subprocess.Popen([sys.executable, "-m", "tensorboard.main", "--logdir", "logs",
                     "--host", args.tensorboard_host, "--port", str(args.tensorboard_port)])


if __name__ == "__main__":
    args, _ = parser.parse_known_args()

    remove_warnings()
    setup_logging()
    smart_pip_mirror()
    prepare_frontend()
    check_dirs(["toml/autosave", "logs"])
    if not args.skip_prepare_environment:
        validate_requirements("requirements.txt")

    run_tensorboard()

    log.info(f"Server started at http://{args.host}:{args.port}")
    if not args.dev:
        webbrowser.open(f"http://{args.host}:{args.port}")
    uvicorn.run("mikazuki.app:app", host=args.host, port=args.port, log_level="error")
