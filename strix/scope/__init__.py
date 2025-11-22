"""Scope configuration module for Strix."""

from .models import (
    CredentialDefinition,
    DomainScope,
    Exclusions,
    NetworkDefinition,
    ScopeConfigModel,
    ScopeMetadata,
    ScopeSettings,
    ServiceDefinition,
    TargetDefinition,
)
from .parser import ScopeConfig
from .validator import ScopeValidator, ValidationResult, validate_scope

__all__ = [
    # Main class
    "ScopeConfig",
    # Models
    "ScopeConfigModel",
    "ScopeMetadata",
    "ScopeSettings",
    "NetworkDefinition",
    "TargetDefinition",
    "ServiceDefinition",
    "CredentialDefinition",
    "Exclusions",
    "DomainScope",
    # Validation
    "ScopeValidator",
    "ValidationResult",
    "validate_scope",
]
