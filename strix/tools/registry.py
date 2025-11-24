import inspect
import logging
import os
from collections.abc import Callable
from enum import Enum
from functools import wraps
from inspect import signature
from pathlib import Path
from typing import Any


tools: list[dict[str, Any]] = []
_tools_by_name: dict[str, Callable[..., Any]] = {}
logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    """Roles that agents can have, determining tool access."""

    COORDINATOR = "coordinator"
    RECONNAISSANCE = "reconnaissance"
    VULNERABILITY_TESTER = "vulnerability_tester"
    VALIDATOR = "validator"
    REPORTER = "reporter"
    FIX_GENERATOR = "fix_generator"
    FULL_ACCESS = "full_access"


# Tool profiles mapping roles to allowed tools
TOOL_PROFILES: dict[AgentRole, set[str]] = {
    AgentRole.COORDINATOR: {
        "agents_graph",
        "finish",
        "thinking",
        "notes",
    },
    AgentRole.RECONNAISSANCE: {
        "terminal",
        "proxy",
        "browser",
        "web_search",
        "notes",
        "thinking",
        "python",
    },
    AgentRole.VULNERABILITY_TESTER: {
        "terminal",
        "proxy",
        "browser",
        "python",
        "file_edit",
        "notes",
        "thinking",
        "reporting",
        "agents_graph",
    },
    AgentRole.VALIDATOR: {
        "terminal",
        "proxy",
        "browser",
        "python",
        "notes",
        "thinking",
    },
    AgentRole.REPORTER: {
        "notes",
        "reporting",
        "thinking",
        "file_edit",
    },
    AgentRole.FIX_GENERATOR: {
        "file_edit",
        "notes",
        "thinking",
        "python",
    },
    AgentRole.FULL_ACCESS: set(),  # Empty means all tools allowed
}

# Tools that are sequential and should not run in parallel
SEQUENTIAL_TOOLS: set[str] = {
    "terminal",
    "browser",
    "file_edit",
}

# Tools that can be parallelized
PARALLEL_TOOLS: set[str] = {
    "proxy",
    "notes",
    "thinking",
    "web_search",
    "python",
}


class ImplementedInClientSideOnlyError(Exception):
    def __init__(
        self,
        message: str = "This tool is implemented in the client side only",
    ) -> None:
        self.message = message
        super().__init__(self.message)


def _process_dynamic_content(content: str) -> str:
    if "{{DYNAMIC_MODULES_DESCRIPTION}}" in content:
        try:
            from strix.prompts import generate_modules_description

            modules_description = generate_modules_description()
            content = content.replace("{{DYNAMIC_MODULES_DESCRIPTION}}", modules_description)
        except ImportError:
            logger.warning("Could not import prompts utilities for dynamic schema generation")
            content = content.replace(
                "{{DYNAMIC_MODULES_DESCRIPTION}}",
                "List of prompt modules to load for this agent (max 5). Module discovery failed.",
            )

    return content


def _load_xml_schema(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        content = path.read_text()

        content = _process_dynamic_content(content)

        start_tag = '<tool name="'
        end_tag = "</tool>"
        tools_dict = {}

        pos = 0
        while True:
            start_pos = content.find(start_tag, pos)
            if start_pos == -1:
                break

            name_start = start_pos + len(start_tag)
            name_end = content.find('"', name_start)
            if name_end == -1:
                break
            tool_name = content[name_start:name_end]

            end_pos = content.find(end_tag, name_end)
            if end_pos == -1:
                break
            end_pos += len(end_tag)

            tool_element = content[start_pos:end_pos]
            tools_dict[tool_name] = tool_element

            pos = end_pos

            if pos >= len(content):
                break
    except (IndexError, ValueError, UnicodeError) as e:
        logger.warning(f"Error loading schema file {path}: {e}")
        return None
    else:
        return tools_dict


def _get_module_name(func: Callable[..., Any]) -> str:
    module = inspect.getmodule(func)
    if not module:
        return "unknown"

    module_name = module.__name__
    if ".tools." in module_name:
        parts = module_name.split(".tools.")[-1].split(".")
        if len(parts) >= 1:
            return parts[0]
    return "unknown"


def register_tool(
    func: Callable[..., Any] | None = None, *, sandbox_execution: bool = True
) -> Callable[..., Any]:
    def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
        func_dict = {
            "name": f.__name__,
            "function": f,
            "module": _get_module_name(f),
            "sandbox_execution": sandbox_execution,
        }

        sandbox_mode = os.getenv("STRIX_SANDBOX_MODE", "false").lower() == "true"
        if not sandbox_mode:
            try:
                module_path = Path(inspect.getfile(f))
                schema_file_name = f"{module_path.stem}_schema.xml"
                schema_path = module_path.parent / schema_file_name

                xml_tools = _load_xml_schema(schema_path)

                if xml_tools is not None and f.__name__ in xml_tools:
                    func_dict["xml_schema"] = xml_tools[f.__name__]
                else:
                    func_dict["xml_schema"] = (
                        f'<tool name="{f.__name__}">'
                        "<description>Schema not found for tool.</description>"
                        "</tool>"
                    )
            except (TypeError, FileNotFoundError) as e:
                logger.warning(f"Error loading schema for {f.__name__}: {e}")
                func_dict["xml_schema"] = (
                    f'<tool name="{f.__name__}">'
                    "<description>Error loading schema.</description>"
                    "</tool>"
                )

        tools.append(func_dict)
        _tools_by_name[str(func_dict["name"])] = f

        @wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return f(*args, **kwargs)

        return wrapper

    if func is None:
        return decorator
    return decorator(func)


def get_tool_by_name(name: str) -> Callable[..., Any] | None:
    return _tools_by_name.get(name)


def get_tool_names() -> list[str]:
    return list(_tools_by_name.keys())


def needs_agent_state(tool_name: str) -> bool:
    tool_func = get_tool_by_name(tool_name)
    if not tool_func:
        return False
    sig = signature(tool_func)
    return "agent_state" in sig.parameters


def should_execute_in_sandbox(tool_name: str) -> bool:
    for tool in tools:
        if tool.get("name") == tool_name:
            return bool(tool.get("sandbox_execution", True))
    return True


def get_tools_prompt() -> str:
    tools_by_module: dict[str, list[dict[str, Any]]] = {}
    for tool in tools:
        module = tool.get("module", "unknown")
        if module not in tools_by_module:
            tools_by_module[module] = []
        tools_by_module[module].append(tool)

    xml_sections = []
    for module, module_tools in sorted(tools_by_module.items()):
        tag_name = f"{module}_tools"
        section_parts = [f"<{tag_name}>"]
        for tool in module_tools:
            tool_xml = tool.get("xml_schema", "")
            if tool_xml:
                indented_tool = "\n".join(f"  {line}" for line in tool_xml.split("\n"))
                section_parts.append(indented_tool)
        section_parts.append(f"</{tag_name}>")
        xml_sections.append("\n".join(section_parts))

    return "\n\n".join(xml_sections)


def clear_registry() -> None:
    tools.clear()
    _tools_by_name.clear()


def is_tool_allowed_for_role(tool_name: str, role: AgentRole) -> bool:
    """
    Check if a tool is allowed for a given agent role.

    Args:
        tool_name: Name of the tool to check
        role: The agent's role

    Returns:
        True if the tool is allowed, False otherwise
    """
    # Full access role can use all tools
    if role == AgentRole.FULL_ACCESS:
        return True

    # Get the allowed tools for this role
    allowed_tools = TOOL_PROFILES.get(role, set())

    # Check if tool is in allowed set
    # Tools are stored by module name in registry, so we check module
    for tool in tools:
        if tool.get("name") == tool_name:
            tool_module = tool.get("module", "unknown")
            return tool_module in allowed_tools or tool_name in allowed_tools

    return False


def get_tools_for_role(role: AgentRole) -> list[dict[str, Any]]:
    """
    Get all tools available for a given role.

    Args:
        role: The agent's role

    Returns:
        List of tool dictionaries available to the role
    """
    if role == AgentRole.FULL_ACCESS:
        return tools.copy()

    allowed_modules = TOOL_PROFILES.get(role, set())
    return [
        tool for tool in tools
        if tool.get("module", "unknown") in allowed_modules
        or tool.get("name") in allowed_modules
    ]


def get_tools_prompt_for_role(role: AgentRole) -> str:
    """
    Generate tool prompt XML for a specific role.

    Args:
        role: The agent's role

    Returns:
        XML string with tool definitions for the role
    """
    role_tools = get_tools_for_role(role)

    tools_by_module: dict[str, list[dict[str, Any]]] = {}
    for tool in role_tools:
        module = tool.get("module", "unknown")
        if module not in tools_by_module:
            tools_by_module[module] = []
        tools_by_module[module].append(tool)

    xml_sections = []
    for module, module_tools in sorted(tools_by_module.items()):
        tag_name = f"{module}_tools"
        section_parts = [f"<{tag_name}>"]
        for tool in module_tools:
            tool_xml = tool.get("xml_schema", "")
            if tool_xml:
                indented_tool = "\n".join(f"  {line}" for line in tool_xml.split("\n"))
                section_parts.append(indented_tool)
        section_parts.append(f"</{tag_name}>")
        xml_sections.append("\n".join(section_parts))

    return "\n\n".join(xml_sections)


def validate_tool_availability(
    tool_name: str,
    role: AgentRole | None = None,
) -> tuple[bool, str | None]:
    """
    Validate if a tool is available and allowed.

    Args:
        tool_name: Name of the tool
        role: Optional role to check against

    Returns:
        Tuple of (is_available, error_message)
    """
    # Check if tool exists
    if tool_name not in _tools_by_name:
        return False, f"Tool '{tool_name}' not found in registry"

    # Check role permissions if role specified
    if role is not None and not is_tool_allowed_for_role(tool_name, role):
        return False, f"Tool '{tool_name}' not allowed for role '{role.value}'"

    return True, None


def get_parallelization_strategy(tool_names: list[str]) -> dict[str, list[str]]:
    """
    Determine parallelization strategy for a set of tools.

    Args:
        tool_names: List of tool names to execute

    Returns:
        Dict with 'parallel' and 'sequential' lists of tool names
    """
    parallel = []
    sequential = []

    for name in tool_names:
        # Get tool module
        tool_module = "unknown"
        for tool in tools:
            if tool.get("name") == name:
                tool_module = tool.get("module", "unknown")
                break

        if tool_module in SEQUENTIAL_TOOLS or name in SEQUENTIAL_TOOLS:
            sequential.append(name)
        else:
            parallel.append(name)

    return {
        "parallel": parallel,
        "sequential": sequential,
    }


def get_available_roles() -> list[str]:
    """Get list of available agent roles."""
    return [role.value for role in AgentRole]
