"""
Strix Scope Config Parser

Parses scope configuration from YAML, JSON, and CSV files.
Handles CIDR pre-computation and data normalization.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from pathlib import Path
from typing import Any

import yaml

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


logger = logging.getLogger(__name__)


class ScopeParseError(Exception):
    """Error parsing scope configuration."""

    def __init__(self, message: str, file_path: str | None = None, line: int | None = None) -> None:
        self.file_path = file_path
        self.line = line
        location = ""
        if file_path:
            location = f" in {file_path}"
        if line:
            location += f" at line {line}"
        super().__init__(f"{message}{location}")


class ScopeConfigParser:
    """
    Parser for scope configuration files.

    Supports YAML, JSON, and CSV formats.
    """

    SUPPORTED_FORMATS = {".yaml", ".yml", ".json", ".csv"}

    def __init__(self) -> None:
        self._env_vars_resolved: dict[str, str] = {}

    def parse_file(self, file_path: str | Path) -> ScopeConfig:
        """
        Parse a scope configuration file.

        Args:
            file_path: Path to the configuration file

        Returns:
            Parsed and validated ScopeConfig

        Raises:
            ScopeParseError: If parsing fails
        """
        path = Path(file_path)

        if not path.exists():
            raise ScopeParseError(f"File not found: {path}")

        suffix = path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise ScopeParseError(
                f"Unsupported file format: {suffix}. Supported: {', '.join(self.SUPPORTED_FORMATS)}"
            )

        try:
            if suffix in {".yaml", ".yml"}:
                config = self._parse_yaml(path)
            elif suffix == ".json":
                config = self._parse_json(path)
            elif suffix == ".csv":
                config = self._parse_csv(path)
            else:
                raise ScopeParseError(f"Unknown format: {suffix}")

            # Compute derived values
            config.compute_all()

            logger.info(
                f"Parsed scope config: {config.metadata.engagement_name} "
                f"with {len(config.targets)} targets"
            )

            return config

        except yaml.YAMLError as e:
            raise ScopeParseError(f"YAML parse error: {e}", str(path)) from e
        except json.JSONDecodeError as e:
            raise ScopeParseError(f"JSON parse error: {e}", str(path), e.lineno) from e
        except csv.Error as e:
            raise ScopeParseError(f"CSV parse error: {e}", str(path)) from e

    def parse_string(self, content: str, format: str = "yaml") -> ScopeConfig:
        """
        Parse scope configuration from a string.

        Args:
            content: Configuration content
            format: Format type (yaml, json)

        Returns:
            Parsed and validated ScopeConfig
        """
        if format in {"yaml", "yml"}:
            data = yaml.safe_load(content)
        elif format == "json":
            data = json.loads(content)
        else:
            raise ScopeParseError(f"Unsupported format for string parsing: {format}")

        config = self._build_config(data)
        config.compute_all()
        return config

    def _parse_yaml(self, path: Path) -> ScopeConfig:
        """Parse YAML configuration file."""
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return self._build_config(data, str(path))

    def _parse_json(self, path: Path) -> ScopeConfig:
        """Parse JSON configuration file."""
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return self._build_config(data, str(path))

    def _parse_csv(self, path: Path) -> ScopeConfig:
        """
        Parse CSV configuration file.

        CSV format is simplified, containing only target definitions.
        """
        targets: list[TargetDefinition] = []

        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)

            for row_num, row in enumerate(reader, start=2):
                try:
                    target = self._parse_csv_row(row)
                    targets.append(target)
                except Exception as e:
                    raise ScopeParseError(
                        f"Error parsing row: {e}", str(path), row_num
                    ) from e

        # Create minimal metadata for CSV files
        metadata = ScopeMetadata(
            engagement_name=path.stem,
            engagement_type=EngagementType.INTERNAL,
        )

        return ScopeConfig(
            metadata=metadata,
            settings=ScopeSettings(),
            targets=targets,
        )

    def _parse_csv_row(self, row: dict[str, str]) -> TargetDefinition:
        """Parse a single CSV row into a TargetDefinition."""
        target_type_str = row.get("type", "infrastructure").strip()
        try:
            target_type = TargetType(target_type_str)
        except ValueError:
            target_type = TargetType.INFRASTRUCTURE

        # Parse ports (semicolon-separated)
        ports: list[int] = []
        ports_str = row.get("ports", "").strip()
        if ports_str:
            ports = [int(p.strip()) for p in ports_str.split(";") if p.strip()]

        # Parse tags (semicolon-separated)
        tags: list[str] = []
        tags_str = row.get("tags", "").strip()
        if tags_str:
            tags = [t.strip() for t in tags_str.split(";") if t.strip()]

        # Parse focus areas (semicolon-separated)
        focus_areas: list[str] = []
        focus_str = row.get("focus_areas", "").strip()
        if focus_str:
            focus_areas = [f.strip() for f in focus_str.split(";") if f.strip()]

        # Parse credentials from environment variable references
        credentials: list[CredentialDefinition] = []
        creds_env = row.get("credentials_env", "").strip()
        if creds_env:
            # Format: USER_ENV:PASS_ENV or TOKEN_ENV
            parts = creds_env.split(":")
            if len(parts) == 2:
                credentials.append(
                    CredentialDefinition(
                        username=os.getenv(parts[0], parts[0]),
                        password_env=parts[1],
                    )
                )
            elif len(parts) == 1:
                credentials.append(
                    CredentialDefinition(
                        token_env=parts[0],
                    )
                )

        # Determine target identifier based on type
        target_value = row.get("target", "").strip()
        host = None
        url = None
        repo = None
        local_path = None

        if target_type in {TargetType.INFRASTRUCTURE, TargetType.NETWORK_DEVICE}:
            host = target_value
        elif target_type in {TargetType.WEB_APPLICATION, TargetType.API}:
            url = target_value
        elif target_type == TargetType.REPOSITORY:
            repo = target_value
        elif target_type == TargetType.LOCAL_CODE:
            local_path = target_value
        else:
            # Try to infer from value
            if target_value.startswith(("http://", "https://")):
                url = target_value
            elif target_value.startswith(("git@", "https://github.com", "https://gitlab.com")):
                repo = target_value
            elif target_value.startswith(("./", "/")):
                local_path = target_value
            else:
                host = target_value

        return TargetDefinition(
            host=host,
            url=url,
            repo=repo,
            path=local_path,
            name=row.get("name", target_value).strip(),
            type=target_type,
            network=row.get("network", "").strip() or None,
            ports=ports,
            tags=tags,
            focus_areas=focus_areas,
            credentials=credentials,
        )

    def _build_config(self, data: dict[str, Any], file_path: str | None = None) -> ScopeConfig:
        """Build ScopeConfig from parsed data dictionary."""
        try:
            # Parse metadata
            metadata_data = data.get("metadata", {})
            metadata = self._parse_metadata(metadata_data)

            # Parse settings
            settings_data = data.get("settings", {})
            settings = self._parse_settings(settings_data)

            # Parse networks
            networks_data = data.get("networks", [])
            networks = [self._parse_network(n) for n in networks_data]

            # Parse targets
            targets_data = data.get("targets", [])
            targets = [self._parse_target(t) for t in targets_data]

            # Parse exclusions
            exclusions_data = data.get("exclusions", {})
            exclusions = self._parse_exclusions(exclusions_data)

            # Parse domains
            domains_data = data.get("domains", {})
            domains = self._parse_domains(domains_data)

            # Parse test focus
            test_focus_data = data.get("test_focus", [])
            test_focus = self._parse_test_focus(test_focus_data)

            return ScopeConfig(
                metadata=metadata,
                settings=settings,
                networks=networks,
                targets=targets,
                exclusions=exclusions,
                domains=domains,
                test_focus=test_focus,
            )

        except Exception as e:
            raise ScopeParseError(f"Failed to build config: {e}", file_path) from e

    def _parse_metadata(self, data: dict[str, Any]) -> ScopeMetadata:
        """Parse metadata section."""
        engagement_type = data.get("engagement_type", "internal")
        if isinstance(engagement_type, str):
            try:
                engagement_type = EngagementType(engagement_type)
            except ValueError:
                engagement_type = EngagementType.INTERNAL

        return ScopeMetadata(
            engagement_name=data.get("engagement_name", "Unnamed Engagement"),
            engagement_type=engagement_type,
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            tester=data.get("tester"),
            notes=data.get("notes"),
            client=data.get("client"),
            project_id=data.get("project_id"),
        )

    def _parse_settings(self, data: dict[str, Any]) -> ScopeSettings:
        """Parse settings section."""
        operational_mode = data.get("operational_mode", "poc-only")
        if isinstance(operational_mode, str):
            try:
                operational_mode = OperationalMode(operational_mode)
            except ValueError:
                operational_mode = OperationalMode.POC_ONLY

        return ScopeSettings(
            operational_mode=operational_mode,
            max_agents=data.get("max_agents", 20),
            require_validation=data.get("require_validation", True),
            generate_fixes=data.get("generate_fixes", False),
            max_iterations=data.get("max_iterations", 300),
            timeout_minutes=data.get("timeout_minutes", 120),
            parallel_scanning=data.get("parallel_scanning", True),
            auto_escalate=data.get("auto_escalate", False),
        )

    def _parse_network(self, data: dict[str, Any]) -> NetworkDefinition:
        """Parse a network definition."""
        network_type = data.get("type", "internal")
        if isinstance(network_type, str):
            try:
                network_type = NetworkType(network_type)
            except ValueError:
                network_type = NetworkType.INTERNAL

        return NetworkDefinition(
            name=data.get("name", "Unnamed Network"),
            type=network_type,
            cidr=data.get("cidr", "0.0.0.0/0"),
            vlan=data.get("vlan"),
            gateway=data.get("gateway"),
            description=data.get("description"),
        )

    def _parse_target(self, data: dict[str, Any]) -> TargetDefinition:
        """Parse a target definition."""
        target_type = data.get("type", "infrastructure")
        if isinstance(target_type, str):
            try:
                target_type = TargetType(target_type)
            except ValueError:
                target_type = TargetType.INFRASTRUCTURE

        auth_type = data.get("auth_type", "none")
        if isinstance(auth_type, str):
            try:
                auth_type = AuthType(auth_type)
            except ValueError:
                auth_type = AuthType.NONE

        # Parse services
        services = []
        for svc in data.get("services", []):
            services.append(
                ServiceDefinition(
                    port=svc.get("port", 0),
                    service=svc.get("service", "unknown"),
                    version=svc.get("version"),
                    protocol=svc.get("protocol", "tcp"),
                    banner=svc.get("banner"),
                )
            )

        # Parse credentials
        credentials = []
        for cred in data.get("credentials", []):
            access_level = cred.get("access_level", "user")
            if isinstance(access_level, str):
                try:
                    access_level = AccessLevel(access_level)
                except ValueError:
                    access_level = AccessLevel.USER

            credentials.append(
                CredentialDefinition(
                    username=cred.get("username"),
                    password=cred.get("password"),
                    password_env=cred.get("password_env"),
                    access_level=access_level,
                    token=cred.get("token"),
                    token_env=cred.get("token_env"),
                    api_key=cred.get("api_key"),
                    api_key_env=cred.get("api_key_env"),
                    description=cred.get("description"),
                )
            )

        return TargetDefinition(
            host=data.get("host"),
            url=data.get("url"),
            repo=data.get("repo"),
            path=data.get("path"),
            name=data.get("name", "Unnamed Target"),
            type=target_type,
            network=data.get("network"),
            description=data.get("description"),
            tags=data.get("tags", []),
            ports=data.get("ports", []),
            services=services,
            technologies=data.get("technologies", []),
            auth_type=auth_type,
            openapi_spec=data.get("openapi_spec"),
            graphql_schema=data.get("graphql_schema"),
            credentials=credentials,
            token_env=data.get("token_env"),
            branch=data.get("branch"),
            focus_areas=data.get("focus_areas", []),
            modules=data.get("modules", []),
            priority=data.get("priority", 1),
            critical=data.get("critical", False),
        )

    def _parse_exclusions(self, data: dict[str, Any]) -> ExclusionDefinition:
        """Parse exclusion definitions."""
        return ExclusionDefinition(
            hosts=data.get("hosts", []),
            cidrs=data.get("cidrs", []),
            urls=data.get("urls", []),
            paths=data.get("paths", []),
            ports=data.get("ports", []),
            services=data.get("services", []),
        )

    def _parse_domains(self, data: dict[str, Any]) -> DomainScope:
        """Parse domain scope definitions."""
        return DomainScope(
            in_scope=data.get("in_scope", []),
            out_of_scope=data.get("out_of_scope", []),
        )

    def _parse_test_focus(self, data: list[str] | dict[str, Any]) -> TestFocus:
        """Parse test focus configuration."""
        if isinstance(data, list):
            # Simple list format (just areas)
            return TestFocus(areas=data)
        elif isinstance(data, dict):
            return TestFocus(
                areas=data.get("areas", []),
                excluded_areas=data.get("excluded_areas", []),
                priority_vulnerabilities=data.get("priority_vulnerabilities", []),
            )
        return TestFocus()

    def resolve_env_vars(self, config: ScopeConfig) -> dict[str, str | None]:
        """
        Resolve all environment variables referenced in the config.

        Returns a dictionary of env var names to their resolved values (or None if not set).
        """
        env_vars: dict[str, str | None] = {}

        for target in config.targets:
            if target.token_env:
                env_vars[target.token_env] = os.getenv(target.token_env)

            for cred in target.credentials:
                if cred.password_env:
                    env_vars[cred.password_env] = os.getenv(cred.password_env)
                if cred.token_env:
                    env_vars[cred.token_env] = os.getenv(cred.token_env)
                if cred.api_key_env:
                    env_vars[cred.api_key_env] = os.getenv(cred.api_key_env)

        return env_vars


def load_scope(file_path: str | Path) -> ScopeConfig:
    """
    Convenience function to load a scope configuration file.

    Args:
        file_path: Path to the configuration file

    Returns:
        Parsed ScopeConfig
    """
    parser = ScopeConfigParser()
    return parser.parse_file(file_path)


def load_scope_from_string(content: str, format: str = "yaml") -> ScopeConfig:
    """
    Convenience function to load scope configuration from a string.

    Args:
        content: Configuration content
        format: Format type (yaml, json)

    Returns:
        Parsed ScopeConfig
    """
    parser = ScopeConfigParser()
    return parser.parse_string(content, format)
