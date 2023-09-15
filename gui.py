import argparse
import subprocess
import sys
import webbrowser
import platform

from mikazuki.utils import check_run
from mikazuki.launch_utils import (check_dirs, prepare_frontend,
                                   remove_warnings, smart_pip_mirror,
                                   validate_requirements, setup_windows_bitsandbytes)
from mikazuki.log import log

parser = argparse.ArgumentParser(description="GUI for stable diffusion training")
parser.add_argument("--host", type=str, default="127.0.0.1")
parser.add_argument("--port", type=int, default=28000, help="Port to run the server on")
parser.add_argument("--listen", action="store_true")
parser.add_argument("--skip-prepare-environment", action="store_true")
parser.add_argument("--disable-tensorboard", action="store_true")
parser.add_argument("--tensorboard-host", type=str, default="127.0.0.1", help="Port to run the tensorboard")
parser.add_argument("--tensorboard-port", type=int, default=6006, help="Port to run the tensorboard")
parser.add_argument("--dev", action="store_true")


def run_tensorboard():
    log.info("Starting tensorboard...")
    subprocess.Popen([sys.executable, "-m", "tensorboard.main", "--logdir", "logs",
                     "--host", args.tensorboard_host, "--port", str(args.tensorboard_port)])


if __name__ == "__main__":
    args, _ = parser.parse_known_args()
    log.info(f'{platform.system()} Python {platform.python_version()} {sys.executable}')

    remove_warnings()
    smart_pip_mirror()

    if not args.skip_prepare_environment:
        prepare_frontend()
        check_dirs(["config/autosave", "logs"])
        if not check_run("mikazuki/scripts/torch_check.py"):
            sys.exit(1)
        requirements_file = "requirements_win.txt" if sys.platform == "win32" else "requirements.txt"
        validate_requirements(requirements_file)
        setup_windows_bitsandbytes()

    if not args.disable_tensorboard:
        run_tensorboard()

    if args.listen:
        args.host = "0.0.0.0"
        args.tensorboard_host = "0.0.0.0"
        
    import uvicorn
    log.info(f"Server started at http://{args.host}:{args.port}")
    if not args.dev and sys.platform == "win32":
        webbrowser.open(f"http://{args.host}:{args.port}")
    uvicorn.run("mikazuki.app:app", host=args.host, port=args.port, log_level="error")
