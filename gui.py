import argparse
import os
import platform
import sys

from mikazuki.launch_utils import (
    base_dir_path,
    check_port_available,
    find_available_port,
    prepare_environment,
)
from mikazuki.log import log


parser = argparse.ArgumentParser(description="GUI for stable diffusion training")
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=28000, help="Port to run the server on")
parser.add_argument("--listen", action="store_true")
parser.add_argument("--skip-prepare-environment", action="store_true")
parser.add_argument("--skip-prepare-onnxruntime", action="store_true")
parser.add_argument("--disable-auto-mirror", action="store_true")
parser.add_argument("--dev", action="store_true")


def launch() -> None:
    log.info("Starting SD-Trainer Mikazuki GUI...")
    log.info(f"Base directory: {base_dir_path()}, Working directory: {os.getcwd()}")
    log.info(f"{platform.system()} Python {platform.python_version()} {sys.executable}")

    if not args.skip_prepare_environment:
        prepare_environment(
            disable_auto_mirror=args.disable_auto_mirror,
            prepare_onnxruntime=not args.skip_prepare_onnxruntime,
        )

    if not check_port_available(args.port):
        available_port = find_available_port(30000, 30020)
        if available_port is None:
            raise RuntimeError("No available port found")
        args.port = available_port

    os.environ["MIKAZUKI_HOST"] = args.host
    os.environ["MIKAZUKI_PORT"] = str(args.port)
    os.environ["MIKAZUKI_DEV"] = "1" if args.dev else "0"

    if args.listen:
        args.host = "0.0.0.0"

    import uvicorn

    log.info(f"Server started at http://{args.host}:{args.port}")
    uvicorn.run(
        "mikazuki.app:app",
        host=args.host,
        port=args.port,
        log_level="error",
        reload=args.dev,
    )


if __name__ == "__main__":
    args = parser.parse_args()
    launch()
