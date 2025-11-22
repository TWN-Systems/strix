"""Progress tracking tools for agents to offload context and track scan progress.

These tools allow agents to:
- Save structured data (findings, scanned endpoints, etc.) to disk
- Load previously saved progress data
- List all available progress keys
- Persist state across crashes/restarts
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from strix.tools.registry import register_tool


logger = logging.getLogger(__name__)

_progress_cache: dict[str, Any] = {}
_progress_file_path: Path | None = None


def _get_progress_file() -> Path | None:
    """Get the path to the progress.json file in the run directory."""
    global _progress_file_path  # noqa: PLW0603
    if _progress_file_path is not None:
        return _progress_file_path

    try:
        from strix.telemetry.tracer import get_global_tracer

        tracer = get_global_tracer()
        if tracer:
            run_dir = tracer.get_run_dir()
            _progress_file_path = run_dir / "progress.json"
            return _progress_file_path
    except (ImportError, AttributeError):
        pass
    return None


def _load_progress_from_disk() -> dict[str, Any]:
    """Load progress data from disk if file exists."""
    global _progress_cache  # noqa: PLW0603
    progress_file = _get_progress_file()

    if progress_file and progress_file.exists():
        try:
            with progress_file.open("r", encoding="utf-8") as f:
                _progress_cache = json.load(f)
            logger.info(f"Loaded progress data with {len(_progress_cache)} keys from {progress_file}")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load progress from disk: {e}")
            _progress_cache = {}

    return _progress_cache


def _save_progress_to_disk() -> bool:
    """Save all progress data to disk atomically."""
    progress_file = _get_progress_file()
    if not progress_file:
        return False

    try:
        # Ensure parent directory exists
        progress_file.parent.mkdir(parents=True, exist_ok=True)

        # Write atomically using temp file
        temp_file = progress_file.with_suffix(".json.tmp")
        with temp_file.open("w", encoding="utf-8") as f:
            json.dump(_progress_cache, f, indent=2, ensure_ascii=False, default=str)

        # Atomic rename
        temp_file.replace(progress_file)
        logger.debug(f"Progress saved to {progress_file}")
        return True

    except (OSError, IOError) as e:
        logger.error(f"Failed to save progress to disk: {e}")
        return False


@register_tool(sandbox_execution=False)
def save_progress(
    key: str,
    data: dict[str, Any],
    append: bool = False,
) -> dict[str, Any]:
    """Save structured progress data to disk for persistence across crashes.

    Use this to track:
    - Scanned endpoints/targets
    - Discovered services
    - Intermediate findings
    - Task completion status
    - Any data you want to persist and reference later

    Args:
        key: Unique identifier for this progress data (e.g., "scanned_ports", "discovered_services")
        data: The data to save (must be JSON-serializable)
        append: If True and key exists with a list value, append data to the list instead of replacing

    Returns:
        Success status and file path
    """
    try:
        if not key or not key.strip():
            return {"success": False, "error": "Key cannot be empty"}

        if not isinstance(data, dict):
            return {"success": False, "error": "Data must be a dictionary"}

        # Load existing progress on first access
        if not _progress_cache:
            _load_progress_from_disk()

        key = key.strip()
        timestamp = datetime.now(UTC).isoformat()

        if append and key in _progress_cache:
            existing = _progress_cache[key].get("data")
            if isinstance(existing, list) and isinstance(data.get("items"), list):
                # Append items to existing list
                existing.extend(data["items"])
                _progress_cache[key]["updated_at"] = timestamp
            else:
                # Can't append, just update
                _progress_cache[key] = {
                    "data": data,
                    "created_at": _progress_cache[key].get("created_at", timestamp),
                    "updated_at": timestamp,
                }
        else:
            _progress_cache[key] = {
                "data": data,
                "created_at": timestamp,
                "updated_at": timestamp,
            }

        # Immediately persist to disk
        persisted = _save_progress_to_disk()

        return {
            "success": True,
            "message": f"Progress '{key}' saved successfully",
            "key": key,
            "persisted_to_disk": persisted,
        }

    except (ValueError, TypeError) as e:
        return {"success": False, "error": f"Failed to save progress: {e}"}


@register_tool(sandbox_execution=False)
def load_progress(key: str) -> dict[str, Any]:
    """Load previously saved progress data.

    Args:
        key: The key used when saving the progress data

    Returns:
        The saved data or error if not found
    """
    try:
        if not key or not key.strip():
            return {"success": False, "error": "Key cannot be empty", "data": None}

        # Load from disk on first access
        if not _progress_cache:
            _load_progress_from_disk()

        key = key.strip()

        if key not in _progress_cache:
            return {
                "success": False,
                "error": f"Progress key '{key}' not found",
                "data": None,
                "available_keys": list(_progress_cache.keys()),
            }

        entry = _progress_cache[key]
        return {
            "success": True,
            "key": key,
            "data": entry.get("data"),
            "created_at": entry.get("created_at"),
            "updated_at": entry.get("updated_at"),
        }

    except (ValueError, TypeError) as e:
        return {"success": False, "error": f"Failed to load progress: {e}", "data": None}


@register_tool(sandbox_execution=False)
def list_progress() -> dict[str, Any]:
    """List all available progress keys and their metadata.

    Returns:
        List of all progress keys with creation/update timestamps
    """
    try:
        # Load from disk on first access
        if not _progress_cache:
            _load_progress_from_disk()

        progress_list = []
        for key, entry in _progress_cache.items():
            data = entry.get("data", {})
            # Calculate size hint
            if isinstance(data, dict):
                size_hint = f"{len(data)} keys"
            elif isinstance(data, list):
                size_hint = f"{len(data)} items"
            else:
                size_hint = "unknown"

            progress_list.append({
                "key": key,
                "created_at": entry.get("created_at"),
                "updated_at": entry.get("updated_at"),
                "size_hint": size_hint,
            })

        # Sort by updated_at descending
        progress_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

        return {
            "success": True,
            "progress": progress_list,
            "total_count": len(progress_list),
        }

    except (ValueError, TypeError) as e:
        return {
            "success": False,
            "error": f"Failed to list progress: {e}",
            "progress": [],
            "total_count": 0,
        }
