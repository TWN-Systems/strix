import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from strix.tools.registry import register_tool


logger = logging.getLogger(__name__)

_notes_storage: dict[str, dict[str, Any]] = {}
_notes_file_path: Path | None = None


def _get_notes_file() -> Path | None:
    """Get the path to the notes.json file in the run directory."""
    global _notes_file_path  # noqa: PLW0603
    if _notes_file_path is not None:
        return _notes_file_path

    try:
        from strix.telemetry.tracer import get_global_tracer

        tracer = get_global_tracer()
        if tracer:
            run_dir = tracer.get_run_dir()
            _notes_file_path = run_dir / "notes.json"
            return _notes_file_path
    except (ImportError, AttributeError):
        pass
    return None


def _load_notes_from_disk() -> None:
    """Load notes from disk if file exists."""
    global _notes_storage  # noqa: PLW0603
    notes_file = _get_notes_file()
    if notes_file and notes_file.exists():
        try:
            with notes_file.open("r", encoding="utf-8") as f:
                _notes_storage = json.load(f)
            logger.info(f"Loaded {len(_notes_storage)} notes from {notes_file}")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load notes from disk: {e}")


def _save_notes_to_disk() -> bool:
    """Save all notes to disk (crash-proof)."""
    notes_file = _get_notes_file()
    if not notes_file:
        return False

    try:
        # Ensure parent directory exists
        notes_file.parent.mkdir(parents=True, exist_ok=True)

        # Write atomically using temp file
        temp_file = notes_file.with_suffix(".json.tmp")
        with temp_file.open("w", encoding="utf-8") as f:
            json.dump(_notes_storage, f, indent=2, ensure_ascii=False)

        # Atomic rename
        temp_file.replace(notes_file)
        return True

    except (OSError, IOError) as e:
        logger.error(f"Failed to save notes to disk: {e}")
        return False


def _filter_notes(
    category: str | None = None,
    tags: list[str] | None = None,
    priority: str | None = None,
    search_query: str | None = None,
) -> list[dict[str, Any]]:
    filtered_notes = []

    for note_id, note in _notes_storage.items():
        if category and note.get("category") != category:
            continue

        if priority and note.get("priority") != priority:
            continue

        if tags:
            note_tags = note.get("tags", [])
            if not any(tag in note_tags for tag in tags):
                continue

        if search_query:
            search_lower = search_query.lower()
            title_match = search_lower in note.get("title", "").lower()
            content_match = search_lower in note.get("content", "").lower()
            if not (title_match or content_match):
                continue

        note_with_id = note.copy()
        note_with_id["note_id"] = note_id
        filtered_notes.append(note_with_id)

    filtered_notes.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return filtered_notes


@register_tool
def create_note(
    title: str,
    content: str,
    category: str = "general",
    tags: list[str] | None = None,
    priority: str = "normal",
) -> dict[str, Any]:
    try:
        # Load existing notes from disk on first access
        if not _notes_storage:
            _load_notes_from_disk()

        if not title or not title.strip():
            return {"success": False, "error": "Title cannot be empty", "note_id": None}

        if not content or not content.strip():
            return {"success": False, "error": "Content cannot be empty", "note_id": None}

        valid_categories = ["general", "findings", "methodology", "todo", "questions", "plan"]
        if category not in valid_categories:
            return {
                "success": False,
                "error": f"Invalid category. Must be one of: {', '.join(valid_categories)}",
                "note_id": None,
            }

        valid_priorities = ["low", "normal", "high", "urgent"]
        if priority not in valid_priorities:
            return {
                "success": False,
                "error": f"Invalid priority. Must be one of: {', '.join(valid_priorities)}",
                "note_id": None,
            }

        note_id = str(uuid.uuid4())[:5]
        timestamp = datetime.now(UTC).isoformat()

        note = {
            "title": title.strip(),
            "content": content.strip(),
            "category": category,
            "tags": tags or [],
            "priority": priority,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

        _notes_storage[note_id] = note

        # Immediately persist to disk
        persisted = _save_notes_to_disk()

    except (ValueError, TypeError) as e:
        return {"success": False, "error": f"Failed to create note: {e}", "note_id": None}
    else:
        return {
            "success": True,
            "note_id": note_id,
            "message": f"Note '{title}' created successfully",
            "persisted_to_disk": persisted,
        }


@register_tool
def list_notes(
    category: str | None = None,
    tags: list[str] | None = None,
    priority: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    try:
        # Load existing notes from disk on first access
        if not _notes_storage:
            _load_notes_from_disk()

        filtered_notes = _filter_notes(
            category=category, tags=tags, priority=priority, search_query=search
        )

        return {
            "success": True,
            "notes": filtered_notes,
            "total_count": len(filtered_notes),
        }

    except (ValueError, TypeError) as e:
        return {
            "success": False,
            "error": f"Failed to list notes: {e}",
            "notes": [],
            "total_count": 0,
        }


@register_tool
def update_note(
    note_id: str,
    title: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
    priority: str | None = None,
) -> dict[str, Any]:
    try:
        # Load existing notes from disk on first access
        if not _notes_storage:
            _load_notes_from_disk()

        if note_id not in _notes_storage:
            return {"success": False, "error": f"Note with ID '{note_id}' not found"}

        note = _notes_storage[note_id]

        if title is not None:
            if not title.strip():
                return {"success": False, "error": "Title cannot be empty"}
            note["title"] = title.strip()

        if content is not None:
            if not content.strip():
                return {"success": False, "error": "Content cannot be empty"}
            note["content"] = content.strip()

        if tags is not None:
            note["tags"] = tags

        if priority is not None:
            valid_priorities = ["low", "normal", "high", "urgent"]
            if priority not in valid_priorities:
                return {
                    "success": False,
                    "error": f"Invalid priority. Must be one of: {', '.join(valid_priorities)}",
                }
            note["priority"] = priority

        note["updated_at"] = datetime.now(UTC).isoformat()

        # Immediately persist to disk
        persisted = _save_notes_to_disk()

        return {
            "success": True,
            "message": f"Note '{note['title']}' updated successfully",
            "persisted_to_disk": persisted,
        }

    except (ValueError, TypeError) as e:
        return {"success": False, "error": f"Failed to update note: {e}"}


@register_tool
def delete_note(note_id: str) -> dict[str, Any]:
    try:
        # Load existing notes from disk on first access
        if not _notes_storage:
            _load_notes_from_disk()

        if note_id not in _notes_storage:
            return {"success": False, "error": f"Note with ID '{note_id}' not found"}

        note_title = _notes_storage[note_id]["title"]
        del _notes_storage[note_id]

        # Immediately persist to disk
        persisted = _save_notes_to_disk()

    except (ValueError, TypeError) as e:
        return {"success": False, "error": f"Failed to delete note: {e}"}
    else:
        return {
            "success": True,
            "message": f"Note '{note_title}' deleted successfully",
            "persisted_to_disk": persisted,
        }
