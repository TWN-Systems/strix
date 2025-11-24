# MCP Integration Plan

This document outlines the strategy for integrating the Model Context Protocol (MCP) into Strix, enabling interoperability with external AI tools like Claude Code, OpenAI Codex CLI, and Google Gemini CLI while preserving the performance benefits of Strix's native tool system.

## Table of Contents

- [Overview](#overview)
- [Related Issues](#related-issues)
- [Current Architecture](#current-architecture)
- [Integration Strategy: Hybrid Approach](#integration-strategy-hybrid-approach)
- [MCP Server Implementation](#mcp-server-implementation)
- [MCP Client Implementation](#mcp-client-implementation)
- [zen-mcp-server Integration](#zen-mcp-server-integration)
- [Claude Code Integration](#claude-code-integration)
- [OpenAI Codex CLI Integration](#openai-codex-cli-integration)
- [Google Gemini CLI Integration](#google-gemini-cli-integration)
- [Configuration Design](#configuration-design)
- [Implementation Phases](#implementation-phases)
- [Trade-offs and Considerations](#trade-offs-and-considerations)
- [Security Considerations](#security-considerations)

---

## Overview

### What is MCP?

The Model Context Protocol (MCP) is an open standard that enables AI applications to share context, tools, and resources. It provides a unified way for AI assistants to interact with external systems through:

- **Tools**: Executable functions that AI can invoke
- **Resources**: Data sources the AI can read
- **Prompts**: Reusable prompt templates

### Why MCP for Strix?

Strix currently uses a custom tool system optimized for penetration testing workflows. While highly performant, this creates barriers for:

1. **External orchestration**: Using Strix tools from Claude Code, Codex, or Gemini
2. **Multi-model workflows**: Coordinating multiple AI models in a single engagement
3. **Ecosystem integration**: Leveraging the growing MCP tool ecosystem

### Design Goals

1. **Preserve performance**: Native tools remain the fast path for internal operations
2. **Enable interoperability**: Expose Strix capabilities via MCP for external tools
3. **Minimize complexity**: Clean abstractions that don't complicate the core system
4. **Bidirectional support**: Both expose tools (server) and consume tools (client)

---

## Related Issues

This plan addresses the following GitHub issues:

| Issue | Title | Summary |
|-------|-------|---------|
| [#31](https://github.com/usestrix/strix/issues/31) | Integration with OpenAI's Codex | Enable Codex CLI as an orchestration layer |
| [#66](https://github.com/usestrix/strix/issues/66) | Add support for Claude Code | Use Claude Code's auth/session management |
| [#109](https://github.com/usestrix/strix/issues/109) | MCP Support | Expose Strix services via MCP protocol |
| [#117](https://github.com/usestrix/strix/issues/117) | Add support for Google Gemini 3.0 | Integrate Gemini as an LLM provider |

---

## Current Architecture

### Native Tool System

Strix's existing tool system is built around:

```
┌─────────────────────────────────────────────────────────────┐
│                    TOOL REGISTRY                            │
│   @register_tool decorator → tools dict → XML schemas       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    TOOL EXECUTOR                            │
│   execute_tool() → route to sandbox or host                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
┌─────────────────┐        ┌─────────────────┐
│  SANDBOX EXEC   │        │   HOST EXEC     │
│  (Docker/HTTP)  │        │   (Direct)      │
└─────────────────┘        └─────────────────┘
```

### Strengths of Native System

- **Low latency**: Direct function calls, no protocol overhead
- **Type safety**: Python type hints with Pydantic validation
- **Sandbox isolation**: Secure execution in Docker containers
- **Role-based access**: Tools filtered by agent role (COORDINATOR, RECONNAISSANCE, etc.)
- **Tight integration**: Tools can access AgentState directly

### Integration Points for MCP

| Component | MCP Role | Notes |
|-----------|----------|-------|
| `tools/registry.py` | Tool definitions | Can generate MCP tool schemas |
| `tools/executor.py` | Tool execution | Can handle MCP tool calls |
| `llm/llm.py` | LLM interface | Can route to MCP clients |
| `runtime/tool_server.py` | HTTP interface | Can expose MCP endpoint |
| `agents/base_agent.py` | Agent loop | Can consume MCP tool results |

---

## Integration Strategy: Hybrid Approach

The recommended approach is a **hybrid architecture** that maintains native tools as the primary execution path while adding MCP as an optional interoperability layer.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         STRIX AGENT                                 │
│                                                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │
│  │  NATIVE     │    │   MCP       │    │   MCP       │             │
│  │  TOOLS      │    │  SERVER     │    │  CLIENT     │             │
│  │  (Fast)     │    │  (Expose)   │    │  (Consume)  │             │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘             │
│         │                  │                  │                     │
│         └────────┬─────────┴────────┬─────────┘                     │
│                  │                  │                               │
│                  ▼                  ▼                               │
│         ┌─────────────────────────────────────┐                     │
│         │      UNIFIED TOOL INTERFACE         │                     │
│         │  execute_tool(name, params, source) │                     │
│         └─────────────────────────────────────┘                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  Claude Code  │    │   Codex CLI   │    │  Gemini CLI   │
│  (via MCP)    │    │   (via MCP)   │    │  (via MCP)    │
└───────────────┘    └───────────────┘    └───────────────┘
```

### Key Principles

1. **Native first**: Internal tool calls bypass MCP entirely
2. **MCP for external**: Only use MCP when interacting with external systems
3. **Adapter pattern**: Translate between native and MCP formats at boundaries
4. **Configuration-driven**: Enable/disable MCP features via environment

---

## MCP Server Implementation

Exposing Strix tools as an MCP server allows external AI tools to invoke them.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    STRIX MCP SERVER                         │
│                                                             │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │  MCP Protocol   │    │  Tool Adapter   │                │
│  │  Handler        │───▶│  (Native ↔ MCP) │                │
│  └─────────────────┘    └────────┬────────┘                │
│                                  │                          │
│                                  ▼                          │
│                    ┌─────────────────────────┐              │
│                    │    Native Tool Registry │              │
│                    │    + Tool Executor      │              │
│                    └─────────────────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

### Tool Schema Translation

Native tool definition:
```python
@register_tool(sandbox_execution=True)
def terminal_execute(command: str, timeout: int = 120) -> dict[str, Any]:
    """Execute a bash command in the sandbox environment."""
    ...
```

MCP tool schema:
```json
{
  "name": "terminal_execute",
  "description": "Execute a bash command in the sandbox environment.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "command": {"type": "string", "description": "The command to execute"},
      "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 120}
    },
    "required": ["command"]
  }
}
```

### Required Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `mcp/server.py` | New file | MCP protocol handler |
| `mcp/adapters.py` | New file | Tool schema translation |
| `mcp/auth.py` | New file | Authentication for MCP connections |
| `tools/registry.py` | Modify | Add MCP schema generation |

### Exposed Tools (Recommended Subset)

Not all tools should be exposed via MCP. Recommended subset:

| Tool | Expose | Reason |
|------|--------|--------|
| `terminal_execute` | Yes | Core capability |
| `browser_action` | Yes | Web testing |
| `python_action` | Yes | Code execution |
| `str_replace_editor` | Yes | File editing |
| `list_requests` | Yes | Proxy inspection |
| `send_request` | Yes | HTTP testing |
| `create_vulnerability_report` | Yes | Output |
| `create_agent` | No | Internal orchestration |
| `agent_finish` | No | Internal lifecycle |
| `think` | No | Internal reasoning |

### Server Startup Options

```bash
# Option 1: Standalone MCP server
strix --mcp-server --port 8080

# Option 2: Integrated with scan (exposes tools during scan)
strix --target example.com --enable-mcp --mcp-port 8080

# Option 3: Unix socket (for local tools like Claude Code)
strix --mcp-server --socket /tmp/strix-mcp.sock
```

---

## MCP Client Implementation

Consuming external MCP tools allows Strix to leverage ecosystem tools.

### Use Cases

1. **Extended capabilities**: Use zen-mcp-server's `thinkdeep`, `consensus` tools
2. **Multi-model validation**: Route findings to other models for verification
3. **Documentation lookup**: Use `apilookup` for current API docs

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    STRIX AGENT                              │
│                                                             │
│  ┌─────────────────┐                                        │
│  │  LLM Response   │                                        │
│  │  Parser         │                                        │
│  └────────┬────────┘                                        │
│           │                                                 │
│           ▼                                                 │
│  ┌─────────────────────────────────────┐                   │
│  │       TOOL DISPATCHER               │                   │
│  │  if native_tool → native_executor   │                   │
│  │  if mcp_tool → mcp_client           │                   │
│  └────────┬────────────────┬───────────┘                   │
│           │                │                               │
│           ▼                ▼                               │
│  ┌─────────────┐  ┌─────────────────┐                      │
│  │   Native    │  │   MCP Client    │                      │
│  │   Executor  │  │   Pool          │                      │
│  └─────────────┘  └────────┬────────┘                      │
│                            │                               │
└────────────────────────────┼───────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌───────────┐  ┌───────────┐  ┌───────────┐
       │ zen-mcp   │  │ custom    │  │ other     │
       │ server    │  │ server    │  │ server    │
       └───────────┘  └───────────┘  └───────────┘
```

### Required Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `mcp/client.py` | New file | MCP protocol client |
| `mcp/pool.py` | New file | Connection pooling |
| `tools/executor.py` | Modify | Route MCP tools |
| `llm/utils.py` | Modify | Parse MCP tool invocations |

---

## zen-mcp-server Integration

[zen-mcp-server](https://github.com/BeehiveInnovations/zen-mcp-server) provides multi-model orchestration capabilities that complement Strix.

### Relevant Features

| Feature | Strix Use Case |
|---------|---------------|
| `chat` | Multi-turn brainstorming with different models |
| `thinkdeep` | Extended reasoning for complex vulnerabilities |
| `consensus` | Multi-model validation of findings |
| `codereview` | Security-focused code review |
| `clink` | Bridge to Claude Code/Codex for specific tasks |
| `apilookup` | Current API documentation for testing |

### Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         STRIX SCAN                                  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    STRIX AGENT                               │   │
│  │                                                              │   │
│  │  Native Tools:                   MCP Tools (zen-mcp):        │   │
│  │  - terminal_execute              - thinkdeep                 │   │
│  │  - browser_action                - consensus                 │   │
│  │  - python_action                 - codereview                │   │
│  │  - send_request                  - apilookup                 │   │
│  │  - create_vulnerability_report   - clink (→ Claude/Codex)   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ▼                                      │
│                    ┌─────────────────┐                             │
│                    │  zen-mcp-server │                             │
│                    │  (subprocess)   │                             │
│                    └────────┬────────┘                             │
│                             │                                       │
│              ┌──────────────┼──────────────┐                       │
│              ▼              ▼              ▼                        │
│         ┌────────┐    ┌────────┐    ┌────────┐                     │
│         │ Gemini │    │ OpenAI │    │ Grok   │                     │
│         │ Pro    │    │ O3     │    │        │                     │
│         └────────┘    └────────┘    └────────┘                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Setup Requirements

1. **Clone zen-mcp-server**:
   ```bash
   git clone https://github.com/BeehiveInnovations/zen-mcp-server.git
   ```

2. **Configure API keys** (in `.env`):
   ```bash
   OPENROUTER_API_KEY=...
   GOOGLE_API_KEY=...
   OPENAI_API_KEY=...
   ```

3. **Configure Strix** to use zen-mcp:
   ```bash
   export STRIX_MCP_SERVERS='[{"name": "zen", "command": ["./zen-mcp-server/run-server.sh"]}]'
   ```

### Workflow Example: Multi-Model Vulnerability Validation

```
1. Strix discovers potential SQLi via native tools
   └─▶ terminal_execute: sqlmap scan
   └─▶ browser_action: capture response

2. Route to zen-mcp for validation
   └─▶ thinkdeep: "Analyze this SQLi finding..."
   └─▶ consensus: Get opinions from Gemini + O3

3. Document with native tools
   └─▶ create_vulnerability_report: Include multi-model analysis
```

---

## Claude Code Integration

Claude Code integration addresses [Issue #66](https://github.com/usestrix/strix/issues/66).

### Integration Options

#### Option A: Claude Code as MCP Client (Recommended)

Strix runs as an MCP server, Claude Code connects as client.

```
┌─────────────────┐         ┌─────────────────┐
│  Claude Code    │  MCP    │  Strix MCP      │
│  (orchestrator) │ ◀─────▶ │  Server         │
└─────────────────┘         └─────────────────┘
```

**Configuration** (`~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "strix": {
      "command": "strix",
      "args": ["--mcp-server"],
      "env": {
        "STRIX_SANDBOX_MODE": "true"
      }
    }
  }
}
```

**Benefits**:
- Claude Code handles auth/session management
- Strix tools appear in Claude Code's tool palette
- User can orchestrate scans conversationally

#### Option B: Claude Code as LLM Provider

Use Claude Code's authentication instead of direct API keys.

```bash
# Instead of:
export STRIX_LLM="anthropic/claude-sonnet-4-20250514"
export LLM_API_KEY="sk-ant-..."

# Use:
export STRIX_LLM="claude-code/claude-sonnet-4.5"
export STRIX_CLAUDE_CODE_PATH="/usr/local/bin/claude"
```

**Implementation**: Subprocess wrapper that invokes `claude` CLI for completions.

**Benefits**:
- No API key management
- Uses Claude Code's token optimization
- Better for CI/CD environments

#### Option C: Via zen-mcp-server clink

Use zen-mcp-server's `clink` tool to spawn Claude Code subagents.

```
Strix Agent → zen-mcp → clink → Claude Code subprocess
```

**Benefits**:
- Minimal changes to Strix
- Fresh context for each Claude Code invocation
- Good for specific sub-tasks (code review, analysis)

### Recommended Approach

1. **Primary**: Option A (MCP Server) for full orchestration
2. **Secondary**: Option C (clink) for sub-task delegation
3. **Future**: Option B for API-key-free operation

---

## OpenAI Codex CLI Integration

Codex CLI integration addresses [Issue #31](https://github.com/usestrix/strix/issues/31).

### Integration Options

#### Option A: Codex as MCP Client

```
┌─────────────────┐         ┌─────────────────┐
│  Codex CLI      │  MCP    │  Strix MCP      │
│  (orchestrator) │ ◀─────▶ │  Server         │
└─────────────────┘         └─────────────────┘
```

**Configuration** (`~/.codex/config.json`):
```json
{
  "mcpServers": {
    "strix": {
      "command": "strix",
      "args": ["--mcp-server"]
    }
  }
}
```

#### Option B: Via zen-mcp-server

Use zen-mcp's `clink` to spawn Codex subagents for specific tasks.

#### Option C: Direct LiteLLM Integration

Codex models are already supported via LiteLLM:

```bash
export STRIX_LLM="openai/codex-medium"
export LLM_API_KEY="sk-..."
```

### Codex-Specific Considerations

- **Rate limits**: "Several hundred rounds per day for ChatGPT subscribers"
- **Strengths**: Code understanding and generation
- **Use case**: Code analysis, exploit development assistance

---

## Google Gemini CLI Integration

Gemini integration addresses [Issue #117](https://github.com/usestrix/strix/issues/117).

### Current Status

Gemini is already partially supported via LiteLLM:

```bash
export STRIX_LLM="gemini/gemini-2.0-flash"
export GOOGLE_API_KEY="..."
```

### Full Gemini CLI Integration

#### Option A: Direct LiteLLM (Already Available)

```bash
# Gemini 2.0 Flash (fast, cheap)
export STRIX_LLM="gemini/gemini-2.0-flash"

# Gemini 3.0 Pro (advanced reasoning)
export STRIX_LLM="gemini/gemini-3.0-pro"

export GOOGLE_API_KEY="your-api-key"
```

#### Option B: Gemini CLI as MCP Client

```
┌─────────────────┐         ┌─────────────────┐
│  Gemini CLI     │  MCP    │  Strix MCP      │
│  (orchestrator) │ ◀─────▶ │  Server         │
└─────────────────┘         └─────────────────┘
```

#### Option C: Via zen-mcp-server

Use zen-mcp to access Gemini models for validation/thinking:

```
Strix (Claude) → zen-mcp → Gemini Pro (validation)
```

### Gemini-Specific Features

- **Long context**: 1M+ token context window
- **Grounding**: Web search integration
- **Thinking mode**: Deep reasoning for complex analysis

---

## Configuration Design

### Environment Variables

```bash
# MCP Server Configuration
STRIX_MCP_ENABLED=true                    # Enable MCP features
STRIX_MCP_SERVER_PORT=8080                # MCP server port
STRIX_MCP_SERVER_SOCKET=/tmp/strix.sock   # Unix socket path
STRIX_MCP_AUTH_TOKEN=...                  # Authentication token

# MCP Client Configuration
STRIX_MCP_SERVERS='[
  {"name": "zen", "command": ["./zen-mcp-server/run-server.sh"]},
  {"name": "custom", "url": "http://localhost:9000"}
]'

# Tool Exposure Configuration
STRIX_MCP_EXPOSED_TOOLS="terminal_execute,browser_action,python_action,send_request"
STRIX_MCP_BLOCKED_TOOLS="create_agent,agent_finish"

# Multi-Model Configuration (for zen-mcp)
ZEN_DEFAULT_MODEL="gemini/gemini-3.0-pro"
ZEN_THINKING_MODEL="openai/o3"
```

### Configuration File (`strix.config.yaml`)

```yaml
mcp:
  server:
    enabled: true
    port: 8080
    socket: /tmp/strix-mcp.sock
    auth:
      type: token
      token: ${STRIX_MCP_AUTH_TOKEN}

    exposed_tools:
      - terminal_execute
      - browser_action
      - python_action
      - str_replace_editor
      - list_requests
      - send_request
      - create_vulnerability_report

    blocked_tools:
      - create_agent
      - agent_finish
      - think

  clients:
    - name: zen
      type: subprocess
      command: ["./zen-mcp-server/run-server.sh"]
      tools:
        - thinkdeep
        - consensus
        - codereview
        - apilookup

    - name: custom
      type: http
      url: http://localhost:9000
      auth:
        type: bearer
        token: ${CUSTOM_MCP_TOKEN}

llm:
  providers:
    claude-code:
      enabled: true
      path: /usr/local/bin/claude
      model: claude-sonnet-4.5

    gemini:
      enabled: true
      model: gemini/gemini-3.0-pro
      api_key: ${GOOGLE_API_KEY}
```

---

## Implementation Phases

### Phase 1: MCP Server Foundation

**Goal**: Expose Strix tools via MCP for external orchestration

**Tasks**:
1. Create `strix/mcp/` module structure
2. Implement MCP protocol handler (stdio/HTTP)
3. Add tool schema translation (native → MCP)
4. Implement authentication layer
5. Add `--mcp-server` CLI flag

**Deliverables**:
- Strix can run as MCP server
- Claude Code can connect and invoke tools

### Phase 2: MCP Client Integration

**Goal**: Consume external MCP tools (zen-mcp-server)

**Tasks**:
1. Implement MCP client with connection pooling
2. Add MCP tool discovery and registration
3. Modify tool executor to route MCP tools
4. Add MCP tool invocation parsing

**Deliverables**:
- Strix can use zen-mcp tools (thinkdeep, consensus)
- Multi-model validation workflows possible

### Phase 3: zen-mcp-server Integration

**Goal**: Deep integration with zen-mcp-server capabilities

**Tasks**:
1. Bundle zen-mcp-server or document setup
2. Add workflow templates for multi-model analysis
3. Integrate `clink` for Claude Code/Codex subagents
4. Add `apilookup` for dynamic API documentation

**Deliverables**:
- One-command setup for multi-model workflows
- Pre-built templates for vulnerability validation

### Phase 4: Native CLI Integration

**Goal**: Direct integration with Claude Code, Codex, Gemini CLIs

**Tasks**:
1. Claude Code LLM provider wrapper
2. Codex CLI integration
3. Gemini CLI integration
4. Unified configuration interface

**Deliverables**:
- API-key-free operation via Claude Code
- Seamless model switching

---

## Trade-offs and Considerations

### Performance Impact

| Operation | Native | Via MCP | Overhead |
|-----------|--------|---------|----------|
| Tool invocation | ~1ms | ~50-100ms | Protocol + serialization |
| Tool discovery | Startup | Each connection | Negligible |
| Context sharing | Direct | JSON serialization | ~10-50ms |

**Mitigation**: Keep frequently-used tools native, use MCP for extended capabilities.

### Complexity Trade-offs

| Approach | Complexity | Flexibility | Performance |
|----------|------------|-------------|-------------|
| Native only | Low | Limited | Excellent |
| MCP only | Medium | High | Good |
| Hybrid (recommended) | Medium-High | Excellent | Excellent |

### When to Use MCP vs Native

**Use Native Tools**:
- High-frequency operations (terminal, browser)
- Security-critical operations (sandbox execution)
- Operations requiring AgentState access
- Performance-critical paths

**Use MCP Tools**:
- Multi-model validation
- Extended reasoning (thinkdeep)
- External tool integration
- Ecosystem tools (apilookup)

---

## Security Considerations

### MCP Server Security

1. **Authentication**: Require token-based auth for all connections
2. **Authorization**: Role-based tool access (mirror native TOOL_PROFILES)
3. **Sandboxing**: MCP tool calls execute in existing sandbox
4. **Rate limiting**: Prevent abuse via connection limits

### MCP Client Security

1. **Server validation**: Only connect to configured MCP servers
2. **Tool whitelisting**: Explicitly list allowed external tools
3. **Result validation**: Sanitize external tool results
4. **Timeout enforcement**: Prevent hung connections

### Sensitive Data Handling

1. **API keys**: Never expose via MCP tool results
2. **Scan data**: Scope MCP access to current engagement
3. **Credentials**: Mask in tool invocation logs
4. **Reports**: Access control for vulnerability data

---

## Summary

This integration plan enables Strix to:

1. **Expose tools via MCP** for orchestration by Claude Code, Codex, Gemini
2. **Consume MCP tools** from zen-mcp-server for multi-model workflows
3. **Maintain performance** by keeping native tools as the fast path
4. **Preserve simplicity** through clean abstractions and configuration-driven features

The hybrid approach ensures that:
- Existing users see no change in behavior
- Power users can enable MCP for advanced workflows
- The codebase remains maintainable without MCP lock-in

### Next Steps

1. Review and approve this plan
2. Prioritize phases based on user demand
3. Begin Phase 1 implementation
4. Gather feedback and iterate

---

## References

- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [zen-mcp-server](https://github.com/BeehiveInnovations/zen-mcp-server)
- [LiteLLM Documentation](https://docs.litellm.ai/)
- [Claude Code Documentation](https://docs.anthropic.com/en/docs/claude-code)
- [Issue #31: Codex Integration](https://github.com/usestrix/strix/issues/31)
- [Issue #66: Claude Code Support](https://github.com/usestrix/strix/issues/66)
- [Issue #109: MCP Support](https://github.com/usestrix/strix/issues/109)
- [Issue #117: Gemini 3.0 Support](https://github.com/usestrix/strix/issues/117)
