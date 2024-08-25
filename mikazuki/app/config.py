import os
import json
from pathlib import Path
from mikazuki.log import log

class Config:

    def __init__(self, path: str):
        self.path = path
        self._stored = {}
        self._default = {
            "last_path": "",
            "saved_params": {}
        }
        self.lock = False

    def load_config(self):
        log.info(f"Loading config from {self.path}")
        if not os.path.exists(self.path):
            self._stored = self._default
            self.save_config()
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._stored = json.load(f)
        except Exception as e:
            log.error(f"Error loading config: {e}")
            self._stored = self._default
            return

    def save_config(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._stored, f, indent=4, ensure_ascii=False)
        except Exception as e:
            log.error(f"Error saving config: {e}")

    def __getitem__(self, key):

        return self._stored.get(key, None)

    def __setitem__(self, key, value):
        self._stored[key] = value


app_config = Config(Path(__file__).parents[2].absolute() / "assets" / "config.json")
