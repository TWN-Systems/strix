# Inter-Agent Communication

This diagram illustrates the message passing system between agents in the Strix multi-agent architecture.

## Overview

Inter-agent communication involves:
1. Message queue management for each agent
2. Asynchronous message sending between agents
3. Blocking and non-blocking message retrieval
4. Message type handling (information, query, instruction)
5. Parent-child and sibling communication patterns

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant Root as Root Agent
    participant MQ as Message Queue Manager
    participant Queue1 as Root's Queue
    participant Queue2 as Child's Queue
    participant Child as Child Agent

    rect rgb(240, 248, 255)
        Note over Root,Child: Phase 1: Agent and Queue Setup
        Root->>MQ: Register root agent
        MQ->>Queue1: Create queue for root
        Queue1-->>MQ: Queue ready

        Root->>Root: create_agent(task, name)
        Root->>MQ: Register child agent
        MQ->>Queue2: Create queue for child
        Queue2-->>MQ: Queue ready
    end

    rect rgb(255, 248, 240)
        Note over Root,Child: Phase 2: Parent → Child Communication
        Root->>MQ: send_message_to_agent(<br/>target=child_id,<br/>content="Focus on /api/admin endpoint",<br/>type="instruction"<br/>)

        MQ->>MQ: Validate target exists
        MQ->>MQ: Create message object
        Note right of MQ: {<br/>  from: root_id,<br/>  to: child_id,<br/>  content: "...",<br/>  type: "instruction",<br/>  timestamp: now()<br/>}

        MQ->>Queue2: Enqueue message
        MQ-->>Root: Message sent

        Note over Child: During iteration
        Child->>Child: _process_iteration()
        Child->>MQ: get_pending_messages(child_id)
        MQ->>Queue2: Dequeue all messages
        Queue2-->>MQ: List[Message]
        MQ-->>Child: Messages from parent
        Child->>Child: Add to conversation history
    end

    rect rgb(240, 255, 240)
        Note over Root,Child: Phase 3: Child → Parent Communication
        Child->>Child: Found vulnerability

        Child->>MQ: send_message_to_agent(<br/>target=parent_id,<br/>content="Found SQLi in /api/admin",<br/>type="information"<br/>)

        MQ->>Queue1: Enqueue message

        Note over Root: During iteration
        Root->>MQ: get_pending_messages(root_id)
        MQ->>Queue1: Dequeue all messages
        Queue1-->>MQ: List[Message]
        MQ-->>Root: Messages from child
        Root->>Root: Process finding
    end

    rect rgb(255, 240, 255)
        Note over Root,Child: Phase 4: Blocking Wait
        Child->>Child: Need clarification from parent

        Child->>MQ: wait_for_message(timeout=300)
        activate Child
        Note right of Child: Agent blocks execution

        loop Poll until message or timeout
            MQ->>Queue2: Check for messages

            alt No messages
                MQ->>MQ: Sleep(poll_interval)
            else Message available
                Queue2-->>MQ: Message
                MQ-->>Child: Message received
                Note over Child: Continue execution
            end
        end
        deactivate Child

        alt Timeout reached
            MQ-->>Child: TimeoutError
            Child->>Child: Handle timeout
        end
    end
```

## Multi-Agent Communication Patterns

```mermaid
sequenceDiagram
    autonumber
    participant Root as Root Agent
    participant MQ as Message Queue
    participant SQLi as SQLi Agent
    participant XSS as XSS Agent
    participant Report as Report Agent

    Note over Root,Report: Pattern 1: Broadcast from Root

    Root->>MQ: send_message_to_agent(sqli_id, "New endpoint: /api/v2")
    Root->>MQ: send_message_to_agent(xss_id, "New endpoint: /api/v2")

    MQ-->>SQLi: Endpoint notification
    MQ-->>XSS: Endpoint notification

    Note over Root,Report: Pattern 2: Aggregation to Root

    SQLi->>MQ: send_message_to_agent(root_id, "SQLi found")
    XSS->>MQ: send_message_to_agent(root_id, "XSS found")

    MQ-->>Root: SQLi finding
    MQ-->>Root: XSS finding

    Root->>Root: Aggregate findings

    Note over Root,Report: Pattern 3: Chain Coordination

    Root->>Report: create_agent(task="Generate report")
    Root->>MQ: send_message_to_agent(report_id, findings_summary)
    MQ-->>Report: All findings data

    Report->>Report: Generate report
    Report->>MQ: send_message_to_agent(root_id, "Report ready")
    MQ-->>Root: Report completion
```

## Message Types and Handling

```mermaid
sequenceDiagram
    autonumber
    participant Sender
    participant MQ as Message Queue
    participant Receiver

    rect rgb(240, 248, 255)
        Note over Sender,Receiver: Type: "information"
        Sender->>MQ: send(type="information", content="Found 3 endpoints")
        MQ-->>Receiver: Information message
        Receiver->>Receiver: Add to context
        Note right of Receiver: No response expected
    end

    rect rgb(255, 248, 240)
        Note over Sender,Receiver: Type: "query"
        Sender->>MQ: send(type="query", content="What is the auth mechanism?")
        MQ-->>Receiver: Query message
        Receiver->>Receiver: Process query
        Receiver->>MQ: send(type="information", content="JWT with RS256")
        MQ-->>Sender: Query response
    end

    rect rgb(240, 255, 240)
        Note over Sender,Receiver: Type: "instruction"
        Sender->>MQ: send(type="instruction", content="Test /api/admin for IDOR")
        MQ-->>Receiver: Instruction message
        Receiver->>Receiver: Execute instruction
        Note right of Receiver: Updates task focus
    end
```

## Agent Graph Visualization

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant ViewGraph as view_agent_graph()
    participant GraphMgr as Agent Graph Manager

    Agent->>ViewGraph: view_agent_graph()
    ViewGraph->>GraphMgr: Get all agents

    GraphMgr->>GraphMgr: Build hierarchy tree
    GraphMgr->>GraphMgr: Collect statuses

    GraphMgr-->>ViewGraph: Agent hierarchy data

    ViewGraph-->>Agent: Graph visualization
    Note right of Agent: root (running)<br/>├── sqli_discovery (completed)<br/>├── xss_discovery (running)<br/>│   └── xss_validation (running)<br/>└── idor_discovery (pending)
```

## Key Components

| Component | File Location | Responsibility |
|-----------|---------------|----------------|
| send_message_to_agent | `tools/agents_graph/actions.py` | Send messages |
| wait_for_message | `tools/agents_graph/actions.py` | Blocking receive |
| view_agent_graph | `tools/agents_graph/actions.py` | Hierarchy visualization |
| Message Queue Manager | `tools/agents_graph/message_queue.py` | Queue management |
| Agent Graph Manager | `tools/agents_graph/manager.py` | Agent tracking |

## Message Structure

```python
Message:
    id: str                 # Unique message ID
    from_agent: str         # Sender agent ID
    to_agent: str           # Recipient agent ID
    content: str            # Message content
    type: str               # "information" | "query" | "instruction"
    timestamp: datetime     # Send time
    read: bool              # Read status
```

## Communication Guidelines

### When to Use Each Message Type

| Type | Use Case | Example |
|------|----------|---------|
| **information** | Share findings, status updates | "Found SQLi at /api/users" |
| **query** | Request information from another agent | "What endpoints have you discovered?" |
| **instruction** | Direct another agent's focus | "Test the admin panel next" |

### Best Practices

1. **Minimize messaging** - Agents should be autonomous; only message when necessary
2. **Use information type** - Most common; share findings without expecting response
3. **Avoid loops** - Don't create circular query patterns
4. **Parent aggregation** - Children report to parents, not siblings
5. **Clear content** - Messages become part of conversation history

## Error Handling

```mermaid
sequenceDiagram
    autonumber
    participant Sender
    participant MQ as Message Queue
    participant Receiver

    alt Target agent doesn't exist
        Sender->>MQ: send_message_to_agent(invalid_id, content)
        MQ-->>Sender: Error: Agent not found
    end

    alt Queue overflow
        Sender->>MQ: send_message_to_agent(target, content)
        MQ->>MQ: Check queue size
        alt Queue full
            MQ-->>Sender: Error: Queue full
        end
    end

    alt Timeout on wait
        Receiver->>MQ: wait_for_message(timeout=60)
        MQ->>MQ: Poll for 60 seconds
        MQ-->>Receiver: TimeoutError
        Receiver->>Receiver: Handle timeout (continue or retry)
    end
```
