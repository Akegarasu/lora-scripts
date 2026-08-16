"""Safe, batch-oriented editor for local Caption sidecar files."""

from .service import TagEditorService, get_tag_editor_service

__all__ = ["TagEditorService", "get_tag_editor_service"]
