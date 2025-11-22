# Scope Configuration

## Overview

Strix supports structured scope configuration via YAML or JSON files, enabling complex engagements with multiple networks, VLANs, and mixed internal/external targets. The scope system provides:

- **Network definitions** with CIDR ranges and VLAN info
- **Target metadata** including services, credentials, and focus areas
- **Exclusion rules** for hosts, URLs, ports, and paths
- **Domain boundaries** with wildcard support
- **Operational mode** control (recon-only, poc-only, full-pentest)

## Quick Start

```bash
# Run with scope file
strix --scope scope.yaml

# Validate scope file without running
strix --scope scope.yaml --validate

# Filter targets by criteria
strix --scope scope.yaml --filter "tags:critical"
strix --scope scope.yaml --filter "network:DMZ"

# Combine scope with manual targets
strix --scope scope.yaml --target https://extra-target.com
```

---

## Scope File Formats

### YAML (Recommended)

```yaml
# scope.yaml
metadata:
  engagement_name: "Acme Corp Pentest 2024"
  engagement_type: "internal"  # internal | external | hybrid
  start_date: "2024-01-15"
  end_date: "2024-01-30"
  tester: "security-team"

# Global settings
settings:
  operational_mode: "poc-only"  # recon-only | poc-only | full-pentest
  max_agents: 20
  require_validation: true
  generate_fixes: false

# Network scope definitions
networks:
  - name: "Corporate LAN"
    type: "internal"
    vlan: 10
    cidr: "10.0.10.0/24"
    gateway: "10.0.10.1"
    description: "Main corporate network"

  - name: "Server VLAN"
    type: "internal"
    vlan: 101
    cidr: "10.0.101.0/24"
    gateway: "10.0.101.1"
    description: "Production servers"

  - name: "DMZ"
    type: "external"
    cidr: "203.0.113.0/24"
    description: "Public-facing servers"

# Specific targets within scope
targets:
  # Infrastructure targets
  - host: "10.0.101.2"
    name: "Proxmox Host 1"
    type: "infrastructure"
    network: "Server VLAN"
    ports: [22, 8006]
    services:
      - port: 8006
        service: "proxmox-ve"
        version: "8.1"
    credentials:
      - username: "root"
        password_env: "PROXMOX_ROOT_PASS"  # Reference env var
        access_level: "admin"
    tags: ["hypervisor", "critical"]
    modules: ["proxmox_ve"]

  # Web application targets
  - url: "https://app.acme.com"
    name: "Customer Portal"
    type: "web_application"
    network: "DMZ"
    technologies: ["Django", "PostgreSQL", "Redis"]
    credentials:
      - username: "testuser@acme.com"
        password_env: "PORTAL_TEST_PASS"
        access_level: "user"
    focus_areas: ["authentication", "idor", "business_logic"]
    tags: ["customer-facing", "pii"]

  # API targets
  - url: "https://api.acme.com"
    name: "REST API"
    type: "api"
    network: "DMZ"
    auth_type: "bearer"
    token_env: "API_BEARER_TOKEN"
    openapi_spec: "./specs/api-v2.yaml"
    tags: ["api", "critical"]

  # Code repositories
  - repo: "https://github.com/acme/backend"
    name: "Backend Codebase"
    type: "repository"
    branch: "main"
    focus_areas: ["sql_injection", "authentication_jwt", "secrets"]

  - path: "./frontend"
    name: "Frontend Codebase"
    type: "local_code"
    focus_areas: ["xss", "csrf"]

# Exclusions - DO NOT TEST
exclusions:
  hosts:
    - "10.0.101.1"      # Gateway
    - "10.0.101.254"    # Network monitoring
  cidrs:
    - "10.0.102.0/24"   # Out of scope network
  urls:
    - "https://app.acme.com/health"
    - "https://app.acme.com/metrics"
  paths:
    - "/api/v1/legacy/*"
    - "/admin/dangerous/*"
  ports:
    - 161   # SNMP - don't touch
    - 162

# Domain scope for web testing
domains:
  in_scope:
    - "*.acme.com"
    - "*.acme-staging.com"
  out_of_scope:
    - "mail.acme.com"
    - "vpn.acme.com"
```

### JSON

```json
{
  "metadata": {
    "engagement_name": "Acme Corp Pentest 2024",
    "engagement_type": "internal"
  },
  "settings": {
    "operational_mode": "poc-only"
  },
  "networks": [
    {
      "name": "Server VLAN",
      "type": "internal",
      "vlan": 101,
      "cidr": "10.0.101.0/24"
    }
  ],
  "targets": [
    {
      "host": "10.0.101.2",
      "name": "Proxmox Host 1",
      "type": "infrastructure",
      "ports": [22, 8006]
    }
  ],
  "exclusions": {
    "hosts": ["10.0.101.1"],
    "cidrs": ["10.0.102.0/24"]
  }
}
```

---

## CLI Integration

### Basic Usage

```bash
# Load scope from YAML file
strix --scope scope.yaml

# Load scope from JSON file
strix --scope scope.json

# Validate scope file and exit
strix --scope scope.yaml --validate
```

### Filtering Targets

Filter targets from the scope file by various criteria:

```bash
# Filter by tags (comma-separated for multiple)
strix --scope scope.yaml --filter "tags:critical"
strix --scope scope.yaml --filter "tags:hypervisor,pii"

# Filter by network name
strix --scope scope.yaml --filter "network:DMZ"
strix --scope scope.yaml --filter "network:Server VLAN"

# Filter by target type
strix --scope scope.yaml --filter "type:infrastructure"
strix --scope scope.yaml --filter "type:web_application"

# Combine multiple filters
strix --scope scope.yaml --filter "tags:critical" --filter "network:DMZ"
```

### Combining with Manual Targets

Scope files can be combined with manual `--target` arguments:

```bash
# Scope file + additional target
strix --scope scope.yaml --target https://extra-target.com

# Scope file + custom instructions
strix --scope scope.yaml --instruction "Focus on authentication vulnerabilities"
```

---

## Validation

The scope validator checks for:

1. **Target validity**
   - At least one identifier (host, url, repo, or path)
   - Valid IP addresses for host fields
   - Valid port ranges (1-65535)

2. **Network validity**
   - No duplicate network names
   - Valid VLAN IDs (1-4094)
   - Valid CIDR notation
   - Gateway within CIDR range (warning if not)

3. **Exclusion validity**
   - Valid CIDR notation
   - Valid port ranges
   - Warnings for overlaps between targets and exclusions

4. **Credential security**
   - Warnings for missing environment variables

5. **Reference integrity**
   - Target network references must exist
   - Module references validated against available modules

### Validation Output

```bash
$ strix --scope scope.yaml --validate

Scope file is valid: scope.yaml

Warnings:
  - pve-node-01: Environment variable not set: PVE_ROOT_PASS

Scope Summary:
  Engagement: Proxmox Cluster Assessment
  Type: internal
  Mode: recon-only
  Networks: 1
  Targets: 3
```

---

## How Scope Affects Agent Behavior

When a scope file is loaded, the root agent receives:

1. **Scope Context** - Engagement metadata, settings, and network definitions
2. **Exclusion Rules** - Hosts, CIDRs, URLs, paths, and ports to avoid

### Operational Mode

The scope's `operational_mode` setting controls agent behavior:

| Mode | Behavior |
|------|----------|
| `recon-only` | Reconnaissance only, no exploitation, PoCs generated but not executed |
| `poc-only` | Discovery and PoC validation in sandbox, no active exploitation |
| `full-pentest` | Full testing including exploitation within scope boundaries |

### Scope Boundaries

Agents automatically respect:

- **In-scope**: Targets listed in scope, IPs within network CIDRs, domains matching `in_scope` patterns
- **Excluded**: Hosts, CIDRs, URLs, paths, ports, and domains in exclusion lists
- **Out-of-scope**: Domains matching `out_of_scope` patterns

---

## Target Definition Reference

### Common Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Human-readable name |
| `type` | string | `infrastructure`, `web_application`, `api`, `repository`, `local_code` |
| `network` | string | Reference to network definition |
| `tags` | list | Arbitrary tags for filtering |
| `focus_areas` | list | Vulnerability types to prioritize |
| `modules` | list | Prompt modules to load |

### Target Identifiers (one required)

| Field | Type | Description |
|-------|------|-------------|
| `host` | string | IP address |
| `url` | string | Web URL |
| `repo` | string | Git repository URL |
| `path` | string | Local filesystem path |

### Infrastructure Fields

| Field | Type | Description |
|-------|------|-------------|
| `ports` | list[int] | Open ports |
| `services` | list | Service definitions with port, service, version |
| `credentials` | list | Credential definitions |

### Web/API Fields

| Field | Type | Description |
|-------|------|-------------|
| `technologies` | list | Known tech stack |
| `auth_type` | string | `bearer`, `basic`, `api_key` |
| `token_env` | string | Environment variable for auth token |
| `openapi_spec` | string | Path to OpenAPI spec file |

### Repository Fields

| Field | Type | Description |
|-------|------|-------------|
| `branch` | string | Git branch to analyze |

---

## Templates

Pre-built scope templates are available in `templates/scope/`:

- `scope.yaml` - Full YAML template with all options
- `scope.json` - JSON template
- `scope-simple.csv` - Simple CSV for target lists
- `proxmox-cluster.yaml` - Proxmox cluster assessment

---

## Future: Database Integration

The scope parser is designed with future SQLite/Redis integration in mind:

```python
# Current: File-based
scope = ScopeConfig.from_file("scope.yaml")

# Future: Database-backed
scope = ScopeConfig.from_dict(db.get_scope(engagement_id))
db.save_scope(engagement_id, scope.to_dict())

# Future: Redis cache
scope = ScopeConfig.from_dict(redis.get_json("scope:12345"))
```

The `to_dict()` and `from_dict()` methods enable serialization to any backend. See `docs/CACHE_IMPLEMENTATION.md` for the planned caching architecture.

---

## Module Structure

```
strix/scope/
├── __init__.py      # Public exports
├── models.py        # Pydantic models for scope configuration
├── parser.py        # ScopeConfig class with parsing and conversion
└── validator.py     # ScopeValidator with validation rules
```

### Key Classes

- **ScopeConfig**: Main class for loading, validating, and querying scope
- **ScopeConfigModel**: Pydantic model for scope structure
- **ScopeValidator**: Validates scope for correctness and security
- **ValidationResult**: Contains errors and warnings from validation
