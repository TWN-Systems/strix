# Strix Prompting Guide

This guide covers how to customize and direct Strix agents through user instructions and prompt modules.

## Table of Contents

- [User Instructions](#user-instructions)
  - [Inline Instructions](#inline-instructions)
  - [File-Based Instructions](#file-based-instructions)
  - [Instruction Examples](#instruction-examples)
- [Prompt Modules](#prompt-modules)
  - [Available Modules](#available-modules)
  - [Module Structure](#module-structure)
  - [How Modules Are Loaded](#how-modules-are-loaded)
- [Agent Specialization](#agent-specialization)
- [Best Practices](#best-practices)

---

## User Instructions

User instructions allow you to provide custom guidance to the Strix agent, focusing its testing on specific areas, providing credentials, or constraining its behavior.

### Inline Instructions

Pass instructions directly via the `--instruction` flag:

```bash
# Focus on specific vulnerability types
strix --target https://example.com --instruction "Focus on IDOR and XSS vulnerabilities"

# Provide test credentials
strix --target https://app.example.com --instruction "Use credentials admin:password123 for authenticated testing"

# Target specific endpoints
strix --target https://api.example.com --instruction "Focus on the /api/users endpoint for authorization issues"

# Constrain testing behavior
strix --target https://example.com --instruction "Avoid denial of service attacks and rate-limit testing"
```

### File-Based Instructions

For complex or detailed instructions, use a file (supports `.txt` or `.md`):

```bash
# From a text file
strix --target https://example.com --instruction ./instructions.txt

# From a markdown file
strix --target https://app.com --instruction /path/to/detailed_instructions.md
```

**Example instruction file (`instructions.md`):**

```markdown
# Testing Instructions

## Priority Vulnerabilities
- Focus on authentication bypass vulnerabilities
- Test for JWT token manipulation
- Check for IDOR in user profile endpoints

## Test Credentials
- Admin user: admin@example.com / AdminPass123!
- Regular user: user@example.com / UserPass456!

## Scope Constraints
- Do not test the /admin/backup endpoint
- Avoid any actions that could modify production data
- Focus on read operations for initial assessment

## Areas of Interest
- The password reset flow has been recently updated
- The /api/v2/ endpoints are new and untested
- Check multi-tenancy isolation between organizations
```

### Instruction Examples

| Goal | Instruction |
|------|-------------|
| Focus on specific vulns | `"Focus on SQL injection and authentication bypass"` |
| Authenticated testing | `"Login with username 'testuser' and password 'testpass123'"` |
| API testing | `"Test REST API endpoints, focusing on authorization checks"` |
| Business logic | `"Look for business logic flaws in the checkout process"` |
| Compliance focus | `"Identify OWASP Top 10 vulnerabilities for compliance audit"` |
| Specific feature | `"Test the file upload functionality for arbitrary file upload vulnerabilities"` |
| Technology stack | `"The application uses FastAPI backend with PostgreSQL database"` |
| Rate limiting | `"Be careful with rate limits - max 10 requests per second"` |

### How Instructions Flow Through the System

1. CLI parses `--instruction` flag (inline or reads from file)
2. Instructions passed to root agent via `scan_config["user_instructions"]`
3. Root agent receives instructions in its task description
4. Root agent can reference instructions when creating specialized sub-agents
5. Sub-agents inherit context through their task descriptions

---

## Prompt Modules

Prompt modules are specialized knowledge packages that give agents deep expertise in specific vulnerability types, frameworks, technologies, or protocols.

### Available Modules

Modules are organized by category:

#### Vulnerabilities

| Module | Description |
|--------|-------------|
| `sql_injection` | SQL injection testing across MySQL, PostgreSQL, MSSQL, Oracle |
| `xss` | Cross-site scripting detection and validation |
| `idor` | Insecure Direct Object Reference testing |
| `authentication_jwt` | JWT token security and authentication bypass |
| `business_logic` | Business logic vulnerability discovery |
| `race_conditions` | Race condition and TOCTOU vulnerability testing |
| `ssrf` | Server-Side Request Forgery detection |
| `xxe` | XML External Entity injection |
| `csrf` | Cross-Site Request Forgery testing |
| `rce` | Remote Code Execution vulnerability discovery |
| `path_traversal_lfi_rfi` | Path traversal and file inclusion vulnerabilities |
| `mass_assignment` | Mass assignment and parameter binding flaws |
| `insecure_file_uploads` | File upload security testing |
| `broken_function_level_authorization` | Authorization and access control testing |

#### Frameworks

| Module | Description |
|--------|-------------|
| `fastapi` | FastAPI-specific security testing patterns |
| `nextjs` | Next.js application security testing |

#### Technologies

| Module | Description |
|--------|-------------|
| `firebase_firestore` | Firebase/Firestore security rules and testing |
| `supabase` | Supabase security configuration and testing |

#### Protocols

| Module | Description |
|--------|-------------|
| `graphql` | GraphQL API security testing |

#### Coordination

| Module | Description |
|--------|-------------|
| `root_agent` | Loaded by default for the root orchestrating agent |

### Module Structure

Each module is a Jinja2 template (`.jinja`) containing structured knowledge in XML format:

```xml
<vulnerability_guide>
  <title>VULNERABILITY NAME</title>

  <critical>
    Why this vulnerability is important and its potential impact
  </critical>

  <scope>
    What systems, technologies, and contexts to test
  </scope>

  <methodology>
    Step-by-step testing approach:
    1. Identification phase
    2. Confirmation phase
    3. Exploitation phase
    4. Validation phase
  </methodology>

  <injection_surfaces>
    Where to look for injection points and attack vectors
  </injection_surfaces>

  <detection_channels>
    How to confirm exploitation (error-based, time-based, OOB, etc.)
  </detection_channels>

  <validation>
    Requirements for proving a vulnerability is real:
    1. Demonstrate reliable oracle
    2. Extract verifiable data
    3. Provide reproducible requests
  </validation>

  <false_positives>
    Common scenarios that appear vulnerable but aren't
  </false_positives>

  <pro_tips>
    Advanced techniques and expert recommendations
  </pro_tips>
</vulnerability_guide>
```

### How Modules Are Loaded

Modules are loaded dynamically when creating specialized agents:

```python
# The root agent creates a specialized sub-agent
create_agent(
    task="Test all API endpoints for SQL injection vulnerabilities",
    name="SQL Injection Specialist",
    prompt_modules="sql_injection"  # Load SQL injection expertise
)

# Multiple modules can be combined (max 5)
create_agent(
    task="Test authentication system security",
    name="Auth Security Specialist",
    prompt_modules="authentication_jwt,business_logic,idor"
)
```

**Module Loading Process:**

1. `get_available_prompt_modules()` discovers all `.jinja` files in prompt categories
2. Agent specifies modules via `prompt_modules` parameter (comma-separated)
3. `load_prompt_modules()` reads and renders templates
4. Module content injected into agent's system prompt
5. Agent gains specialized knowledge for its task

---

## Agent Specialization

Strix uses a multi-agent architecture where specialized agents handle specific testing tasks.

### Agent Hierarchy

```
Root Agent (coordination/root_agent)
├── Discovery Agent (vulnerability modules)
│   └── Validation Agent (same modules)
│       └── Reporting Agent
├── Discovery Agent (framework modules)
│   └── Validation Agent
│       └── Reporting Agent
└── Fixing Agent (white-box only)
```

### Agent Types and Their Roles

| Agent Type | Purpose | Typical Modules |
|------------|---------|-----------------|
| **Root Agent** | Orchestrates scan, spawns specialists | `root_agent` (auto-loaded) |
| **Discovery Agent** | Finds potential vulnerabilities | 1-3 vulnerability modules |
| **Validation Agent** | Creates PoC exploits | Same as discovery agent |
| **Reporting Agent** | Documents findings | None (uses reporting tools) |
| **Fixing Agent** | Patches code (white-box) | Framework-specific modules |

### Specialization Best Practices

**DO:**
- Give each agent 1-5 focused modules
- Create separate agents for different vulnerability classes
- Use framework modules when the technology is known
- Combine related vulnerability modules (e.g., `authentication_jwt` + `business_logic`)

**DON'T:**
- Load all modules into one agent
- Create agents without any specialized modules
- Mix unrelated vulnerability types in one agent

---

## Best Practices

### Writing Effective Instructions

1. **Be specific about priorities**
   ```
   Good: "Focus on authorization vulnerabilities in the /api/admin/* endpoints"
   Vague: "Test the API"
   ```

2. **Provide context about the application**
   ```
   Good: "This is a multi-tenant SaaS app. Test for tenant isolation issues."
   Missing context: "Test for security issues"
   ```

3. **Include credentials when needed**
   ```
   Good: "Use these test accounts: admin@test.com/Admin123, user@test.com/User456"
   Incomplete: "Test authenticated endpoints"
   ```

4. **Set clear constraints**
   ```
   Good: "Do not test /api/billing endpoints or perform any payment transactions"
   Risky: No constraints specified
   ```

5. **Mention recent changes**
   ```
   Good: "The password reset flow was updated last week - test it thoroughly"
   Less useful: Generic testing request
   ```

### Combining Instructions with Modules

Instructions and modules work together:

- **Instructions** = What to test and how to approach it
- **Modules** = Deep technical knowledge for specific vulnerability types

Example workflow:

```bash
# User provides high-level guidance
strix --target https://api.example.com \
  --instruction "Focus on JWT security. The app uses RS256 tokens with refresh token rotation."
```

The root agent then:
1. Reads the user instructions
2. Creates a specialized agent with `authentication_jwt` module
3. The agent uses both the instructions AND module expertise
4. Results in targeted, knowledgeable testing

### Instruction File Organization

For complex engagements, structure your instruction file:

```markdown
# Penetration Test Instructions

## Scope
- In scope: api.example.com, app.example.com
- Out of scope: admin.example.com, *.internal.example.com

## Credentials
| Role | Username | Password |
|------|----------|----------|
| Admin | admin@test.com | AdminTest123! |
| User | user@test.com | UserTest456! |
| Guest | guest@test.com | GuestTest789! |

## Priority Vulnerabilities
1. Authentication bypass
2. IDOR in user data endpoints
3. SQL injection in search functionality

## Technology Stack
- Backend: FastAPI (Python 3.11)
- Database: PostgreSQL 15
- Auth: JWT with RS256, 15-minute access tokens
- Frontend: Next.js 14

## Known Issues
- Rate limiting is disabled on staging
- Some endpoints return verbose error messages

## Constraints
- Maximum 50 requests per second
- Do not modify or delete any data
- Stop testing if you encounter PII
```

---

## Related Documentation

- [Scope Configuration Reference](./scope-configuration.md) - Configuring test boundaries
- [Prompt Modules README](../strix/prompts/README.md) - Creating custom modules
- [Contributing Guide](../CONTRIBUTING.md) - Adding new prompt modules
