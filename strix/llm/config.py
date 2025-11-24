from __future__ import annotations

import os
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from strix.llm.roles import LLMRole, TaskType


class LLMConfig:
    """Configuration for LLM instances.

    Supports both simple single-model configuration and role-based multi-model routing.

    Args:
        model_name: Model identifier (e.g., "anthropic/claude-sonnet-4-20250514")
        enable_prompt_caching: Enable Anthropic prompt caching
        prompt_modules: List of prompt modules to load
        timeout: Request timeout in seconds
        role: LLM role for multi-model routing (primary, fast, thinking, etc.)
        task_type: Task type for automatic role selection
    """

    def __init__(
        self,
        model_name: str | None = None,
        enable_prompt_caching: bool = True,
        prompt_modules: list[str] | None = None,
        timeout: int | None = None,
        role: str | LLMRole | None = None,
        task_type: str | TaskType | None = None,
    ):
        # If role or task_type is specified, use role-based routing
        if role is not None or task_type is not None:
            self.model_name = self._resolve_model_from_role(role, task_type)
        else:
            self.model_name = model_name or os.getenv("STRIX_LLM", "openai/gpt-5")

        if not self.model_name:
            raise ValueError("STRIX_LLM environment variable must be set and not empty")

        self.enable_prompt_caching = enable_prompt_caching
        self.prompt_modules = prompt_modules or []
        self.timeout = timeout or int(os.getenv("LLM_TIMEOUT", "600"))

        # Store role information for tracing
        self.role = role
        self.task_type = task_type

    def _resolve_model_from_role(
        self,
        role: str | LLMRole | None,
        task_type: str | TaskType | None,
    ) -> str:
        """Resolve model name from role or task type."""
        # Import here to avoid circular imports
        from strix.llm.roles import get_model_for_role, get_model_for_task

        if role is not None:
            return get_model_for_role(role)
        if task_type is not None:
            return get_model_for_task(task_type)

        return os.getenv("STRIX_LLM", "openai/gpt-5")

    @classmethod
    def for_role(
        cls,
        role: str | LLMRole,
        enable_prompt_caching: bool = True,
        prompt_modules: list[str] | None = None,
        timeout: int | None = None,
    ) -> LLMConfig:
        """Create a config for a specific LLM role.

        Args:
            role: The LLM role (primary, fast, thinking, coding, validation)
            enable_prompt_caching: Enable Anthropic prompt caching
            prompt_modules: List of prompt modules to load
            timeout: Request timeout in seconds

        Returns:
            LLMConfig configured for the specified role
        """
        return cls(
            role=role,
            enable_prompt_caching=enable_prompt_caching,
            prompt_modules=prompt_modules,
            timeout=timeout,
        )

    @classmethod
    def for_task(
        cls,
        task_type: str | TaskType,
        enable_prompt_caching: bool = True,
        prompt_modules: list[str] | None = None,
        timeout: int | None = None,
    ) -> LLMConfig:
        """Create a config automatically routed based on task type.

        Args:
            task_type: The task type (planning, reconnaissance, exploitation, etc.)
            enable_prompt_caching: Enable Anthropic prompt caching
            prompt_modules: List of prompt modules to load
            timeout: Request timeout in seconds

        Returns:
            LLMConfig with model selected based on task type routing
        """
        return cls(
            task_type=task_type,
            enable_prompt_caching=enable_prompt_caching,
            prompt_modules=prompt_modules,
            timeout=timeout,
        )
