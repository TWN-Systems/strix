"""
Strix Scope Models

Comprehensive Pydantic models for defining engagement scope, targets,
networks, and credentials for security assessments.
"""

from __future__ import annotations

import ipaddress
import re
from datetime import date
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator, model_validator


class EngagementType(str, Enum):
    """Type of security engagement."""

    INTERNAL = "internal"
    EXTERNAL = "external"
    WEB_APP = "web_application"
    API = "api"
    INFRASTRUCTURE = "infrastructure"
    CLOUD = "cloud"
    HYBRID = "hybrid"


class OperationalMode(str, Enum):
    """Operational mode for the engagement."""

    RECON_ONLY = "recon-only"
    POC_ONLY = "poc-only"
    FULL_EXPLOIT = "full-exploit"
    PASSIVE = "passive"


class TargetType(str, Enum):
    """Type of target being assessed."""

    INFRASTRUCTURE = "infrastructure"
    WEB_APPLICATION = "web_application"
    API = "api"
    REPOSITORY = "repository"
    LOCAL_CODE = "local_code"
    MOBILE = "mobile"
    IOT = "iot"
    NETWORK_DEVICE = "network_device"


class NetworkType(str, Enum):
    """Type of network."""

    INTERNAL = "internal"
    EXTERNAL = "external"
    DMZ = "dmz"
    CLOUD = "cloud"
    HYBRID = "hybrid"


class AuthType(str, Enum):
    """Authentication type for API targets."""

    NONE = "none"
    BASIC = "basic"
    BEARER = "bearer"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    JWT = "jwt"
    CUSTOM = "custom"


class AccessLevel(str, Enum):
    """Access level for credentials."""

    NONE = "none"
    USER = "user"
    ADMIN = "admin"
    SUPERUSER = "superuser"
    SERVICE = "service"
    READ_ONLY = "read_only"


class ScopeMetadata(BaseModel):
    """Metadata about the engagement."""

    engagement_name: str = Field(..., min_length=1, description="Name of the engagement")
    engagement_type: EngagementType = Field(
        default=EngagementType.INTERNAL, description="Type of engagement"
    )
    start_date: date | None = Field(default=None, description="Start date of the engagement")
    end_date: date | None = Field(default=None, description="End date of the engagement")
    tester: str | None = Field(default=None, description="Name of the tester")
    notes: str | None = Field(default=None, description="Additional engagement notes")
    client: str | None = Field(default=None, description="Client name")
    project_id: str | None = Field(default=None, description="Project identifier")

    @model_validator(mode="after")
    def validate_dates(self) -> ScopeMetadata:
        """Validate that end_date is after start_date."""
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class ScopeSettings(BaseModel):
    """Settings for the scope/engagement."""

    operational_mode: OperationalMode = Field(
        default=OperationalMode.POC_ONLY, description="Operational mode for testing"
    )
    max_agents: int = Field(default=20, ge=1, le=100, description="Maximum number of agents")
    require_validation: bool = Field(
        default=True, description="Require scope validation before testing"
    )
    generate_fixes: bool = Field(
        default=False, description="Generate fix recommendations for vulnerabilities"
    )
    max_iterations: int = Field(
        default=300, ge=1, le=1000, description="Maximum iterations per agent"
    )
    timeout_minutes: int = Field(
        default=120, ge=1, le=480, description="Timeout in minutes for the engagement"
    )
    parallel_scanning: bool = Field(
        default=True, description="Enable parallel scanning of targets"
    )
    auto_escalate: bool = Field(
        default=False, description="Automatically escalate findings"
    )


class ServiceDefinition(BaseModel):
    """Definition of a service running on a target."""

    port: int = Field(..., ge=1, le=65535, description="Port number")
    service: str = Field(..., min_length=1, description="Service name")
    version: str | None = Field(default=None, description="Service version")
    protocol: str = Field(default="tcp", pattern="^(tcp|udp)$", description="Protocol")
    banner: str | None = Field(default=None, description="Service banner")


class CredentialDefinition(BaseModel):
    """Definition of credentials for authentication."""

    username: str | None = Field(default=None, description="Username")
    password: str | None = Field(default=None, description="Password (plaintext - use env vars)")
    password_env: str | None = Field(
        default=None, description="Environment variable containing password"
    )
    access_level: AccessLevel = Field(
        default=AccessLevel.USER, description="Access level for these credentials"
    )
    token: str | None = Field(default=None, description="Token value (use env vars)")
    token_env: str | None = Field(
        default=None, description="Environment variable containing token"
    )
    api_key: str | None = Field(default=None, description="API key (use env vars)")
    api_key_env: str | None = Field(
        default=None, description="Environment variable containing API key"
    )
    description: str | None = Field(default=None, description="Description of credentials")

    @model_validator(mode="after")
    def validate_credentials(self) -> CredentialDefinition:
        """Ensure at least one credential method is provided."""
        has_password = self.password or self.password_env
        has_token = self.token or self.token_env
        has_api_key = self.api_key or self.api_key_env

        if not (self.username or has_password or has_token or has_api_key):
            raise ValueError("At least one credential method must be provided")
        return self


class NetworkDefinition(BaseModel):
    """Definition of a network in scope."""

    name: str = Field(..., min_length=1, description="Network name")
    type: NetworkType = Field(default=NetworkType.INTERNAL, description="Network type")
    cidr: str = Field(..., description="CIDR notation for the network")
    vlan: int | None = Field(default=None, ge=1, le=4094, description="VLAN ID")
    gateway: str | None = Field(default=None, description="Gateway IP address")
    description: str | None = Field(default=None, description="Network description")

    # Pre-computed values (populated during parsing)
    network_address: str | None = Field(default=None, description="Computed network address")
    broadcast_address: str | None = Field(default=None, description="Computed broadcast address")
    num_hosts: int | None = Field(default=None, description="Computed number of hosts")
    host_range: tuple[str, str] | None = Field(default=None, description="Computed host range")

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        """Validate CIDR notation."""
        try:
            ipaddress.ip_network(v, strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid CIDR notation: {v}") from e
        return v

    @field_validator("gateway")
    @classmethod
    def validate_gateway(cls, v: str | None) -> str | None:
        """Validate gateway IP address."""
        if v is None:
            return v
        try:
            ipaddress.ip_address(v)
        except ValueError as e:
            raise ValueError(f"Invalid gateway IP address: {v}") from e
        return v

    def compute_network_info(self) -> None:
        """Compute network information from CIDR."""
        network = ipaddress.ip_network(self.cidr, strict=False)
        self.network_address = str(network.network_address)
        self.broadcast_address = str(network.broadcast_address)
        self.num_hosts = network.num_addresses - 2 if network.prefixlen < 31 else network.num_addresses
        if network.num_addresses > 2:
            hosts = list(network.hosts())
            self.host_range = (str(hosts[0]), str(hosts[-1]))


class TargetDefinition(BaseModel):
    """Definition of a target in scope."""

    # Target identifiers (one required)
    host: str | None = Field(default=None, description="IP address or hostname")
    url: str | None = Field(default=None, description="URL for web targets")
    repo: str | None = Field(default=None, description="Repository URL")
    path: str | None = Field(default=None, description="Local path for code analysis")

    # Common fields
    name: str = Field(..., min_length=1, description="Human-readable target name")
    type: TargetType = Field(default=TargetType.INFRASTRUCTURE, description="Target type")
    network: str | None = Field(default=None, description="Associated network name")
    description: str | None = Field(default=None, description="Target description")
    tags: list[str] = Field(default_factory=list, description="Tags for filtering")

    # Infrastructure-specific
    ports: list[int] = Field(default_factory=list, description="Ports to scan")
    services: list[ServiceDefinition] = Field(
        default_factory=list, description="Known services"
    )

    # Web/API-specific
    technologies: list[str] = Field(
        default_factory=list, description="Known technologies in use"
    )
    auth_type: AuthType = Field(default=AuthType.NONE, description="Authentication type")
    openapi_spec: str | None = Field(default=None, description="Path to OpenAPI spec")
    graphql_schema: str | None = Field(default=None, description="Path to GraphQL schema")

    # Credentials
    credentials: list[CredentialDefinition] = Field(
        default_factory=list, description="Credentials for authentication"
    )
    token_env: str | None = Field(
        default=None, description="Environment variable for bearer token"
    )

    # Repository-specific
    branch: str | None = Field(default=None, description="Git branch to analyze")

    # Focus and modules
    focus_areas: list[str] = Field(
        default_factory=list, description="Vulnerability types to focus on"
    )
    modules: list[str] = Field(
        default_factory=list, description="Prompt modules to load for this target"
    )

    # Priority and criticality
    priority: int = Field(default=1, ge=1, le=10, description="Priority level (1-10)")
    critical: bool = Field(default=False, description="Mark as critical target")

    @model_validator(mode="after")
    def validate_target_identifier(self) -> TargetDefinition:
        """Ensure at least one target identifier is provided."""
        identifiers = [self.host, self.url, self.repo, self.path]
        if not any(identifiers):
            raise ValueError(
                "At least one target identifier (host, url, repo, path) must be provided"
            )
        return self

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str | None) -> str | None:
        """Validate host IP address or hostname."""
        if v is None:
            return v
        # Try as IP address first
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError:
            pass
        # Validate as hostname
        hostname_pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
        if not re.match(hostname_pattern, v):
            raise ValueError(f"Invalid host: {v}")
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        """Validate URL format."""
        if v is None:
            return v
        url_pattern = r"^https?://[^\s]+$"
        if not re.match(url_pattern, v):
            raise ValueError(f"Invalid URL format: {v}")
        return v

    @field_validator("ports")
    @classmethod
    def validate_ports(cls, v: list[int]) -> list[int]:
        """Validate port numbers."""
        for port in v:
            if not 1 <= port <= 65535:
                raise ValueError(f"Invalid port number: {port}")
        return v

    def get_identifier(self) -> str:
        """Get the primary identifier for this target."""
        return self.host or self.url or self.repo or self.path or self.name


class ExclusionDefinition(BaseModel):
    """Definition of exclusions from scope."""

    hosts: list[str] = Field(default_factory=list, description="Hosts to exclude")
    cidrs: list[str] = Field(default_factory=list, description="CIDR ranges to exclude")
    urls: list[str] = Field(default_factory=list, description="URLs to exclude")
    paths: list[str] = Field(
        default_factory=list, description="URL paths to exclude (supports wildcards)"
    )
    ports: list[int] = Field(default_factory=list, description="Ports to exclude")
    services: list[str] = Field(default_factory=list, description="Services to exclude")

    # Pre-computed exclusion networks
    exclusion_networks: list[Any] = Field(
        default_factory=list, description="Computed exclusion networks"
    )

    @field_validator("cidrs")
    @classmethod
    def validate_cidrs(cls, v: list[str]) -> list[str]:
        """Validate CIDR notations."""
        for cidr in v:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError as e:
                raise ValueError(f"Invalid exclusion CIDR: {cidr}") from e
        return v

    @field_validator("ports")
    @classmethod
    def validate_ports(cls, v: list[int]) -> list[int]:
        """Validate port numbers."""
        for port in v:
            if not 1 <= port <= 65535:
                raise ValueError(f"Invalid exclusion port: {port}")
        return v

    def compute_exclusion_networks(self) -> None:
        """Pre-compute exclusion networks for faster matching."""
        self.exclusion_networks = [
            ipaddress.ip_network(cidr, strict=False) for cidr in self.cidrs
        ]


class DomainScope(BaseModel):
    """Domain-based scope definition."""

    in_scope: list[str] = Field(
        default_factory=list, description="Domains in scope (supports wildcards)"
    )
    out_of_scope: list[str] = Field(
        default_factory=list, description="Domains out of scope"
    )

    # Compiled patterns for matching
    in_scope_patterns: list[Any] = Field(
        default_factory=list, description="Compiled regex patterns for in-scope"
    )
    out_of_scope_patterns: list[Any] = Field(
        default_factory=list, description="Compiled regex patterns for out-of-scope"
    )

    def compile_patterns(self) -> None:
        """Compile domain patterns to regex for efficient matching."""
        self.in_scope_patterns = []
        self.out_of_scope_patterns = []

        for domain in self.in_scope:
            pattern = domain.replace(".", r"\.").replace("*", r"[^.]+")
            self.in_scope_patterns.append(re.compile(f"^{pattern}$", re.IGNORECASE))

        for domain in self.out_of_scope:
            pattern = domain.replace(".", r"\.").replace("*", r"[^.]+")
            self.out_of_scope_patterns.append(re.compile(f"^{pattern}$", re.IGNORECASE))

    def is_in_scope(self, domain: str) -> bool:
        """Check if a domain is in scope."""
        # First check out-of-scope (explicit exclusions take precedence)
        for pattern in self.out_of_scope_patterns:
            if pattern.match(domain):
                return False

        # Then check in-scope
        for pattern in self.in_scope_patterns:
            if pattern.match(domain):
                return True

        return False


class TestFocus(BaseModel):
    """Test focus areas and priorities."""

    areas: list[str] = Field(
        default_factory=list, description="Specific test focus areas"
    )
    excluded_areas: list[str] = Field(
        default_factory=list, description="Test areas to exclude"
    )
    priority_vulnerabilities: list[str] = Field(
        default_factory=list, description="High-priority vulnerability types"
    )


class ScopeConfig(BaseModel):
    """Complete scope configuration for an engagement."""

    metadata: ScopeMetadata = Field(..., description="Engagement metadata")
    settings: ScopeSettings = Field(
        default_factory=ScopeSettings, description="Engagement settings"
    )
    networks: list[NetworkDefinition] = Field(
        default_factory=list, description="Networks in scope"
    )
    targets: list[TargetDefinition] = Field(
        default_factory=list, description="Targets in scope"
    )
    exclusions: ExclusionDefinition = Field(
        default_factory=ExclusionDefinition, description="Scope exclusions"
    )
    domains: DomainScope = Field(
        default_factory=DomainScope, description="Domain-based scope"
    )
    test_focus: TestFocus = Field(
        default_factory=TestFocus, description="Test focus configuration"
    )

    # Lookup tables (populated during parsing)
    networks_by_name: dict[str, NetworkDefinition] = Field(
        default_factory=dict, description="Networks indexed by name"
    )
    targets_by_name: dict[str, TargetDefinition] = Field(
        default_factory=dict, description="Targets indexed by name"
    )
    targets_by_tag: dict[str, list[TargetDefinition]] = Field(
        default_factory=dict, description="Targets indexed by tag"
    )

    def build_indexes(self) -> None:
        """Build lookup indexes for efficient access."""
        # Index networks by name
        self.networks_by_name = {net.name: net for net in self.networks}

        # Index targets by name
        self.targets_by_name = {target.name: target for target in self.targets}

        # Index targets by tag
        self.targets_by_tag = {}
        for target in self.targets:
            for tag in target.tags:
                if tag not in self.targets_by_tag:
                    self.targets_by_tag[tag] = []
                self.targets_by_tag[tag].append(target)

    def compute_all(self) -> None:
        """Compute all derived values and indexes."""
        # Compute network info
        for network in self.networks:
            network.compute_network_info()

        # Compute exclusion networks
        self.exclusions.compute_exclusion_networks()

        # Compile domain patterns
        self.domains.compile_patterns()

        # Build indexes
        self.build_indexes()

    def get_targets_by_filter(
        self,
        tags: list[str] | None = None,
        target_type: TargetType | None = None,
        network: str | None = None,
        critical_only: bool = False,
    ) -> list[TargetDefinition]:
        """Filter targets based on criteria."""
        result = self.targets.copy()

        if tags:
            result = [
                t for t in result if any(tag in t.tags for tag in tags)
            ]

        if target_type:
            result = [t for t in result if t.type == target_type]

        if network:
            result = [t for t in result if t.network == network]

        if critical_only:
            result = [t for t in result if t.critical]

        return result

    def is_host_in_scope(self, host: str) -> bool:
        """Check if a host IP is within scope."""
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            # Not an IP, check as hostname in domains
            return self.domains.is_in_scope(host)

        # Check exclusions first
        for excluded in self.exclusions.hosts:
            try:
                if ip == ipaddress.ip_address(excluded):
                    return False
            except ValueError:
                continue

        for network in self.exclusions.exclusion_networks:
            if ip in network:
                return False

        # Check if in any defined network
        for network in self.networks:
            try:
                net = ipaddress.ip_network(network.cidr, strict=False)
                if ip in net:
                    return True
            except ValueError:
                continue

        return False

    def is_port_in_scope(self, port: int) -> bool:
        """Check if a port is within scope."""
        return port not in self.exclusions.ports

    def is_url_in_scope(self, url: str) -> bool:
        """Check if a URL is within scope."""
        # Check exact exclusions
        if url in self.exclusions.urls:
            return False

        # Check path pattern exclusions
        for path_pattern in self.exclusions.paths:
            regex_pattern = path_pattern.replace("*", ".*")
            if re.search(regex_pattern, url):
                return False

        return True
