"""Custom Scripts module for deterministic tool execution."""

from strix.tools.scripts.scripts_registry import (
    ScriptCategory,
    ScriptExecutionResult,
    ScriptLanguage,
    ScriptMetadata,
    ScriptsRegistry,
    get_scripts_registry,
    set_scripts_registry,
)
from strix.tools.scripts.scripts_actions import (
    create_script,
    execute_script,
    list_scripts,
    delete_script,
)


__all__ = [
    # Registry
    "ScriptCategory",
    "ScriptExecutionResult",
    "ScriptLanguage",
    "ScriptMetadata",
    "ScriptsRegistry",
    "get_scripts_registry",
    "set_scripts_registry",
    # Actions
    "create_script",
    "execute_script",
    "list_scripts",
    "delete_script",
]
