"""LLM Roles configuration for multi-model routing.

This module implements Phase 1 of the MCP integration plan, providing:
- Role-based model definitions (primary, fast, local, thinking, coding, validation)
- Task-to-role routing configuration
- Cost optimization settings
- YAML configuration loading

Example configuration (llm.yaml):
    roles:
      primary:
        provider: anthropic
        model: claude-sonnet-4-20250514
      fast:
        provider: google
        model: gemini-2.0-flash
      thinking:
        provider: google
        model: gemini-3.0-pro

    routing:
      default: primary
      planning: thinking
      reconnaissance: primary
      exploitation: coding
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class LLMRole(str, Enum):
    """Predefined LLM roles for different tasks."""

    PRIMARY = "primary"  # Main agent loop - balanced
    FAST = "fast"  # Quick operations - low latency, cheap
    LOCAL = "local"  # Cost-free, offline via Ollama
    THINKING = "thinking"  # Complex reasoning - deep analysis
    CODING = "coding"  # Code analysis - code-optimized
    VALIDATION = "validation"  # Cross-check findings - different model family


class TaskType(str, Enum):
    """Task types that can be routed to different LLM roles."""

    DEFAULT = "default"
    PLANNING = "planning"
    RECONNAISSANCE = "reconnaissance"
    EXPLOITATION = "exploitation"
    REPORTING = "reporting"
    VULN_ANALYSIS = "vuln_analysis"
    CODE_REVIEW = "code_review"
    FINDING_VALIDATION = "finding_validation"


@dataclass
class RoleConfig:
    """Configuration for a single LLM role."""

    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int | None = None
    timeout: int = 600
    fallback_to: str | None = None  # Role to fallback to if this one fails

    @property
    def model_name(self) -> str:
        """Get the full model name in LiteLLM format."""
        if "/" in self.model:
            return self.model
        return f"{self.provider}/{self.model}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "provider": self.provider,
            "model": self.model,
            "api_key": "***" if self.api_key else None,
            "base_url": self.base_url,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "fallback_to": self.fallback_to,
        }


@dataclass
class CostConfig:
    """Cost optimization configuration."""

    prefer_local: bool = False
    local_timeout_seconds: int = 30
    fast_threshold_tokens: int = 500  # Use fast model for requests under this token count


@dataclass
class LLMRolesConfig:
    """Complete LLM roles configuration."""

    roles: dict[str, RoleConfig] = field(default_factory=dict)
    routing: dict[str, str] = field(default_factory=dict)
    cost: CostConfig = field(default_factory=CostConfig)

    _instance: LLMRolesConfig | None = None

    def get_role(self, role_name: str) -> RoleConfig | None:
        """Get a role configuration by name."""
        return self.roles.get(role_name)

    def get_role_for_task(self, task_type: str | TaskType) -> RoleConfig | None:
        """Get the appropriate role for a given task type."""
        if isinstance(task_type, TaskType):
            task_type = task_type.value

        role_name = self.routing.get(task_type, self.routing.get("default", "primary"))
        return self.get_role(role_name)

    def get_model_for_task(self, task_type: str | TaskType) -> str | None:
        """Get the model name for a given task type."""
        role = self.get_role_for_task(task_type)
        return role.model_name if role else None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "roles": {name: role.to_dict() for name, role in self.roles.items()},
            "routing": self.routing,
            "cost": {
                "prefer_local": self.cost.prefer_local,
                "local_timeout_seconds": self.cost.local_timeout_seconds,
                "fast_threshold_tokens": self.cost.fast_threshold_tokens,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LLMRolesConfig:
        """Create configuration from dictionary."""
        roles = {}
        for name, role_data in data.get("roles", {}).items():
            # Resolve environment variables in values
            api_key = role_data.get("api_key")
            if api_key and api_key.startswith("${") and api_key.endswith("}"):
                env_var = api_key[2:-1]
                api_key = os.getenv(env_var)

            base_url = role_data.get("base_url")
            if base_url and "${" in base_url:
                # Handle ${VAR:-default} syntax
                import re

                match = re.match(r"\$\{(\w+)(?::-([^}]*))?\}", base_url)
                if match:
                    env_var = match.group(1)
                    default = match.group(2) or ""
                    base_url = os.getenv(env_var, default)

            roles[name] = RoleConfig(
                provider=role_data.get("provider", ""),
                model=role_data.get("model", ""),
                api_key=api_key,
                base_url=base_url,
                max_tokens=role_data.get("max_tokens"),
                timeout=role_data.get("timeout", 600),
                fallback_to=role_data.get("fallback_to"),
            )

        cost_data = data.get("cost", {})
        cost = CostConfig(
            prefer_local=cost_data.get("prefer_local", False),
            local_timeout_seconds=cost_data.get("local_timeout_seconds", 30),
            fast_threshold_tokens=cost_data.get("fast_threshold_tokens", 500),
        )

        return cls(
            roles=roles,
            routing=data.get("routing", {"default": "primary"}),
            cost=cost,
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> LLMRolesConfig:
        """Load configuration from a YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"LLM roles config not found: {path}")

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls.from_dict(data.get("llm", data))

    @classmethod
    def from_env(cls) -> LLMRolesConfig:
        """Create configuration from environment variables.

        Environment variables:
            STRIX_LLM: Primary model (default)
            STRIX_LLM_FAST: Fast model for quick operations
            STRIX_LLM_LOCAL: Local model (Ollama)
            STRIX_LLM_THINKING: Thinking/reasoning model
            STRIX_LLM_CODING: Coding-optimized model
            STRIX_LLM_VALIDATION: Validation model (different family)
        """
        roles = {}

        # Primary model (required)
        primary_model = os.getenv("STRIX_LLM", "openai/gpt-5")
        if primary_model:
            provider, model = _parse_model_string(primary_model)
            roles["primary"] = RoleConfig(provider=provider, model=model)

        # Fast model
        fast_model = os.getenv("STRIX_LLM_FAST")
        if fast_model:
            provider, model = _parse_model_string(fast_model)
            roles["fast"] = RoleConfig(provider=provider, model=model, fallback_to="primary")

        # Local model (Ollama)
        local_model = os.getenv("STRIX_LLM_LOCAL")
        if local_model:
            provider, model = _parse_model_string(local_model)
            roles["local"] = RoleConfig(
                provider=provider,
                model=model,
                base_url=os.getenv("OLLAMA_API_BASE", "http://localhost:11434"),
                fallback_to="fast",
            )

        # Thinking model
        thinking_model = os.getenv("STRIX_LLM_THINKING")
        if thinking_model:
            provider, model = _parse_model_string(thinking_model)
            roles["thinking"] = RoleConfig(provider=provider, model=model, fallback_to="primary")

        # Coding model
        coding_model = os.getenv("STRIX_LLM_CODING")
        if coding_model:
            provider, model = _parse_model_string(coding_model)
            roles["coding"] = RoleConfig(provider=provider, model=model, fallback_to="primary")

        # Validation model
        validation_model = os.getenv("STRIX_LLM_VALIDATION")
        if validation_model:
            provider, model = _parse_model_string(validation_model)
            roles["validation"] = RoleConfig(
                provider=provider, model=model, fallback_to="primary"
            )

        # Default routing
        routing = {
            "default": "primary",
            "planning": "thinking" if "thinking" in roles else "primary",
            "reconnaissance": "primary",
            "exploitation": "coding" if "coding" in roles else "primary",
            "reporting": "fast" if "fast" in roles else "primary",
            "vuln_analysis": "thinking" if "thinking" in roles else "primary",
            "code_review": "coding" if "coding" in roles else "primary",
            "finding_validation": "validation" if "validation" in roles else "primary",
        }

        cost = CostConfig(
            prefer_local=os.getenv("STRIX_PREFER_LOCAL", "false").lower() == "true",
            local_timeout_seconds=int(os.getenv("STRIX_LOCAL_TIMEOUT", "30")),
            fast_threshold_tokens=int(os.getenv("STRIX_FAST_THRESHOLD", "500")),
        )

        return cls(roles=roles, routing=routing, cost=cost)


def _parse_model_string(model_string: str) -> tuple[str, str]:
    """Parse a model string into provider and model name.

    Examples:
        "anthropic/claude-sonnet-4" -> ("anthropic", "claude-sonnet-4")
        "gpt-5" -> ("openai", "gpt-5")
        "ollama/llama3.1" -> ("ollama", "llama3.1")
    """
    if "/" in model_string:
        parts = model_string.split("/", 1)
        return parts[0], parts[1]

    # Default providers based on model name patterns
    model_lower = model_string.lower()
    if any(name in model_lower for name in ["claude", "opus", "sonnet", "haiku"]):
        return "anthropic", model_string
    if any(name in model_lower for name in ["gemini", "palm", "bard"]):
        return "google", model_string
    if any(name in model_lower for name in ["llama", "mistral", "qwen", "deepseek"]):
        return "ollama", model_string

    # Default to OpenAI
    return "openai", model_string


# Global configuration instance
_global_roles_config: LLMRolesConfig | None = None


def get_roles_config() -> LLMRolesConfig:
    """Get the global LLM roles configuration.

    Loads from:
    1. STRIX_LLM_CONFIG environment variable (path to YAML)
    2. ./llm.yaml in current directory
    3. Environment variables (STRIX_LLM_*)
    """
    global _global_roles_config  # noqa: PLW0603

    if _global_roles_config is not None:
        return _global_roles_config

    # Try loading from config file first
    config_path = os.getenv("STRIX_LLM_CONFIG")
    if config_path and Path(config_path).exists():
        logger.info(f"Loading LLM roles from config: {config_path}")
        _global_roles_config = LLMRolesConfig.from_yaml(config_path)
        return _global_roles_config

    # Try default config location
    default_path = Path.cwd() / "llm.yaml"
    if default_path.exists():
        logger.info(f"Loading LLM roles from default config: {default_path}")
        _global_roles_config = LLMRolesConfig.from_yaml(default_path)
        return _global_roles_config

    # Fall back to environment variables
    logger.info("Loading LLM roles from environment variables")
    _global_roles_config = LLMRolesConfig.from_env()
    return _global_roles_config


def set_roles_config(config: LLMRolesConfig) -> None:
    """Set the global LLM roles configuration."""
    global _global_roles_config  # noqa: PLW0603
    _global_roles_config = config


def get_model_for_role(role: str | LLMRole) -> str:
    """Get the model name for a specific role."""
    if isinstance(role, LLMRole):
        role = role.value

    config = get_roles_config()
    role_config = config.get_role(role)

    if role_config:
        return role_config.model_name

    # Fallback to primary model or environment variable
    primary = config.get_role("primary")
    if primary:
        return primary.model_name

    return os.getenv("STRIX_LLM", "openai/gpt-5")


def get_model_for_task(task: str | TaskType) -> str:
    """Get the appropriate model for a task type."""
    config = get_roles_config()
    model = config.get_model_for_task(task)
    return model or os.getenv("STRIX_LLM", "openai/gpt-5")
