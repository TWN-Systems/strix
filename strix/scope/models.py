"""Pydantic models for scope configuration."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class ScopeMetadata(BaseModel):
    """Engagement metadata."""

    engagement_name: str = "Unnamed Engagement"
    engagement_type: str = "internal"  # internal | external | hybrid
    start_date: str | None = None
    end_date: str | None = None
    tester: str | None = None
    notes: str | None = None

    @field_validator("engagement_type")
    @classmethod
    def validate_engagement_type(cls, v: str) -> str:
        valid_types = {"internal", "external", "hybrid"}
        if v.lower() not in valid_types:
            raise ValueError(f"engagement_type must be one of: {valid_types}")
        return v.lower()


class ScopeSettings(BaseModel):
    """Global scan settings."""

    operational_mode: str = "poc-only"  # recon-only | poc-only | full-pentest
    max_agents: int = 20
    require_validation: bool = True
    generate_fixes: bool = False

    @field_validator("operational_mode")
    @classmethod
    def validate_operational_mode(cls, v: str) -> str:
        valid_modes = {"recon-only", "poc-only", "full-pentest"}
        if v.lower() not in valid_modes:
            raise ValueError(f"operational_mode must be one of: {valid_modes}")
        return v.lower()


class ServiceDefinition(BaseModel):
    """Service running on a port."""

    port: int
    service: str
    version: str | None = None


class CredentialDefinition(BaseModel):
    """Credential for a target (password stored via env var reference)."""

    username: str
    password_env: str | None = None  # Environment variable name
    token_env: str | None = None  # For bearer tokens
    access_level: str = "user"  # user | admin | readonly


class NetworkDefinition(BaseModel):
    """Network/VLAN definition."""

    name: str
    type: str = "internal"  # internal | external
    vlan: int | None = None
    cidr: str | None = None
    gateway: str | None = None
    description: str | None = None

    @field_validator("type")
    @classmethod
    def validate_network_type(cls, v: str) -> str:
        valid_types = {"internal", "external"}
        if v.lower() not in valid_types:
            raise ValueError(f"network type must be one of: {valid_types}")
        return v.lower()


class TargetDefinition(BaseModel):
    """Individual target definition."""

    # One of these must be set
    host: str | None = None  # IP address
    url: str | None = None  # Web URL
    repo: str | None = None  # Git repository
    path: str | None = None  # Local path

    # Metadata
    name: str | None = None
    type: str | None = None  # infrastructure | web_application | api | repository | local_code
    network: str | None = None  # Reference to NetworkDefinition.name

    # Details
    ports: list[int] = Field(default_factory=list)
    services: list[ServiceDefinition] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    credentials: list[CredentialDefinition] = Field(default_factory=list)

    # Testing configuration
    focus_areas: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    # API-specific
    auth_type: str | None = None  # bearer | basic | api_key
    token_env: str | None = None
    openapi_spec: str | None = None

    # Repository-specific
    branch: str | None = None

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_target_value(self) -> str:
        """Get the primary target identifier."""
        return self.host or self.url or self.repo or self.path or ""

    def get_target_type(self) -> str:
        """Infer target type if not explicitly set."""
        if self.type:
            return self.type
        if self.host:
            return "infrastructure"
        if self.url:
            return "web_application"
        if self.repo:
            return "repository"
        if self.path:
            return "local_code"
        return "unknown"


class Exclusions(BaseModel):
    """Targets and patterns to exclude from testing."""

    hosts: list[str] = Field(default_factory=list)
    cidrs: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)
    ports: list[int] = Field(default_factory=list)


class DomainScope(BaseModel):
    """Domain boundaries for web testing."""

    in_scope: list[str] = Field(default_factory=list)  # Supports wildcards: *.example.com
    out_of_scope: list[str] = Field(default_factory=list)


class ScopeConfigModel(BaseModel):
    """Complete scope configuration model."""

    metadata: ScopeMetadata = Field(default_factory=ScopeMetadata)
    settings: ScopeSettings = Field(default_factory=ScopeSettings)
    networks: list[NetworkDefinition] = Field(default_factory=list)
    targets: list[TargetDefinition] = Field(default_factory=list)
    exclusions: Exclusions = Field(default_factory=Exclusions)
    domains: DomainScope = Field(default_factory=DomainScope)

    def get_network_by_name(self, name: str) -> NetworkDefinition | None:
        """Look up network by name."""
        for network in self.networks:
            if network.name == name:
                return network
        return None
