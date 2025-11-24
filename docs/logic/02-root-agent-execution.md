# Root Agent Scan Execution

This diagram illustrates the main execution loop of the Root Agent (StrixAgent) during a security scan.

## Overview

The root agent execution involves:
1. Sandbox initialization (Docker container creation)
2. Task construction and conversation initialization
3. Main agent loop with LLM interactions
4. Tool execution and result processing
5. Iteration management and completion

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant CLI
    participant StrixAgent
    participant State as AgentState
    participant DockerRuntime
    participant Sandbox
    participant LLM
    participant ToolRegistry
    participant Tracer

    CLI->>StrixAgent: execute_scan(targets, instructions)

    rect rgb(240, 248, 255)
        Note over StrixAgent,State: Phase 1: State Initialization
        StrixAgent->>State: Create AgentState
        State->>State: Set agent_id, agent_name="root"
        State->>State: Set status="running"
        State->>State: Set iteration=0
        State-->>StrixAgent: State initialized
    end

    rect rgb(255, 248, 240)
        Note over StrixAgent,Sandbox: Phase 2: Sandbox Setup
        StrixAgent->>StrixAgent: _initialize_sandbox_and_state()
        StrixAgent->>DockerRuntime: create_sandbox()
        DockerRuntime->>DockerRuntime: find_available_port()
        DockerRuntime->>DockerRuntime: generate_sandbox_token()
        DockerRuntime->>Sandbox: docker run strix-sandbox
        Sandbox->>Sandbox: Start tool server
        Sandbox->>Sandbox: Initialize Caido proxy
        Sandbox-->>DockerRuntime: Container ready
        DockerRuntime-->>StrixAgent: sandbox_id, token, workspace_path
        StrixAgent->>State: Store sandbox credentials
    end

    rect rgb(240, 255, 240)
        Note over StrixAgent,LLM: Phase 3: Conversation Setup
        StrixAgent->>StrixAgent: Build task description
        Note right of StrixAgent: Includes targets,<br/>instructions, workspace info
        StrixAgent->>State: Add system message (prompt)
        StrixAgent->>State: Add user message (task)
        StrixAgent->>Tracer: log_agent_creation()
    end

    rect rgb(255, 240, 255)
        Note over StrixAgent,Tracer: Phase 4: Main Agent Loop
        loop Until completion or max_iterations (300)
            StrixAgent->>StrixAgent: _process_iteration()

            alt Has pending messages from sub-agents
                StrixAgent->>State: Get pending messages
                StrixAgent->>State: Add messages to conversation
            end

            StrixAgent->>LLM: generate(messages, tools)
            Note right of LLM: Constructs prompt with:<br/>- System prompt<br/>- Tool definitions<br/>- Vulnerability modules<br/>- Conversation history

            LLM->>LLM: Call LiteLLM completion
            LLM-->>StrixAgent: Response (text + tool_calls)

            StrixAgent->>Tracer: log_chat_message(assistant)
            StrixAgent->>State: Add assistant message

            alt Response contains tool calls
                StrixAgent->>StrixAgent: _execute_actions(tool_calls)

                loop For each tool invocation
                    StrixAgent->>ToolRegistry: process_tool_invocation(tool)
                    ToolRegistry->>ToolRegistry: Validate tool exists
                    ToolRegistry->>ToolRegistry: Parse parameters

                    alt Tool runs in sandbox
                        ToolRegistry->>Sandbox: Execute tool
                        Sandbox-->>ToolRegistry: Tool result
                    else Tool runs on host
                        ToolRegistry->>ToolRegistry: Execute locally
                    end

                    ToolRegistry-->>StrixAgent: Tool result
                    StrixAgent->>Tracer: log_tool_execution()
                    StrixAgent->>State: Add tool result message
                end
            end

            alt Tool is "finish_scan"
                StrixAgent->>StrixAgent: Validate no running sub-agents
                StrixAgent->>State: Set status="completed"
                StrixAgent->>Tracer: set_final_scan_result()
                Note over StrixAgent: Break loop
            else Tool is "create_agent"
                StrixAgent->>StrixAgent: Spawn sub-agent thread
                Note right of StrixAgent: See Sub-Agent diagram
            end

            StrixAgent->>State: Increment iteration
        end
    end

    rect rgb(255, 255, 240)
        Note over StrixAgent,CLI: Phase 5: Completion
        StrixAgent->>Tracer: Finalize telemetry
        StrixAgent->>DockerRuntime: cleanup_sandbox()
        DockerRuntime->>Sandbox: docker stop/rm
        StrixAgent-->>CLI: Scan complete (final_report)
    end
```

## Detailed Iteration Flow

```mermaid
sequenceDiagram
    autonumber
    participant Agent as StrixAgent
    participant State as AgentState
    participant LLM
    participant Tools as Tool Executor
    participant Tracer

    Note over Agent: Single Iteration

    Agent->>Agent: Check iteration < max_iterations

    alt Messages from sub-agents pending
        Agent->>State: pop_pending_messages()
        State-->>Agent: List[Message]
        Agent->>State: Append to conversation
    end

    Agent->>LLM: generate()

    activate LLM
    LLM->>LLM: Build full prompt
    LLM->>LLM: Call model API
    LLM->>LLM: Parse response
    LLM-->>Agent: AssistantMessage
    deactivate LLM

    Agent->>Tracer: log_chat_message()
    Agent->>State: messages.append(response)

    alt Has tool_calls in response
        loop Each tool_call
            Agent->>Tools: execute(tool_name, params)

            activate Tools
            Tools->>Tools: Validate parameters
            Tools->>Tools: Route to handler

            alt Sandbox tool
                Tools->>Tools: Send to sandbox via HTTP
            else Host tool
                Tools->>Tools: Execute directly
            end

            Tools-->>Agent: ToolResult
            deactivate Tools

            Agent->>Tracer: log_tool_execution()
            Agent->>State: messages.append(tool_result)
        end
    end

    Agent->>State: iteration += 1

    alt finish_scan called
        Agent->>Agent: Verify completion conditions
        Agent-->>Agent: Exit loop
    else Continue
        Agent-->>Agent: Next iteration
    end
```

## Key Components

| Component | File Location | Responsibility |
|-----------|---------------|----------------|
| StrixAgent | `agents/StrixAgent/strix_agent.py` | Root agent implementation |
| BaseAgent | `agents/base_agent.py` | Core agent loop and tool processing |
| AgentState | `agents/state.py` | Agent state management |
| DockerRuntime | `runtime/docker_runtime.py` | Sandbox container management |
| LLM | `llm/llm.py` | Model interaction layer |
| ToolRegistry | `tools/registry.py` | Tool registration and routing |
| Tracer | `telemetry/tracer.py` | Execution logging |

## Agent Loop Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_iterations` | 300 | Maximum loop iterations before forced stop |
| `llm_timeout` | 600s | Timeout for individual LLM calls |
| `tool_timeout` | 300s | Timeout for tool execution |

## State Transitions

```
Created → Running → Completed
              ↓
           Error
              ↓
          Waiting (for sub-agents)
              ↓
           Running
```
