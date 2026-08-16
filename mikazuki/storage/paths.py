from pathlib import Path

from mikazuki.launch_utils import base_dir_path


def app_root() -> Path:
    return base_dir_path()


def runs_dir() -> Path:
    return app_root() / "config" / "runs"


def jobs_log_dir() -> Path:
    return app_root() / "logs" / "jobs"


def caption_db_path() -> Path:
    return app_root() / "config" / "caption-jobs.db"
