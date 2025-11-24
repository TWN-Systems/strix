# OWASP Top 10 Integration & Mapping

This diagram illustrates how Strix integrates OWASP Top 10 standards for comprehensive vulnerability classification across multiple security domains.

## Overview

The OWASP integration provides:
1. Four OWASP Top 10 standards (Web, API, LLM, MCP - all 2025 editions)
2. Automated vulnerability-to-OWASP category mapping
3. Cross-standard correlation for multi-domain vulnerabilities
4. Report appendix generation with detailed guidance
5. MITRE ATT&CK cross-references for threat intelligence

## Architecture

```mermaid
flowchart TB
    subgraph OWASP Standards
        WEB[Web Top 10 2025]
        API[API Top 10 2025]
        LLM[LLM Top 10 2025]
        MCP[MCP Top 10 2025]
    end

    subgraph Core Module
        BASE[OWASPCategory]
        MAPPER[Vulnerability Mapper]
        REPORT[Report Generator]
    end

    subgraph Integration Points
        VULN[Vulnerability Reports]
        PLAN[Scan Planner]
        TI[Threat Intelligence]
    end

    WEB --> BASE
    API --> BASE
    LLM --> BASE
    MCP --> BASE
    BASE --> MAPPER
    MAPPER --> VULN
    MAPPER --> PLAN
    BASE --> REPORT
    BASE --> TI
```

## Sequence Diagram: Vulnerability to OWASP Mapping

```mermaid
sequenceDiagram
    autonumber
    participant Agent as Discovery Agent
    participant VulnReport as Vulnerability Reporter
    participant OWASPMapper as OWASP Mapper
    participant WebTop10 as Web Top 10
    participant APITop10 as API Top 10
    participant LLMTop10 as LLM Top 10
    participant MCPTop10 as MCP Top 10
    participant Report as Final Report

    rect rgb(240, 248, 255)
        Note over Agent,VulnReport: Phase 1: Vulnerability Discovery
        Agent->>Agent: Discover SQL Injection vulnerability
        Agent->>VulnReport: create_vulnerability_report(<br/>title="SQL Injection",<br/>severity="critical"<br/>)
    end

    rect rgb(255, 248, 240)
        Note over VulnReport,MCPTop10: Phase 2: OWASP Mapping
        VulnReport->>OWASPMapper: map_vulnerability_to_owasp("SQL Injection")

        OWASPMapper->>OWASPMapper: Normalize vulnerability name
        Note right of OWASPMapper: vuln_lower = "sql injection"

        par Check all standards
            OWASPMapper->>WebTop10: Check Web Top 10 2025
            WebTop10-->>OWASPMapper: A03:2025 - Injection (relevance: 1.0)
        and
            OWASPMapper->>APITop10: Check API Top 10 2025
            APITop10-->>OWASPMapper: API8:2025 - Security Misconfiguration (relevance: 0.7)
        and
            OWASPMapper->>LLMTop10: Check LLM Top 10 2025
            LLMTop10-->>OWASPMapper: No direct match
        and
            OWASPMapper->>MCPTop10: Check MCP Top 10 2025
            MCPTop10-->>OWASPMapper: No direct match
        end

        OWASPMapper->>OWASPMapper: Create OWASPMapping objects
        OWASPMapper-->>VulnReport: [OWASPMapping(A03:2025), OWASPMapping(API8:2025)]
    end

    rect rgb(240, 255, 240)
        Note over VulnReport,Report: Phase 3: Enrich Report
        VulnReport->>VulnReport: Add OWASP references to report
        VulnReport->>VulnReport: Include testing guidance
        VulnReport->>VulnReport: Add MITRE ATT&CK cross-references

        VulnReport->>Report: Generate enriched report
        Note right of Report: Report includes:<br/>- OWASP A03:2025 reference<br/>- Attack vectors<br/>- Prevention guidance<br/>- MITRE T1190 mapping
    end
```

## Sequence Diagram: Multi-Standard Vulnerability Mapping

```mermaid
sequenceDiagram
    autonumber
    participant Scanner as Security Scanner
    participant Mapper as OWASP Mapper
    participant Standards as OWASP Standards
    participant TI as Threat Intel

    Scanner->>Mapper: map_vulnerability_to_owasp("SSRF")

    rect rgb(255, 248, 240)
        Note over Mapper,Standards: SSRF maps to multiple standards
        Mapper->>Standards: Query all standards for "ssrf"

        Standards-->>Mapper: Web A10:2025 - SSRF (relevance: 1.0)
        Standards-->>Mapper: API7:2025 - Server Side Request Forgery (relevance: 1.0)
        Standards-->>Mapper: MCP05:2025 - SSRF via Tools (relevance: 1.0)
    end

    Mapper->>Mapper: Aggregate mappings
    Mapper->>Mapper: Deduplicate by category ID

    rect rgb(240, 255, 240)
        Note over Mapper,TI: Cross-reference with MITRE
        Mapper->>TI: get_mitre_mappings(category)
        TI-->>Mapper: [T1190, T1046]
    end

    Mapper-->>Scanner: Multi-standard mapping result
    Note right of Scanner: SSRF is relevant across:<br/>- Web applications<br/>- API security<br/>- MCP/Agent contexts
```

## Sequence Diagram: Report Appendix Generation

```mermaid
sequenceDiagram
    autonumber
    participant Reporter as Report Generator
    participant AppendixGen as Appendix Generator
    participant Standard as OWASP Standard
    participant Categories as Category Definitions
    participant Output as Markdown Output

    Reporter->>AppendixGen: generate_report_appendix(OWASPStandard.WEB_TOP10_2025)

    rect rgb(240, 248, 255)
        Note over AppendixGen,Categories: Phase 1: Load Standard Data
        AppendixGen->>Standard: Get standard title
        Standard-->>AppendixGen: "OWASP Web Application Top 10 (2025)"

        AppendixGen->>Categories: Get all categories
        Categories-->>AppendixGen: A01-A10 category definitions
    end

    rect rgb(255, 248, 240)
        Note over AppendixGen,Output: Phase 2: Generate Markdown
        loop For each category (A01-A10)
            AppendixGen->>Categories: Get category details
            Categories-->>AppendixGen: OWASPCategory object

            AppendixGen->>AppendixGen: Format category section
            Note right of AppendixGen: ## A01 - Broken Access Control<br/>**Severity:** CRITICAL<br/><br/>Description...<br/><br/>### Attack Vectors<br/>- ...<br/><br/>### Prevention<br/>- ...
        end

        AppendixGen->>Output: Write markdown content
    end

    AppendixGen-->>Reporter: Complete markdown appendix
```

## Sequence Diagram: OWASP Category Lookup with Testing Guidance

```mermaid
sequenceDiagram
    autonumber
    participant Planner as Scan Planner
    participant OWASP as OWASP Module
    participant Category as OWASPCategory
    participant Guidance as Testing Guidance

    Planner->>OWASP: get_web_top10("A01")
    OWASP->>Category: Lookup A01:2025

    Category-->>OWASP: OWASPCategory(<br/>id="A01",<br/>name="Broken Access Control",<br/>severity=CRITICAL<br/>)

    OWASP-->>Planner: Category object

    rect rgb(240, 255, 240)
        Note over Planner,Guidance: Retrieve Testing Guidance
        Planner->>OWASP: get_testing_guidance(category)

        OWASP->>Category: Access testing_guidance field
        Category-->>OWASP: Testing procedures list

        OWASP-->>Planner: Testing guidance
        Note right of Planner: Guidance includes:<br/>- Test vertical privilege escalation<br/>- Test horizontal IDOR<br/>- Check RBAC enforcement<br/>- Verify JWT claims validation
    end

    rect rgb(255, 240, 255)
        Note over Planner,Guidance: Retrieve MITRE Mappings
        Planner->>OWASP: get_mitre_mappings(category)

        OWASP->>Category: Access mitre_techniques field
        Category-->>OWASP: MITRE technique IDs

        OWASP-->>Planner: MITRE references
        Note right of Planner: MITRE techniques:<br/>- T1078 (Valid Accounts)<br/>- T1087 (Account Discovery)
    end
```

## Sequence Diagram: Severity-Based Category Filtering

```mermaid
sequenceDiagram
    autonumber
    participant Analyzer as Security Analyzer
    participant OWASP as OWASP Module
    participant Web as WEB_TOP10_2025
    participant API as API_TOP10_2025
    participant LLM as LLM_TOP10_2025
    participant MCP as MCP_TOP10_2025

    Analyzer->>OWASP: get_all_categories_by_severity(Severity.CRITICAL)

    par Query all standards
        OWASP->>Web: Filter by severity=critical
        Web-->>OWASP: [A01, A03]
    and
        OWASP->>API: Filter by severity=critical
        API-->>OWASP: [API1, API2, API5]
    and
        OWASP->>LLM: Filter by severity=critical
        LLM-->>OWASP: [LLM01, LLM06]
    and
        OWASP->>MCP: Filter by severity=critical
        MCP-->>OWASP: [MCP01, MCP02, MCP06]
    end

    OWASP->>OWASP: Aggregate all critical categories
    OWASP-->>Analyzer: 10 critical categories across 4 standards

    Note right of Analyzer: Critical categories:<br/>Web: Access Control, Injection<br/>API: BOLA, Auth, BFLA<br/>LLM: Prompt Injection, Agency<br/>MCP: Tool Injection, Access
```

## Key Components

| Component | File Location | Responsibility |
|-----------|---------------|----------------|
| OWASP Module | `strix/core/owasp/__init__.py` | Main exports and utility functions |
| Base Classes | `strix/core/owasp/base.py` | OWASPCategory, OWASPMapping, enums |
| Web Top 10 | `strix/core/owasp/web_applications.py` | OWASP Web Application Top 10 2025 |
| API Top 10 | `strix/core/owasp/api_security.py` | OWASP API Security Top 10 2025 |
| LLM Top 10 | `strix/core/owasp/llm_top10.py` | OWASP LLM Top 10 2025 |
| MCP Top 10 | `strix/core/owasp/mcp_top10.py` | OWASP MCP Top 10 2025 |
| Scan Planner | `strix/agents/planner.py` | Integrates OWASP refs into scan steps |

## OWASP Standards Coverage

### Web Application Top 10 (2025)

| ID | Category | Severity |
|----|----------|----------|
| A01 | Broken Access Control | Critical |
| A02 | Cryptographic Failures | High |
| A03 | Injection | Critical |
| A04 | Insecure Design | High |
| A05 | Security Misconfiguration | Medium |
| A06 | Vulnerable and Outdated Components | Medium |
| A07 | Identification and Authentication Failures | High |
| A08 | Software and Data Integrity Failures | High |
| A09 | Security Logging and Monitoring Failures | Medium |
| A10 | Server-Side Request Forgery (SSRF) | High |

### API Security Top 10 (2025)

| ID | Category | Severity |
|----|----------|----------|
| API1 | Broken Object Level Authorization | Critical |
| API2 | Broken Authentication | Critical |
| API3 | Broken Object Property Level Authorization | High |
| API4 | Unrestricted Resource Consumption | Medium |
| API5 | Broken Function Level Authorization | Critical |
| API6 | Unrestricted Access to Sensitive Business Flows | Medium |
| API7 | Server Side Request Forgery | High |
| API8 | Security Misconfiguration | High |
| API9 | Improper Inventory Management | Medium |
| API10 | Unsafe Consumption of APIs | Medium |

### LLM Top 10 (2025)

| ID | Category | Severity |
|----|----------|----------|
| LLM01 | Prompt Injection | Critical |
| LLM02 | Sensitive Information Disclosure | High |
| LLM03 | Supply Chain Vulnerabilities | Medium |
| LLM04 | Data and Model Poisoning | High |
| LLM05 | Improper Output Handling | High |
| LLM06 | Excessive Agency | Critical |
| LLM07 | System Prompt Leakage | Medium |
| LLM08 | Vector and Embedding Weaknesses | Medium |
| LLM09 | Misinformation | Medium |
| LLM10 | Unbounded Consumption | Medium |

### MCP Top 10 (2025)

| ID | Category | Severity |
|----|----------|----------|
| MCP01 | Tool Injection | Critical |
| MCP02 | Resource Access Control Bypass | Critical |
| MCP03 | Sensitive Information Disclosure | High |
| MCP04 | Insecure Transport | Medium |
| MCP05 | Server-Side Request Forgery via Tools | High |
| MCP06 | Insecure Tool Execution | Critical |
| MCP07 | Insufficient Audit Logging | Medium |
| MCP08 | Excessive Permissions | High |
| MCP09 | Denial of Service | Medium |
| MCP10 | Insufficient Input Validation | High |

## OWASPCategory Data Structure

```python
@dataclass
class OWASPCategory:
    id: str                              # "A01", "API1", "LLM01", "MCP01"
    name: str                            # Category name
    description: str                     # Full description
    standard: OWASPStandard              # Which Top 10 standard
    severity: Severity                   # critical, high, medium, low
    cwe_ids: list[str]                   # Related CWE IDs
    attack_vectors: list[str]            # How it's exploited
    impact: str                          # Business impact
    detection_methods: list[str]         # How to detect
    prevention: list[str]                # Mitigation strategies
    testing_guidance: list[str]          # Testing procedures
    examples: list[str]                  # Exploit examples
    mitre_techniques: list[str]          # MITRE ATT&CK mappings
    url: str                             # OWASP reference URL
```

## Cross-Standard Vulnerability Mapping

```
Vulnerability Type → OWASP Mappings:
├── SQL Injection
│   ├── Web A03:2025 (Injection) - relevance: 1.0
│   └── API8:2025 (Misconfiguration) - relevance: 0.7
├── SSRF
│   ├── Web A10:2025 (SSRF) - relevance: 1.0
│   ├── API7:2025 (SSRF) - relevance: 1.0
│   └── MCP05:2025 (SSRF via Tools) - relevance: 1.0
├── Prompt Injection
│   ├── LLM01:2025 (Prompt Injection) - relevance: 1.0
│   └── MCP01:2025 (Tool Injection) - relevance: 0.9
├── IDOR
│   ├── Web A01:2025 (Broken Access Control) - relevance: 1.0
│   └── API1:2025 (BOLA) - relevance: 1.0
└── Authentication
    ├── Web A07:2025 (Auth Failures) - relevance: 1.0
    └── API2:2025 (Broken Auth) - relevance: 1.0
```

## Integration with Scan Planner

The OWASP module integrates with the Scan Planner to provide threat intelligence tagging:

```python
# Each ScanStep includes OWASP references
ScanStep(
    module="sql_injection",
    owasp_refs=[
        OWASPReference(
            category_id="A03:2025",
            category_name="Injection",
            standard="Web Top 10 2025",
            severity="critical"
        )
    ],
    cwe_ids=["CWE-89", "CWE-564"],
    mitre_ttps=[...]
)
```
