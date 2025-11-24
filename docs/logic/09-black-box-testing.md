# Black-Box Testing Workflow

This diagram illustrates the external security testing workflow without source code access.

## Overview

Black-box testing involves:
1. Target reconnaissance and endpoint discovery
2. Application mapping via browser automation
3. Parameter enumeration and fuzzing
4. Vulnerability scanning and exploitation
5. Finding validation and reporting

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant Browser as browser_action
    participant Proxy as HTTP Proxy
    participant Terminal as terminal_execute
    participant Python as python_action
    participant Report as Vulnerability Reporter

    rect rgb(240, 248, 255)
        Note over Agent,Proxy: Phase 1: Reconnaissance
        Agent->>Proxy: scope_rules(allowlist=["*.target.com"])

        Agent->>Browser: browser_action(launch)
        Agent->>Browser: browser_action(goto, url="https://target.com")
        Browser->>Proxy: GET https://target.com
        Proxy-->>Browser: Homepage

        Agent->>Browser: browser_action(screenshot)
        Browser-->>Agent: Page screenshot

        Agent->>Agent: Analyze page structure
        Note right of Agent: Identify:<br/>- Navigation links<br/>- Forms<br/>- JavaScript files<br/>- API endpoints
    end

    rect rgb(255, 248, 240)
        Note over Agent,Proxy: Phase 2: Application Mapping
        loop Explore application
            Agent->>Browser: browser_action(click, selector="a.nav-link")
            Browser->>Proxy: Request captured
            Proxy-->>Browser: Response

            Agent->>Browser: browser_action(screenshot)
            Agent->>Agent: Record new page
        end

        Agent->>Proxy: list_sitemap()
        Proxy-->>Agent: Discovered endpoints
        Note right of Agent: target.com/<br/>├── /login<br/>├── /dashboard<br/>├── /api/users<br/>├── /api/products<br/>└── /admin
    end

    rect rgb(240, 255, 240)
        Note over Agent,Python: Phase 3: Parameter Enumeration
        Agent->>Proxy: list_requests(filter="method:GET")
        Proxy-->>Agent: GET requests

        Agent->>Agent: Extract parameters
        Note right of Agent: Parameters found:<br/>- /api/users?id=<br/>- /api/products?category=<br/>- /search?q=

        Agent->>Python: python_action("""<br/># Enumerate parameter values<br/>for i in range(1, 100):<br/>    r = requests.get(f'{url}/api/users?id={i}')<br/>    if r.status_code == 200:<br/>        print(f'Valid ID: {i}')<br/>""")
        Python-->>Agent: Valid IDs: 1, 2, 5, 10, 42
    end

    rect rgb(255, 240, 255)
        Note over Agent,Terminal: Phase 4: Automated Scanning
        Agent->>Terminal: terminal_execute("""<br/>sqlmap -u "https://target.com/api/users?id=1" \<br/>  --batch --level=3 --risk=2<br/>""")
        Terminal-->>Agent: SQLMap results

        Agent->>Terminal: terminal_execute("""<br/>ffuf -u "https://target.com/FUZZ" \<br/>  -w /wordlists/common.txt \<br/>  -mc 200,301,302<br/>""")
        Terminal-->>Agent: Directory fuzzing results

        Agent->>Terminal: terminal_execute("""<br/>nuclei -u "https://target.com" \<br/>  -t cves/ -t vulnerabilities/<br/>""")
        Terminal-->>Agent: Nuclei scan results
    end

    rect rgb(255, 255, 240)
        Note over Agent,Proxy: Phase 5: Manual Testing
        Agent->>Proxy: view_request(id=15)
        Proxy-->>Agent: Login request details

        Agent->>Proxy: repeat_request(<br/>id=15,<br/>modifications={<br/>  "body": {"username": "admin' OR '1'='1", "password": "x"}<br/>}<br/>)
        Proxy-->>Agent: Response (SQLi test)

        Agent->>Browser: browser_action(type, selector="#search", text="<script>alert(1)</script>")
        Agent->>Browser: browser_action(click, selector="#submit")
        Browser-->>Agent: XSS test result
    end

    rect rgb(248, 248, 255)
        Note over Agent,Report: Phase 6: Validation & Reporting
        Agent->>Agent: Analyze all findings

        alt Vulnerability confirmed
            Agent->>Python: python_action("""<br/># Build PoC<br/>exploit_payload = "..."<br/>result = exploit(target, payload)<br/>print(f"Data extracted: {result}")<br/>""")
            Python-->>Agent: PoC execution result

            Agent->>Report: create_vulnerability_report(<br/>title="SQL Injection in Login",<br/>severity="critical",<br/>content="PoC and impact..."<br/>)
        end
    end
```

## Endpoint Discovery Techniques

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant Browser
    participant Proxy
    participant Terminal

    Note over Agent,Terminal: Multiple Discovery Methods

    rect rgb(240, 248, 255)
        Note over Agent,Browser: Method 1: Browser Crawling
        Agent->>Browser: browser_action(goto, url)
        loop Click all links
            Agent->>Browser: browser_action(click)
            Browser->>Proxy: Captured request
        end
        Agent->>Proxy: list_sitemap()
    end

    rect rgb(255, 248, 240)
        Note over Agent,Terminal: Method 2: Directory Fuzzing
        Agent->>Terminal: terminal_execute("""<br/>ffuf -u "{url}/FUZZ" -w wordlist.txt<br/>""")
        Terminal-->>Agent: Discovered paths
    end

    rect rgb(240, 255, 240)
        Note over Agent,Browser: Method 3: JavaScript Analysis
        Agent->>Browser: browser_action(execute_js, """<br/>return Array.from(document.scripts)<br/>  .map(s => s.src).filter(Boolean)<br/>""")
        Browser-->>Agent: Script URLs

        Agent->>Browser: browser_action(execute_js, """<br/>// Extract API endpoints from JS<br/>return window.__ROUTES__ || []<br/>""")
        Browser-->>Agent: API routes from JS
    end

    rect rgb(255, 240, 255)
        Note over Agent,Proxy: Method 4: Response Analysis
        Agent->>Proxy: list_requests()
        Proxy-->>Agent: All requests

        Agent->>Agent: Extract endpoints from responses
        Note right of Agent: Parse:<br/>- href attributes<br/>- API references<br/>- Form actions
    end
```

## Fuzzing Workflow

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant Python as python_action
    participant Proxy
    participant Target

    Note over Agent,Target: Parameter Fuzzing

    Agent->>Agent: Select fuzzing target
    Note right of Agent: Target: /api/users?id=1

    Agent->>Python: python_action("""<br/>payloads = [<br/>    "1", "0", "-1", "999999",  # Boundary<br/>    "1'", "1\"", "1;--",        # SQLi<br/>    "<script>", "{{7*7}}",      # XSS/SSTI<br/>    "../../../etc/passwd",       # Path traversal<br/>    "${7*7}", "{{constructor}}" # Injection<br/>]<br/><br/>for p in payloads:<br/>    r = requests.get(url, params={'id': p})<br/>    print(f'{p}: {r.status_code} {len(r.text)}')<br/>""")

    loop For each payload
        Python->>Proxy: GET /api/users?id={payload}
        Proxy->>Target: Forward request
        Target-->>Proxy: Response
        Proxy-->>Python: Response
    end

    Python-->>Agent: Fuzzing results
    Note right of Agent: Results:<br/>1: 200 1234<br/>1': 500 5678 ← Interesting!<br/>-1: 404 100<br/>...

    Agent->>Agent: Analyze anomalies
    Agent->>Agent: Follow up on SQLi indicator
```

## Authentication Testing

```mermaid
sequenceDiagram
    autonumber
    participant Agent
    participant Browser
    participant Proxy
    participant Python

    Note over Agent,Python: Authentication Flow Testing

    rect rgb(240, 248, 255)
        Note over Agent,Proxy: Capture Auth Flow
        Agent->>Browser: browser_action(goto, "/login")
        Agent->>Browser: browser_action(type, "#username", "testuser")
        Agent->>Browser: browser_action(type, "#password", "testpass")
        Agent->>Browser: browser_action(click, "#login-btn")
        Browser->>Proxy: POST /api/auth/login
        Proxy-->>Browser: JWT token
    end

    rect rgb(255, 248, 240)
        Note over Agent,Proxy: Analyze Token
        Agent->>Proxy: view_request(filter="path:/api/auth")
        Proxy-->>Agent: Auth request/response

        Agent->>Python: python_action("""<br/>import jwt<br/>token = "eyJ..."<br/>decoded = jwt.decode(token, options={"verify_signature": False})<br/>print(decoded)<br/>""")
        Python-->>Agent: Token payload
        Note right of Agent: {<br/>  "sub": "user123",<br/>  "role": "user",<br/>  "alg": "HS256"<br/>}
    end

    rect rgb(240, 255, 240)
        Note over Agent,Proxy: Test JWT Vulnerabilities
        Agent->>Python: python_action("""<br/># Algorithm confusion attack<br/>import jwt<br/>forged = jwt.encode(<br/>    {"sub": "admin", "role": "admin"},<br/>    key="",<br/>    algorithm="none"<br/>)<br/>""")
        Python-->>Agent: Forged token

        Agent->>Proxy: send_request(<br/>method="GET",<br/>url="/api/admin",<br/>headers={"Authorization": f"Bearer {forged}"}<br/>)
        Proxy-->>Agent: Response (test result)
    end
```

## Key Components

| Component | File Location | Responsibility |
|-----------|---------------|----------------|
| browser_action | `tools/browser/actions.py` | Web automation |
| terminal_execute | `tools/terminal/actions.py` | Security tools (sqlmap, ffuf) |
| python_action | `tools/python/actions.py` | Custom fuzzing scripts |
| Proxy Tools | `tools/proxy/actions.py` | Traffic analysis |
| Vulnerability Modules | `prompts/vulnerabilities/` | Attack patterns |

## Scanning Tools Integration

| Tool | Purpose | Example Command |
|------|---------|-----------------|
| **sqlmap** | SQL injection | `sqlmap -u "url?id=1" --batch` |
| **ffuf** | Fuzzing | `ffuf -u "url/FUZZ" -w wordlist.txt` |
| **nuclei** | Vulnerability scanning | `nuclei -u "url" -t cves/` |
| **nikto** | Web server scanning | `nikto -h "url"` |
| **wfuzz** | Parameter fuzzing | `wfuzz -z file,wordlist "url?FUZZ=test"` |

## Black-Box Testing Phases

```
Phase 1: Reconnaissance
├── Passive: DNS, WHOIS, certificate transparency
└── Active: Port scanning, banner grabbing

Phase 2: Mapping
├── Browser crawling
├── Directory fuzzing
└── JavaScript analysis

Phase 3: Enumeration
├── Parameter discovery
├── Hidden endpoint discovery
└── User enumeration

Phase 4: Vulnerability Scanning
├── Automated scanners (sqlmap, nuclei)
├── Manual payload testing
└── Business logic testing

Phase 5: Exploitation
├── PoC development
├── Impact demonstration
└── Data extraction proof

Phase 6: Reporting
├── Vulnerability documentation
├── Reproduction steps
└── Remediation guidance
```

## Response Analysis Patterns

| Response Pattern | Potential Vulnerability |
|------------------|------------------------|
| 500 error on special chars | SQL/Command injection |
| Different response length | Boolean-based injection |
| Delayed response | Time-based injection |
| Error message exposure | Information disclosure |
| Reflected input | XSS potential |
| Path in error | Path traversal |
