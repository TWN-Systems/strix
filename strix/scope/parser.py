"""Scope configuration parser."""

import ipaddress
import json
import os
from fnmatch import fnmatch
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from .models import (
    CredentialDefinition,
    DomainScope,
    Exclusions,
    NetworkDefinition,
    ScopeConfigModel,
    ScopeMetadata,
    ScopeSettings,
    TargetDefinition,
)


class ScopeConfig:
    """
    Scope configuration manager.

    Parses scope files (YAML/JSON) and provides methods for:
    - Converting to existing targets_info format
    - Checking if targets are in scope
    - Retrieving credentials
    - Getting exclusion rules for agent context

    Designed for future SQLite/Redis integration via to_dict()/from_dict().
    """

    def __init__(self, model: ScopeConfigModel):
        self.model = model
        self._network_cidrs: dict[str, ipaddress.IPv4Network | ipaddress.IPv6Network] = {}
        self._exclusion_cidrs: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        self._parse_cidrs()

    def _parse_cidrs(self) -> None:
        """Pre-parse CIDR notations for efficient scope checking."""
        for network in self.model.networks:
            if network.cidr:
                try:
                    self._network_cidrs[network.name] = ipaddress.ip_network(
                        network.cidr, strict=False
                    )
                except ValueError:
                    pass  # Invalid CIDR, will be caught by validator

        for cidr in self.model.exclusions.cidrs:
            try:
                self._exclusion_cidrs.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError:
                pass

    @classmethod
    def from_file(cls, path: Path | str) -> "ScopeConfig":
        """Load scope configuration from YAML or JSON file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Scope file not found: {path}")

        content = path.read_text(encoding="utf-8")

        if path.suffix in (".yaml", ".yml"):
            config_dict = yaml.safe_load(content) or {}
        elif path.suffix == ".json":
            config_dict = json.loads(content)
        else:
            raise ValueError(f"Unsupported scope file format: {path.suffix}. Use .yaml or .json")

        return cls.from_dict(config_dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScopeConfig":
        """Create ScopeConfig from dictionary (for future database loading)."""
        model = ScopeConfigModel(
            metadata=ScopeMetadata(**data.get("metadata", {})),
            settings=ScopeSettings(**data.get("settings", {})),
            networks=[NetworkDefinition(**n) for n in data.get("networks", [])],
            targets=[TargetDefinition(**t) for t in data.get("targets", [])],
            exclusions=Exclusions(**data.get("exclusions", {})),
            domains=DomainScope(**data.get("domains", {})),
        )
        return cls(model)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary (for future database storage)."""
        return self.model.model_dump()

    # -------------------------------------------------------------------------
    # Conversion to existing targets_info format
    # -------------------------------------------------------------------------

    def to_targets_info(self) -> list[dict[str, Any]]:
        """
        Convert scope targets to existing targets_info format for compatibility
        with current Strix CLI/agent infrastructure.
        """
        targets_info = []

        for target in self.model.targets:
            target_type = target.get_target_type()
            target_value = target.get_target_value()

            if not target_value:
                continue

            # Map to existing format
            if target_type == "infrastructure":
                info = {
                    "type": "ip_address",
                    "details": {"target_ip": target_value},
                    "original": target_value,
                }
            elif target_type in ("web_application", "api"):
                info = {
                    "type": "web_application",
                    "details": {"target_url": target_value},
                    "original": target_value,
                }
            elif target_type == "repository":
                info = {
                    "type": "repository",
                    "details": {"target_repo": target_value},
                    "original": target_value,
                }
            elif target_type == "local_code":
                resolved_path = str(Path(target_value).resolve())
                info = {
                    "type": "local_code",
                    "details": {"target_path": resolved_path},
                    "original": target_value,
                }
            else:
                continue

            # Add extended metadata for agent context
            info["scope_metadata"] = {
                "name": target.name,
                "network": target.network,
                "ports": target.ports,
                "services": [s.model_dump() for s in target.services],
                "technologies": target.technologies,
                "focus_areas": target.focus_areas,
                "modules": target.modules,
                "tags": target.tags,
                "auth_type": target.auth_type,
                "openapi_spec": target.openapi_spec,
                "branch": target.branch,
            }

            targets_info.append(info)

        return targets_info

    def get_instruction_context(self) -> str:
        """
        Generate instruction context string from scope settings.
        This supplements the --instruction flag.
        """
        parts = []

        # Operational mode
        mode = self.model.settings.operational_mode
        mode_text = {
            "recon-only": "Recon only, no exploitation, generate PoCs but do not execute",
            "poc-only": "Discovery and PoC validation only, no active exploitation",
            "full-pentest": "Full penetration test, exploitation allowed within scope",
        }
        parts.append(mode_text.get(mode, ""))

        # Engagement type
        eng_type = self.model.metadata.engagement_type
        if eng_type == "internal":
            parts.append("Internal network assessment")
        elif eng_type == "external":
            parts.append("External/perimeter assessment")

        # Validation requirement
        if self.model.settings.require_validation:
            parts.append("All findings must be validated before reporting")

        return ". ".join(filter(None, parts))

    # -------------------------------------------------------------------------
    # Scope checking
    # -------------------------------------------------------------------------

    def is_in_scope(self, target: str) -> bool:
        """
        Check if a discovered target is within scope.

        Handles:
        - IP addresses (against network CIDRs and explicit hosts)
        - URLs (against domain patterns)
        - Ports (against port exclusions)
        """
        # Check exclusions first
        if self._is_excluded(target):
            return False

        # Check if explicitly in targets
        for t in self.model.targets:
            if t.get_target_value() == target:
                return True

        # Check if IP is in any network CIDR
        try:
            ip = ipaddress.ip_address(target)
            for _name, network in self._network_cidrs.items():
                if ip in network:
                    return True
        except ValueError:
            pass  # Not an IP

        # Check domain patterns for URLs
        try:
            parsed = urlparse(target)
            if parsed.netloc:
                return self._is_domain_in_scope(parsed.netloc)
        except ValueError:
            pass

        return False

    def is_port_in_scope(self, port: int) -> bool:
        """Check if a port is allowed (not in exclusions)."""
        return port not in self.model.exclusions.ports

    def is_path_in_scope(self, path: str) -> bool:
        """Check if a URL path is allowed (not matching exclusion patterns)."""
        for pattern in self.model.exclusions.paths:
            if fnmatch(path, pattern):
                return False
        return True

    def _is_excluded(self, target: str) -> bool:
        """Check if target matches any exclusion rule."""
        # Check host exclusions
        if target in self.model.exclusions.hosts:
            return True

        # Check URL exclusions
        if target in self.model.exclusions.urls:
            return True

        # Check CIDR exclusions
        try:
            ip = ipaddress.ip_address(target)
            for excluded_cidr in self._exclusion_cidrs:
                if ip in excluded_cidr:
                    return True
        except ValueError:
            pass

        # Check domain out_of_scope
        try:
            parsed = urlparse(target)
            if parsed.netloc:
                for pattern in self.model.domains.out_of_scope:
                    if fnmatch(parsed.netloc, pattern):
                        return True
        except ValueError:
            pass

        return False

    def _is_domain_in_scope(self, domain: str) -> bool:
        """Check if domain matches in_scope patterns."""
        # First check out_of_scope
        for pattern in self.model.domains.out_of_scope:
            if fnmatch(domain, pattern):
                return False

        # Then check in_scope
        for pattern in self.model.domains.in_scope:
            if fnmatch(domain, pattern):
                return True

        # If no in_scope patterns defined, allow anything not excluded
        if not self.model.domains.in_scope:
            return True

        return False

    # -------------------------------------------------------------------------
    # Credentials
    # -------------------------------------------------------------------------

    def get_credentials(self, target: str) -> list[dict[str, str]]:
        """
        Get credentials for a target, resolving env var references.

        Returns list of dicts with resolved username/password/token.
        """
        credentials = []

        for t in self.model.targets:
            if t.get_target_value() != target:
                continue

            for cred in t.credentials:
                resolved = self._resolve_credential(cred)
                if resolved:
                    credentials.append(resolved)

            # Also check target-level token_env
            if t.token_env:
                token = os.environ.get(t.token_env)
                if token:
                    credentials.append({
                        "type": "bearer",
                        "token": token,
                        "access_level": "unknown",
                    })

        return credentials

    def _resolve_credential(self, cred: CredentialDefinition) -> dict[str, str] | None:
        """Resolve a credential definition to actual values."""
        result: dict[str, str] = {
            "username": cred.username,
            "access_level": cred.access_level,
        }

        if cred.password_env:
            password = os.environ.get(cred.password_env)
            if password:
                result["password"] = password
                result["type"] = "password"
            else:
                return None  # Env var not set

        if cred.token_env:
            token = os.environ.get(cred.token_env)
            if token:
                result["token"] = token
                result["type"] = "token"
            elif not cred.password_env:
                return None  # Neither password nor token available

        return result

    # -------------------------------------------------------------------------
    # Agent context
    # -------------------------------------------------------------------------

    def get_exclusion_rules(self) -> dict[str, Any]:
        """Get exclusion rules formatted for agent context."""
        return {
            "excluded_hosts": self.model.exclusions.hosts,
            "excluded_cidrs": self.model.exclusions.cidrs,
            "excluded_urls": self.model.exclusions.urls,
            "excluded_paths": self.model.exclusions.paths,
            "excluded_ports": self.model.exclusions.ports,
            "out_of_scope_domains": self.model.domains.out_of_scope,
        }

    def get_agent_context(self) -> dict[str, Any]:
        """
        Get complete scope context for injection into agent prompts.
        """
        return {
            "engagement": {
                "name": self.model.metadata.engagement_name,
                "type": self.model.metadata.engagement_type,
            },
            "settings": {
                "mode": self.model.settings.operational_mode,
                "require_validation": self.model.settings.require_validation,
                "max_agents": self.model.settings.max_agents,
            },
            "networks": [
                {
                    "name": n.name,
                    "type": n.type,
                    "cidr": n.cidr,
                    "vlan": n.vlan,
                }
                for n in self.model.networks
            ],
            "target_count": len(self.model.targets),
            "exclusions": self.get_exclusion_rules(),
            "in_scope_domains": self.model.domains.in_scope,
        }

    def get_target_by_value(self, value: str) -> TargetDefinition | None:
        """Look up target definition by its value (IP, URL, etc.)."""
        for target in self.model.targets:
            if target.get_target_value() == value:
                return target
        return None

    # -------------------------------------------------------------------------
    # Filtering
    # -------------------------------------------------------------------------

    def filter_targets(
        self,
        tags: list[str] | None = None,
        network: str | None = None,
        target_type: str | None = None,
    ) -> list[TargetDefinition]:
        """Filter targets by criteria."""
        results = []

        for target in self.model.targets:
            # Filter by tags (any match)
            if tags:
                if not any(t in target.tags for t in tags):
                    continue

            # Filter by network
            if network and target.network != network:
                continue

            # Filter by type
            if target_type and target.get_target_type() != target_type:
                continue

            results.append(target)

        return results

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def metadata(self) -> ScopeMetadata:
        return self.model.metadata

    @property
    def settings(self) -> ScopeSettings:
        return self.model.settings

    @property
    def networks(self) -> list[NetworkDefinition]:
        return self.model.networks

    @property
    def targets(self) -> list[TargetDefinition]:
        return self.model.targets

    @property
    def exclusions(self) -> Exclusions:
        return self.model.exclusions

    @property
    def domains(self) -> DomainScope:
        return self.model.domains
