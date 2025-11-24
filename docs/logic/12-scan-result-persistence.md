# Scan Result Persistence

This diagram illustrates how scan results, vulnerability reports, and telemetry are persisted.

## Overview

Scan result persistence involves:
1. Telemetry collection during scan execution
2. Vulnerability report storage
3. Final scan result generation
4. Output directory structure
5. Report formatting and display

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant Agent as StrixAgent
    participant Reporter as create_vulnerability_report()
    participant Tracer as Tracer
    participant Storage as File Storage
    participant CLI as CLI Display
    participant User

    rect rgb(240, 248, 255)
        Note over Agent,Tracer: Phase 1: Tracer Initialization
        Agent->>Tracer: Initialize(run_name)
        Tracer->>Tracer: Generate run_id
        Tracer->>Tracer: Set timestamps

        Tracer->>Storage: Create output directory
        Note right of Storage: strix_runs/<run_name>/

        Storage-->>Tracer: Directory ready
        Tracer-->>Agent: Tracer initialized
    end

    rect rgb(255, 248, 240)
        Note over Agent,Tracer: Phase 2: Continuous Logging
        loop During scan execution
            Agent->>Tracer: log_agent_creation(agent_info)
            Tracer->>Tracer: Store agent data

            Agent->>Tracer: log_tool_execution(tool, params, result)
            Tracer->>Tracer: Store execution data

            Agent->>Tracer: log_chat_message(role, content)
            Tracer->>Tracer: Store message
        end
    end

    rect rgb(240, 255, 240)
        Note over Agent,CLI: Phase 3: Vulnerability Reporting
        Agent->>Reporter: create_vulnerability_report(<br/>title="SQL Injection",<br/>severity="critical",<br/>content="..."<br/>)

        Reporter->>Reporter: Validate report data
        Reporter->>Reporter: Add metadata

        Reporter->>Tracer: add_vulnerability_report(report)
        Tracer->>Tracer: Store vulnerability
        Tracer->>Storage: Write vulnerability file
        Note right of Storage: vulnerabilities/vuln_001.json

        Tracer->>Tracer: Trigger callback
        Tracer->>CLI: vulnerability_callback(report)
        CLI->>CLI: Render vulnerability panel
        CLI->>User: Display finding
        Note right of User: ┌─ CRITICAL ─────────────────┐<br/>│ SQL Injection in User API │<br/>│ /api/users?id=...         │<br/>└────────────────────────────┘
    end

    rect rgb(255, 240, 255)
        Note over Agent,Storage: Phase 4: Scan Completion
        Agent->>Agent: finish_scan(report_content)

        Agent->>Tracer: set_final_scan_result(report)
        Tracer->>Tracer: Compile final report

        Tracer->>Storage: Write final_report.md
        Tracer->>Storage: Write run_info.json
        Tracer->>Storage: Write chat_history.json
        Tracer->>Storage: Write agent_graph.json
        Tracer->>Storage: Write tool_executions.json

        Tracer-->>Agent: Persistence complete
    end

    rect rgb(255, 255, 240)
        Note over CLI,User: Phase 5: Final Display
        Agent-->>CLI: Scan complete

        CLI->>Storage: Read final report
        Storage-->>CLI: Report content

        CLI->>CLI: Format report
        CLI->>User: Display final report
        CLI->>User: Show summary statistics
        Note right of User: Scan Complete!<br/>Found: 3 Critical, 2 High, 1 Medium<br/>Results: strix_runs/my-scan/
    end
```

## Output Directory Structure

```mermaid
sequenceDiagram
    autonumber
    participant Tracer
    participant FS as File System

    Tracer->>FS: Create directory structure

    Note over FS: strix_runs/<run_name>/
    Note right of FS: │<br/>├── run_info.json<br/>│   └── Run metadata, timestamps, targets<br/>│<br/>├── final_report.md<br/>│   └── Executive summary report<br/>│<br/>├── vulnerabilities/<br/>│   ├── vuln_001.json<br/>│   ├── vuln_002.json<br/>│   └── vuln_003.json<br/>│<br/>├── chat_history.json<br/>│   └── All agent conversations<br/>│<br/>├── agent_graph.json<br/>│   └── Agent hierarchy and status<br/>│<br/>├── tool_executions.json<br/>│   └── All tool calls and results<br/>│<br/>└── workspace/<br/>    └── Modified files, artifacts
```

## Vulnerability Report Structure

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant Reporter
    participant Tracer

    Agent->>Reporter: create_vulnerability_report()

    Note over Reporter: Report Structure

    Note right of Reporter: {<br/>  "id": "vuln_001",<br/>  "title": "SQL Injection in User API",<br/>  "severity": "critical",<br/>  "timestamp": "2024-01-15T10:30:00Z",<br/><br/>  "content": {<br/>    "description": "...",<br/>    "endpoint": "/api/users",<br/>    "method": "GET",<br/>    "parameter": "id",<br/>    "payload": "1' OR '1'='1",<br/><br/>    "impact": "Full database extraction",<br/>    "reproduction": [<br/>      "1. Navigate to /api/users?id=1",<br/>      "2. Modify id to: 1' OR '1'='1",<br/>      "3. Observe all user data returned"<br/>    ],<br/><br/>    "evidence": {<br/>      "request": "GET /api/users?id=...",<br/>      "response": "200 OK [user data]"<br/>    },<br/><br/>    "remediation": "Use parameterized queries"<br/>  },<br/><br/>  "agent_id": "sqli_discovery",<br/>  "related_findings": ["vuln_002"]<br/>}

    Reporter->>Tracer: Store report
```

## Real-Time Display Flow

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant Tracer
    participant Callback as Vulnerability Callback
    participant Renderer as CLI Renderer
    participant Terminal

    Agent->>Tracer: add_vulnerability_report(report)

    Tracer->>Callback: Invoke callback(report)

    Callback->>Renderer: Render vulnerability panel

    Renderer->>Renderer: Format based on severity
    Note right of Renderer: Critical: Red border<br/>High: Orange border<br/>Medium: Yellow border<br/>Low: Blue border<br/>Info: Gray border

    Renderer->>Renderer: Build panel content
    Note right of Renderer: ┌─ CRITICAL: SQL Injection ─┐<br/>│                            │<br/>│ Endpoint: /api/users       │<br/>│ Parameter: id              │<br/>│ Payload: 1' OR '1'='1      │<br/>│                            │<br/>│ Impact: Database exposure  │<br/>│                            │<br/>└────────────────────────────┘

    Renderer->>Terminal: Print to stdout
    Terminal-->>Renderer: Displayed
```

## Run Info Structure

```mermaid
sequenceDiagram
    autonumber
    participant Tracer
    participant Storage as File Storage

    Tracer->>Storage: Write run_info.json

    Note over Storage: Run Info Structure

    Note right of Storage: {<br/>  "run_id": "abc123",<br/>  "run_name": "my-security-scan",<br/>  "started_at": "2024-01-15T10:00:00Z",<br/>  "completed_at": "2024-01-15T11:30:00Z",<br/>  "duration_seconds": 5400,<br/><br/>  "targets": [<br/>    {<br/>      "type": "web_application",<br/>      "value": "https://target.com"<br/>    },<br/>    {<br/>      "type": "repository",<br/>      "value": "https://github.com/org/repo"<br/>    }<br/>  ],<br/><br/>  "instructions": "Focus on auth vulnerabilities",<br/><br/>  "statistics": {<br/>    "total_agents": 5,<br/>    "total_iterations": 450,<br/>    "tool_executions": 1200,<br/>    "vulnerabilities_found": 6<br/>  },<br/><br/>  "vulnerability_summary": {<br/>    "critical": 1,<br/>    "high": 2,<br/>    "medium": 2,<br/>    "low": 1,<br/>    "info": 0<br/>  },<br/><br/>  "exit_code": 2<br/>}
```

## Key Components

| Component | File Location | Responsibility |
|-----------|---------------|----------------|
| Tracer | `telemetry/tracer.py` | Central telemetry collection |
| create_vulnerability_report | `tools/reporting/actions.py` | Report creation tool |
| CLI Renderer | `interface/tool_components/reporting_renderer.py` | Display formatting |
| Storage Manager | `utils/utils.py` | File operations |

## Output File Formats

| File | Format | Content |
|------|--------|---------|
| `run_info.json` | JSON | Run metadata, statistics |
| `final_report.md` | Markdown | Executive summary |
| `vulnerabilities/*.json` | JSON | Individual findings |
| `chat_history.json` | JSON | All conversations |
| `agent_graph.json` | JSON | Agent hierarchy |
| `tool_executions.json` | JSON | Tool call log |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Scan completed, no vulnerabilities found |
| 1 | Scan failed with error |
| 2 | Scan completed, vulnerabilities found |

## Report Generation Flow

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant Tracer
    participant Generator as Report Generator

    Agent->>Agent: finish_scan()

    Agent->>Tracer: Request final report

    Tracer->>Generator: Generate report

    Generator->>Generator: Collect all vulnerabilities
    Generator->>Generator: Sort by severity

    Generator->>Generator: Build executive summary
    Note right of Generator: # Security Assessment Report<br/><br/>## Executive Summary<br/>Scan completed with 6 findings...<br/><br/>## Critical Findings<br/>### 1. SQL Injection (Critical)<br/>...<br/><br/>## High Findings<br/>...<br/><br/>## Recommendations<br/>1. Implement parameterized queries<br/>2. Add input validation<br/>...

    Generator->>Generator: Add statistics
    Generator->>Generator: Add reproduction steps

    Generator-->>Tracer: Complete report
    Tracer-->>Agent: Report ready
```

## Persistence Guarantees

1. **Atomic writes** - Files written atomically to prevent corruption
2. **Incremental saving** - Vulnerabilities saved as found
3. **Crash recovery** - Partial results preserved on failure
4. **Idempotent** - Safe to re-run with same run_name
