"""Strix LLM - Language model integration layer.

This package provides:
- LLM wrapper with LiteLLM backend (100+ providers)
- Role-based multi-model routing
- Cost optimization and token tracking
- Memory compression for long conversations

Usage:
    from strix.llm import LLM, LLMConfig

    # Simple usage
    config = LLMConfig()  # Uses STRIX_LLM env var
    llm = LLM(config, agent_name="MyAgent")

    # Role-based configuration
    from strix.llm.roles import LLMRole
    config = LLMConfig.for_role(LLMRole.THINKING)

    # Task-based routing
    from strix.llm.roles import TaskType
    config = LLMConfig.for_task(TaskType.PLANNING)
"""

import litellm

from strix.llm.config import LLMConfig
from strix.llm.llm import LLM, LLMRequestFailedError
from strix.llm.roles import (
    CostConfig,
    LLMRole,
    LLMRolesConfig,
    RoleConfig,
    TaskType,
    get_model_for_role,
    get_model_for_task,
    get_roles_config,
    set_roles_config,
)


__all__ = [
    # Core LLM
    "LLM",
    "LLMConfig",
    "LLMRequestFailedError",
    # Roles
    "CostConfig",
    "LLMRole",
    "LLMRolesConfig",
    "RoleConfig",
    "TaskType",
    "get_model_for_role",
    "get_model_for_task",
    "get_roles_config",
    "set_roles_config",
]

litellm._logging._disable_debugging()

litellm.drop_params = True
