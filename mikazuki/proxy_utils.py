import os


def tageditor_ws_uri() -> str:
    host = os.environ.get("MIKAZUKI_TAGEDITOR_HOST", "127.0.0.1")
    port = os.environ.get("MIKAZUKI_TAGEDITOR_PORT", "28001")
    return f"ws://{host}:{port}/queue/join"
