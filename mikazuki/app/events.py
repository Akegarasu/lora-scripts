import json
from typing import Optional


SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def resolve_event_cursor(cursor: Optional[int], last_event_id: Optional[str]) -> int:
    # EventSource keeps its original URL when reconnecting; the latest event
    # header must take precedence over that URL's initial cursor.
    if last_event_id is not None:
        try:
            resumed_cursor = int(last_event_id)
            if resumed_cursor >= 0:
                return resumed_cursor
        except (TypeError, ValueError):
            pass
    return max(0, cursor or 0)


def format_sse(event: str, payload, *, event_id: Optional[int] = None) -> str:
    parts = []
    if event_id is not None:
        parts.append(f"id: {event_id}")
    parts.append(f"event: {event}")
    parts.append(f"data: {json.dumps(payload, ensure_ascii=False, allow_nan=False)}")
    return "\n".join(parts) + "\n\n"
