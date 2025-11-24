"""
Strix Scope System

A comprehensive scoping system for defining engagement scope, targets,
networks, credentials, and validation for security assessments.

Usage:
    from strix.scope import load_scope, validate_scope, ScopeConfig

    # Load from file
    config = load_scope("path/to/scope.yaml")

    # Validate
    result = validate_scope(config)
    if not result.is_valid:
        for issue in result.get_errors():
            print(f"Error: {issue}")

    # Filter targets
    web_targets = config.get_targets_by_filter(
        target_type=TargetType.WEB_APPLICATION,
        tags=["production"],
    )
"""

from .config import (
    ScopeConfigParser,
    ScopeParseError,
    load_scope,
    load_scope_from_string,
)
from .models import (
    AccessLevel,
    AuthType,
    CredentialDefinition,
    DomainScope,
    EngagementType,
    ExclusionDefinition,
    NetworkDefinition,
    NetworkType,
    OperationalMode,
    ScopeConfig,
    ScopeMetadata,
    ScopeSettings,
    ServiceDefinition,
    TargetDefinition,
    TargetType,
    TestFocus,
)
from .validator import (
    ScopeValidator,
    ValidationIssue,
    ValidationPhase,
    ValidationResult,
    ValidationSeverity,
    validate_scope,
)


__all__ = [
    # Models - Core
    "ScopeConfig",
    "ScopeMetadata",
    "ScopeSettings",
    "TargetDefinition",
    "NetworkDefinition",
    "CredentialDefinition",
    "ServiceDefinition",
    "ExclusionDefinition",
    "DomainScope",
    "TestFocus",
    # Models - Enums
    "EngagementType",
    "OperationalMode",
    "TargetType",
    "NetworkType",
    "AuthType",
    "AccessLevel",
    # Config Parser
    "ScopeConfigParser",
    "ScopeParseError",
    "load_scope",
    "load_scope_from_string",
    # Validator
    "ScopeValidator",
    "ValidationResult",
    "ValidationIssue",
    "ValidationPhase",
    "ValidationSeverity",
    "validate_scope",
]
