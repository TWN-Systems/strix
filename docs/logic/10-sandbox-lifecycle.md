# Sandbox Lifecycle Management

This diagram illustrates Docker container lifecycle management for the isolated execution environment.

## Overview

Sandbox lifecycle management involves:
1. Container creation with proper configuration
2. Port allocation for proxy and tool server
3. Tool server initialization and authentication
4. Workspace mounting and file access
5. Graceful shutdown and cleanup

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant Agent as StrixAgent
    participant DockerRuntime as Docker Runtime
    participant PortManager as Port Manager
    participant Docker as Docker Daemon
    participant Container as Sandbox Container
    participant ToolServer as Tool Server
    participant Caido as Caido Proxy

    rect rgb(240, 248, 255)
        Note over Agent,PortManager: Phase 1: Resource Allocation
        Agent->>DockerRuntime: create_sandbox()

        DockerRuntime->>PortManager: find_available_port()
        PortManager->>PortManager: Scan port range
        PortManager-->>DockerRuntime: proxy_port (e.g., 8080)

        DockerRuntime->>PortManager: find_available_port()
        PortManager-->>DockerRuntime: tool_server_port (e.g., 8081)

        DockerRuntime->>DockerRuntime: Generate sandbox_token
        Note right of DockerRuntime: token = secrets.token_urlsafe(32)
    end

    rect rgb(255, 248, 240)
        Note over DockerRuntime,Container: Phase 2: Container Creation
        DockerRuntime->>Docker: docker create

        Note right of Docker: Configuration:<br/>- Image: ghcr.io/usestrix/strix-sandbox:0.1.10<br/>- Ports: {proxy_port}, {tool_server_port}<br/>- Volumes: /workspace<br/>- Env: SANDBOX_TOKEN, PROXY_PORT

        Docker->>Container: Create container
        Container-->>Docker: container_id
        Docker-->>DockerRuntime: container_id

        DockerRuntime->>Docker: docker start {container_id}
        Docker->>Container: Start container
        Container-->>Docker: Started
    end

    rect rgb(240, 255, 240)
        Note over Container,Caido: Phase 3: Service Initialization
        Container->>ToolServer: Start tool server
        ToolServer->>ToolServer: Load authentication
        ToolServer->>ToolServer: Bind to 0.0.0.0:{port}
        ToolServer-->>Container: Tool server ready

        Container->>Caido: Start Caido proxy
        Caido->>Caido: Initialize proxy engine
        Caido->>Caido: Bind to 0.0.0.0:{proxy_port}
        Caido-->>Container: Proxy ready
    end

    rect rgb(255, 240, 255)
        Note over Agent,ToolServer: Phase 4: Connection Verification
        DockerRuntime->>DockerRuntime: Wait for services

        loop Health check (max 30s)
            DockerRuntime->>ToolServer: GET /health
            alt Not ready
                DockerRuntime->>DockerRuntime: Sleep(1s)
            else Ready
                ToolServer-->>DockerRuntime: 200 OK
                Note over DockerRuntime: Services ready
            end
        end

        DockerRuntime-->>Agent: SandboxInfo(<br/>  sandbox_id,<br/>  token,<br/>  proxy_port,<br/>  tool_server_port,<br/>  workspace_path<br/>)
    end

    rect rgb(255, 255, 240)
        Note over Agent,ToolServer: Phase 5: Active Usage
        loop During agent execution
            Agent->>ToolServer: POST /execute (with Bearer token)
            ToolServer->>ToolServer: Validate token
            ToolServer->>ToolServer: Execute tool
            ToolServer-->>Agent: Result
        end
    end

    rect rgb(248, 248, 255)
        Note over Agent,Container: Phase 6: Cleanup
        Agent->>DockerRuntime: cleanup_sandbox(sandbox_id)

        DockerRuntime->>Docker: docker stop {container_id}
        Docker->>Container: SIGTERM
        Container->>ToolServer: Shutdown
        Container->>Caido: Shutdown
        Container-->>Docker: Stopped

        DockerRuntime->>Docker: docker rm {container_id}
        Docker-->>DockerRuntime: Removed

        DockerRuntime->>PortManager: Release ports
        DockerRuntime-->>Agent: Cleanup complete
    end
```

## Container Configuration

```mermaid
sequenceDiagram
    autonumber
    participant Runtime as Docker Runtime
    participant Docker

    Runtime->>Docker: docker create

    Note over Docker: Container Configuration

    Note right of Docker: Image:<br/>ghcr.io/usestrix/strix-sandbox:0.1.10

    Note right of Docker: Environment Variables:<br/>SANDBOX_TOKEN=xxxxx<br/>PROXY_PORT=8080<br/>TOOL_SERVER_PORT=8081<br/>HTTP_PROXY=http://localhost:8080<br/>HTTPS_PROXY=http://localhost:8080

    Note right of Docker: Port Mappings:<br/>-p {host_proxy}:8080<br/>-p {host_tool}:8081

    Note right of Docker: Volume Mounts:<br/>-v /host/workspace:/workspace:rw

    Note right of Docker: Resource Limits:<br/>--memory=4g<br/>--cpus=2

    Note right of Docker: Security:<br/>--network=bridge<br/>--cap-drop=ALL<br/>--cap-add=NET_BIND_SERVICE

    Docker-->>Runtime: Container created
```

## Tool Server Architecture

```mermaid
sequenceDiagram
    autonumber
    participant Client as Agent (Host)
    participant Server as Tool Server
    participant Auth as Auth Middleware
    participant Handler as Tool Handler
    participant Runtime as Tool Runtime

    Client->>Server: POST /execute
    Note right of Client: Headers:<br/>Authorization: Bearer {token}<br/>Content-Type: application/json

    Server->>Auth: Validate request
    Auth->>Auth: Extract Bearer token
    Auth->>Auth: Compare with SANDBOX_TOKEN

    alt Token invalid
        Auth-->>Server: 401 Unauthorized
        Server-->>Client: Authentication failed
    end

    Auth-->>Server: Authenticated

    Server->>Handler: Dispatch request
    Note right of Handler: Request body:<br/>{<br/>  "tool": "terminal_execute",<br/>  "params": {<br/>    "command": "ls -la"<br/>  }<br/>}

    Handler->>Handler: Lookup tool handler
    Handler->>Runtime: Execute tool

    alt terminal_execute
        Runtime->>Runtime: subprocess.run(cmd)
    else browser_action
        Runtime->>Runtime: playwright.action()
    else python_action
        Runtime->>Runtime: exec(code)
    else str_replace_editor
        Runtime->>Runtime: file_operation()
    end

    Runtime-->>Handler: Result
    Handler-->>Server: Tool result
    Server-->>Client: 200 OK + JSON response
```

## Workspace Management

```mermaid
sequenceDiagram
    autonumber
    participant Host as Host System
    participant Runtime as Docker Runtime
    participant Container as Sandbox
    participant Workspace as /workspace

    rect rgb(240, 248, 255)
        Note over Host,Workspace: Initial Setup
        Host->>Host: Create workspace directory
        Note right of Host: /tmp/strix-{run_id}/workspace/

        Host->>Host: Copy target files
        Note right of Host: - Cloned repositories<br/>- Local source code<br/>- Configuration files

        Runtime->>Container: Mount workspace
        Container->>Workspace: /workspace accessible
    end

    rect rgb(255, 248, 240)
        Note over Container,Workspace: During Execution
        Container->>Workspace: Read source files
        Workspace-->>Container: File contents

        Container->>Workspace: Write test artifacts
        Note right of Workspace: - Screenshots<br/>- Logs<br/>- Generated scripts

        Container->>Workspace: Modify source (patches)
        Workspace-->>Container: File updated
    end

    rect rgb(240, 255, 240)
        Note over Host,Workspace: Bidirectional Access
        Note over Host: Host can also access<br/>/tmp/strix-{run_id}/workspace/<br/>for inspection
    end
```

## Port Allocation Strategy

```mermaid
sequenceDiagram
    autonumber
    participant Agent1 as Agent 1
    participant Agent2 as Agent 2
    participant PortMgr as Port Manager
    participant Pool as Port Pool

    Note over PortMgr,Pool: Port Pool: 8000-9000

    Agent1->>PortMgr: Request proxy port
    PortMgr->>Pool: Find available
    Pool-->>PortMgr: 8080
    PortMgr->>Pool: Mark 8080 in use
    PortMgr-->>Agent1: 8080

    Agent1->>PortMgr: Request tool server port
    PortMgr->>Pool: Find available
    Pool-->>PortMgr: 8081
    PortMgr->>Pool: Mark 8081 in use
    PortMgr-->>Agent1: 8081

    Note over Agent1,Agent2: Multiple agents can run<br/>with different ports

    Agent2->>PortMgr: Request proxy port
    PortMgr->>Pool: Find available (skip 8080, 8081)
    Pool-->>PortMgr: 8082
    PortMgr-->>Agent2: 8082

    Note over Agent1,Pool: On cleanup

    Agent1->>PortMgr: Release ports
    PortMgr->>Pool: Mark 8080, 8081 available
```

## Key Components

| Component | File Location | Responsibility |
|-----------|---------------|----------------|
| Docker Runtime | `runtime/docker_runtime.py` | Container lifecycle |
| Tool Server | `runtime/tool_server.py` | Request handling in sandbox |
| Port Manager | `runtime/docker_runtime.py` | Port allocation |
| Workspace Manager | `utils/utils.py` | File preparation |

## Container Services

| Service | Port | Purpose |
|---------|------|---------|
| Tool Server | 8081 (default) | Execute tools via HTTP |
| Caido Proxy | 8080 (default) | HTTP traffic interception |
| Browser | N/A | Playwright automation |
| Python Runtime | N/A | Code execution |
| Terminal | N/A | Shell command execution |

## Sandbox Security Model

```
┌─────────────────────────────────────────────────┐
│                 Host System                      │
│  ┌───────────────────────────────────────────┐  │
│  │            Docker Container                │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │  Isolated Network (bridge)          │  │  │
│  │  │  - No host network access           │  │  │
│  │  │  - Controlled port exposure         │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  │                                           │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │  Limited Capabilities               │  │  │
│  │  │  - cap-drop=ALL                     │  │  │
│  │  │  - Only NET_BIND_SERVICE            │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  │                                           │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │  Resource Limits                    │  │  │
│  │  │  - Memory: 4GB                      │  │  │
│  │  │  - CPU: 2 cores                     │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  │                                           │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │  Authenticated Access               │  │  │
│  │  │  - Bearer token required            │  │  │
│  │  │  - Token generated per session      │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────┘  │
│                                                  │
│  ┌───────────────────────────────────────────┐  │
│  │  Mounted Volume (/workspace)              │  │
│  │  - Read/Write access                      │  │
│  │  - Isolated from host filesystem          │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## Error Handling

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant Runtime as Docker Runtime
    participant Docker

    alt Container creation fails
        Agent->>Runtime: create_sandbox()
        Runtime->>Docker: docker create
        Docker-->>Runtime: Error (e.g., image not found)
        Runtime-->>Agent: SandboxCreationError
        Agent->>Agent: Abort scan
    end

    alt Health check timeout
        Runtime->>Runtime: Wait for services
        loop 30 seconds
            Runtime->>Runtime: Health check fails
        end
        Runtime->>Docker: docker logs
        Docker-->>Runtime: Container logs
        Runtime-->>Agent: ServiceStartupError
        Agent->>Runtime: cleanup_sandbox()
    end

    alt Container crashes mid-execution
        Agent->>Runtime: execute_tool()
        Runtime->>Docker: Container not responding
        Runtime->>Docker: docker inspect
        Docker-->>Runtime: Container exited
        Runtime-->>Agent: ContainerCrashedError
        Agent->>Agent: Attempt recovery or abort
    end
```
