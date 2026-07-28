from pathlib import PurePosixPath


STATIC_PREFIXES = ("assets/", "font-roboto/")


def should_fallback_to_spa(path: str, status_code: int) -> bool:
    """Return whether a missing request is a client-side navigation route."""
    normalized = str(PurePosixPath(path.lstrip("/")))
    if status_code != 404 or normalized.startswith(STATIC_PREFIXES):
        return False
    return not PurePosixPath(normalized).suffix or normalized.endswith(".html")
