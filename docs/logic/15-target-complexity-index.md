# Target Complexity Index (TCI) Calculation

This diagram illustrates the Target Complexity Index calculation system that enables adaptive, context-aware vulnerability scanning.

## Overview

The TCI system provides:
1. Multi-dimensional fingerprint analysis (25+ attributes)
2. Configurable weighted scoring (9 component dimensions)
3. Complexity level classification (minimal → critical)
4. Security posture assessment
5. Module recommendations and scan hints
6. Integration with the Adaptive Scan Planner

## Architecture

```mermaid
flowchart TB
    subgraph Input
        FP[TargetFingerprint]
        CFG[TCIConfig]
    end

    subgraph TCI Calculator
        CALC[TargetComplexityIndex]
        PORT[Port Score]
        SVC[Service Diversity]
        RISK[High-Risk Ports]
        TECH[Tech Stack]
        AUTH[Auth Complexity]
        API[API Surface]
        WAF[WAF/CDN]
        DATA[Data Sensitivity]
        CLOUD[Cloud Complexity]
    end

    subgraph Output
        RESULT[TCIResult]
        SCORE[Score 0-100]
        LEVEL[ComplexityLevel]
        POSTURE[SecurityPosture]
        MODULES[Recommended Modules]
        HINTS[Scan Hints]
    end

    FP --> CALC
    CFG --> CALC
    CALC --> PORT & SVC & RISK & TECH & AUTH & API & WAF & DATA & CLOUD
    PORT & SVC & RISK & TECH & AUTH & API & WAF & DATA & CLOUD --> RESULT
    RESULT --> SCORE & LEVEL & POSTURE & MODULES & HINTS
```

## Sequence Diagram: TCI Calculation Flow

```mermaid
sequenceDiagram
    autonumber
    participant Scanner as Scanner Agent
    participant TCI as TargetComplexityIndex
    participant Config as TCIConfig
    participant FP as TargetFingerprint
    participant Result as TCIResult

    Scanner->>FP: Create fingerprint from recon
    Note right of FP: TargetFingerprint(<br/>open_ports=[22,80,443,8080],<br/>technologies=["nginx","django"],<br/>auth_types=["jwt","oauth2"],<br/>has_waf=True,<br/>api_endpoints=150<br/>)

    Scanner->>TCI: compute_tci(fingerprint, config)
    TCI->>Config: Load weight configuration
    Config-->>TCI: TCIConfig with weights

    rect rgb(240, 248, 255)
        Note over TCI,FP: Phase 1: Component Score Calculation

        TCI->>TCI: _calculate_port_score()
        Note right of TCI: 4 ports → score: 0.24

        TCI->>TCI: _calculate_service_diversity_score()
        Note right of TCI: 3 unique services → score: 0.40

        TCI->>TCI: _calculate_high_risk_ports_score()
        Note right of TCI: SSH(22), HTTP-Alt(8080) → score: 0.40

        TCI->>TCI: _calculate_tech_stack_score()
        Note right of TCI: nginx(0.4), django(0.5) → score: 0.55

        TCI->>TCI: _calculate_auth_complexity_score()
        Note right of TCI: jwt(0.7), oauth2(0.85) → score: 0.95

        TCI->>TCI: _calculate_api_surface_score()
        Note right of TCI: 150 endpoints → score: 0.70

        TCI->>TCI: _calculate_waf_complexity_score()
        Note right of TCI: WAF present → score: 0.50

        TCI->>TCI: _calculate_data_sensitivity_score()
        Note right of TCI: Default → score: 0.50

        TCI->>TCI: _calculate_cloud_complexity_score()
        Note right of TCI: No cloud → score: 0.00
    end

    rect rgb(255, 248, 240)
        Note over TCI,Result: Phase 2: Weighted Aggregation
        TCI->>TCI: Calculate weighted sum
        Note right of TCI: weighted_score = Σ(score × weight)

        TCI->>TCI: Normalize to 0-100 scale
        Note right of TCI: final_score = 65.4
    end

    rect rgb(240, 255, 240)
        Note over TCI,Result: Phase 3: Classification
        TCI->>TCI: _determine_complexity_level(65.4)
        Note right of TCI: 61-80 → HIGH

        TCI->>TCI: _determine_security_posture()
        Note right of TCI: WAF present → STANDARD
    end

    rect rgb(255, 240, 255)
        Note over TCI,Result: Phase 4: Recommendations
        TCI->>TCI: _generate_module_recommendations()
        Note right of TCI: jwt → authentication_jwt, idor<br/>oauth → oauth_testing<br/>api → api_security, business_logic

        TCI->>TCI: _generate_priority_vulnerabilities()
        Note right of TCI: JWT Vulnerabilities, IDOR,<br/>Broken Access Control, XSS

        TCI->>TCI: Calculate scan hints
        Note right of TCI: timeout_multiplier: 1.95<br/>safe_mode: true<br/>max_parallel: 5
    end

    TCI->>Result: Create TCIResult
    TCI-->>Scanner: TCIResult(score=65.4, level=HIGH)
```

## Sequence Diagram: Port and Service Analysis

```mermaid
sequenceDiagram
    autonumber
    participant TCI as TCI Calculator
    participant FP as Fingerprint
    participant Scores as Score Components

    TCI->>FP: Get open_ports
    FP-->>TCI: [21, 22, 80, 443, 3306, 8080]

    rect rgb(240, 248, 255)
        Note over TCI,Scores: Port Count Scoring
        TCI->>TCI: port_count = 6

        alt 0-5 ports (Low)
            TCI->>Scores: score = count/5 × 0.3
        else 6-15 ports (Medium)
            TCI->>Scores: score = 0.3 + (count-5)/10 × 0.4
        else 16-30 ports (High)
            TCI->>Scores: score = 0.7 + (count-15)/15 × 0.2
        else 30+ ports (Critical)
            TCI->>Scores: score = 0.9 + min(0.1, (count-30)/50 × 0.1)
        end

        Note right of Scores: 6 ports → 0.34
    end

    rect rgb(255, 248, 240)
        Note over TCI,Scores: High-Risk Port Detection
        TCI->>TCI: Check against HIGH_RISK_PORTS set
        Note right of TCI: HIGH_RISK_PORTS includes:<br/>21(FTP), 22(SSH), 23(Telnet),<br/>3306(MySQL), 3389(RDP), etc.

        TCI->>TCI: high_risk_found = [21, 22, 3306]
        TCI->>TCI: base_score = min(1.0, 3/10) = 0.3

        TCI->>TCI: Check dangerous ports
        Note right of TCI: Dangerous: 23, 445, 3389,<br/>1433, 3306, 5432, 27017

        TCI->>TCI: 3306 is dangerous → bonus +0.2
        TCI->>Scores: high_risk_score = 0.5
    end

    rect rgb(240, 255, 240)
        Note over TCI,Scores: Service Diversity Scoring
        TCI->>FP: Get services mapping
        FP-->>TCI: {21: "ftp", 22: "ssh", 80: "http", 443: "https", 3306: "mysql", 8080: "http-proxy"}

        TCI->>TCI: unique_services = 5
        TCI->>TCI: score = log₂(5+1) / 5
        TCI->>Scores: service_diversity_score = 0.52
    end
```

## Sequence Diagram: Technology Stack Analysis

```mermaid
sequenceDiagram
    autonumber
    participant TCI as TCI Calculator
    participant FP as Fingerprint
    participant VulnDB as TECH_VULNERABILITY_SCORES
    participant Scores as Score Components

    TCI->>FP: Get all technologies
    FP-->>TCI: technologies + frameworks + languages + databases

    rect rgb(240, 248, 255)
        Note over TCI,VulnDB: Technology Vulnerability Scoring
        TCI->>TCI: all_tech = ["nginx", "django", "python", "postgresql"]

        loop For each technology
            TCI->>VulnDB: Get vulnerability score
            VulnDB-->>TCI: nginx: 0.4
            VulnDB-->>TCI: django: 0.5
            VulnDB-->>TCI: python: 0.4
            VulnDB-->>TCI: postgresql: 0.6
        end

        TCI->>TCI: avg_score = (0.4 + 0.5 + 0.4 + 0.6) / 4 = 0.475
        TCI->>TCI: count_bonus = min(0.2, 4/20) = 0.2
        TCI->>Scores: tech_stack_score = 0.675
    end

    rect rgb(255, 240, 255)
        Note over TCI,VulnDB: Technology Vulnerability Reference
        Note right of VulnDB: High-risk technologies:<br/>- wordpress: 0.8<br/>- php: 0.7<br/>- mssql: 0.8<br/>- joomla: 0.8<br/><br/>Lower-risk technologies:<br/>- rust: 0.2<br/>- go: 0.3<br/>- sqlite: 0.3
    end
```

## Sequence Diagram: Authentication Complexity Analysis

```mermaid
sequenceDiagram
    autonumber
    participant TCI as TCI Calculator
    participant FP as Fingerprint
    participant AuthDB as AUTH_COMPLEXITY_SCORES
    participant Scores as Score Components

    TCI->>FP: Get auth_types and has_mfa
    FP-->>TCI: auth_types=["jwt", "oauth2"], has_mfa=True

    rect rgb(240, 248, 255)
        Note over TCI,AuthDB: Authentication Scoring
        loop For each auth type
            TCI->>AuthDB: Get complexity score
            AuthDB-->>TCI: jwt: 0.7
            AuthDB-->>TCI: oauth2: 0.85
        end

        TCI->>TCI: base_score = max(0.7, 0.85) = 0.85
    end

    rect rgb(255, 248, 240)
        Note over TCI,Scores: Apply Bonuses
        TCI->>TCI: Check MFA
        Note right of TCI: has_mfa=True → +0.2 bonus

        TCI->>TCI: Check multiple auth types
        Note right of TCI: 2 auth types → +0.1 bonus

        TCI->>TCI: score = min(1.0, 0.85 + 0.2 + 0.1)
        TCI->>Scores: auth_complexity_score = 1.0
    end

    rect rgb(240, 255, 240)
        Note over TCI,AuthDB: Authentication Complexity Reference
        Note right of AuthDB: AUTH_COMPLEXITY_SCORES:<br/>- none: 0.0<br/>- basic: 0.3<br/>- api_key: 0.4<br/>- bearer: 0.5<br/>- jwt: 0.7<br/>- oauth2: 0.85<br/>- saml: 0.9<br/>- mfa: 1.0
    end
```

## Sequence Diagram: Module Recommendations Generation

```mermaid
sequenceDiagram
    autonumber
    participant TCI as TCI Calculator
    participant FP as Fingerprint
    participant ModuleMap as MODULE_RECOMMENDATIONS
    participant Result as Recommendations

    TCI->>FP: Analyze fingerprint characteristics

    rect rgb(240, 248, 255)
        Note over TCI,ModuleMap: Check Feature Flags

        TCI->>FP: Check auth_types
        FP-->>TCI: ["jwt"]
        TCI->>ModuleMap: has_jwt → modules
        ModuleMap-->>Result: ["authentication_jwt", "idor"]

        TCI->>FP: Check has_graphql
        FP-->>TCI: True
        TCI->>ModuleMap: has_graphql → modules
        ModuleMap-->>Result: ["graphql_security", "idor"]

        TCI->>FP: Check databases
        FP-->>TCI: ["postgresql"]
        TCI->>ModuleMap: has_database → modules
        ModuleMap-->>Result: ["sql_injection"]

        TCI->>FP: Check api_endpoints
        FP-->>TCI: 150
        TCI->>ModuleMap: has_api → modules
        ModuleMap-->>Result: ["api_security", "idor", "business_logic"]

        TCI->>FP: Check cloud_provider
        FP-->>TCI: "aws"
        TCI->>ModuleMap: has_cloud → modules
        ModuleMap-->>Result: ["cloud_security"]
    end

    rect rgb(255, 248, 240)
        Note over TCI,Result: Finalize Recommendations
        TCI->>TCI: Deduplicate modules
        TCI->>TCI: Sort alphabetically
        TCI->>TCI: Limit to 5 modules

        TCI-->>Result: ["api_security", "authentication_jwt",<br/>"cloud_security", "graphql_security", "idor"]
    end
```

## Sequence Diagram: Security Posture Determination

```mermaid
sequenceDiagram
    autonumber
    participant TCI as TCI Calculator
    participant FP as Fingerprint
    participant Posture as SecurityPosture

    TCI->>FP: Analyze security indicators

    rect rgb(240, 248, 255)
        Note over TCI,FP: Count Hardening Indicators
        TCI->>FP: has_waf?
        FP-->>TCI: True → +1

        TCI->>FP: has_rate_limiting?
        FP-->>TCI: True → +1

        TCI->>FP: has_csrf_protection?
        FP-->>TCI: True → +1

        TCI->>FP: has_mfa?
        FP-->>TCI: True → +1

        TCI->>FP: security_headers count >= 4?
        FP-->>TCI: True → +1

        TCI->>TCI: hardening_indicators = 5
    end

    rect rgb(255, 248, 240)
        Note over TCI,FP: Count Permissive Indicators
        TCI->>FP: auth_types includes "none"?
        FP-->>TCI: False

        TCI->>FP: has_graphql_introspection?
        FP-->>TCI: True → +1

        TCI->>FP: Telnet (23) or FTP (21) open?
        FP-->>TCI: False

        TCI->>FP: outdated_components?
        FP-->>TCI: [] → 0

        TCI->>FP: known_vulnerabilities?
        FP-->>TCI: [] → 0

        TCI->>TCI: permissive_indicators = 1
    end

    rect rgb(240, 255, 240)
        Note over TCI,Posture: Determine Posture
        alt hardening >= 3 AND permissive == 0
            TCI->>Posture: HARDENED
        else permissive >= 2
            TCI->>Posture: PERMISSIVE
        else hardening > 0 OR permissive > 0
            TCI->>Posture: STANDARD
        else
            TCI->>Posture: UNKNOWN
        end

        TCI-->>Posture: STANDARD (5 hardening, 1 permissive)
    end
```

## Sequence Diagram: Scan Hints Calculation

```mermaid
sequenceDiagram
    autonumber
    participant TCI as TCI Calculator
    participant FP as Fingerprint
    participant Hints as Scan Hints

    rect rgb(240, 248, 255)
        Note over TCI,Hints: Timeout Multiplier
        TCI->>TCI: base = 1.0 + (score/100)
        Note right of TCI: score=65 → base=1.65

        TCI->>FP: has_waf?
        FP-->>TCI: True → +0.3

        TCI->>FP: has_rate_limiting?
        FP-->>TCI: True → +0.2

        TCI->>FP: api_endpoints > 100?
        FP-->>TCI: 150 > 100 → +0.2

        TCI->>Hints: timeout_multiplier = min(3.0, 2.35) = 2.35
    end

    rect rgb(255, 248, 240)
        Note over TCI,Hints: Safe Mode Determination
        TCI->>FP: handles_payment OR handles_healthcare?
        FP-->>TCI: False

        TCI->>FP: has_waf OR has_rate_limiting?
        FP-->>TCI: True → safe_mode = True

        TCI->>FP: Check URL for "prod" keywords
        FP-->>TCI: No production indicators

        TCI->>Hints: safe_mode = True (WAF detected)
    end

    rect rgb(240, 255, 240)
        Note over TCI,Hints: Max Parallel Tests
        TCI->>TCI: base = 10

        TCI->>FP: has_waf?
        FP-->>TCI: True → base = min(10, 5) = 5

        TCI->>FP: has_rate_limiting?
        FP-->>TCI: True → base = min(5, 3) = 3

        TCI->>FP: handles_payment OR handles_healthcare?
        FP-->>TCI: False

        TCI->>TCI: Check score >= 80?
        Note right of TCI: score=65 < 80 → no reduction

        TCI->>Hints: max_parallel_tests = 3
    end
```

## Key Components

| Component | File Location | Responsibility |
|-----------|---------------|----------------|
| TCI Calculator | `strix/core/tci.py` | Main complexity calculation |
| TargetFingerprint | `strix/core/tci.py` | Target characteristic model |
| TCIConfig | `strix/core/tci.py` | Configurable weight settings |
| TCIResult | `strix/core/tci.py` | Calculation result with recommendations |
| compute_tci() | `strix/core/tci.py` | Convenience function |
| Scan Planner | `strix/agents/planner.py` | Consumes TCI for adaptive planning |

## Weight Configuration

| Component | Default Weight | Description |
|-----------|----------------|-------------|
| port_count_weight | 0.10 | Number of open ports |
| service_diversity_weight | 0.08 | Variety of services |
| high_risk_ports_weight | 0.12 | Dangerous ports (DBs, admin, etc.) |
| tech_stack_weight | 0.10 | Technology vulnerability richness |
| framework_count_weight | 0.05 | Number of frameworks |
| auth_complexity_weight | 0.15 | Authentication mechanism complexity |
| api_surface_weight | 0.12 | API endpoint count/complexity |
| graphql_weight | 0.05 | GraphQL presence |
| waf_cdn_weight | 0.08 | WAF/CDN evasion complexity |
| cloud_complexity_weight | 0.07 | Cloud infrastructure |
| data_sensitivity_weight | 0.08 | Data sensitivity indicators |

## Complexity Levels

| Level | Score Range | Characteristics |
|-------|-------------|-----------------|
| MINIMAL | 0-20 | Simple target, few attack vectors |
| LOW | 21-40 | Basic web app, limited API |
| MEDIUM | 41-60 | Standard enterprise app |
| HIGH | 61-80 | Complex stack, multiple auth, large API |
| CRITICAL | 81-100 | Highly complex, hardened, sensitive data |

## TCIResult Structure

```python
@dataclass
class TCIResult:
    # Overall score (0-100)
    score: float

    # Classification
    complexity_level: ComplexityLevel    # minimal → critical
    security_posture: SecurityPosture    # hardened, standard, permissive, unknown

    # Component scores (0-1 scale)
    port_score: float
    service_diversity_score: float
    high_risk_ports_score: float
    tech_stack_score: float
    auth_complexity_score: float
    api_surface_score: float
    waf_complexity_score: float
    data_sensitivity_score: float
    cloud_complexity_score: float

    # Recommendations
    recommended_modules: list[str]       # Up to 5 prompt modules
    priority_vulnerabilities: list[str]  # Up to 8 vuln types

    # Scan hints
    suggested_timeout_multiplier: float  # 1.0 - 3.0
    suggested_safe_mode: bool
    max_parallel_tests: int              # 1 - 10
```

## Integration with Scan Planner

```mermaid
sequenceDiagram
    autonumber
    participant Scanner as Scanner
    participant TCI as TCI Calculator
    participant Planner as ScanPlanner
    participant Plan as ScanPlan

    Scanner->>TCI: compute_tci(fingerprint)
    TCI-->>Scanner: TCIResult(score=65, level=HIGH)

    Scanner->>Planner: generate_plan(target, fingerprint, tci_result)

    Planner->>Planner: _calculate_quotas(tci_result)
    Note right of Planner: HIGH complexity →<br/>max_requests: 1000<br/>max_duration: 60min<br/>rate_limit: 10 rps

    Planner->>Planner: _select_modules(tci_result)
    Note right of Planner: Uses tci_result.recommended_modules

    Planner->>Planner: _generate_steps()
    Note right of Planner: Adjusts timeouts by<br/>tci_result.timeout_multiplier

    Planner->>Plan: Create adaptive scan plan
    Planner-->>Scanner: ScanPlan with TCI-driven configuration
```
