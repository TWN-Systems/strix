"""Scope configuration validation."""

import ipaddress
import os
from dataclasses import dataclass, field
from pathlib import Path

from .models import ScopeConfigModel


@dataclass
class ValidationResult:
    """Result of scope validation."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.valid = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def __bool__(self) -> bool:
        return self.valid


class ScopeValidator:
    """Validates scope configuration for correctness and security."""

    def __init__(self, model: ScopeConfigModel):
        self.model = model
        self.result = ValidationResult()

    def validate(self) -> ValidationResult:
        """Run all validation checks."""
        self._validate_targets()
        self._validate_networks()
        self._validate_cidrs()
        self._validate_exclusions()
        self._validate_credentials()
        self._validate_network_references()
        self._validate_modules()
        return self.result

    def _validate_targets(self) -> None:
        """Validate target definitions."""
        for i, target in enumerate(self.model.targets):
            target_id = target.name or f"targets[{i}]"

            # Must have at least one identifier
            if not any([target.host, target.url, target.repo, target.path]):
                self.result.add_error(
                    f"{target_id}: Must specify at least one of: host, url, repo, path"
                )

            # Validate host is valid IP
            if target.host:
                try:
                    ipaddress.ip_address(target.host)
                except ValueError:
                    self.result.add_error(f"{target_id}: Invalid IP address: {target.host}")

            # Validate URL format
            if target.url:
                if not target.url.startswith(("http://", "https://")):
                    self.result.add_warning(
                        f"{target_id}: URL should start with http:// or https://: {target.url}"
                    )

            # Validate local path exists
            if target.path:
                path = Path(target.path).expanduser()
                if not path.exists():
                    self.result.add_warning(f"{target_id}: Local path does not exist: {target.path}")
                elif not path.is_dir():
                    self.result.add_error(f"{target_id}: Local path is not a directory: {target.path}")

            # Validate port ranges
            for port in target.ports:
                if not 1 <= port <= 65535:
                    self.result.add_error(f"{target_id}: Invalid port number: {port}")

    def _validate_networks(self) -> None:
        """Validate network definitions."""
        names = set()
        for i, network in enumerate(self.model.networks):
            network_id = network.name or f"networks[{i}]"

            # Check for duplicate names
            if network.name in names:
                self.result.add_error(f"Duplicate network name: {network.name}")
            names.add(network.name)

            # Validate VLAN range
            if network.vlan is not None:
                if not 1 <= network.vlan <= 4094:
                    self.result.add_error(f"{network_id}: Invalid VLAN ID: {network.vlan}")

            # Validate gateway is within CIDR
            if network.cidr and network.gateway:
                try:
                    net = ipaddress.ip_network(network.cidr, strict=False)
                    gw = ipaddress.ip_address(network.gateway)
                    if gw not in net:
                        self.result.add_warning(
                            f"{network_id}: Gateway {network.gateway} is not within CIDR {network.cidr}"
                        )
                except ValueError:
                    pass  # CIDR validation handled separately

    def _validate_cidrs(self) -> None:
        """Validate all CIDR notations."""
        # Network CIDRs
        for network in self.model.networks:
            if network.cidr:
                try:
                    ipaddress.ip_network(network.cidr, strict=False)
                except ValueError as e:
                    self.result.add_error(f"Invalid CIDR in network '{network.name}': {e}")

        # Exclusion CIDRs
        for cidr in self.model.exclusions.cidrs:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError as e:
                self.result.add_error(f"Invalid CIDR in exclusions: {cidr} - {e}")

    def _validate_exclusions(self) -> None:
        """Validate exclusion rules."""
        # Validate excluded hosts are valid IPs
        for host in self.model.exclusions.hosts:
            try:
                ipaddress.ip_address(host)
            except ValueError:
                self.result.add_warning(
                    f"Excluded host is not a valid IP: {host}. Will be treated as hostname."
                )

        # Validate excluded ports
        for port in self.model.exclusions.ports:
            if not 1 <= port <= 65535:
                self.result.add_error(f"Invalid excluded port number: {port}")

        # Check for overlap between targets and exclusions
        excluded_ips = set(self.model.exclusions.hosts)
        for target in self.model.targets:
            if target.host and target.host in excluded_ips:
                self.result.add_warning(
                    f"Target '{target.name or target.host}' is also in exclusions list"
                )

    def _validate_credentials(self) -> None:
        """Validate credential security and availability."""
        for target in self.model.targets:
            target_id = target.name or target.get_target_value()

            for cred in target.credentials:
                # Check password_env is set and available
                if cred.password_env:
                    if not os.environ.get(cred.password_env):
                        self.result.add_warning(
                            f"{target_id}: Environment variable not set: {cred.password_env}"
                        )

                # Check token_env is set and available
                if cred.token_env:
                    if not os.environ.get(cred.token_env):
                        self.result.add_warning(
                            f"{target_id}: Environment variable not set: {cred.token_env}"
                        )

            # Check target-level token_env
            if target.token_env:
                if not os.environ.get(target.token_env):
                    self.result.add_warning(
                        f"{target_id}: Environment variable not set: {target.token_env}"
                    )

    def _validate_network_references(self) -> None:
        """Validate that target network references exist."""
        network_names = {n.name for n in self.model.networks}

        for target in self.model.targets:
            if target.network and target.network not in network_names:
                self.result.add_error(
                    f"Target '{target.name or target.get_target_value()}' references "
                    f"undefined network: {target.network}"
                )

    def _validate_modules(self) -> None:
        """Validate prompt module references."""
        try:
            from strix.prompts import get_all_module_names

            available_modules = set(get_all_module_names())

            for target in self.model.targets:
                for module in target.modules:
                    if module not in available_modules:
                        self.result.add_warning(
                            f"Target '{target.name or target.get_target_value()}' "
                            f"references unknown module: {module}"
                        )
        except ImportError:
            pass  # Can't validate modules without strix.prompts


def validate_scope(model: ScopeConfigModel) -> ValidationResult:
    """Convenience function to validate a scope configuration."""
    validator = ScopeValidator(model)
    return validator.validate()
