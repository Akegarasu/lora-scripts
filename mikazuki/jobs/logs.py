from pathlib import Path
from typing import List, Tuple


def tail_log(path: str, tail: int = 500) -> Tuple[int, List[str]]:
    log_path = Path(path)
    if not log_path.exists():
        return 0, []

    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
        cursor = f.tell()

    if tail > 0:
        lines = lines[-tail:]
    return cursor, [line.rstrip("\r\n") for line in lines]


def read_log_from(path: str, cursor: int = 0) -> Tuple[int, List[str]]:
    log_path = Path(path)
    if not log_path.exists():
        return cursor, []

    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        f.seek(cursor)
        lines = f.readlines()
        next_cursor = f.tell()
    return next_cursor, [line.rstrip("\r\n") for line in lines]
