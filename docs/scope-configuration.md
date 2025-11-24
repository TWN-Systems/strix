# Scope Configuration Reference

This reference covers how to configure and manage testing scope in Strix, including scope rules, request filtering, and sitemap management.

## Table of Contents

- [Overview](#overview)
- [Scope Rules](#scope-rules)
  - [Creating Scopes](#creating-scopes)
  - [Managing Scopes](#managing-scopes)
  - [Allowlist and Denylist](#allowlist-and-denylist)
  - [Glob Pattern Syntax](#glob-pattern-syntax)
- [HTTPQL Filtering](#httpql-filtering)
  - [Filter Syntax](#filter-syntax)
  - [Field Reference](#field-reference)
  - [Filter Examples](#filter-examples)
- [Sitemap Management](#sitemap-management)
- [Multi-Target Scoping](#multi-target-scoping)
- [Best Practices](#best-practices)

---

## Overview

Strix uses Caido as its underlying HTTP proxy, providing powerful scope management and request filtering capabilities. Scope configuration helps you:

- Define test boundaries (which hosts/paths to test)
- Exclude sensitive areas from testing
- Filter and organize captured traffic
- Focus analysis on relevant requests

---

## Scope Rules

Scope rules define what URLs and domains are in-scope for testing. The agent uses the `scope_rules` tool to manage scopes.

### Creating Scopes

Create a new scope with allowlist and denylist patterns:

```xml
<function=scope_rules>
<parameter=action>create</parameter>
<parameter=scope_name>API Testing</parameter>
<parameter=allowlist>["api.example.com", "*.api.example.com"]</parameter>
<parameter=denylist>["*.gif", "*.jpg", "*.png", "*.css", "*.js"]</parameter>
</function>
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | `create` for new scopes |
| `scope_name` | string | Yes | Human-readable name for the scope |
| `allowlist` | list | No | Domain/path patterns to include |
| `denylist` | list | No | Patterns to exclude |

**Response:**

```json
{
  "scope": {
    "id": "scope_abc123",
    "name": "API Testing",
    "allowlist": ["api.example.com", "*.api.example.com"],
    "denylist": ["*.gif", "*.jpg", "*.png", "*.css", "*.js"]
  },
  "message": "Scope created successfully"
}
```

### Managing Scopes

#### List All Scopes

```xml
<function=scope_rules>
<parameter=action>list</parameter>
</function>
```

**Response:**

```json
{
  "scopes": [
    {"id": "scope_abc123", "name": "API Testing", ...},
    {"id": "scope_def456", "name": "Admin Panel", ...}
  ],
  "count": 2
}
```

#### Get Specific Scope

```xml
<function=scope_rules>
<parameter=action>get</parameter>
<parameter=scope_id>scope_abc123</parameter>
</function>
```

#### Update Scope

```xml
<function=scope_rules>
<parameter=action>update</parameter>
<parameter=scope_id>scope_abc123</parameter>
<parameter=scope_name>API Testing v2</parameter>
<parameter=allowlist>["api.example.com", "api-v2.example.com"]</parameter>
<parameter=denylist>["*.gif", "*.jpg", "*.png"]</parameter>
</function>
```

#### Delete Scope

```xml
<function=scope_rules>
<parameter=action>delete</parameter>
<parameter=scope_id>scope_abc123</parameter>
</function>
```

**Response:**

```json
{
  "message": "Scope deleted successfully",
  "deletedId": "scope_abc123"
}
```

### Allowlist and Denylist

**Allowlist:**
- Defines which domains/paths ARE included in scope
- Empty allowlist = allow ALL domains
- Requests must match at least one allowlist pattern

**Denylist:**
- Defines which patterns are EXCLUDED from scope
- Denylist overrides allowlist (exclusions take priority)
- Use for static assets, third-party resources, sensitive areas

**Common Denylist Patterns:**

```json
[
  "*.gif", "*.jpg", "*.jpeg", "*.png", "*.svg", "*.ico",
  "*.css", "*.js", "*.woff", "*.woff2", "*.ttf", "*.eot",
  "*.map", "*.webp", "*.mp4", "*.mp3"
]
```

### Glob Pattern Syntax

Scope rules use glob patterns for matching:

| Pattern | Meaning | Example |
|---------|---------|---------|
| `*` | Match any characters | `*.example.com` matches `api.example.com` |
| `?` | Match single character | `api?.com` matches `api1.com`, `api2.com` |
| `[abc]` | Match one of characters | `[abc].example.com` matches `a.example.com` |
| `[a-z]` | Match character range | `[a-z].example.com` matches `a.example.com` |
| `[^abc]` | Match none of characters | `[^0-9].example.com` excludes numeric subdomains |
| `**` | Match any path depth | `**/api/**` matches any path containing `/api/` |

**Examples:**

```json
{
  "allowlist": [
    "example.com",           // Exact match
    "*.example.com",         // All subdomains
    "api.*.example.com",     // api.staging.example.com, api.prod.example.com
    "example.com/api/*"      // All paths under /api/
  ],
  "denylist": [
    "*.example.com/admin/*", // Exclude admin paths
    "cdn.example.com",       // Exclude CDN
    "*.js",                  // Exclude JavaScript files
    "*logout*"               // Exclude logout-related paths
  ]
}
```

---

## HTTPQL Filtering

HTTPQL is Caido's query language for filtering HTTP requests. Use it to find specific requests in proxy history.

### Filter Syntax

Filters follow the pattern: `field.operator:value`

**Combining Filters:**

- `AND` - Both conditions must match
- `OR` - Either condition matches
- Parentheses `()` for grouping

```
(req.method.eq:"POST" OR req.method.eq:"PUT") AND req.path.cont:"/api/"
```

### Field Reference

#### Request Fields

| Field | Type | Description |
|-------|------|-------------|
| `req.method` | text | HTTP method (GET, POST, etc.) |
| `req.host` | text | Target hostname |
| `req.port` | integer | Target port |
| `req.path` | text | URL path |
| `req.query` | text | Query string |
| `req.ext` | text | File extension |
| `req.raw` | bytes | Raw request data |
| `req.created_at` | date | Request timestamp |

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `resp.code` | integer | HTTP status code |
| `resp.roundtrip` | integer | Response time (ms) |
| `resp.raw` | bytes | Raw response data |

#### Special Fields

| Field | Type | Description |
|-------|------|-------------|
| `source` | text | Request source (e.g., `intercept`) |
| `preset` | text | Saved filter preset name |
| `id` | integer | Request ID |

### Operators by Type

#### Integer Fields (`port`, `code`, `roundtrip`, `id`)

| Operator | Meaning | Example |
|----------|---------|---------|
| `eq` | Equals | `resp.code.eq:200` |
| `ne` | Not equals | `resp.code.ne:404` |
| `gt` | Greater than | `resp.code.gt:399` |
| `gte` | Greater than or equal | `resp.code.gte:400` |
| `lt` | Less than | `resp.code.lt:500` |
| `lte` | Less than or equal | `resp.code.lte:299` |

#### Text Fields (`method`, `host`, `path`, `query`, `ext`)

| Operator | Meaning | Example |
|----------|---------|---------|
| `eq` | Exact match | `req.method.eq:"POST"` |
| `cont` | Contains | `req.path.cont:"/api/"` |
| `regex` | Regex match | `req.host.regex:".*\\.example\\.com"` |

#### Date Fields (`created_at`)

| Operator | Meaning | Example |
|----------|---------|---------|
| `gt` | After date | `req.created_at.gt:"2024-01-01T00:00:00Z"` |
| `lt` | Before date | `req.created_at.lt:"2024-12-31T23:59:59Z"` |

### Filter Examples

#### By HTTP Method

```
# All POST requests
req.method.eq:"POST"

# POST or PUT requests
req.method.eq:"POST" OR req.method.eq:"PUT"

# Non-GET requests
req.method.ne:"GET"
```

#### By Response Code

```
# Successful responses
resp.code.gte:200 AND resp.code.lt:300

# Client errors (4xx)
resp.code.gte:400 AND resp.code.lt:500

# Server errors (5xx)
resp.code.gte:500

# Interesting codes for testing
resp.code.eq:401 OR resp.code.eq:403 OR resp.code.eq:500
```

#### By Path

```
# API endpoints
req.path.cont:"/api/"

# Admin paths
req.path.cont:"/admin"

# User-related endpoints
req.path.regex:"/users?/[0-9]+"

# Authentication endpoints
req.path.regex:"/(login|logout|auth|oauth)"
```

#### By Host

```
# Specific subdomain
req.host.eq:"api.example.com"

# All subdomains
req.host.regex:".*\\.example\\.com"

# Multiple hosts
req.host.eq:"api.example.com" OR req.host.eq:"app.example.com"
```

#### Combined Filters

```
# POST to API with auth errors
req.method.eq:"POST" AND req.path.cont:"/api/" AND (resp.code.eq:401 OR resp.code.eq:403)

# Slow API responses
req.path.cont:"/api/" AND resp.roundtrip.gt:1000

# Recent requests to admin
req.path.cont:"/admin" AND req.created_at.gt:"2024-01-01T00:00:00Z"

# JSON API responses with errors
req.path.cont:"/api/" AND resp.code.gte:400 AND req.ext.ne:"js"
```

#### Using Filters with Scope

```xml
<function=list_requests>
<parameter=httpql_filter>req.method.eq:"POST" AND req.path.cont:"/api/"</parameter>
<parameter=scope_id>scope_abc123</parameter>
<parameter=sort_by>response_time</parameter>
<parameter=sort_order>desc</parameter>
</function>
```

---

## Sitemap Management

The sitemap provides a hierarchical view of discovered URLs from proxy traffic.

### Viewing the Sitemap

#### List Root Domains

```xml
<function=list_sitemap>
</function>
```

**Response:**

```json
{
  "entries": [
    {
      "id": "entry_1",
      "kind": "DOMAIN",
      "label": "example.com",
      "hasDescendants": true
    },
    {
      "id": "entry_2",
      "kind": "DOMAIN",
      "label": "api.example.com",
      "hasDescendants": true
    }
  ],
  "page": 1,
  "total_pages": 1,
  "total_count": 2,
  "has_more": false
}
```

#### Expand a Directory

```xml
<function=list_sitemap>
<parameter=parent_id>entry_1</parameter>
<parameter=depth>DIRECT</parameter>
</function>
```

#### Get Full Tree

```xml
<function=list_sitemap>
<parameter=parent_id>entry_1</parameter>
<parameter=depth>ALL</parameter>
</function>
```

#### Filter by Scope

```xml
<function=list_sitemap>
<parameter=scope_id>scope_abc123</parameter>
</function>
```

### Sitemap Entry Types

| Kind | Description |
|------|-------------|
| `DOMAIN` | Root domain entry (e.g., `example.com`) |
| `DIRECTORY` | Path directory (e.g., `/api/`, `/admin/`) |
| `REQUEST` | Individual endpoint |
| `REQUEST_BODY` | POST/PUT body variations |
| `REQUEST_QUERY` | GET parameter variations |

### Viewing Entry Details

```xml
<function=view_sitemap_entry>
<parameter=entry_id>entry_123</parameter>
</function>
```

**Response includes:**
- Entry metadata
- All related HTTP requests
- Request methods, paths, response codes
- Timing information

---

## Multi-Target Scoping

When testing multiple targets, Strix organizes them into separate workspace subdirectories:

```bash
# Multiple targets
strix --target https://api.example.com --target https://app.example.com

# Mixed target types (white-box testing)
strix --target https://github.com/org/repo --target https://staging.example.com
```

### Workspace Organization

```
/workspace/
├── target_1/           # First target (e.g., cloned repo)
│   └── ...
├── target_2/           # Second target workspace
│   └── ...
└── shared/             # Shared resources
```

### Scope Strategy for Multi-Target

1. **Create separate scopes** for each target domain
2. **Use scope filtering** when analyzing traffic
3. **Cross-correlate findings** between targets

Example workflow:

```xml
<!-- Create scope for API -->
<function=scope_rules>
<parameter=action>create</parameter>
<parameter=scope_name>API Target</parameter>
<parameter=allowlist>["api.example.com"]</parameter>
</function>

<!-- Create scope for App -->
<function=scope_rules>
<parameter=action>create</parameter>
<parameter=scope_name>App Target</parameter>
<parameter=allowlist>["app.example.com"]</parameter>
</function>

<!-- List requests for specific target -->
<function=list_requests>
<parameter=scope_id>api_scope_id</parameter>
</function>
```

---

## Best Practices

### 1. Define Scope Early

Set up scope rules at the start of testing to:
- Focus on authorized targets
- Exclude third-party domains
- Filter out static assets

```xml
<function=scope_rules>
<parameter=action>create</parameter>
<parameter=scope_name>Primary Testing Scope</parameter>
<parameter=allowlist>["*.example.com"]</parameter>
<parameter=denylist>[
  "cdn.example.com",
  "analytics.example.com",
  "*.gif", "*.jpg", "*.png", "*.css", "*.js", "*.woff*"
]</parameter>
</function>
```

### 2. Use Meaningful Scope Names

```
Good:
- "API v2 Testing"
- "Admin Panel Assessment"
- "Payment Flow Scope"

Bad:
- "test"
- "scope1"
- "asdf"
```

### 3. Leverage HTTPQL for Analysis

```
# Find potential vulnerabilities
resp.code.eq:500                          # Server errors
resp.code.eq:403                          # Authorization issues
req.path.regex:"/users?/[0-9]+"           # IDOR candidates
req.method.eq:"POST" AND resp.code.eq:200 # Successful mutations
```

### 4. Organize by Test Phase

```
Phase 1: Discovery
- Broad scope, minimal denylist
- Capture all traffic

Phase 2: Analysis
- Filter by endpoint type
- Group by functionality

Phase 3: Exploitation
- Narrow scope to vulnerable areas
- Focus on specific endpoints
```

### 5. Exclude Sensitive Areas

Always exclude:
- Logout/session destruction endpoints
- Data deletion endpoints
- Payment processing (unless authorized)
- Admin backup/restore functions

```json
{
  "denylist": [
    "*logout*",
    "*delete*",
    "*/admin/backup*",
    "*/payment/*"
  ]
}
```

### 6. Use Sitemap for Attack Surface

```
1. Start with list_sitemap() to see domains
2. Expand interesting directories
3. Check hasDescendants for depth
4. Use view_sitemap_entry() for details
5. Prioritize endpoints with multiple request variations
```

---

## Related Documentation

- [Prompting Guide](./prompting-guide.md) - Customizing agent behavior
- [Caido Documentation](https://docs.caido.io/) - Underlying proxy documentation
- [HTTPQL Reference](https://docs.caido.io/reference/httpql) - Full query language reference
