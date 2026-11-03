"""Backend preferences shared by all browser clients."""

import json
import threading
from pathlib import Path

from mikazuki.storage.paths import app_root


class AppSettings:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else app_root() / "config" / "app-settings.json"
        self._lock = threading.RLock()

    def _read(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        if not isinstance(value, dict):
            raise ValueError("app-settings.json must contain an object")
        mcp = value.get("mcp", {})
        if not isinstance(mcp, dict) or type(mcp.get("enabled", True)) is not bool:
            raise ValueError("app-settings.json mcp.enabled must be a boolean")
        return value

    def mcp_enabled(self) -> bool:
        with self._lock:
            return self._read().get("mcp", {}).get("enabled", True)

    def set_mcp_enabled(self, enabled: bool) -> None:
        with self._lock:
            value = self._read()
            value.setdefault("mcp", {})["enabled"] = enabled
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".json.tmp")
            try:
                temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                temporary.replace(self.path)
            finally:
                temporary.unlink(missing_ok=True)
