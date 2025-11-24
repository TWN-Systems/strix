"""
Strix Scope Validator

Multi-phase validation for scope configurations.
Validates targets, networks, credentials, and modules.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .models import (
    CredentialDefinition,
    NetworkDefinition,
    ScopeConfig,
    TargetDefinition,
    TargetType,
)


logger = logging.getLogger(__name__)


class ValidationSeverity(str, Enum):
    """Severity level for validation issues."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationPhase(str, Enum):
    """Validation phases."""

    METADATA = "metadata"
    NETWORKS = "networks"
    TARGETS = "targets"
    CREDENTIALS = "credentials"
    MODULES = "modules"
    EXCLUSIONS = "exclusions"
    CROSS_REFERENCE = "cross_reference"


@dataclass
class ValidationIssue:
    """A single validation issue."""

    phase: ValidationPhase
    severity: ValidationSeverity
    message: str
    location: str | None = None
    suggestion: str | None = None
    code: str | None = None

    def __str__(self) -> str:
        loc = f" [{self.location}]" if self.location else ""
        sug = f" (Suggestion: {self.suggestion})" if self.suggestion else ""
        return f"[{self.severity.value.upper()}]{loc} {self.message}{sug}"


@dataclass
class ValidationResult:
    """Result of scope validation."""

    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    warnings_count: int = 0
    errors_count: int = 0

    def add_issue(self, issue: ValidationIssue) -> None:
        """Add a validation issue."""
        self.issues.append(issue)
        if issue.severity == ValidationSeverity.ERROR:
            self.errors_count += 1
            self.is_valid = False
        elif issue.severity == ValidationSeverity.WARNING:
            self.warnings_count += 1

    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return self.errors_count > 0

    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return self.warnings_count > 0

    def get_errors(self) -> list[ValidationIssue]:
        """Get all error issues."""
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]

    def get_warnings(self) -> list[ValidationIssue]:
        """Get all warning issues."""
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    def summary(self) -> str:
        """Get a summary of validation results."""
        status = "PASSED" if self.is_valid else "FAILED"
        return (
            f"Validation {status}: {self.errors_count} errors, "
            f"{self.warnings_count} warnings"
        )


class ScopeValidator:
    """
    Multi-phase validator for scope configurations.

    Performs validation in the following phases:
    1. Metadata validation
    2. Network validation (CIDR, gateway, VLAN)
    3. Target validation (identifiers, ports, URLs)
    4. Credential validation (env vars, access levels)
    5. Module validation (available modules)
    6. Exclusion validation (CIDR, ports)
    7. Cross-reference validation (network references, etc.)
    """

    # Known prompt modules (loaded dynamically if available)
    KNOWN_MODULES: set[str] = set()

    # Valid focus areas
    KNOWN_FOCUS_AREAS: set[str] = {
        "authentication",
        "authorization",
        "idor",
        "xss",
        "sql_injection",
        "csrf",
        "xxe",
        "rce",
        "ssrf",
        "business_logic",
        "race_conditions",
        "path_traversal",
        "mass_assignment",
        "insecure_uploads",
        "api_security",
        "graphql",
        "secrets",
        "misconfigurations",
        "default_credentials",
        "privilege_escalation",
    }

    def __init__(self) -> None:
        self._load_available_modules()

    def _load_available_modules(self) -> None:
        """Load available prompt modules."""
        try:
            from strix.prompts import get_available_prompt_modules

            self.KNOWN_MODULES = set(get_available_prompt_modules())
            logger.debug(f"Loaded {len(self.KNOWN_MODULES)} prompt modules")
        except ImportError:
            logger.warning("Could not load prompt modules for validation")
            self.KNOWN_MODULES = set()

    def validate(self, config: ScopeConfig) -> ValidationResult:
        """
        Perform full validation on a scope configuration.

        Args:
            config: The scope configuration to validate

        Returns:
            ValidationResult with all issues found
        """
        result = ValidationResult(is_valid=True)

        # Phase 1: Metadata
        self._validate_metadata(config, result)

        # Phase 2: Networks
        self._validate_networks(config, result)

        # Phase 3: Targets
        self._validate_targets(config, result)

        # Phase 4: Credentials
        self._validate_credentials(config, result)

        # Phase 5: Modules
        self._validate_modules(config, result)

        # Phase 6: Exclusions
        self._validate_exclusions(config, result)

        # Phase 7: Cross-references
        self._validate_cross_references(config, result)

        logger.info(result.summary())
        return result

    def validate_quick(self, config: ScopeConfig) -> ValidationResult:
        """
        Perform quick validation (metadata and targets only).

        Useful for fast feedback during editing.
        """
        result = ValidationResult(is_valid=True)
        self._validate_metadata(config, result)
        self._validate_targets(config, result)
        return result

    def _validate_metadata(self, config: ScopeConfig, result: ValidationResult) -> None:
        """Validate metadata section."""
        meta = config.metadata

        # Check engagement name
        if not meta.engagement_name or meta.engagement_name.strip() == "":
            result.add_issue(
                ValidationIssue(
                    phase=ValidationPhase.METADATA,
                    severity=ValidationSeverity.ERROR,
                    message="Engagement name is required",
                    location="metadata.engagement_name",
                    code="META_001",
                )
            )

        # Check dates
        if meta.start_date and meta.end_date:
            if meta.end_date < meta.start_date:
                result.add_issue(
                    ValidationIssue(
                        phase=ValidationPhase.METADATA,
                        severity=ValidationSeverity.ERROR,
                        message="End date must be after start date",
                        location="metadata.end_date",
                        code="META_002",
                    )
                )

        # Warn if no tester specified
        if not meta.tester:
            result.add_issue(
                ValidationIssue(
                    phase=ValidationPhase.METADATA,
                    severity=ValidationSeverity.WARNING,
                    message="No tester name specified",
                    location="metadata.tester",
                    suggestion="Add tester name for audit trail",
                    code="META_003",
                )
            )

    def _validate_networks(self, config: ScopeConfig, result: ValidationResult) -> None:
        """Validate network definitions."""
        network_names: set[str] = set()

        for idx, network in enumerate(config.networks):
            location = f"networks[{idx}]"

            # Check for duplicate network names
            if network.name in network_names:
                result.add_issue(
                    ValidationIssue(
                        phase=ValidationPhase.NETWORKS,
                        severity=ValidationSeverity.ERROR,
                        message=f"Duplicate network name: {network.name}",
                        location=location,
                        code="NET_001",
                    )
                )
            network_names.add(network.name)

            # Validate CIDR
            try:
                net = ipaddress.ip_network(network.cidr, strict=False)

                # Warn about very large networks
                if net.prefixlen < 16:
                    result.add_issue(
                        ValidationIssue(
                            phase=ValidationPhase.NETWORKS,
                            severity=ValidationSeverity.WARNING,
                            message=f"Very large network ({network.cidr}) - {net.num_addresses} addresses",
                            location=f"{location}.cidr",
                            suggestion="Consider using a more specific CIDR",
                            code="NET_002",
                        )
                    )

            except ValueError as e:
                result.add_issue(
                    ValidationIssue(
                        phase=ValidationPhase.NETWORKS,
                        severity=ValidationSeverity.ERROR,
                        message=f"Invalid CIDR: {e}",
                        location=f"{location}.cidr",
                        code="NET_003",
                    )
                )
                continue

            # Validate gateway
            if network.gateway:
                try:
                    gw = ipaddress.ip_address(network.gateway)
                    net_obj = ipaddress.ip_network(network.cidr, strict=False)
                    if gw not in net_obj:
                        result.add_issue(
                            ValidationIssue(
                                phase=ValidationPhase.NETWORKS,
                                severity=ValidationSeverity.WARNING,
                                message=f"Gateway {network.gateway} is not in network {network.cidr}",
                                location=f"{location}.gateway",
                                code="NET_004",
                            )
                        )
                except ValueError as e:
                    result.add_issue(
                        ValidationIssue(
                            phase=ValidationPhase.NETWORKS,
                            severity=ValidationSeverity.ERROR,
                            message=f"Invalid gateway IP: {e}",
                            location=f"{location}.gateway",
                            code="NET_005",
                        )
                    )

            # Validate VLAN
            if network.vlan is not None:
                if not 1 <= network.vlan <= 4094:
                    result.add_issue(
                        ValidationIssue(
                            phase=ValidationPhase.NETWORKS,
                            severity=ValidationSeverity.ERROR,
                            message=f"Invalid VLAN ID: {network.vlan} (must be 1-4094)",
                            location=f"{location}.vlan",
                            code="NET_006",
                        )
                    )

    def _validate_targets(self, config: ScopeConfig, result: ValidationResult) -> None:
        """Validate target definitions."""
        target_names: set[str] = set()

        if not config.targets:
            result.add_issue(
                ValidationIssue(
                    phase=ValidationPhase.TARGETS,
                    severity=ValidationSeverity.WARNING,
                    message="No targets defined in scope",
                    suggestion="Add at least one target to scan",
                    code="TGT_001",
                )
            )
            return

        for idx, target in enumerate(config.targets):
            location = f"targets[{idx}]"

            # Check for duplicate target names
            if target.name in target_names:
                result.add_issue(
                    ValidationIssue(
                        phase=ValidationPhase.TARGETS,
                        severity=ValidationSeverity.WARNING,
                        message=f"Duplicate target name: {target.name}",
                        location=location,
                        code="TGT_002",
                    )
                )
            target_names.add(target.name)

            # Validate target has an identifier
            identifiers = [target.host, target.url, target.repo, target.path]
            if not any(identifiers):
                result.add_issue(
                    ValidationIssue(
                        phase=ValidationPhase.TARGETS,
                        severity=ValidationSeverity.ERROR,
                        message="Target must have at least one identifier (host, url, repo, path)",
                        location=location,
                        code="TGT_003",
                    )
                )

            # Validate host
            if target.host:
                self._validate_host(target.host, f"{location}.host", result)

            # Validate URL
            if target.url:
                self._validate_url(target.url, f"{location}.url", result)

            # Validate repository
            if target.repo:
                self._validate_repo(target.repo, f"{location}.repo", result)

            # Validate local path
            if target.path:
                self._validate_local_path(target.path, f"{location}.path", result)

            # Validate ports
            for port in target.ports:
                if not 1 <= port <= 65535:
                    result.add_issue(
                        ValidationIssue(
                            phase=ValidationPhase.TARGETS,
                            severity=ValidationSeverity.ERROR,
                            message=f"Invalid port number: {port}",
                            location=f"{location}.ports",
                            code="TGT_004",
                        )
                    )

            # Validate focus areas
            for area in target.focus_areas:
                if area.lower() not in self.KNOWN_FOCUS_AREAS:
                    result.add_issue(
                        ValidationIssue(
                            phase=ValidationPhase.TARGETS,
                            severity=ValidationSeverity.INFO,
                            message=f"Unknown focus area: {area}",
                            location=f"{location}.focus_areas",
                            suggestion=f"Known areas: {', '.join(sorted(self.KNOWN_FOCUS_AREAS))}",
                            code="TGT_005",
                        )
                    )

    def _validate_host(self, host: str, location: str, result: ValidationResult) -> None:
        """Validate a host identifier."""
        # Try as IP
        try:
            ipaddress.ip_address(host)
            return
        except ValueError:
            pass

        # Validate as hostname
        hostname_pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
        if not re.match(hostname_pattern, host):
            result.add_issue(
                ValidationIssue(
                    phase=ValidationPhase.TARGETS,
                    severity=ValidationSeverity.ERROR,
                    message=f"Invalid host: {host}",
                    location=location,
                    code="TGT_006",
                )
            )

    def _validate_url(self, url: str, location: str, result: ValidationResult) -> None:
        """Validate a URL."""
        url_pattern = r"^https?://[^\s]+$"
        if not re.match(url_pattern, url):
            result.add_issue(
                ValidationIssue(
                    phase=ValidationPhase.TARGETS,
                    severity=ValidationSeverity.ERROR,
                    message=f"Invalid URL format: {url}",
                    location=location,
                    suggestion="URL must start with http:// or https://",
                    code="TGT_007",
                )
            )

    def _validate_repo(self, repo: str, location: str, result: ValidationResult) -> None:
        """Validate a repository URL."""
        valid_patterns = [
            r"^https?://github\.com/",
            r"^https?://gitlab\.com/",
            r"^https?://bitbucket\.org/",
            r"^git@",
            r"^ssh://",
        ]

        if not any(re.match(p, repo) for p in valid_patterns):
            result.add_issue(
                ValidationIssue(
                    phase=ValidationPhase.TARGETS,
                    severity=ValidationSeverity.WARNING,
                    message=f"Unrecognized repository URL format: {repo}",
                    location=location,
                    code="TGT_008",
                )
            )

    def _validate_local_path(self, path: str, location: str, result: ValidationResult) -> None:
        """Validate a local path."""
        resolved = Path(path).expanduser()

        if not resolved.exists():
            result.add_issue(
                ValidationIssue(
                    phase=ValidationPhase.TARGETS,
                    severity=ValidationSeverity.WARNING,
                    message=f"Local path does not exist: {path}",
                    location=location,
                    code="TGT_009",
                )
            )
        elif not resolved.is_dir() and not resolved.is_file():
            result.add_issue(
                ValidationIssue(
                    phase=ValidationPhase.TARGETS,
                    severity=ValidationSeverity.ERROR,
                    message=f"Path is not a file or directory: {path}",
                    location=location,
                    code="TGT_010",
                )
            )

    def _validate_credentials(self, config: ScopeConfig, result: ValidationResult) -> None:
        """Validate credential definitions and environment variables."""
        for idx, target in enumerate(config.targets):
            target_loc = f"targets[{idx}]"

            # Check token_env
            if target.token_env:
                if not os.getenv(target.token_env):
                    result.add_issue(
                        ValidationIssue(
                            phase=ValidationPhase.CREDENTIALS,
                            severity=ValidationSeverity.WARNING,
                            message=f"Environment variable not set: {target.token_env}",
                            location=f"{target_loc}.token_env",
                            suggestion=f"Set {target.token_env} environment variable",
                            code="CRED_001",
                        )
                    )

            # Check credentials
            for cred_idx, cred in enumerate(target.credentials):
                cred_loc = f"{target_loc}.credentials[{cred_idx}]"
                self._validate_credential(cred, cred_loc, result)

    def _validate_credential(
        self, cred: CredentialDefinition, location: str, result: ValidationResult
    ) -> None:
        """Validate a single credential definition."""
        # Check password_env
        if cred.password_env and not os.getenv(cred.password_env):
            result.add_issue(
                ValidationIssue(
                    phase=ValidationPhase.CREDENTIALS,
                    severity=ValidationSeverity.WARNING,
                    message=f"Password environment variable not set: {cred.password_env}",
                    location=location,
                    code="CRED_002",
                )
            )

        # Check token_env
        if cred.token_env and not os.getenv(cred.token_env):
            result.add_issue(
                ValidationIssue(
                    phase=ValidationPhase.CREDENTIALS,
                    severity=ValidationSeverity.WARNING,
                    message=f"Token environment variable not set: {cred.token_env}",
                    location=location,
                    code="CRED_003",
                )
            )

        # Check api_key_env
        if cred.api_key_env and not os.getenv(cred.api_key_env):
            result.add_issue(
                ValidationIssue(
                    phase=ValidationPhase.CREDENTIALS,
                    severity=ValidationSeverity.WARNING,
                    message=f"API key environment variable not set: {cred.api_key_env}",
                    location=location,
                    code="CRED_004",
                )
            )

        # Warn about plaintext secrets
        if cred.password:
            result.add_issue(
                ValidationIssue(
                    phase=ValidationPhase.CREDENTIALS,
                    severity=ValidationSeverity.WARNING,
                    message="Plaintext password in configuration",
                    location=location,
                    suggestion="Use password_env instead for security",
                    code="CRED_005",
                )
            )

        if cred.token:
            result.add_issue(
                ValidationIssue(
                    phase=ValidationPhase.CREDENTIALS,
                    severity=ValidationSeverity.WARNING,
                    message="Plaintext token in configuration",
                    location=location,
                    suggestion="Use token_env instead for security",
                    code="CRED_006",
                )
            )

        if cred.api_key:
            result.add_issue(
                ValidationIssue(
                    phase=ValidationPhase.CREDENTIALS,
                    severity=ValidationSeverity.WARNING,
                    message="Plaintext API key in configuration",
                    location=location,
                    suggestion="Use api_key_env instead for security",
                    code="CRED_007",
                )
            )

    def _validate_modules(self, config: ScopeConfig, result: ValidationResult) -> None:
        """Validate prompt module references."""
        if not self.KNOWN_MODULES:
            return  # Skip if modules couldn't be loaded

        for idx, target in enumerate(config.targets):
            for module in target.modules:
                if module not in self.KNOWN_MODULES:
                    result.add_issue(
                        ValidationIssue(
                            phase=ValidationPhase.MODULES,
                            severity=ValidationSeverity.WARNING,
                            message=f"Unknown prompt module: {module}",
                            location=f"targets[{idx}].modules",
                            suggestion=f"Available modules: {', '.join(sorted(self.KNOWN_MODULES))}",
                            code="MOD_001",
                        )
                    )

            # Warn if too many modules
            if len(target.modules) > 5:
                result.add_issue(
                    ValidationIssue(
                        phase=ValidationPhase.MODULES,
                        severity=ValidationSeverity.WARNING,
                        message=f"Too many modules ({len(target.modules)}) - max recommended is 5",
                        location=f"targets[{idx}].modules",
                        code="MOD_002",
                    )
                )

    def _validate_exclusions(self, config: ScopeConfig, result: ValidationResult) -> None:
        """Validate exclusion definitions."""
        excl = config.exclusions

        # Validate excluded CIDRs
        for idx, cidr in enumerate(excl.cidrs):
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError as e:
                result.add_issue(
                    ValidationIssue(
                        phase=ValidationPhase.EXCLUSIONS,
                        severity=ValidationSeverity.ERROR,
                        message=f"Invalid exclusion CIDR: {e}",
                        location=f"exclusions.cidrs[{idx}]",
                        code="EXCL_001",
                    )
                )

        # Validate excluded hosts
        for idx, host in enumerate(excl.hosts):
            try:
                ipaddress.ip_address(host)
            except ValueError:
                # Not an IP, validate as hostname
                hostname_pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
                if not re.match(hostname_pattern, host):
                    result.add_issue(
                        ValidationIssue(
                            phase=ValidationPhase.EXCLUSIONS,
                            severity=ValidationSeverity.WARNING,
                            message=f"Invalid exclusion host: {host}",
                            location=f"exclusions.hosts[{idx}]",
                            code="EXCL_002",
                        )
                    )

        # Validate excluded ports
        for idx, port in enumerate(excl.ports):
            if not 1 <= port <= 65535:
                result.add_issue(
                    ValidationIssue(
                        phase=ValidationPhase.EXCLUSIONS,
                        severity=ValidationSeverity.ERROR,
                        message=f"Invalid exclusion port: {port}",
                        location=f"exclusions.ports[{idx}]",
                        code="EXCL_003",
                    )
                )

    def _validate_cross_references(self, config: ScopeConfig, result: ValidationResult) -> None:
        """Validate cross-references between sections."""
        network_names = {n.name for n in config.networks}

        # Check target network references
        for idx, target in enumerate(config.targets):
            if target.network and target.network not in network_names:
                result.add_issue(
                    ValidationIssue(
                        phase=ValidationPhase.CROSS_REFERENCE,
                        severity=ValidationSeverity.WARNING,
                        message=f"Target references unknown network: {target.network}",
                        location=f"targets[{idx}].network",
                        suggestion=f"Available networks: {', '.join(network_names) or 'none defined'}",
                        code="XREF_001",
                    )
                )

            # Check if target host is in referenced network
            if target.network and target.host and target.network in network_names:
                network = config.networks_by_name.get(target.network)
                if network:
                    try:
                        host_ip = ipaddress.ip_address(target.host)
                        net = ipaddress.ip_network(network.cidr, strict=False)
                        if host_ip not in net:
                            result.add_issue(
                                ValidationIssue(
                                    phase=ValidationPhase.CROSS_REFERENCE,
                                    severity=ValidationSeverity.WARNING,
                                    message=f"Target host {target.host} is not in network {network.cidr}",
                                    location=f"targets[{idx}].host",
                                    code="XREF_002",
                                )
                            )
                    except ValueError:
                        pass  # Not an IP, skip network containment check


def validate_scope(config: ScopeConfig) -> ValidationResult:
    """
    Convenience function to validate a scope configuration.

    Args:
        config: The scope configuration to validate

    Returns:
        ValidationResult with all issues found
    """
    validator = ScopeValidator()
    return validator.validate(config)
