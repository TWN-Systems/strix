# HTTP Request Capture & Analysis

This diagram illustrates how HTTP traffic is captured, stored, and analyzed through the Caido proxy integration.

## Overview

HTTP request capture involves:
1. Caido proxy initialization in the sandbox
2. Browser/terminal traffic routing through proxy
3. Request interception and storage
4. HTTPQL query-based filtering
5. Request replay and modification

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant Browser as Browser Tool
    participant Terminal as Terminal Tool
    participant Proxy as Caido Proxy
    participant Storage as Request Storage
    participant ProxyTools as Proxy Tools
    participant Sitemap as Sitemap Builder

    rect rgb(240, 248, 255)
        Note over Agent,Proxy: Phase 1: Proxy Initialization
        Agent->>Agent: Sandbox creation (see Sandbox diagram)
        Note right of Proxy: Proxy starts with sandbox<br/>Listens on allocated port

        Agent->>ProxyTools: scope_rules(allowlist=["*.target.com"])
        ProxyTools->>Proxy: Configure scope
        Proxy-->>ProxyTools: Scope configured
        ProxyTools-->>Agent: Scope set
    end

    rect rgb(255, 248, 240)
        Note over Agent,Storage: Phase 2: Traffic Capture (Browser)
        Agent->>Browser: browser_action(launch)
        Browser->>Browser: Configure proxy settings
        Note right of Browser: HTTP_PROXY=localhost:{port}

        Agent->>Browser: browser_action(goto, url="https://target.com")
        Browser->>Proxy: GET https://target.com
        Proxy->>Proxy: Check scope rules

        alt URL in scope
            Proxy->>Proxy: Forward request to target
            Proxy->>Storage: Store request/response
            Proxy-->>Browser: Response
        else URL out of scope
            Proxy->>Proxy: Forward without storing
            Proxy-->>Browser: Response
        end

        Browser-->>Agent: Page loaded

        Agent->>Browser: browser_action(click, selector="#login")
        Browser->>Proxy: POST https://target.com/api/login
        Proxy->>Storage: Store request
        Proxy-->>Browser: Response
    end

    rect rgb(240, 255, 240)
        Note over Agent,Storage: Phase 3: Traffic Capture (Terminal)
        Agent->>Terminal: terminal_execute("curl https://target.com/api/users")
        Note right of Terminal: curl uses HTTP_PROXY env

        Terminal->>Proxy: GET https://target.com/api/users
        Proxy->>Storage: Store request/response
        Proxy-->>Terminal: Response
        Terminal-->>Agent: curl output
    end

    rect rgb(255, 240, 255)
        Note over Agent,ProxyTools: Phase 4: Request Querying
        Agent->>ProxyTools: list_requests(<br/>filter="host:target.com AND method:POST",<br/>limit=50<br/>)

        ProxyTools->>Proxy: HTTPQL query
        Proxy->>Storage: Search requests
        Storage-->>Proxy: Matching requests
        Proxy-->>ProxyTools: Request list

        ProxyTools-->>Agent: List of request summaries
        Note right of Agent: [{id: 1, method: POST,<br/>  path: /api/login,<br/>  status: 200}, ...]

        Agent->>ProxyTools: view_request(id=1)
        ProxyTools->>Storage: Get full request
        Storage-->>ProxyTools: Complete request/response
        ProxyTools-->>Agent: Full HTTP details
        Note right of Agent: Headers, body,<br/>response headers,<br/>response body, timing
    end

    rect rgb(255, 255, 240)
        Note over Agent,Sitemap: Phase 5: Sitemap Analysis
        Agent->>ProxyTools: list_sitemap()
        ProxyTools->>Sitemap: Get sitemap tree
        Sitemap->>Storage: Aggregate by path
        Storage-->>Sitemap: Grouped requests
        Sitemap-->>ProxyTools: Hierarchical sitemap

        ProxyTools-->>Agent: Sitemap structure
        Note right of Agent: target.com/<br/>├── api/<br/>│   ├── users (GET, POST)<br/>│   ├── login (POST)<br/>│   └── admin (GET)<br/>└── static/...

        Agent->>ProxyTools: view_sitemap_entry(path="/api/users")
        ProxyTools-->>Agent: All requests to /api/users
    end
```

## Request Replay & Modification

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant ProxyTools as Proxy Tools
    participant Proxy as Caido Proxy
    participant Target as Target Server

    rect rgb(240, 248, 255)
        Note over Agent,Target: Replay Original Request
        Agent->>ProxyTools: repeat_request(id=1)
        ProxyTools->>Proxy: Get request #1
        Proxy-->>ProxyTools: Original request
        ProxyTools->>Target: Send identical request
        Target-->>ProxyTools: Response
        ProxyTools-->>Agent: New response
    end

    rect rgb(255, 248, 240)
        Note over Agent,Target: Modified Request (Parameter Tampering)
        Agent->>ProxyTools: repeat_request(<br/>id=1,<br/>modifications={<br/>  "body": {"id": "1 OR 1=1"}<br/>}<br/>)

        ProxyTools->>Proxy: Get request #1
        Proxy-->>ProxyTools: Original request
        ProxyTools->>ProxyTools: Apply modifications
        ProxyTools->>Target: Send modified request
        Target-->>ProxyTools: Response
        ProxyTools-->>Agent: Response with SQLi payload
    end

    rect rgb(240, 255, 240)
        Note over Agent,Target: Custom Request
        Agent->>ProxyTools: send_request(<br/>method="POST",<br/>url="https://target.com/api/admin",<br/>headers={"Authorization": "Bearer token"},<br/>body={"action": "delete_user"}<br/>)

        ProxyTools->>Target: Custom HTTP request
        Target-->>ProxyTools: Response
        ProxyTools->>Proxy: Store in history
        ProxyTools-->>Agent: Response details
    end
```

## HTTPQL Filter Examples

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant ProxyTools as Proxy Tools
    participant Proxy as Caido Proxy

    Note over Agent,Proxy: HTTPQL Query Examples

    Agent->>ProxyTools: list_requests(filter="status:500")
    Note right of ProxyTools: Find server errors
    ProxyTools-->>Agent: Error responses

    Agent->>ProxyTools: list_requests(filter="method:POST AND path:/api/*")
    Note right of ProxyTools: Find API POST requests
    ProxyTools-->>Agent: API mutations

    Agent->>ProxyTools: list_requests(filter="body.contains:password")
    Note right of ProxyTools: Find password submissions
    ProxyTools-->>Agent: Auth requests

    Agent->>ProxyTools: list_requests(filter="response.body.contains:error")
    Note right of ProxyTools: Find error messages
    ProxyTools-->>Agent: Verbose error responses

    Agent->>ProxyTools: list_requests(filter="header:Authorization")
    Note right of ProxyTools: Find authenticated requests
    ProxyTools-->>Agent: Requests with auth
```

## Scope Configuration

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant ProxyTools as Proxy Tools
    participant Proxy as Caido Proxy

    Agent->>ProxyTools: scope_rules(<br/>allowlist=["*.target.com", "api.target.com"],<br/>denylist=["*.google.com", "*.analytics.com"]<br/>)

    ProxyTools->>Proxy: Configure allowlist
    Proxy->>Proxy: Add patterns to allowlist

    ProxyTools->>Proxy: Configure denylist
    Proxy->>Proxy: Add patterns to denylist

    Note over Proxy: Scope Logic:<br/>1. Check denylist (reject if match)<br/>2. Check allowlist (accept if match)<br/>3. Default: reject

    ProxyTools-->>Agent: Scope configured

    Note over Agent,Proxy: Traffic Filtering

    rect rgb(255, 240, 240)
        Agent->>Proxy: Request to analytics.com
        Proxy->>Proxy: Denylist match
        Proxy-->>Agent: Forwarded (not stored)
    end

    rect rgb(240, 255, 240)
        Agent->>Proxy: Request to target.com
        Proxy->>Proxy: Allowlist match
        Proxy->>Proxy: Store request
        Proxy-->>Agent: Response (stored)
    end
```

## Key Components

| Component | File Location | Responsibility |
|-----------|---------------|----------------|
| Proxy Manager | `tools/proxy/manager.py` | Caido proxy control |
| list_requests | `tools/proxy/actions.py` | Query captured requests |
| view_request | `tools/proxy/actions.py` | Get full request details |
| send_request | `tools/proxy/actions.py` | Custom HTTP requests |
| repeat_request | `tools/proxy/actions.py` | Replay with modifications |
| scope_rules | `tools/proxy/actions.py` | Configure capture scope |
| list_sitemap | `tools/proxy/actions.py` | Get hierarchical view |
| Caido Proxy | (in sandbox) | HTTP interception engine |

## Request Data Structure

```python
CapturedRequest:
    id: int                     # Unique request ID
    method: str                 # HTTP method
    url: str                    # Full URL
    path: str                   # URL path
    host: str                   # Target host
    headers: Dict[str, str]     # Request headers
    body: Optional[str]         # Request body
    timestamp: datetime         # Capture time

    response:
        status: int             # HTTP status code
        headers: Dict[str, str] # Response headers
        body: str               # Response body
        time_ms: int            # Response time
```

## Common Workflows

### 1. Endpoint Discovery
```
browser_action(goto) → list_sitemap() → Analyze attack surface
```

### 2. Parameter Testing
```
view_request(id) → repeat_request(modifications) → Analyze response
```

### 3. Error Analysis
```
list_requests(filter="status:500") → view_request(id) → Investigate
```

### 4. Authentication Flow Analysis
```
list_requests(filter="path:/auth/*") → view_request(id) → Extract tokens
```
