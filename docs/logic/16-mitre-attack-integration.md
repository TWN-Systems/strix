# MITRE ATT&CK Integration

This diagram illustrates how Strix integrates MITRE ATT&CK Tactics, Techniques, and Procedures (TTPs) for threat intelligence tagging and attack chain analysis.

## Overview

The MITRE ATT&CK integration provides:
1. Comprehensive technique database (70+ techniques across all tactics)
2. Action-to-TTP mapping for security testing operations
3. Attack chain construction from action sequences
4. Indicator of Compromise (IoC) classification
5. Risk scoring based on tactic criticality
6. Cross-references with OWASP categories

## Architecture

```mermaid
flowchart TB
    subgraph MITRE Framework
        TACTICS[14 Tactics]
        TECHNIQUES[70+ Techniques]
        SUBTECHS[Sub-Techniques]
    end

    subgraph Core Module
        TECHDB[Technique Database]
        ACTIONMAP[Action Mappings]
        VULNMAP[Vulnerability Mappings]
        IOCCREATE[IoC Creator]
        CHAINBUILD[Chain Builder]
    end

    subgraph Integration Points
        PLANNER[Scan Planner]
        VULN[Vulnerability Reports]
        TELEMETRY[Telemetry]
    end

    TACTICS --> TECHNIQUES
    TECHNIQUES --> SUBTECHS
    TECHNIQUES --> TECHDB
    TECHDB --> ACTIONMAP
    TECHDB --> VULNMAP
    ACTIONMAP --> PLANNER
    VULNMAP --> VULN
    TECHDB --> IOCCREATE
    ACTIONMAP --> CHAINBUILD
    CHAINBUILD --> TELEMETRY
```

## Sequence Diagram: Action to TTP Mapping

```mermaid
sequenceDiagram
    autonumber
    participant Agent as Security Agent
    participant MitreModule as MITRE Module
    participant ActionMap as ACTION_TTP_MAPPINGS
    participant TechDB as TECHNIQUES Database
    participant Result as TTP List

    Agent->>MitreModule: map_action_to_ttps("sql_injection")

    rect rgb(240, 248, 255)
        Note over MitreModule,ActionMap: Phase 1: Lookup Action Mapping
        MitreModule->>ActionMap: Get technique IDs for "sql_injection"
        ActionMap-->>MitreModule: ["T1190"]
    end

    rect rgb(255, 248, 240)
        Note over MitreModule,TechDB: Phase 2: Retrieve Technique Details
        loop For each technique ID
            MitreModule->>TechDB: Get technique "T1190"
            TechDB-->>MitreModule: MITRETechnique(<br/>id="T1190",<br/>name="Exploit Public-Facing Application",<br/>tactic=INITIAL_ACCESS,<br/>platforms=[WINDOWS, LINUX, MACOS]<br/>)
        end
    end

    MitreModule->>Result: Build technique list
    MitreModule-->>Agent: [MITRETechnique(T1190)]

    Note right of Agent: Agent now has threat<br/>intelligence context for<br/>SQL injection testing
```

## Sequence Diagram: Vulnerability to TTP Mapping

```mermaid
sequenceDiagram
    autonumber
    participant Reporter as Vulnerability Reporter
    participant MitreModule as MITRE Module
    participant VulnMap as Vulnerability Mappings
    participant TechDB as TECHNIQUES Database

    Reporter->>MitreModule: get_ttps_for_vulnerability("XSS")

    rect rgb(240, 248, 255)
        Note over MitreModule,VulnMap: Phase 1: Match Vulnerability Type
        MitreModule->>MitreModule: Normalize: "xss" or "cross-site scripting"
        MitreModule->>VulnMap: Query vulnerability mapping
        VulnMap-->>MitreModule: ["T1059.007", "T1539"]
    end

    rect rgb(255, 248, 240)
        Note over MitreModule,TechDB: Phase 2: Retrieve Techniques
        MitreModule->>TechDB: Get "T1059.007"
        TechDB-->>MitreModule: MITRETechnique(<br/>name="JavaScript Execution",<br/>tactic=EXECUTION<br/>)

        MitreModule->>TechDB: Get "T1539"
        TechDB-->>MitreModule: MITRETechnique(<br/>name="Steal Web Session Cookie",<br/>tactic=CREDENTIAL_ACCESS<br/>)
    end

    MitreModule-->>Reporter: [T1059.007, T1539]

    Note right of Reporter: XSS maps to:<br/>- Execution (JS execution)<br/>- Credential Access (cookie theft)
```

## Sequence Diagram: Attack Chain Construction

```mermaid
sequenceDiagram
    autonumber
    participant Analyzer as Attack Analyzer
    participant MitreModule as MITRE Module
    participant ActionMap as Action Mappings
    participant Chain as Attack Chain

    Analyzer->>MitreModule: get_attack_chain(["port_scanning", "sql_injection", "credential_harvesting", "data_exfiltration"])

    rect rgb(240, 248, 255)
        Note over MitreModule,ActionMap: Phase 1: Map Actions to Techniques
        loop For each action
            MitreModule->>ActionMap: port_scanning
            ActionMap-->>MitreModule: T1595.001, T1046

            MitreModule->>ActionMap: sql_injection
            ActionMap-->>MitreModule: T1190

            MitreModule->>ActionMap: credential_harvesting
            ActionMap-->>MitreModule: T1552, T1555

            MitreModule->>ActionMap: data_exfiltration
            ActionMap-->>MitreModule: T1041, T1567
        end
    end

    rect rgb(255, 248, 240)
        Note over MitreModule,Chain: Phase 2: Organize by Tactic
        MitreModule->>MitreModule: Group techniques by tactic
        MitreModule->>MitreModule: Sort by kill chain order

        Note right of MitreModule: Kill Chain Order:<br/>1. Reconnaissance<br/>2. Initial Access<br/>3. Credential Access<br/>4. Exfiltration
    end

    MitreModule->>Chain: Build ordered chain
    MitreModule-->>Analyzer: Attack Chain

    Note right of Analyzer: Chain represents:<br/>TA0043 → T1595.001, T1046<br/>TA0001 → T1190<br/>TA0006 → T1552, T1555<br/>TA0010 → T1041, T1567
```

## Sequence Diagram: IoC Creation with TTP Mapping

```mermaid
sequenceDiagram
    autonumber
    participant Detector as Threat Detector
    participant MitreModule as MITRE Module
    participant ActionMap as Action Mappings
    participant IoC as IoC Object

    Detector->>MitreModule: create_ioc(<br/>type=URL,<br/>value="http://malicious.com/shell.php",<br/>severity=HIGH,<br/>related_actions=["webshell_deployment"]<br/>)

    rect rgb(240, 248, 255)
        Note over MitreModule,ActionMap: Phase 1: Map Related Actions to TTPs
        MitreModule->>ActionMap: webshell_deployment
        ActionMap-->>MitreModule: ["T1505.003"]

        MitreModule->>MitreModule: Deduplicate technique IDs
    end

    rect rgb(255, 248, 240)
        Note over MitreModule,IoC: Phase 2: Create IoC Object
        MitreModule->>IoC: Create IoC(<br/>ioc_type=URL,<br/>value="http://malicious.com/shell.php",<br/>severity=HIGH,<br/>related_techniques=["T1505.003"]<br/>)
    end

    MitreModule-->>Detector: IoC with TTP context

    Note right of Detector: IoC includes:<br/>- Type: URL<br/>- Severity: HIGH<br/>- Related: T1505.003 (Web Shell)
```

## Sequence Diagram: TTP Mapping with Risk Scoring

```mermaid
sequenceDiagram
    autonumber
    participant Planner as Scan Planner
    participant MitreModule as MITRE Module
    participant ActionMap as Action Mappings
    participant RiskCalc as Risk Calculator

    Planner->>MitreModule: create_ttp_mapping(<br/>action="remote_code_execution",<br/>description="Attempt RCE on target"<br/>)

    rect rgb(240, 248, 255)
        Note over MitreModule,ActionMap: Phase 1: Get Techniques
        MitreModule->>ActionMap: remote_code_execution
        ActionMap-->>MitreModule: ["T1203", "T1190"]

        MitreModule->>MitreModule: Retrieve technique objects
        Note right of MitreModule: T1203: Execution tactic<br/>T1190: Initial Access tactic
    end

    rect rgb(255, 248, 240)
        Note over MitreModule,RiskCalc: Phase 2: Calculate Risk Score
        MitreModule->>RiskCalc: Get tactic risk weights
        Note right of RiskCalc: Tactic Risks:<br/>INITIAL_ACCESS: 0.8<br/>EXECUTION: 0.9<br/>PRIVILEGE_ESCALATION: 0.9<br/>CREDENTIAL_ACCESS: 0.85<br/>EXFILTRATION: 0.9<br/>IMPACT: 1.0

        MitreModule->>MitreModule: risk_score = max([0.9, 0.8])
        RiskCalc-->>MitreModule: risk_score = 0.9
    end

    MitreModule-->>Planner: TTPMapping(<br/>action="remote_code_execution",<br/>techniques=[T1203, T1190],<br/>risk_score=0.9<br/>)
```

## Sequence Diagram: Technique Retrieval by Tactic

```mermaid
sequenceDiagram
    autonumber
    participant Analyzer as Security Analyzer
    participant MitreModule as MITRE Module
    participant TechDB as TECHNIQUES Database

    Analyzer->>MitreModule: get_techniques_for_tactic(MITRETactic.CREDENTIAL_ACCESS)

    MitreModule->>TechDB: Filter by tactic=TA0006

    rect rgb(240, 248, 255)
        Note over TechDB: Credential Access Techniques
        TechDB-->>MitreModule: T1110 - Brute Force
        TechDB-->>MitreModule: T1110.001 - Password Guessing
        TechDB-->>MitreModule: T1110.003 - Password Spraying
        TechDB-->>MitreModule: T1555 - Credentials from Password Stores
        TechDB-->>MitreModule: T1552 - Unsecured Credentials
        TechDB-->>MitreModule: T1539 - Steal Web Session Cookie
        TechDB-->>MitreModule: T1528 - Steal Application Access Token
    end

    MitreModule-->>Analyzer: List of 7 credential access techniques
```

## Sequence Diagram: Platform-Specific Technique Filtering

```mermaid
sequenceDiagram
    autonumber
    participant Planner as Scan Planner
    participant MitreModule as MITRE Module
    participant TechDB as TECHNIQUES Database

    Planner->>MitreModule: get_techniques_for_platform(MITREPlatform.CLOUD)

    rect rgb(240, 248, 255)
        Note over MitreModule,TechDB: Filter by platform
        MitreModule->>TechDB: Filter where CLOUD in platforms

        TechDB-->>MitreModule: T1078 - Valid Accounts
        TechDB-->>MitreModule: T1078.004 - Cloud Accounts
        TechDB-->>MitreModule: T1110 - Brute Force
        TechDB-->>MitreModule: T1552 - Unsecured Credentials
        TechDB-->>MitreModule: T1530 - Data from Cloud Storage
        TechDB-->>MitreModule: T1562 - Impair Defenses
        TechDB-->>MitreModule: T1498 - Network DoS
    end

    MitreModule-->>Planner: Cloud-applicable techniques

    Note right of Planner: Use for cloud-targeted scans:<br/>- Cloud account abuse<br/>- Cloud storage access<br/>- Cloud DoS testing
```

## Sequence Diagram: Scan Planner TTP Integration

```mermaid
sequenceDiagram
    autonumber
    participant Planner as ScanPlanner
    participant ModuleMap as MODULE_MITRE_TTPS
    participant Step as ScanStep
    participant TTPRef as TTPReference

    Planner->>Planner: _create_step(module="sql_injection")

    rect rgb(240, 248, 255)
        Note over Planner,ModuleMap: Phase 1: Get Module TTPs
        Planner->>Planner: _get_module_ttps("sql_injection")
        Planner->>ModuleMap: Lookup sql_injection
        ModuleMap-->>Planner: [{"id": "T1190", "name": "Exploit Public-Facing Application", "tactic": "Initial Access"}]
    end

    rect rgb(255, 248, 240)
        Note over Planner,TTPRef: Phase 2: Create TTP References
        loop For each TTP data
            Planner->>TTPRef: Create TTPReference(<br/>technique_id="T1190",<br/>technique_name="Exploit...",<br/>tactic="Initial Access",<br/>url="https://attack.mitre.org/techniques/T1190/"<br/>)
        end
    end

    Planner->>Step: Create ScanStep with mitre_ttps
    Step-->>Planner: ScanStep(<br/>module="sql_injection",<br/>mitre_ttps=[TTPReference(T1190)],<br/>owasp_refs=[...],<br/>cwe_ids=[...]<br/>)
```

## Key Components

| Component | File Location | Responsibility |
|-----------|---------------|----------------|
| MITRE Module | `strix/core/mitre.py` | Core TTP functionality |
| MITRETactic | `strix/core/mitre.py` | 14 ATT&CK tactics enum |
| MITRETechnique | `strix/core/mitre.py` | Technique data structure |
| TECHNIQUES | `strix/core/mitre.py` | 70+ technique database |
| ACTION_TTP_MAPPINGS | `strix/core/mitre.py` | Action-to-TTP lookup |
| IoC | `strix/core/mitre.py` | Indicator of Compromise |
| Scan Planner | `strix/agents/planner.py` | TTP-tagged scan steps |

## MITRE ATT&CK Tactics (Kill Chain Order)

| ID | Tactic | Description |
|----|--------|-------------|
| TA0043 | Reconnaissance | Information gathering about targets |
| TA0042 | Resource Development | Establishing resources for operations |
| TA0001 | Initial Access | Gaining initial foothold |
| TA0002 | Execution | Running malicious code |
| TA0003 | Persistence | Maintaining access |
| TA0004 | Privilege Escalation | Gaining higher permissions |
| TA0005 | Defense Evasion | Avoiding detection |
| TA0006 | Credential Access | Stealing credentials |
| TA0007 | Discovery | Learning about the environment |
| TA0008 | Lateral Movement | Moving through network |
| TA0009 | Collection | Gathering target data |
| TA0011 | Command and Control | Communicating with compromised systems |
| TA0010 | Exfiltration | Stealing data |
| TA0040 | Impact | Disrupting availability/integrity |

## Action to TTP Mappings

```
Security Testing Actions → MITRE Techniques:

Reconnaissance:
├── port_scanning → T1595.001, T1046
├── vulnerability_scanning → T1595.002
├── service_enumeration → T1046, T1592
├── directory_bruteforce → T1595, T1087
├── subdomain_enumeration → T1590, T1593
└── osint_gathering → T1589, T1593

Credential Attacks:
├── password_bruteforce → T1110.001
├── password_spraying → T1110.003
├── credential_stuffing → T1110.004
├── session_hijacking → T1539, T1528
└── jwt_attack → T1528, T1539

Web Application Attacks:
├── sql_injection → T1190
├── xss_attack → T1059.007, T1539
├── xxe_attack → T1190, T1005
├── ssrf_attack → T1190, T1046
├── csrf_attack → T1190
├── idor_attack → T1190, T1087
├── file_upload_attack → T1190, T1505.003
├── deserialization_attack → T1190, T1059
└── graphql_injection → T1190

Execution:
├── powershell_execution → T1059.001
├── cmd_execution → T1059.003
├── bash_execution → T1059.004
├── python_execution → T1059.006
└── remote_code_execution → T1203, T1190

Privilege Escalation:
├── privilege_escalation → T1068, T1548
├── uac_bypass → T1548.002
├── sudo_abuse → T1548.003
└── token_manipulation → T1134

Persistence:
├── webshell_deployment → T1505.003
├── account_creation → T1136
└── backdoor_installation → T1505, T1543

Exfiltration:
├── data_collection → T1005, T1213
├── cloud_data_access → T1530
└── data_exfiltration → T1041, T1567
```

## MITRETechnique Structure

```python
@dataclass
class MITRETechnique:
    technique_id: str                    # "T1059.001"
    name: str                            # "PowerShell"
    description: str                     # Full description
    tactic: MITRETactic                  # EXECUTION
    platforms: list[MITREPlatform]       # [WINDOWS]
    permissions_required: list[str]      # ["User"]
    data_sources: list[str]              # ["Command", "Process"]
    detection: str                       # Detection guidance
    mitigation: str                      # Mitigation guidance
    url: str                             # Auto-generated MITRE URL
    sub_techniques: list[str]            # Child technique IDs
    is_sub_technique: bool               # True if sub-technique
    parent_technique: str | None         # Parent ID if sub-technique
```

## IoC Structure

```python
@dataclass
class IoC:
    ioc_type: IoCType                    # IP_ADDRESS, DOMAIN, URL, etc.
    value: str                           # The indicator value
    severity: IoCSeverity                # critical, high, medium, low
    description: str                     # Context description
    related_techniques: list[str]        # MITRE technique IDs
    confidence: float                    # 0.0 - 1.0
    tags: list[str]                      # Custom tags
    source: str                          # Where IoC was found
    first_seen: str | None               # Timestamp
    last_seen: str | None                # Timestamp
```

## Risk Score Calculation

The risk score is calculated based on the highest-risk tactic associated with an action:

```python
TACTIC_RISKS = {
    MITRETactic.INITIAL_ACCESS: 0.8,
    MITRETactic.EXECUTION: 0.9,
    MITRETactic.PRIVILEGE_ESCALATION: 0.9,
    MITRETactic.CREDENTIAL_ACCESS: 0.85,
    MITRETactic.LATERAL_MOVEMENT: 0.8,
    MITRETactic.EXFILTRATION: 0.9,
    MITRETactic.IMPACT: 1.0,
}

# Other tactics default to 0.5
risk_score = max(tactic_risks.get(technique.tactic, 0.5) for technique in techniques)
```

## Integration with Scan Planner

Each scan step includes MITRE ATT&CK tagging:

```python
ScanStep(
    module="sql_injection",
    mitre_ttps=[
        TTPReference(
            technique_id="T1190",
            technique_name="Exploit Public-Facing Application",
            tactic="Initial Access",
            url="https://attack.mitre.org/techniques/T1190/"
        )
    ],
    owasp_refs=[...],
    cwe_ids=["CWE-89", "CWE-564"]
)
```

## Cross-Reference with OWASP

MITRE techniques are cross-referenced with OWASP categories through the `mitre_techniques` field in `OWASPCategory`:

```
OWASP A03:2025 (Injection) → MITRE Techniques:
├── T1190 - Exploit Public-Facing Application
├── T1059 - Command and Scripting Interpreter
└── T1059.007 - JavaScript

OWASP A01:2025 (Broken Access Control) → MITRE Techniques:
├── T1078 - Valid Accounts
├── T1087 - Account Discovery
└── T1134 - Access Token Manipulation
```
