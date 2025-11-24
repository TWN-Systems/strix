"""Script tool actions for agent use.

These tools allow agents to create and execute custom scripts for
deterministic, reproducible security testing operations.
"""

from __future__ import annotations

import asyncio
import json
import traceback
from typing import Any

from strix.tools.registry import register_tool
from strix.tools.scripts.scripts_registry import (
    ScriptCategory,
    ScriptLanguage,
    get_scripts_registry,
)


@register_tool(sandbox_execution=False)
def create_script(
    name: str,
    content: str,
    description: str,
    category: str = "utility",
    language: str = "bash",
    parameters: str | None = None,
    parameter_descriptions: str | None = None,
    tags: str | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """Create or update a custom script for deterministic execution.

    Use this to create reusable scripts for common operations like nmap scans,
    directory enumeration, or custom exploitation scripts. These scripts run
    faster and more reliably than generative approaches.

    Args:
        name: Unique script name (alphanumeric and underscores only)
        content: The script content (bash, python, etc.)
        description: Human-readable description of what the script does
        category: Script category (reconnaissance, scanning, exploitation,
                 post_exploitation, reporting, utility, validation)
        language: Script language (bash, python, ruby, perl, powershell)
        parameters: JSON list of parameter names, e.g., '["target", "port"]'
        parameter_descriptions: JSON object of param descriptions,
                               e.g., '{"target": "IP or hostname"}'
        tags: JSON list of tags for searching, e.g., '["nmap", "ports"]'
        timeout: Execution timeout in seconds (default: 300)

    Returns:
        Dictionary with script metadata on success, or error message

    Example:
        create_script(
            name="my_nmap_scan",
            content="#!/bin/bash\\nnmap -sV $1",
            description="Custom nmap scan",
            category="reconnaissance",
            parameters='["target"]'
        )
    """
    try:
        registry = get_scripts_registry()

        # Parse JSON parameters
        param_list = json.loads(parameters) if parameters else []
        param_desc = json.loads(parameter_descriptions) if parameter_descriptions else {}
        tag_list = json.loads(tags) if tags else []

        # Register the script
        metadata = registry.register_script(
            name=name,
            content=content,
            description=description,
            category=category,
            language=language,
            parameters=param_list,
            parameter_descriptions=param_desc,
            tags=tag_list,
            timeout=timeout,
        )

        return {
            "success": True,
            "message": f"Script '{name}' created successfully (v{metadata.version})",
            "script": metadata.to_dict(),
        }

    except (ValueError, json.JSONDecodeError) as e:
        return {
            "success": False,
            "error": str(e),
        }


@register_tool(sandbox_execution=True)
def execute_script(
    name: str,
    parameters: str | None = None,
) -> dict[str, Any]:
    """Execute a registered script with the given parameters.

    This executes scripts created with create_script in a deterministic manner.
    Much faster and more reliable than generative AI execution for routine tasks.

    Args:
        name: Name of the script to execute
        parameters: JSON object of parameter values,
                   e.g., '{"target": "192.168.1.1", "port": "80"}'

    Returns:
        Dictionary with execution result including stdout, stderr, exit code

    Example:
        execute_script(
            name="nmap_quick_scan",
            parameters='{"target": "192.168.1.1"}'
        )
    """
    # Parse parameters first (separate error handling)
    try:
        params = json.loads(parameters) if parameters else {}
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Invalid JSON in parameters: {e}",
        }

    # Execute the script
    try:
        registry = get_scripts_registry()
        result = asyncio.run(registry.execute(name, **params))
        return result.to_dict()

    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
        }


@register_tool(sandbox_execution=False)
def list_scripts(
    category: str | None = None,
    tags: str | None = None,
) -> dict[str, Any]:
    """List registered scripts, optionally filtered by category or tags.

    Args:
        category: Filter by category (reconnaissance, scanning, exploitation,
                 post_exploitation, reporting, utility, validation)
        tags: JSON list of tags to filter by (any match),
             e.g., '["nmap", "ports"]'

    Returns:
        Dictionary with list of script metadata

    Example:
        list_scripts(category="reconnaissance")
        list_scripts(tags='["nmap"]')
    """
    try:
        registry = get_scripts_registry()

        # Parse filters
        cat = ScriptCategory(category) if category else None
        tag_list = json.loads(tags) if tags else None

        scripts = registry.list_scripts(category=cat, tags=tag_list)

        return {
            "success": True,
            "count": len(scripts),
            "scripts": [s.to_dict() for s in scripts],
        }

    except (ValueError, json.JSONDecodeError) as e:
        return {
            "success": False,
            "error": str(e),
        }


@register_tool(sandbox_execution=False)
def delete_script(name: str) -> dict[str, Any]:
    """Delete a registered script.

    Args:
        name: Name of the script to delete

    Returns:
        Dictionary with success status
    """
    registry = get_scripts_registry()
    deleted = registry.delete_script(name)

    if deleted:
        return {
            "success": True,
            "message": f"Script '{name}' deleted successfully",
        }
    else:
        return {
            "success": False,
            "error": f"Script not found: {name}",
        }
