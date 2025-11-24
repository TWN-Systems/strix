# MCP Integration Plan

This document outlines the strategy for integrating the Model Context Protocol (MCP) into Strix, enabling multi-model workflows, external orchestration, and enterprise integrations while preserving native tool performance.

## Table of Contents

- [Overview](#overview)
- [Related Issues](#related-issues)
- [Strix Native vs zen-mcp Capabilities](#strix-native-vs-zen-mcp-capabilities)
- [Architecture Options](#architecture-options)
- [Option A: Strix-Native](#option-a-strix-native)
- [Option B: External Orchestration](#option-b-external-orchestration)
- [Option C: Unified Architecture (Recommended)](#option-c-unified-architecture-recommended)
- [LLM Roles Configuration](#llm-roles-configuration)
- [MCP for External Integrations](#mcp-for-external-integrations)
- [Deployment Scenarios](#deployment-scenarios)
- [Configuration Reference](#configuration-reference)
- [Implementation Phases](#implementation-phases)
- [Pragmatic Recommendation](#pragmatic-recommendation)

---

## Overview

### The Problem

Strix currently uses a single LLM via LiteLLM. While performant, this limits:

1. **Model specialization**: Different models excel at different tasks
2. **Cost optimization**: Expensive models aren't always needed
3. **External orchestration**: Using Strix from Claude Code, Codex, or Gemini CLI
4. **Validation workflows**: Cross-checking findings with multiple models
5. **Enterprise integration**: Slack alerts, Jira sync, knowledge base updates

### Design Principles

1. **Native first**: Avoid MCP where possible for performance
2. **MCP only for external**: Use MCP for integrations that require it
3. **Unified deployment**: Same codebase for local, CI/CD, and workers
4. **Configuration over code**: Model routing and integrations via YAML

---

## Related Issues

| Issue | Title | Summary |
|-------|-------|---------|
| [#31](https://github.com/usestrix/strix/issues/31) | Integration with OpenAI's Codex | Enable Codex CLI as orchestration layer |
| [#66](https://github.com/usestrix/strix/issues/66) | Add support for Claude Code | Use Claude Code's auth/session management |
| [#109](https://github.com/usestrix/strix/issues/109) | MCP Support | Expose Strix services via MCP protocol |
| [#117](https://github.com/usestrix/strix/issues/117) | Add support for Google Gemini 3.0 | Integrate Gemini as an LLM provider |

---

## Strix Native vs zen-mcp Capabilities

### Existing Strix Agent Communication System

Strix already has a sophisticated multi-agent system that can perform consensus/validation:

| Capability | Strix Native | zen-mcp | Notes |
|------------|--------------|---------|-------|
| **Multi-agent spawning** | ✅ `create_agent()` | ✅ `clink` | Strix spawns threads, zen-mcp spawns subprocesses |
| **Inter-agent messaging** | ✅ `send_message_to_agent()` | ❌ | Strix has async message queues |
| **Wait for responses** | ✅ `wait_for_message()` | ❌ | 10-minute timeout with status tracking |
| **Agent graph tracking** | ✅ `view_agent_graph()` | ❌ | Full hierarchy visualization |
| **Result aggregation** | ✅ Via tracer | ✅ Built-in | Both aggregate results |
| **Multi-model queries** | ⚠️ Needs addition | ✅ `consensus` | Strix can do this with sub-agents |
| **Deep reasoning** | ⚠️ Via sub-agent | ✅ `thinkdeep` | Strix can use thinking model role |
| **Code review** | ⚠️ Via sub-agent | ✅ `codereview` | Strix can use coding model role |
| **API lookup** | ❌ | ✅ `apilookup` | zen-mcp has web access |

### Native Consensus Pattern (Existing Infrastructure)

Strix can already do consensus using its agent system:

```python
# Root agent spawns validation agents with different prompt modules
create_agent(task="Analyze SQLi finding", name="validator_1", modules="sql_injection")
create_agent(task="Analyze SQLi finding", name="validator_2", modules="sql_injection")

# Send the same finding to both
send_message_to_agent(validator_1_id, finding_details, type="query")
send_message_to_agent(validator_2_id, finding_details, type="query")

# Wait for responses
wait_for_message("Waiting for validation consensus")

# Root agent receives both responses and synthesizes
# LLM: "Validator 1 says X, Validator 2 says Y. Consensus: ..."
```

### What's Missing for Full Native Consensus

| Feature | Status | Implementation Needed |
|---------|--------|----------------------|
| Multi-model sub-agents | ❌ | Allow sub-agents to use different LLM |
| Voting mechanism | ❌ | Add quorum/agreement logic |
| Confidence scoring | ❌ | Score based on agreement level |
| Disagreement resolution | ❌ | Escalation or majority rules |
| Result deduplication | ❌ | Filter duplicate findings |

### Recommendation: Build Native, Use MCP for External

- **Consensus/validation**: Build natively in Strix (faster, no MCP overhead)
- **External integrations**: Use MCP (Slack, Jira, Teams - requires it)
- **Multi-model routing**: Build natively via LLM roles config
- **External orchestration**: Expose MCP server when needed

---

## Architecture Options

### Option A: Strix-Native

Strix controls everything, uses LLM roles for multi-model, no MCP.

```
┌─────────────────────────────────────────────────────────────────┐
│                         STRIX                                   │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                    STRIX ROOT AGENT                        │ │
│  │              (Primary LLM via LiteLLM)                     │ │
│  └─────────────────────────┬─────────────────────────────────┘ │
│                            │                                    │
│       ┌────────────────────┼────────────────────┐              │
│       ▼                    ▼                    ▼               │
│  ┌─────────┐         ┌─────────┐         ┌─────────┐           │
│  │ SUB     │         │ SUB     │         │ SUB     │           │
│  │ AGENT   │         │ AGENT   │         │ AGENT   │           │
│  │ (fast)  │         │(thinking)│        │(validate)│          │
│  └─────────┘         └─────────┘         └─────────┘           │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                    NATIVE TOOLS                            │ │
│  │  terminal | browser | proxy | python | reporting           │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Pros**: Maximum speed, no MCP overhead, full control
**Cons**: No external integrations, can't be orchestrated externally

---

### Option B: External Orchestration

External AI tool (Claude Code) orchestrates via zen-mcp, Strix is a tool provider.

```
┌─────────────────────────────────────────────────────────────────┐
│              Claude Code / Codex / Gemini CLI                   │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      zen-mcp-server                             │
│              (Multi-Model Hub + Integrations)                   │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STRIX (MCP Server Mode)                      │
│                 Exposes pentest tools only                      │
└─────────────────────────────────────────────────────────────────┘
```

**Pros**: Conversational workflows, easy multi-model via zen-mcp
**Cons**: MCP overhead on every tool call, Strix loses control

---

### Option C: Unified Architecture (Recommended)

Strix maintains native control with optional MCP layer for external integrations and orchestration.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              STRIX                                      │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                      STRIX ROOT AGENT                              │ │
│  │                  (Primary LLM via LiteLLM)                         │ │
│  │                                                                    │ │
│  │  LLM Roles: primary | fast | local | thinking | coding | validate │ │
│  └──────────────────────────────┬────────────────────────────────────┘ │
│                                 │                                       │
│         ┌───────────────────────┼───────────────────────┐              │
│         ▼                       ▼                       ▼               │
│  ┌─────────────┐        ┌─────────────┐        ┌─────────────┐         │
│  │   NATIVE    │        │   NATIVE    │        │    MCP      │         │
│  │   TOOLS     │        │  CONSENSUS  │        │  GATEWAY    │         │
│  │   (fast)    │        │ (sub-agents)│        │ (external)  │         │
│  └─────────────┘        └─────────────┘        └──────┬──────┘         │
│         │                      │                      │                 │
│         ▼                      ▼                      ▼                 │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    EXECUTION LAYER                                │  │
│  │                                                                   │  │
│  │  Native:              Consensus:           MCP External:          │  │
│  │  - terminal           - multi-agent        - Slack alerts         │  │
│  │  - browser            - multi-model        - Jira tickets         │  │
│  │  - proxy              - validation         - Teams notify         │  │
│  │  - python             - aggregation        - Confluence KB        │  │
│  │  - reporting                               - Custom webhooks      │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                    OPTIONAL: MCP SERVER                            │ │
│  │        (Expose tools for Claude Code / Codex / Gemini)            │ │
│  │                   Only when --mcp-server flag                      │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ (Only when MCP integrations enabled)
                                 ▼
              ┌──────────────────────────────────────┐
              │         EXTERNAL SERVICES            │
              │                                      │
              │  Slack | Jira | Teams | Confluence   │
              │  (via MCP servers or direct APIs)    │
              └──────────────────────────────────────┘
```

**Key Principles**:
1. **Native by default**: All pentest operations stay native (fast)
2. **Native consensus**: Multi-agent validation built into Strix
3. **MCP gateway**: Only for external integrations that require it
4. **Optional MCP server**: Enable only when external orchestration needed

---

## LLM Roles Configuration

### Role Definitions

| Role | Purpose | Characteristics | Example Models |
|------|---------|-----------------|----------------|
| `primary` | Main agent loop | Balanced | `claude-sonnet-4.5` |
| `fast` | Quick operations | Low latency, cheap | `gemini-2.0-flash`, `gpt-4o-mini` |
| `local` | Cost-free, offline | No API calls | `ollama/llama3.1`, `ollama/qwen2.5` |
| `thinking` | Complex reasoning | Deep analysis | `o3`, `gemini-3.0-pro` |
| `coding` | Code analysis | Code-optimized | `claude-sonnet-4.5`, `codex-medium` |
| `validation` | Cross-check findings | Different family | Model different from primary |

### Configuration: `llm.yaml`

```yaml
roles:
  primary:
    provider: anthropic
    model: claude-sonnet-4-20250514

  fast:
    provider: google
    model: gemini-2.0-flash
    max_tokens: 1000

  local:
    provider: ollama
    model: llama3.1
    base_url: http://localhost:11434
    fallback_to: fast

  thinking:
    provider: google
    model: gemini-3.0-pro

  coding:
    provider: anthropic
    model: claude-sonnet-4-20250514

  validation:
    provider: openai
    model: gpt-5-turbo

# Task routing
routing:
  default: primary
  planning: thinking
  reconnaissance: primary
  exploitation: coding
  reporting: fast
  vuln_analysis: thinking
  code_review: coding
  finding_validation: validation

# Cost optimization
cost:
  prefer_local: true
  local_timeout_seconds: 30
  fast_threshold_tokens: 500
```

---

## MCP for External Integrations

### When to Use MCP

| Integration | Use MCP? | Reason |
|-------------|----------|--------|
| Pentest tools (terminal, browser) | ❌ No | Native is faster |
| Multi-model consensus | ❌ No | Native sub-agents work |
| Slack/Teams alerts | ✅ Yes | External service |
| Jira ticket sync | ✅ Yes | External service |
| Confluence/KB updates | ✅ Yes | External service |
| GitHub issue creation | ⚠️ Maybe | Could use direct API |
| External orchestration | ✅ Yes | When Claude Code drives |

### MCP Gateway Architecture

```yaml
# strix.config.yaml - MCP integrations section

mcp:
  gateway:
    enabled: true  # Enable MCP gateway for external integrations

    # MCP servers for external integrations
    servers:
      # Slack notifications
      - name: slack
        type: subprocess
        command: ["npx", "-y", "@anthropic/mcp-slack"]
        env:
          SLACK_BOT_TOKEN: ${SLACK_BOT_TOKEN}
          SLACK_CHANNEL: ${SLACK_CHANNEL}
        tools:
          - slack_post_message
          - slack_upload_file

      # Jira integration
      - name: jira
        type: subprocess
        command: ["npx", "-y", "@anthropic/mcp-jira"]
        env:
          JIRA_URL: ${JIRA_URL}
          JIRA_API_TOKEN: ${JIRA_API_TOKEN}
        tools:
          - jira_create_issue
          - jira_update_issue
          - jira_add_comment

      # Microsoft Teams
      - name: teams
        type: http
        url: http://localhost:3001/mcp
        tools:
          - teams_post_message
          - teams_create_channel

      # Confluence/Knowledge Base
      - name: confluence
        type: subprocess
        command: ["npx", "-y", "@anthropic/mcp-confluence"]
        env:
          CONFLUENCE_URL: ${CONFLUENCE_URL}
          CONFLUENCE_API_TOKEN: ${CONFLUENCE_API_TOKEN}
        tools:
          - confluence_search
          - confluence_create_page
          - confluence_update_page

    # When to automatically use integrations
    auto_triggers:
      on_vulnerability_found:
        - slack_post_message
        - jira_create_issue
      on_scan_complete:
        - slack_post_message
        - confluence_update_page
      on_critical_finding:
        - teams_post_message
        - jira_create_issue

  # MCP server mode (for external orchestration)
  server:
    enabled: false  # Enable with --mcp-server flag
    transport: stdio
```

### Native Tool for MCP Gateway

```python
# New tool: mcp_invoke
@register_tool(sandbox_execution=False)
def mcp_invoke(
    server: str,
    tool: str,
    params: dict
) -> dict:
    """
    Invoke an external MCP tool through the gateway.

    Use for external integrations like Slack, Jira, Teams.
    Native tools are faster - only use MCP when necessary.
    """
    return mcp_gateway.invoke(server, tool, params)
```

---

## Deployment Scenarios

### Scenario 1: Local Development

```bash
# Simple local usage - no MCP
export STRIX_LLM="anthropic/claude-sonnet-4-20250514"
strix --target https://example.com

# With LLM roles for cost optimization
strix --target https://example.com --llm-config llm.yaml

# With local Ollama for cheap iterations
export STRIX_LLM_LOCAL="ollama/llama3.1"
strix --target https://example.com --prefer-local
```

### Scenario 2: CI/CD (GitHub Actions)

```yaml
# .github/workflows/security-scan.yml
name: Security Scan

on:
  pull_request:
    branches: [main]
  workflow_dispatch:
    inputs:
      target:
        description: 'Target URL or repository'
        required: true

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Strix Scan
        env:
          STRIX_LLM: anthropic/claude-sonnet-4-20250514
          LLM_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          STRIX_LLM_FAST: google/gemini-2.0-flash
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          # MCP integrations
          SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
        run: |
          pip install strix
          strix --target ${{ github.event.inputs.target || '.' }} \
                --config strix.config.yaml \
                --output-format sarif \
                --output results.sarif

      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: results.sarif

      - name: Post to Slack on Critical
        if: failure()
        run: |
          # Strix auto-triggers handle this via MCP gateway
          echo "Critical findings posted to Slack automatically"
```

### Scenario 3: Jenkins Pipeline

```groovy
// Jenkinsfile
pipeline {
    agent any

    environment {
        STRIX_LLM = 'anthropic/claude-sonnet-4-20250514'
        LLM_API_KEY = credentials('anthropic-api-key')
        JIRA_API_TOKEN = credentials('jira-api-token')
    }

    stages {
        stage('Security Scan') {
            steps {
                sh '''
                    pip install strix
                    strix --target ${TARGET_URL} \
                          --config strix.config.yaml \
                          --output-dir ./results
                '''
            }
        }

        stage('Process Results') {
            steps {
                // Results already synced to Jira via MCP gateway
                archiveArtifacts artifacts: 'results/**/*'
            }
        }
    }

    post {
        always {
            // Cleanup sandbox containers
            sh 'docker rm -f $(docker ps -aq --filter label=strix) || true'
        }
    }
}
```

### Scenario 4: Temporal.io Worker

```python
# temporal_worker.py
from temporalio import workflow, activity
from temporalio.client import Client
from temporalio.worker import Worker
import subprocess
import json

@activity.defn
async def run_strix_scan(target: str, config: dict) -> dict:
    """Run Strix scan as Temporal activity."""

    # Build command
    cmd = [
        "strix",
        "--target", target,
        "--config", "/etc/strix/config.yaml",
        "--output-format", "json",
        "--output", "/tmp/results.json"
    ]

    # Set environment from config
    env = {
        "STRIX_LLM": config.get("primary_model", "anthropic/claude-sonnet-4-20250514"),
        "LLM_API_KEY": config["api_key"],
        "STRIX_LLM_FAST": config.get("fast_model", "google/gemini-2.0-flash"),
    }

    # Run scan
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    # Load results
    with open("/tmp/results.json") as f:
        return json.load(f)


@activity.defn
async def notify_slack(findings: list, channel: str) -> None:
    """Post findings to Slack via Strix MCP gateway."""
    # This would use Strix's MCP gateway internally
    pass


@activity.defn
async def create_jira_tickets(findings: list, project: str) -> list:
    """Create Jira tickets for findings via Strix MCP gateway."""
    # This would use Strix's MCP gateway internally
    pass


@workflow.defn
class SecurityScanWorkflow:
    @workflow.run
    async def run(self, target: str, config: dict) -> dict:
        # Run the scan
        results = await workflow.execute_activity(
            run_strix_scan,
            args=[target, config],
            start_to_close_timeout=timedelta(hours=2)
        )

        # Process critical findings
        critical = [f for f in results["findings"] if f["severity"] == "critical"]

        if critical:
            # Parallel notifications
            await asyncio.gather(
                workflow.execute_activity(
                    notify_slack,
                    args=[critical, config["slack_channel"]],
                    start_to_close_timeout=timedelta(minutes=5)
                ),
                workflow.execute_activity(
                    create_jira_tickets,
                    args=[critical, config["jira_project"]],
                    start_to_close_timeout=timedelta(minutes=5)
                )
            )

        return results


async def main():
    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue="strix-scans",
        workflows=[SecurityScanWorkflow],
        activities=[run_strix_scan, notify_slack, create_jira_tickets]
    )

    await worker.run()
```

### Scenario 5: Scheduled Worker with Trigger

```yaml
# docker-compose.yml for self-hosted worker
version: '3.8'

services:
  temporal:
    image: temporalio/auto-setup:latest
    ports:
      - "7233:7233"
    environment:
      - DB=postgresql
      - DB_PORT=5432
      - POSTGRES_USER=temporal
      - POSTGRES_PWD=temporal
      - POSTGRES_SEEDS=postgres

  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: temporal
      POSTGRES_PASSWORD: temporal

  strix-worker:
    build: .
    environment:
      TEMPORAL_ADDRESS: temporal:7233
      STRIX_LLM: anthropic/claude-sonnet-4-20250514
      LLM_API_KEY: ${ANTHROPIC_API_KEY}
      SLACK_BOT_TOKEN: ${SLACK_BOT_TOKEN}
      JIRA_API_TOKEN: ${JIRA_API_TOKEN}
    volumes:
      - ./strix-config:/etc/strix
    command: python temporal_worker.py
    deploy:
      replicas: 3  # Multiple workers for parallel scans

  scheduler:
    image: temporalio/admin-tools
    depends_on:
      - temporal
    # Schedule recurring scans
    command: |
      tctl schedule create \
        --schedule-id daily-scan \
        --workflow-type SecurityScanWorkflow \
        --task-queue strix-scans \
        --cron "0 2 * * *" \
        --input '{"target": "https://api.example.com", "config": {...}}'
```

---

## Configuration Reference

### Full Configuration: `strix.config.yaml`

```yaml
#──────────────────────────────────────────────────────────────────────
# LLM ROLES
#──────────────────────────────────────────────────────────────────────
llm:
  roles:
    primary:
      provider: anthropic
      model: claude-sonnet-4-20250514
      api_key: ${ANTHROPIC_API_KEY}

    fast:
      provider: google
      model: gemini-2.0-flash
      api_key: ${GOOGLE_API_KEY}

    local:
      provider: ollama
      model: llama3.1
      base_url: ${OLLAMA_BASE_URL:-http://localhost:11434}

    thinking:
      provider: google
      model: gemini-3.0-pro
      api_key: ${GOOGLE_API_KEY}

    coding:
      provider: anthropic
      model: claude-sonnet-4-20250514
      api_key: ${ANTHROPIC_API_KEY}

    validation:
      provider: openai
      model: gpt-5-turbo
      api_key: ${OPENAI_API_KEY}

  routing:
    default: primary
    planning: thinking
    reconnaissance: primary
    exploitation: coding
    reporting: fast
    finding_validation: validation

  cost:
    prefer_local: true
    fast_threshold_tokens: 500

#──────────────────────────────────────────────────────────────────────
# NATIVE CONSENSUS (No MCP needed)
#──────────────────────────────────────────────────────────────────────
consensus:
  enabled: true

  # Validation settings
  validation:
    # Require N agents to agree
    quorum: 2
    # Agents for validation
    agents:
      - role: validation
        modules: []
      - role: thinking
        modules: []
    # Auto-validate findings above this severity
    auto_validate_severity: high

  # Result aggregation
  aggregation:
    deduplicate: true
    merge_similar: true
    similarity_threshold: 0.8

#──────────────────────────────────────────────────────────────────────
# MCP GATEWAY (For external integrations only)
#──────────────────────────────────────────────────────────────────────
mcp:
  gateway:
    enabled: ${STRIX_MCP_GATEWAY:-false}

    servers:
      - name: slack
        command: ["npx", "-y", "@anthropic/mcp-slack"]
        env:
          SLACK_BOT_TOKEN: ${SLACK_BOT_TOKEN}
        tools: [slack_post_message]

      - name: jira
        command: ["npx", "-y", "@anthropic/mcp-jira"]
        env:
          JIRA_URL: ${JIRA_URL}
          JIRA_API_TOKEN: ${JIRA_API_TOKEN}
        tools: [jira_create_issue, jira_update_issue]

      - name: teams
        url: ${TEAMS_MCP_URL}
        tools: [teams_post_message]

      - name: confluence
        command: ["npx", "-y", "@anthropic/mcp-confluence"]
        env:
          CONFLUENCE_URL: ${CONFLUENCE_URL}
          CONFLUENCE_API_TOKEN: ${CONFLUENCE_API_TOKEN}
        tools: [confluence_search, confluence_create_page]

    auto_triggers:
      on_vulnerability_found:
        critical: [slack_post_message, jira_create_issue]
        high: [jira_create_issue]
      on_scan_complete:
        always: [slack_post_message]
        with_findings: [confluence_update_page]

  # MCP server mode (for external orchestration)
  server:
    enabled: ${STRIX_MCP_SERVER:-false}
    transport: ${STRIX_MCP_TRANSPORT:-stdio}
    port: ${STRIX_MCP_PORT:-8080}
    auth_token: ${STRIX_MCP_TOKEN}

    exposed_tools:
      - terminal_execute
      - browser_action
      - python_action
      - str_replace_editor
      - send_request
      - list_requests
      - create_vulnerability_report

#──────────────────────────────────────────────────────────────────────
# OUTPUT & REPORTING
#──────────────────────────────────────────────────────────────────────
output:
  formats:
    - json
    - sarif
    - markdown

  directory: ${STRIX_OUTPUT_DIR:-./strix_results}
```

---

## Implementation Phases

### Phase 1: LLM Roles & Native Consensus

**Goal**: Multi-model support without MCP

**Tasks**:
1. Implement `llm.yaml` config loader
2. Add role-based model routing to `llm/llm.py`
3. Allow sub-agents to use different LLM roles
4. Add consensus orchestration to root agent
5. Implement result aggregation and deduplication

**Deliverables**:
- Multi-model workflows via native sub-agents
- No MCP dependency for consensus

### Phase 2: MCP Gateway for Integrations

**Goal**: External integrations via MCP

**Tasks**:
1. Create `strix/mcp/gateway.py`
2. Implement MCP server connection pooling
3. Add `mcp_invoke` tool for agent use
4. Implement auto-triggers for findings
5. Add integration-specific helpers

**Deliverables**:
- Slack, Jira, Teams, Confluence integrations
- Auto-notification on findings

### Phase 3: MCP Server Mode

**Goal**: External orchestration support

**Tasks**:
1. Create `strix/mcp/server.py`
2. Implement tool schema translation
3. Add `--mcp-server` CLI flag
4. Support stdio/HTTP transports

**Deliverables**:
- Claude Code/Codex can orchestrate Strix
- Both internal and external modes work

### Phase 4: CI/CD & Worker Support

**Goal**: Production deployment patterns

**Tasks**:
1. Create GitHub Action
2. Document Jenkins integration
3. Create Temporal.io worker template
4. Add Docker Compose for self-hosted
5. Implement result streaming for long scans

**Deliverables**:
- Ready-to-use CI/CD templates
- Worker deployment guide

---

## Pragmatic Recommendation

### TL;DR: Option C with Phased Rollout

**Start with Phase 1 (Native Multi-Model)**:
- Gives you LLM roles (fast, local, thinking, coding, validation)
- Native consensus via sub-agents
- No MCP complexity
- Works everywhere (local, CI/CD, workers)

**Add Phase 2 when needed (MCP Gateway)**:
- Only when you need Slack/Jira/Teams integration
- MCP servers are isolated - don't affect core performance
- Auto-triggers handle notifications automatically

**Add Phase 3 only if needed (MCP Server)**:
- Only if you want Claude Code/Codex orchestration
- Most users won't need this
- Can run alongside native mode

### Why Option C?

| Requirement | Option A | Option B | Option C |
|-------------|----------|----------|----------|
| Maximum speed | ✅ | ❌ | ✅ |
| Multi-model consensus | ⚠️ Manual | ✅ | ✅ Native |
| Slack/Jira integration | ❌ | ✅ | ✅ |
| CI/CD compatible | ✅ | ⚠️ Complex | ✅ |
| Temporal.io workers | ✅ | ⚠️ Complex | ✅ |
| External orchestration | ❌ | ✅ | ✅ Optional |
| Local development | ✅ | ⚠️ Overhead | ✅ |
| Complexity | Low | Medium | Low-Medium |

### Deployment Decision Tree

```
Do you need external orchestration (Claude Code driving)?
├── Yes → Enable MCP server mode (Option C with server)
└── No ─┬─▶ Do you need Slack/Jira/Teams?
        ├── Yes → Enable MCP gateway only (Option C)
        └── No ─▶ Use pure native mode (Option A)
```

### Cost/Performance Optimization

```yaml
# For development (cheap)
STRIX_LLM_PRIMARY=ollama/llama3.1
STRIX_LLM_THINKING=ollama/deepseek-r1

# For CI/CD (balanced)
STRIX_LLM_PRIMARY=google/gemini-2.0-flash
STRIX_LLM_THINKING=anthropic/claude-sonnet-4.5
STRIX_LLM_VALIDATION=openai/gpt-5-turbo

# For production (thorough)
STRIX_LLM_PRIMARY=anthropic/claude-sonnet-4.5
STRIX_LLM_THINKING=openai/o3
STRIX_LLM_VALIDATION=google/gemini-3.0-pro
```

---

## Summary

### Architecture Decision

**Option C: Unified Architecture** is recommended because:

1. **Native first**: Pentest tools and consensus stay fast (no MCP overhead)
2. **MCP only where needed**: Gateway handles Slack/Jira/Teams integrations
3. **Same codebase everywhere**: Local, CI/CD, workers - same config
4. **Optional external orchestration**: MCP server mode when Claude Code needs control
5. **Phased adoption**: Start simple, add integrations as needed

### Files to Create/Modify

| File | Purpose |
|------|---------|
| `strix/llm/roles.py` | LLM role configuration and routing |
| `strix/agents/consensus.py` | Native multi-agent consensus |
| `strix/mcp/gateway.py` | MCP gateway for external integrations |
| `strix/mcp/server.py` | MCP server for external orchestration |
| `strix/tools/mcp_invoke.py` | Tool for agents to use MCP gateway |

---

## References

- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [zen-mcp-server](https://github.com/BeehiveInnovations/zen-mcp-server)
- [Temporal.io Documentation](https://docs.temporal.io/)
- [GitHub Actions SARIF](https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/sarif-support-for-code-scanning)
- [Issue #31: Codex Integration](https://github.com/usestrix/strix/issues/31)
- [Issue #66: Claude Code Support](https://github.com/usestrix/strix/issues/66)
- [Issue #109: MCP Support](https://github.com/usestrix/strix/issues/109)
- [Issue #117: Gemini 3.0 Support](https://github.com/usestrix/strix/issues/117)
