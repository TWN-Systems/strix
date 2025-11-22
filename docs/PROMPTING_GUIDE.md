# Strix Prompting Guide

## Overview

Strix operates with a multi-agent architecture where a **root coordinator** orchestrates specialized child agents. Understanding how to prompt Strix effectively is key to getting useful results.

This guide covers both interface modes:
- **TUI Mode** (default): Interactive terminal UI for real-time collaboration
- **CLI Mode** (`-n`): Headless/non-interactive for automation and CI/CD

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────┐
│                   ROOT COORDINATOR                       │
│  Role: root | Tools: create_agent, messaging, think     │
│  Does NOT perform security testing directly             │
└─────────────────────┬───────────────────────────────────┘
                      │ creates
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
┌───────────┐  ┌───────────┐  ┌───────────┐
│   Recon   │  │  Testing  │  │ Validation│
│   Agent   │  │   Agent   │  │   Agent   │
│ role:recon│  │role:testing│ │role:valid │
└─────┬─────┘  └─────┬─────┘  └───────────┘
      │              │
      ▼              ▼
   Children      Children
```

**Key Points:**
- Root coordinator parses your instructions and delegates work
- Child agents have specialized tools based on their role
- Each agent can load up to 5 prompt modules for domain expertise
- Runtime role enforcement prevents agents from using unauthorized tools

---

## Operational Modes

The root coordinator detects your intended mode from keywords or natural language:

| Mode | Keywords | Behavior |
|------|----------|----------|
| **RECON-ONLY** | `recon only`, `reconnaissance only`, `no exploitation`, `passive` | Discovery only, generates PoCs but doesn't execute exploits |
| **POC-ONLY** | `poc only`, `proof of concept only` | Discovery + validation, runs PoCs in sandbox, no active exploitation |
| **FULL PENTEST** | `full pentest`, `full test`, `exploitation allowed` | Complete testing including active exploitation within scope |
| **DEFAULT** | (no keywords) | Interprets intent; defaults to POC-ONLY if unclear |

---

## TUI Mode (Interactive)

### Starting a Scan

```bash
# Basic scan (TUI mode is default)
strix --target 10.0.101.2

# Short form
strix -t 10.0.101.2

# With initial instructions
strix --target https://example.com --instruction "Focus on authentication"

# Multiple targets
strix --target ./local-code --target https://staging.example.com

# With custom run name
strix --target example.com --run-name "my-pentest-run"
```

### During the Scan

In TUI mode, you can interact with the agent in real-time:

**Providing Additional Context:**
```
The admin panel is at /admin and uses basic auth
```

**Adjusting Scope:**
```
Skip the /api/v1/legacy endpoints, they're deprecated
```

**Answering Agent Questions:**
When the root coordinator needs clarification (e.g., before destructive actions), it will ask. Simply respond in the chat.

**Stopping:**
- `ESC` - Stop the current agent gracefully
- `Ctrl+C` - Quit and save partial results

### Effective TUI Prompts

**Good: Specific with context**
```
Proxmox VE 8.1 server. Test API authentication at port 8006.
Recon only, no destructive actions. I have root credentials if needed: root / [redacted]
```

**Good: Phased approach**
```
Start with reconnaissance. After you show me the findings, I'll decide what to test further.
```

**Less Effective: Vague**
```
hack it
```

---

## CLI Mode (Headless)

### Starting a Scan

```bash
# Non-interactive mode
strix --target 10.0.101.2 -n --instruction "recon only, generate PoCs"

# With custom run name
strix --target https://api.example.com -n \
  --instruction "full pentest, focus on IDOR and auth bypass" \
  --run-name "api-pentest-2024-01"
```

### Instruction Design for CLI

Since there's no interaction, your `--instruction` must be comprehensive:

**Template:**
```
[TARGET CONTEXT] + [OPERATIONAL MODE] + [FOCUS AREAS] + [CONSTRAINTS]
```

**Examples:**

```bash
# Infrastructure recon
--instruction "Proxmox VE server at 10.0.101.2:8006. \
Recon only, no exploitation. Generate PoCs for any CVEs found. \
Focus on API authentication and VM escape vectors."

# Web application pentest
--instruction "E-commerce Django app. Full pentest. \
Focus on payment flow, session management, and IDOR. \
Test credentials: testuser@example.com / TestPass123"

# Code review
--instruction "Python FastAPI backend. Static analysis only. \
Look for SQL injection, auth bypasses, and hardcoded secrets. \
Critical paths: /api/auth/*, /api/admin/*"
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Scan completed, no vulnerabilities |
| 1 | Error during scan |
| 2 | Scan completed, vulnerabilities found |

---

## Instruction Keywords Reference

### Operational Mode Keywords

| Keyword | Effect |
|---------|--------|
| `recon only` | Reconnaissance only, no exploitation |
| `poc only` | Generate and validate PoCs, no active exploitation |
| `full pentest` | Full testing including exploitation |
| `passive` | Same as recon only |
| `no exploitation` | Same as recon only |

### Safety Keywords

| Keyword | Effect |
|---------|--------|
| `no destructive actions` | Extra confirmation before any state changes |
| `read only` | No writes to target system |
| `safe mode` | Maximum caution, ask before each action |

### Focus Keywords

The agent recognizes technology and vulnerability type mentions:

**Technologies:**
- `Proxmox`, `VMware`, `ESXi` → Infrastructure testing focus
- `AWS`, `Azure`, `GCP`, `kubernetes`, `k8s` → Cloud testing focus
- `Django`, `FastAPI`, `Express`, `Next.js` → Framework-specific modules
- `Firebase`, `Supabase`, `Auth0` → Service-specific modules

**Vulnerability Types:**
- `SQL injection`, `SQLi` → sql_injection module
- `XSS`, `cross-site scripting` → xss module
- `authentication`, `auth`, `JWT` → authentication_jwt module
- `IDOR`, `insecure direct object` → idor module
- `SSRF`, `server-side request` → ssrf module
- `file upload` → insecure_file_uploads module

---

## Target Type Detection

The agent auto-detects target types:

| Input | Detected As |
|-------|-------------|
| `https://example.com` | Web Application |
| `192.168.1.1` | Infrastructure |
| `10.0.101.2:8006` | Infrastructure (Proxmox likely) |
| `https://github.com/user/repo` | Repository |
| `./my-project` | Local Code |
| `s3://bucket-name` | Cloud (AWS) |
| `app.apk` | Mobile |

You can override or clarify:
```
--instruction "This IP runs a web application, not infrastructure"
```

---

## Multi-Model Consensus

For high-confidence assessments, request consensus validation:

```bash
--instruction "Critical production API. Use multi-model consensus for all high/critical findings."
```

This spawns advisor agents with different LLM models to independently validate findings.

---

## Agent Roles and Tools

| Role | Purpose | Key Tools |
|------|---------|-----------|
| `root` | Coordination only | create_agent, view_agent_graph, finish_scan, send_message_to_agent, wait_for_message, think |
| `recon` | Discovery and enumeration | terminal, python, browser, proxy, think, agent_finish, create_agent, view_agent_graph, send_message_to_agent, wait_for_message, read_file, write_file, list_directory, web_search |
| `testing` | Vulnerability testing | terminal, python, browser, proxy, think, agent_finish, create_agent, view_agent_graph, send_message_to_agent, wait_for_message, read_file, write_file, web_search |
| `validation` | PoC validation | terminal, python, browser, proxy, think, agent_finish, read_file, send_message_to_agent |
| `reporting` | Report generation | create_vulnerability_report, read_file, write_file, think, agent_finish, send_message_to_agent |
| `fixing` | Code remediation | read_file, write_file, terminal, python, think, agent_finish, send_message_to_agent |

Runtime enforcement prevents agents from using tools outside their role.

---

## Prompt Modules

Agents can load specialized knowledge modules (max 5 per agent). Available modules:

**Vulnerabilities:**
| Module | Use Case |
|--------|----------|
| `sql_injection` | SQL injection testing techniques |
| `xss` | Cross-site scripting testing |
| `ssrf` | Server-side request forgery |
| `xxe` | XML external entity injection |
| `rce` | Remote code execution |
| `csrf` | Cross-site request forgery |
| `idor` | Insecure direct object references |
| `authentication_jwt` | JWT and auth mechanism testing |
| `business_logic` | Business logic flaw testing |
| `insecure_file_uploads` | File upload vulnerabilities |
| `path_traversal_lfi_rfi` | Path traversal and file inclusion |
| `race_conditions` | Race condition vulnerabilities |
| `mass_assignment` | Mass assignment flaws |
| `broken_function_level_authorization` | Authorization bypass |

**Technologies:**
| Module | Use Case |
|--------|----------|
| `proxmox_ve` | Proxmox VE infrastructure testing |
| `firebase_firestore` | Firebase security testing |
| `supabase` | Supabase security testing |

**Frameworks:**
| Module | Use Case |
|--------|----------|
| `fastapi` | FastAPI application testing |
| `nextjs` | Next.js application testing |

**Protocols:**
| Module | Use Case |
|--------|----------|
| `graphql` | GraphQL API testing |

**Coordination:**
| Module | Use Case |
|--------|----------|
| `root_agent` | Root coordinator behavior (auto-loaded for root) |

Modules are auto-selected based on target and focus areas, or explicitly requested.

---

## Output and Reports

Results are saved to `agent_runs/<run-name>/`:

```
agent_runs/
└── scan-2024-01-15-abc123/
    ├── penetration_test_report.md   # Final penetration test report
    ├── vulnerabilities.csv          # Vulnerability index (id, title, severity, timestamp)
    └── vulnerabilities/             # Individual vulnerability reports
        ├── vuln-abc123.md
        └── vuln-def456.md
```

### Vulnerability Report Format

Each vulnerability in `vulnerabilities/` contains:
```markdown
# [Vulnerability Title]

**ID:** vuln-abc123
**Severity:** CRITICAL
**Found:** 2024-01-15T10:30:00Z

## Description

[Detailed vulnerability description and PoC]
```

---

## Examples

### Running with Docker Compose (Development)

If using the development Docker setup:

```bash
# Build the container
docker compose -f docker-compose.dev.yml build

# Run with docker compose (add arguments after 'strix')
docker compose -f docker-compose.dev.yml run --rm strix \
  --target 10.0.101.2 \
  --instruction "your instructions here"
```

### Example 1: Proxmox Recon (CLI)

```bash
strix --target 10.0.101.2 -n \
  --instruction "Proxmox VE server. Recon only, no destructive actions. \
Generate PoCs for any vulnerabilities found. Focus on API auth and known CVEs."
```

### Example 2: Web App Full Pentest (TUI)

```bash
strix --target https://staging.myapp.com \
  --instruction "Full pentest. Django backend with React frontend. \
Test credentials: admin@test.com / AdminTest123"
```

Then interact in TUI to guide testing.

### Example 3: Multi-Target White-Box (CLI)

```bash
strix \
  --target ./backend \
  --target https://api.staging.myapp.com \
  -n \
  --instruction "White-box test. Code in ./backend matches deployed API. \
Focus on auth endpoints and data validation. Generate fixes for confirmed vulns."
```

### Example 4: Cloud Infrastructure (TUI)

```bash
strix --target arn:aws:s3:::my-bucket \
  --instruction "AWS environment audit. Check S3 permissions, IAM policies. \
Recon only."
```

---

## Troubleshooting

### Agent Not Doing What I Expected

1. Check if operational mode was detected correctly
2. Be more explicit with keywords: `recon only`, `full pentest`
3. In TUI mode, provide clarification when asked

### Scan Taking Too Long

1. Narrow the scope: `Focus only on /api/auth/*`
2. Use recon-only mode first, then targeted testing
3. Specify what to skip: `Skip /static and /assets`

### No Vulnerabilities Found

1. Provide credentials if needed
2. Specify entry points: `Start with the login form at /login`
3. Mention known weak areas: `The password reset flow might be vulnerable`

---

## Best Practices

1. **Start with recon** - Understand the target before deep testing
2. **Be specific** - Vague prompts lead to unfocused testing
3. **Provide context** - Technology stack, credentials, known issues
4. **Use TUI for exploration** - CLI for automation
5. **Review partial results** - In TUI, guide based on findings
6. **Set clear boundaries** - What's in/out of scope
