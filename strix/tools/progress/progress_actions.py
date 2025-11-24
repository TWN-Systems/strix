"""
Strix Progress Actions

Provides tools for saving, loading, and listing scan progress.
Enables scan resumption and progress tracking.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from strix.telemetry.tracer import get_global_tracer
from strix.tools.registry import register_tool


logger = logging.getLogger(__name__)


def _get_progress_dir() -> Path:
    """Get the progress directory, creating it if necessary."""
    tracer = get_global_tracer()
    if tracer:
        run_dir = tracer.get_run_dir()
        progress_dir = run_dir / "progress"
    else:
        progress_dir = Path.cwd() / "strix_runs" / "progress"

    progress_dir.mkdir(parents=True, exist_ok=True)
    return progress_dir


def _sanitize_checkpoint_name(name: str) -> str:
    """Sanitize checkpoint name for use as filename."""
    # Replace unsafe characters
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return safe_name[:64]  # Limit length


@register_tool(sandbox_execution=False)
def save_progress(
    checkpoint_name: str,
    data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Save progress checkpoint to disk.

    Args:
        checkpoint_name: Name for this checkpoint (e.g., "recon_complete", "phase_1")
        data: Progress data to save (findings, state, etc.)
        metadata: Optional metadata about the checkpoint

    Returns:
        Status dict with checkpoint file path
    """
    try:
        progress_dir = _get_progress_dir()
        safe_name = _sanitize_checkpoint_name(checkpoint_name)
        checkpoint_file = progress_dir / f"{safe_name}.json"

        checkpoint = {
            "checkpoint_name": checkpoint_name,
            "created_at": datetime.now(UTC).isoformat(),
            "data": data,
            "metadata": metadata or {},
        }

        # Add tracer info if available
        tracer = get_global_tracer()
        if tracer:
            checkpoint["run_id"] = tracer.run_id
            checkpoint["run_name"] = tracer.run_name

        # Atomic write
        temp_file = checkpoint_file.with_suffix(".tmp")
        with temp_file.open("w", encoding="utf-8") as f:
            json.dump(checkpoint, f, indent=2, default=str)
        temp_file.rename(checkpoint_file)

        logger.info(f"Saved progress checkpoint: {checkpoint_name}")

        return {
            "success": True,
            "checkpoint_name": checkpoint_name,
            "file_path": str(checkpoint_file),
            "created_at": checkpoint["created_at"],
        }

    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Failed to save progress: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@register_tool(sandbox_execution=False)
def load_progress(
    checkpoint_name: str,
) -> dict[str, Any]:
    """
    Load a progress checkpoint from disk.

    Args:
        checkpoint_name: Name of the checkpoint to load

    Returns:
        The checkpoint data or error status
    """
    try:
        progress_dir = _get_progress_dir()
        safe_name = _sanitize_checkpoint_name(checkpoint_name)
        checkpoint_file = progress_dir / f"{safe_name}.json"

        if not checkpoint_file.exists():
            return {
                "success": False,
                "error": f"Checkpoint '{checkpoint_name}' not found",
                "available": [f.stem for f in progress_dir.glob("*.json")],
            }

        with checkpoint_file.open("r", encoding="utf-8") as f:
            checkpoint = json.load(f)

        logger.info(f"Loaded progress checkpoint: {checkpoint_name}")

        return {
            "success": True,
            "checkpoint_name": checkpoint_name,
            "created_at": checkpoint.get("created_at"),
            "data": checkpoint.get("data", {}),
            "metadata": checkpoint.get("metadata", {}),
        }

    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load progress: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@register_tool(sandbox_execution=False)
def list_progress() -> dict[str, Any]:
    """
    List all available progress checkpoints.

    Returns:
        Dict with list of checkpoints and their metadata
    """
    try:
        progress_dir = _get_progress_dir()
        checkpoints = []

        for checkpoint_file in sorted(progress_dir.glob("*.json")):
            try:
                with checkpoint_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)

                checkpoints.append({
                    "name": data.get("checkpoint_name", checkpoint_file.stem),
                    "created_at": data.get("created_at"),
                    "run_id": data.get("run_id"),
                    "file": checkpoint_file.name,
                    "size_bytes": checkpoint_file.stat().st_size,
                })
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Could not read checkpoint {checkpoint_file}: {e}")
                checkpoints.append({
                    "name": checkpoint_file.stem,
                    "error": str(e),
                    "file": checkpoint_file.name,
                })

        return {
            "success": True,
            "checkpoints": checkpoints,
            "count": len(checkpoints),
            "directory": str(progress_dir),
        }

    except OSError as e:
        logger.error(f"Failed to list progress: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def delete_progress(checkpoint_name: str) -> dict[str, Any]:
    """
    Delete a progress checkpoint.

    Args:
        checkpoint_name: Name of the checkpoint to delete

    Returns:
        Status dict
    """
    try:
        progress_dir = _get_progress_dir()
        safe_name = _sanitize_checkpoint_name(checkpoint_name)
        checkpoint_file = progress_dir / f"{safe_name}.json"

        if not checkpoint_file.exists():
            return {
                "success": False,
                "error": f"Checkpoint '{checkpoint_name}' not found",
            }

        checkpoint_file.unlink()
        logger.info(f"Deleted progress checkpoint: {checkpoint_name}")

        return {
            "success": True,
            "deleted": checkpoint_name,
        }

    except OSError as e:
        logger.error(f"Failed to delete progress: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def clear_all_progress() -> dict[str, Any]:
    """
    Clear all progress checkpoints.

    Returns:
        Status dict with count of deleted checkpoints
    """
    try:
        progress_dir = _get_progress_dir()
        deleted = 0

        for checkpoint_file in progress_dir.glob("*.json"):
            try:
                checkpoint_file.unlink()
                deleted += 1
            except OSError as e:
                logger.warning(f"Could not delete {checkpoint_file}: {e}")

        logger.info(f"Cleared {deleted} progress checkpoints")

        return {
            "success": True,
            "deleted_count": deleted,
        }

    except OSError as e:
        logger.error(f"Failed to clear progress: {e}")
        return {
            "success": False,
            "error": str(e),
        }
