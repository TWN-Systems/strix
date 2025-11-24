# LLM Prompt Construction

This diagram illustrates how prompts are constructed and sent to the language model.

## Overview

LLM prompt construction involves:
1. System prompt building with base instructions
2. Tool definitions injection
3. Vulnerability module loading
4. Conversation history management
5. Response parsing and tool extraction

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant Agent as StrixAgent
    participant LLMConfig as LLM Config
    participant PromptBuilder as Prompt Builder
    participant ModuleLoader as Module Loader
    participant ToolRegistry as Tool Registry
    participant LLM as LiteLLM
    participant Parser as Response Parser

    rect rgb(240, 248, 255)
        Note over Agent,ModuleLoader: Phase 1: System Prompt Construction
        Agent->>LLMConfig: Get LLM configuration

        Agent->>PromptBuilder: Build system prompt
        PromptBuilder->>PromptBuilder: Load base system prompt
        Note right of PromptBuilder: From: agents/StrixAgent/system_prompt.jinja

        PromptBuilder->>ModuleLoader: Load prompt modules
        Note right of ModuleLoader: Modules: ["sql_injection", "xss"]

        loop For each module
            ModuleLoader->>ModuleLoader: Load module template
            ModuleLoader->>ModuleLoader: Render Jinja2
            ModuleLoader-->>PromptBuilder: Module content
        end

        PromptBuilder->>PromptBuilder: Inject modules into prompt
    end

    rect rgb(255, 248, 240)
        Note over PromptBuilder,ToolRegistry: Phase 2: Tool Definitions
        PromptBuilder->>ToolRegistry: Get tool definitions

        loop For each registered tool
            ToolRegistry->>ToolRegistry: Load tool XML schema
            ToolRegistry-->>PromptBuilder: Tool definition
        end

        PromptBuilder->>PromptBuilder: Format tools section
        Note right of PromptBuilder: <tools><br/>  <tool name="terminal_execute">...</tool><br/>  <tool name="browser_action">...</tool><br/>  ...<br/></tools>
    end

    rect rgb(240, 255, 240)
        Note over Agent,PromptBuilder: Phase 3: Message Assembly
        Agent->>PromptBuilder: Get conversation history

        PromptBuilder->>PromptBuilder: Build messages array
        Note right of PromptBuilder: messages = [<br/>  {role: "system", content: system_prompt},<br/>  {role: "user", content: task},<br/>  {role: "assistant", content: response1},<br/>  {role: "user", content: tool_result1},<br/>  ...<br/>]

        PromptBuilder-->>Agent: Complete messages
    end

    rect rgb(255, 240, 255)
        Note over Agent,LLM: Phase 4: LLM API Call
        Agent->>LLM: generate(messages, tools)

        LLM->>LLM: Configure model parameters
        Note right of LLM: model = STRIX_LLM<br/>temperature = 0.7<br/>max_tokens = 4096<br/>timeout = 600s

        LLM->>LLM: Call LiteLLM completion
        Note right of LLM: litellm.completion(<br/>  model=model,<br/>  messages=messages,<br/>  tools=tools<br/>)

        LLM-->>Agent: Raw response
    end

    rect rgb(255, 255, 240)
        Note over Agent,Parser: Phase 5: Response Parsing
        Agent->>Parser: Parse response

        Parser->>Parser: Extract text content
        Parser->>Parser: Extract tool calls

        alt Has tool_calls
            loop For each tool_call
                Parser->>Parser: Parse tool name
                Parser->>Parser: Parse parameters (XML/JSON)
                Parser->>Parser: Create ToolInvocation
            end
        end

        Parser-->>Agent: ParsedResponse(<br/>  content,<br/>  tool_calls[]<br/>)
    end
```

## System Prompt Structure

```mermaid
sequenceDiagram
    autonumber
    participant Builder as Prompt Builder
    participant Template as Jinja2 Template

    Builder->>Template: Render system_prompt.jinja

    Note over Template: System Prompt Structure

    rect rgb(240, 248, 255)
        Note over Template: Section 1: Identity & Role
        Note right of Template: You are Strix, an AI-powered<br/>cybersecurity agent...<br/>You act like a real hacker...<br/>You have full authorization...
    end

    rect rgb(255, 248, 240)
        Note over Template: Section 2: Communication Rules
        Note right of Template: - Use plain text (no markdown)<br/>- Don't echo tool invocations<br/>- Act autonomously<br/>- Minimize messaging between agents
    end

    rect rgb(240, 255, 240)
        Note over Template: Section 3: Available Tools
        Note right of Template: <tools><br/>  <tool name="terminal_execute"><br/>    <description>...</description><br/>    <parameters>...</parameters><br/>  </tool><br/>  ...<br/></tools>
    end

    rect rgb(255, 240, 255)
        Note over Template: Section 4: Vulnerability Modules
        Note right of Template: <vulnerability_guide><br/>  <title>SQL Injection</title><br/>  <methodology>...</methodology><br/>  <payloads>...</payloads><br/></vulnerability_guide>
    end

    rect rgb(255, 255, 240)
        Note over Template: Section 5: Methodology Guidelines
        Note right of Template: Testing approach:<br/>1. Scope definition<br/>2. Breadth-first discovery<br/>3. Automated scanning<br/>4. Targeted exploitation<br/>5. Validation
    end

    Template-->>Builder: Rendered prompt (~10-50KB)
```

## Vulnerability Module Loading

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant Loader as Module Loader
    participant FileSystem as prompts/vulnerabilities/

    Agent->>Loader: Load modules(["sql_injection", "idor"])

    Loader->>FileSystem: Read sql_injection.jinja
    FileSystem-->>Loader: Template content

    Loader->>Loader: Render template
    Note right of Loader: <vulnerability_guide><br/>  <title>SQL Injection Testing</title><br/>  <critical>...</critical><br/>  <scope>...</scope><br/>  <methodology><br/>    <step>Identify input points</step><br/>    <step>Test with payloads</step><br/>    ...<br/>  </methodology><br/>  <payloads><br/>    ' OR '1'='1<br/>    1; DROP TABLE--<br/>    ...<br/>  </payloads><br/></vulnerability_guide>

    Loader->>FileSystem: Read idor.jinja
    FileSystem-->>Loader: Template content
    Loader->>Loader: Render template

    Loader-->>Agent: Combined module content
```

## Conversation History Management

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant State as Agent State
    participant Memory as Memory Manager
    participant LLM

    Note over Agent,LLM: Iteration N

    Agent->>State: Get message history
    State-->>Agent: messages (potentially large)

    Agent->>Memory: Check context size
    Memory->>Memory: Count tokens

    alt Context exceeds limit
        Memory->>Memory: Compress history
        Note right of Memory: Strategies:<br/>- Summarize old messages<br/>- Remove tool results<br/>- Keep recent context
        Memory-->>Agent: Compressed messages
    else Context within limit
        Memory-->>Agent: Original messages
    end

    Agent->>LLM: generate(messages)
    LLM-->>Agent: Response

    Agent->>State: Append assistant message
    Agent->>State: Append tool results (if any)
```

## Tool Definition Format

```mermaid
sequenceDiagram
    autonumber
    participant Registry as Tool Registry
    participant Schema as XML Schema

    Registry->>Schema: Load tool definitions

    Note over Schema: Tool Definition Example

    Note right of Schema: <tool name="terminal_execute"><br/>  <description><br/>    Execute a shell command in the sandbox<br/>  </description><br/>  <parameters><br/>    <parameter name="command" type="string" required="true"><br/>      The shell command to execute<br/>    </parameter><br/>    <parameter name="timeout" type="integer" required="false"><br/>      Timeout in seconds (default: 300)<br/>    </parameter><br/>  </parameters><br/>  <returns><br/>    stdout, stderr, exit_code<br/>  </returns><br/>  <examples><br/>    <example><br/>      <input>command="ls -la"</input><br/>      <output>Directory listing...</output><br/>    </example><br/>  </examples><br/></tool>

    Schema-->>Registry: Parsed tool definitions
```

## Key Components

| Component | File Location | Responsibility |
|-----------|---------------|----------------|
| LLM Config | `llm/config.py` | Model configuration |
| LLM Class | `llm/llm.py` | LiteLLM wrapper |
| Prompt Builder | `llm/llm.py` | Prompt assembly |
| Module Loader | `prompts/loader.py` | Load Jinja2 templates |
| Memory Compressor | `llm/memory_compressor.py` | Context management |
| Tool Registry | `tools/registry.py` | Tool definitions |

## Model Configuration

| Parameter | Value | Description |
|-----------|-------|-------------|
| `model` | `STRIX_LLM` env | Model identifier |
| `temperature` | 0.7 | Response randomness |
| `max_tokens` | 4096 | Max response length |
| `timeout` | 600s | API call timeout |
| `top_p` | 1.0 | Nucleus sampling |

## Supported Models

| Provider | Models | Notes |
|----------|--------|-------|
| OpenAI | gpt-4, gpt-4-turbo, gpt-4o | Best performance |
| Anthropic | claude-3-opus, claude-3-sonnet | Good for security tasks |
| LiteLLM | Any supported model | Proxy support |

## Response Parsing

```mermaid
sequenceDiagram
    autonumber
    participant LLM
    participant Parser as Response Parser
    participant Agent

    LLM-->>Parser: Raw response

    Parser->>Parser: Extract content
    Note right of Parser: "I'll scan for SQL injection...<br/><tool_invocation><br/>  <tool_name>terminal_execute</tool_name><br/>  <parameters><br/>    <command>sqlmap -u ...</command><br/>  </parameters><br/></tool_invocation>"

    Parser->>Parser: Find tool invocations
    Parser->>Parser: Parse XML structure

    loop For each tool invocation
        Parser->>Parser: Extract tool_name
        Parser->>Parser: Parse parameters
        Parser->>Parser: Create ToolInvocation object
    end

    Parser-->>Agent: ParsedResponse
    Note right of Agent: content: "I'll scan..."<br/>tool_calls: [<br/>  ToolInvocation(<br/>    name="terminal_execute",<br/>    params={"command": "sqlmap..."}<br/>  )<br/>]
```

## Prompt Caching

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant Cache as Prompt Cache
    participant LLM

    Agent->>Cache: Check cache for system prompt

    alt Cache hit
        Cache-->>Agent: Cached system prompt hash
        Agent->>LLM: Use cached prompt reference
        Note right of LLM: Reduces token usage<br/>and latency
    else Cache miss
        Agent->>Agent: Build full system prompt
        Agent->>Cache: Store prompt hash
        Agent->>LLM: Send full prompt
    end

    LLM-->>Agent: Response
```
