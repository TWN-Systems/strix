# Tool Execution Pipeline

This diagram illustrates how tools are invoked, validated, routed, and executed in the Strix architecture.

## Overview

The tool execution pipeline involves:
1. LLM response parsing for tool invocations
2. Tool registry lookup and validation
3. Parameter parsing and type conversion
4. Routing to sandbox or host execution
5. Result serialization and conversation update

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant Agent as StrixAgent
    participant Parser as Response Parser
    participant Registry as Tool Registry
    participant Validator as Parameter Validator
    participant Router as Execution Router
    participant Sandbox as Sandbox (Docker)
    participant ToolServer as Tool Server
    participant Host as Host Executor
    participant Tracer

    Agent->>Agent: Receive LLM response with tool_calls

    rect rgb(240, 248, 255)
        Note over Agent,Parser: Phase 1: Tool Invocation Parsing
        Agent->>Parser: parse_tool_invocations(response)

        loop For each tool_call in response
            Parser->>Parser: Extract tool_name
            Parser->>Parser: Extract parameters (XML/JSON)
            Parser->>Parser: Create ToolInvocation object
        end

        Parser-->>Agent: List[ToolInvocation]
    end

    loop For each ToolInvocation
        rect rgb(255, 248, 240)
            Note over Agent,Registry: Phase 2: Tool Lookup
            Agent->>Registry: get_tool(tool_name)

            alt Tool exists
                Registry-->>Agent: ToolDefinition
            else Tool not found
                Registry-->>Agent: ToolNotFoundError
                Agent->>Agent: Add error to conversation
                Note over Agent: Continue to next tool
            end
        end

        rect rgb(240, 255, 240)
            Note over Agent,Validator: Phase 3: Parameter Validation
            Agent->>Validator: validate_params(tool_def, params)

            Validator->>Validator: Check required parameters
            Validator->>Validator: Validate types
            Validator->>Validator: Apply defaults

            alt Validation passed
                Validator-->>Agent: Validated params
            else Validation failed
                Validator-->>Agent: ValidationError
                Agent->>Agent: Add error to conversation
                Note over Agent: Continue to next tool
            end
        end

        rect rgb(255, 240, 255)
            Note over Agent,Host: Phase 4: Execution Routing
            Agent->>Router: route_execution(tool_def, params)
            Router->>Router: Check tool.execution_location

            alt Tool runs in sandbox
                Router->>Sandbox: Send execution request
                Sandbox->>ToolServer: HTTP POST /execute
                Note right of ToolServer: Authenticated with<br/>sandbox_token

                ToolServer->>ToolServer: Execute tool handler
                ToolServer->>ToolServer: Capture stdout/stderr
                ToolServer-->>Sandbox: Execution result
                Sandbox-->>Router: Result
            else Tool runs on host
                Router->>Host: Execute directly
                Host->>Host: Run tool function
                Host-->>Router: Result
            end

            Router-->>Agent: ToolResult
        end

        rect rgb(255, 255, 240)
            Note over Agent,Tracer: Phase 5: Result Processing
            Agent->>Tracer: log_tool_execution(tool_name, params, result)
            Agent->>Agent: Serialize result to message
            Agent->>Agent: Add to conversation history
        end
    end

    Agent->>Agent: Continue agent loop
```

## Tool Categories and Routing

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant Router as Execution Router
    participant Sandbox
    participant Host

    Note over Router: Tool Routing Decision Tree

    alt Proxy Tools (list_requests, view_request, send_request, etc.)
        Agent->>Router: Execute proxy tool
        Router->>Sandbox: Route to Caido proxy
        Sandbox-->>Agent: HTTP traffic data
    end

    alt Browser Tools (browser_action)
        Agent->>Router: Execute browser tool
        Router->>Sandbox: Route to Playwright
        Sandbox-->>Agent: Browser result/screenshot
    end

    alt Terminal Tools (terminal_execute)
        Agent->>Router: Execute terminal tool
        Router->>Sandbox: Route to shell
        Sandbox-->>Agent: Command output
    end

    alt Python Tools (python_action)
        Agent->>Router: Execute python tool
        Router->>Sandbox: Route to Python runtime
        Sandbox-->>Agent: Execution output
    end

    alt File Tools (str_replace_editor)
        Agent->>Router: Execute file tool
        Router->>Sandbox: Route to file system
        Sandbox-->>Agent: File contents/status
    end

    alt Agent Tools (create_agent, send_message_to_agent)
        Agent->>Router: Execute agent tool
        Router->>Host: Execute on host
        Host-->>Agent: Agent management result
    end

    alt Completion Tools (finish_scan, agent_finish)
        Agent->>Router: Execute completion tool
        Router->>Host: Execute on host
        Host-->>Agent: Completion status
    end

    alt Reporting Tools (create_vulnerability_report)
        Agent->>Router: Execute reporting tool
        Router->>Host: Execute on host (Tracer)
        Host-->>Agent: Report logged
    end
```

## Sandbox Tool Execution Detail

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant HTTP as HTTP Client
    participant ToolServer as Tool Server<br/>(in container)
    participant Handler as Tool Handler
    participant Runtime as Tool Runtime

    Agent->>HTTP: POST http://localhost:{port}/execute
    Note right of HTTP: Headers:<br/>Authorization: Bearer {token}<br/>Content-Type: application/json

    HTTP->>ToolServer: Forward request
    ToolServer->>ToolServer: Validate auth token

    alt Invalid token
        ToolServer-->>HTTP: 401 Unauthorized
        HTTP-->>Agent: AuthenticationError
    end

    ToolServer->>ToolServer: Parse request body
    Note right of ToolServer: {<br/>  tool: "terminal_execute",<br/>  params: {command: "ls -la"}<br/>}

    ToolServer->>Handler: Dispatch to handler
    Handler->>Handler: Lookup tool handler

    alt terminal_execute
        Handler->>Runtime: Execute shell command
        Runtime->>Runtime: subprocess.run()
        Runtime-->>Handler: stdout, stderr, exit_code
    else browser_action
        Handler->>Runtime: Execute Playwright action
        Runtime->>Runtime: page.action()
        Runtime-->>Handler: Result/screenshot
    else python_action
        Handler->>Runtime: Execute Python code
        Runtime->>Runtime: exec() in session
        Runtime-->>Handler: Output
    else str_replace_editor
        Handler->>Runtime: File operation
        Runtime->>Runtime: read/write/edit
        Runtime-->>Handler: File content/status
    end

    Handler-->>ToolServer: Execution result
    ToolServer->>ToolServer: Serialize response
    ToolServer-->>HTTP: 200 OK + JSON body
    HTTP-->>Agent: ToolResult
```

## Key Components

| Component | File Location | Responsibility |
|-----------|---------------|----------------|
| Tool Registry | `tools/registry.py` | Tool registration and lookup |
| Tool Executor | `tools/executor.py` | Execution orchestration |
| Parameter Validator | `tools/validator.py` | Input validation |
| Tool Server | `runtime/tool_server.py` | Sandbox-side handler |
| Tool Handlers | `tools/*/actions.py` | Individual tool implementations |
| Tracer | `telemetry/tracer.py` | Execution logging |

## Available Tools (27 total)

| Category | Tools | Execution Location |
|----------|-------|-------------------|
| **Proxy** | `list_requests`, `view_request`, `send_request`, `repeat_request`, `scope_rules`, `list_sitemap`, `view_sitemap_entry` | Sandbox |
| **Browser** | `browser_action` | Sandbox |
| **Terminal** | `terminal_execute` | Sandbox |
| **Python** | `python_action` | Sandbox |
| **File Edit** | `str_replace_editor` | Sandbox |
| **Agents** | `create_agent`, `send_message_to_agent`, `wait_for_message`, `view_agent_graph` | Host |
| **Completion** | `agent_finish`, `finish_scan` | Host |
| **Reporting** | `create_vulnerability_report` | Host |
| **Analysis** | `think`, `web_search` | Host |
| **Notes** | `create_note`, `list_notes`, `update_note`, `delete_note` | Sandbox |

## Error Handling Flow

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant Executor
    participant Tool
    participant Tracer

    Agent->>Executor: Execute tool

    alt Tool not found
        Executor-->>Agent: Error: Tool '{name}' not found
        Agent->>Agent: Add error message to conversation
    else Parameter validation failed
        Executor-->>Agent: Error: Missing required param '{param}'
        Agent->>Agent: Add error message to conversation
    else Execution timeout
        Executor->>Tool: Execute with timeout
        Tool--xExecutor: TimeoutError
        Executor-->>Agent: Error: Tool execution timed out
        Agent->>Tracer: Log timeout
    else Runtime error
        Executor->>Tool: Execute
        Tool--xExecutor: Exception
        Executor-->>Agent: Error: {exception_message}
        Agent->>Tracer: Log error
    else Success
        Executor->>Tool: Execute
        Tool-->>Executor: Result
        Executor-->>Agent: ToolResult
        Agent->>Tracer: Log success
    end

    Agent->>Agent: Continue to next iteration
```

## Tool Result Format

```python
ToolResult:
    tool_name: str          # Name of executed tool
    success: bool           # Execution success status
    output: str             # Tool output (stdout or result)
    error: Optional[str]    # Error message if failed
    metadata: Dict          # Additional tool-specific data
```
