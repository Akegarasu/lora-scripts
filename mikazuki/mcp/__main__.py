import argparse
import os

from .server import build_server


def main() -> None:
    parser = argparse.ArgumentParser(description="LoRA training MCP (stdio); connects to one existing backend.")
    parser.add_argument("--base-url", default=os.environ.get("MIKAZUKI_BASE_URL", "http://127.0.0.1:28000"))
    parser.add_argument("--timeout", type=float, default=30.0, help="Backend HTTP timeout in seconds (max 600).")
    args = parser.parse_args()
    build_server(args.base_url, timeout=args.timeout).run(transport="stdio")


if __name__ == "__main__":
    main()
