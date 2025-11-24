# Sub-Agent Creation & Coordination

This diagram illustrates how the root agent spawns specialized sub-agents and coordinates their execution.

## Overview

Sub-agent coordination involves:
1. Root agent identifying need for specialized testing
2. Creating sub-agents with specific prompt modules
3. Running sub-agents in separate threads
4. Inter-agent communication via message queue
5. Result aggregation and completion handling

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant RootAgent as Root Agent
    participant CreateAgent as create_agent()
    participant AgentGraph as Agent Graph Manager
    participant Thread as Thread Pool
    participant SubAgent as Sub-Agent
    participant LLM
    participant MessageQueue as Message Queue
    participant Tracer

    Note over RootAgent: Root agent identifies need<br/>for specialized testing

    rect rgb(240, 248, 255)
        Note over RootAgent,AgentGraph: Phase 1: Agent Creation Request
        RootAgent->>CreateAgent: create_agent(task, name, prompt_modules)
        Note right of CreateAgent: Example:<br/>task="Find SQL injection vulnerabilities"<br/>name="sql_discovery"<br/>prompt_modules="sql_injection"

        CreateAgent->>CreateAgent: Validate prompt_modules (max 5)
        CreateAgent->>CreateAgent: Generate unique agent_id
        CreateAgent->>AgentGraph: Register new agent
        AgentGraph->>AgentGraph: Add to agent hierarchy
        AgentGraph->>AgentGraph: Set parent_id = root_agent_id
    end

    rect rgb(255, 248, 240)
        Note over CreateAgent,SubAgent: Phase 2: Sub-Agent Initialization
        CreateAgent->>Thread: spawn _run_agent_in_thread()

        activate Thread
        Thread->>SubAgent: Initialize StrixAgent
        SubAgent->>SubAgent: Load prompt modules
        Note right of SubAgent: Loads specialized knowledge<br/>from prompts/vulnerabilities/

        SubAgent->>SubAgent: Inherit sandbox from parent
        Note right of SubAgent: Shares workspace,<br/>proxy, tools

        SubAgent->>Tracer: log_agent_creation()
        Thread-->>CreateAgent: Thread started
        deactivate Thread

        CreateAgent-->>RootAgent: agent_id returned
    end

    rect rgb(240, 255, 240)
        Note over RootAgent,SubAgent: Phase 3: Parallel Execution
        par Root Agent continues
            RootAgent->>RootAgent: Continue main loop
            RootAgent->>LLM: Process other tasks
        and Sub-Agent executes
            SubAgent->>SubAgent: agent_loop(task)
            loop Sub-agent iterations
                SubAgent->>LLM: generate()
                LLM-->>SubAgent: Response + tools
                SubAgent->>SubAgent: Execute tools
                SubAgent->>Tracer: Log progress
            end
        end
    end

    rect rgb(255, 240, 255)
        Note over RootAgent,MessageQueue: Phase 4: Inter-Agent Communication
        alt Sub-agent needs to report finding
            SubAgent->>MessageQueue: send_message_to_agent(parent_id, message)
            MessageQueue->>MessageQueue: Queue message for parent
            Note right of MessageQueue: Message types:<br/>- information<br/>- query<br/>- instruction

            RootAgent->>RootAgent: Check for messages (each iteration)
            RootAgent->>MessageQueue: get_pending_messages()
            MessageQueue-->>RootAgent: List[Message]
            RootAgent->>RootAgent: Process messages
        end

        alt Root agent needs sub-agent update
            RootAgent->>MessageQueue: send_message_to_agent(sub_agent_id, query)
            SubAgent->>MessageQueue: wait_for_message()
            MessageQueue-->>SubAgent: Message from parent
            SubAgent->>SubAgent: Process query
            SubAgent->>MessageQueue: send_message_to_agent(parent_id, response)
        end
    end

    rect rgb(255, 255, 240)
        Note over SubAgent,Tracer: Phase 5: Sub-Agent Completion
        SubAgent->>SubAgent: agent_finish(summary)
        SubAgent->>MessageQueue: Send final report to parent
        SubAgent->>AgentGraph: Update status="completed"
        SubAgent->>Tracer: Log completion

        RootAgent->>MessageQueue: Receive completion message
        RootAgent->>AgentGraph: view_agent_graph()
        AgentGraph-->>RootAgent: All sub-agents status
    end
```

## Agent Hierarchy Example

```mermaid
sequenceDiagram
    autonumber
    participant Root as Root Agent
    participant Discovery as Discovery Agent<br/>(sql_injection)
    participant Validation as Validation Agent<br/>(sql_injection)
    participant Reporting as Reporting Agent

    Root->>Discovery: create_agent("Find SQLi", modules="sql_injection")
    activate Discovery

    Discovery->>Discovery: Scan for injection points
    Discovery->>Discovery: Test payloads
    Discovery-->>Root: Found 3 potential vulnerabilities

    Root->>Validation: create_agent("Validate SQLi findings", modules="sql_injection")
    activate Validation

    Validation->>Validation: Build PoC for finding #1
    Validation->>Validation: Extract data to prove impact
    Validation-->>Root: Confirmed: Critical SQLi in /api/users

    deactivate Validation

    Discovery->>Discovery: Continue testing
    Discovery-->>Root: No more findings
    deactivate Discovery

    Root->>Reporting: create_agent("Generate report")
    activate Reporting
    Reporting->>Reporting: create_vulnerability_report()
    Reporting-->>Root: Report generated
    deactivate Reporting
```

## Message Queue Detail

```mermaid
sequenceDiagram
    autonumber
    participant Sender as Sending Agent
    participant MQ as Message Queue
    participant Receiver as Receiving Agent

    Sender->>MQ: send_message_to_agent(target_id, content, type)
    Note right of MQ: Message structure:<br/>{<br/>  from_agent: sender_id,<br/>  to_agent: target_id,<br/>  content: "...",<br/>  type: "information",<br/>  timestamp: now()<br/>}

    MQ->>MQ: Validate target agent exists
    MQ->>MQ: Add to target's queue

    alt Receiver checking for messages
        Receiver->>Receiver: _process_iteration()
        Receiver->>MQ: get_pending_messages(agent_id)
        MQ-->>Receiver: List[Message]
        Receiver->>Receiver: Add to conversation history
    end

    alt Receiver explicitly waiting
        Receiver->>MQ: wait_for_message(timeout=300)
        loop Until message or timeout
            MQ->>MQ: Check queue
            alt Message available
                MQ-->>Receiver: Message
            else Timeout
                MQ-->>Receiver: TimeoutError
            end
        end
    end
```

## Key Components

| Component | File Location | Responsibility |
|-----------|---------------|----------------|
| create_agent | `tools/agents_graph/actions.py` | Spawns new sub-agents |
| send_message_to_agent | `tools/agents_graph/actions.py` | Inter-agent messaging |
| wait_for_message | `tools/agents_graph/actions.py` | Blocking message wait |
| view_agent_graph | `tools/agents_graph/actions.py` | Visualize agent hierarchy |
| Agent Graph Manager | `tools/agents_graph/manager.py` | Tracks all agents |
| Message Queue | `tools/agents_graph/message_queue.py` | Message routing |

## Prompt Module Assignment

When creating a sub-agent, prompt modules determine its specialization:

| Module Type | Examples | Purpose |
|-------------|----------|---------|
| Vulnerability | `sql_injection`, `xss`, `idor` | Specific vulnerability testing |
| Framework | `fastapi`, `nextjs` | Framework-specific patterns |
| Protocol | `graphql` | Protocol testing |
| Technology | `firebase_firestore`, `supabase` | Tech-specific security |
| Coordination | `root_agent` | Orchestration (root only) |

## Sub-Agent Constraints

- **Max modules per agent**: 5 (for focus)
- **Sandbox sharing**: Sub-agents share parent's sandbox
- **Independent execution**: Run in separate threads
- **No direct tool sharing**: Communicate via messages
- **Completion requirement**: Must call `agent_finish()` to complete

## Agent Status Lifecycle

```
pending → running → completed
             ↓
          waiting (for child agents)
             ↓
          running
             ↓
          error (on exception)
```
