# Cache Implementation Project

## Overview

This document outlines the implementation of a shared cache layer for Strix's multi-agent system to enable real-time context synchronization, shared mutable state, and improved agent coordination.

## Current State

### How Agents Share Data Today
- **Context inheritance**: One-time copy from parent to child at agent creation
- **Message passing**: Serial `send_message_to_agent()` for communication
- **Completion reports**: XML reports via `agent_finish()` when child completes
- **Shared filesystem**: All agents read/write `/workspace` directory
- **Shared proxy**: Caido proxy history visible to all agents

### Limitations
- No real-time state synchronization between agents
- Parent doesn't see child's discoveries until completion
- No shared variable space for live collaboration
- Agents can duplicate work without knowing what others found
- No centralized findings registry during scan

---

## Proposed Architecture

### Option A: Redis (Recommended for Production)

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Network                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
│  │  Root    │  │  Recon   │  │  Testing │  │  Validation │ │
│  │  Agent   │  │  Agent   │  │  Agent   │  │  Agent      │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬──────┘ │
│       │             │             │               │         │
│       └─────────────┴──────┬──────┴───────────────┘         │
│                            │                                │
│                     ┌──────▼──────┐                         │
│                     │    Redis    │                         │
│                     │   Cache     │                         │
│                     └─────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

**Pros:**
- Production-ready, battle-tested
- Pub/sub for real-time agent notifications
- TTL support for automatic cleanup
- Persistence options if needed
- Excellent Python support (redis-py, aioredis)

**Cons:**
- Additional service to manage
- Overkill for single-machine deployments
- Network overhead (minimal)

### Option B: SQLite with WAL Mode

```python
# Lightweight, no additional services
# Good for single-machine, moderate concurrency

import sqlite3
conn = sqlite3.connect('file:strix_cache?mode=memory&cache=shared', uri=True)
conn.execute('PRAGMA journal_mode=WAL')
```

**Pros:**
- Zero additional dependencies (stdlib)
- No separate service
- Works in shared memory mode
- Familiar SQL interface

**Cons:**
- No pub/sub (requires polling)
- Write contention under high concurrency
- Not designed for cache use case

### Option C: In-Memory Dict with File-Backed Sync (MVP)

```python
# Start simple, evolve later
# Uses existing shared /workspace for persistence

class AgentCache:
    def __init__(self, workspace_path="/workspace/.strix_cache"):
        self._local = {}
        self._cache_file = workspace_path
        self._lock = threading.Lock()

    def set(self, key: str, value: Any, namespace: str = "global") -> None:
        ...

    def get(self, key: str, namespace: str = "global") -> Any:
        ...

    def publish(self, channel: str, message: dict) -> None:
        # Write to file-based message queue
        ...
```

**Pros:**
- No new dependencies
- Easy to implement
- Uses existing /workspace sharing
- Good enough for MVP

**Cons:**
- File I/O overhead
- No true pub/sub
- Scaling limitations
- Race conditions possible without careful locking

---

## Recommended Phased Approach

### Phase 1: File-Backed Shared State (MVP)

**Goal:** Enable agents to share findings in real-time without waiting for completion.

**Implementation:**
```
/workspace/.strix/
├── cache/
│   ├── findings.json      # Deduplicated findings registry
│   ├── targets.json       # Discovered targets/endpoints
│   └── state.json         # Scan-level state
├── messages/
│   ├── {agent_id}/        # Per-agent message inbox
│   │   └── *.json         # Individual messages
│   └── broadcast/         # Broadcast messages
└── locks/
    └── *.lock             # File-based locking
```

**New Tools:**
```python
@register_tool(sandbox_execution=False)
def cache_set(agent_state: Any, key: str, value: str, namespace: str = "global") -> dict:
    """Store a value in the shared agent cache."""
    ...

@register_tool(sandbox_execution=False)
def cache_get(agent_state: Any, key: str, namespace: str = "global") -> dict:
    """Retrieve a value from the shared agent cache."""
    ...

@register_tool(sandbox_execution=False)
def register_finding(agent_state: Any, finding: dict) -> dict:
    """Register a finding in the shared findings registry (auto-deduplicates)."""
    ...

@register_tool(sandbox_execution=False)
def get_findings(agent_state: Any, severity: str = None, category: str = None) -> dict:
    """Query registered findings from all agents."""
    ...
```

**Effort:** 1-2 days
**Risk:** Low

### Phase 2: Redis Integration (Production)

**Goal:** Replace file-backed cache with Redis for better performance and pub/sub.

**Implementation:**
- Add redis container to docker-compose
- Create `strix/cache/redis_cache.py` adapter
- Add pub/sub for agent notifications
- Implement cache namespacing per scan

**New Capabilities:**
```python
# Real-time notifications
await cache.subscribe("findings", on_new_finding)

# Atomic operations
await cache.increment("stats:endpoints_discovered")

# Automatic expiry
await cache.set("temp:scan_token", token, ttl=3600)
```

**Effort:** 2-3 days
**Risk:** Medium (new dependency)

### Phase 3: Advanced Features

**Goal:** Sophisticated multi-agent coordination.

**Features:**
- Distributed locking for exclusive access
- Agent presence/heartbeat tracking
- Scan-level metrics aggregation
- Finding deduplication with similarity scoring
- Dependency graph for agent task ordering

---

## Data Structures

### Shared Findings Registry

```json
{
  "findings": {
    "finding_abc123": {
      "id": "finding_abc123",
      "title": "SQL Injection in login endpoint",
      "severity": "critical",
      "category": "injection",
      "target": "/api/login",
      "discovered_by": "agent_sqli_001",
      "discovered_at": "2024-01-15T10:30:00Z",
      "validated": false,
      "validated_by": null,
      "poc_available": true,
      "hash": "sha256:...",  // For deduplication
      "related_findings": ["finding_def456"]
    }
  },
  "index": {
    "by_severity": {
      "critical": ["finding_abc123"],
      "high": [],
      "medium": [],
      "low": [],
      "info": []
    },
    "by_target": {
      "/api/login": ["finding_abc123"]
    },
    "by_agent": {
      "agent_sqli_001": ["finding_abc123"]
    }
  }
}
```

### Agent State Registry

```json
{
  "agents": {
    "agent_root_001": {
      "id": "agent_root_001",
      "name": "Root Coordinator",
      "role": "root",
      "status": "running",
      "task": "Coordinate Proxmox security assessment",
      "started_at": "2024-01-15T10:00:00Z",
      "last_heartbeat": "2024-01-15T10:35:00Z",
      "children": ["agent_recon_001", "agent_recon_002"],
      "findings_count": 0,
      "current_phase": "reconnaissance"
    }
  },
  "hierarchy": {
    "agent_root_001": {
      "agent_recon_001": {
        "agent_sqli_001": {},
        "agent_xss_001": {}
      },
      "agent_recon_002": {}
    }
  }
}
```

### Target/Endpoint Registry

```json
{
  "targets": {
    "https://10.0.101.2:8006": {
      "type": "infrastructure",
      "service": "proxmox-ve",
      "discovered_by": "agent_recon_001",
      "endpoints": [
        {
          "path": "/api2/json/access/ticket",
          "method": "POST",
          "params": ["username", "password", "realm"],
          "auth_required": false,
          "tested_by": []
        }
      ],
      "technologies": ["Proxmox VE 8.x", "pveproxy"],
      "open_ports": [22, 8006, 3128]
    }
  }
}
```

---

## Integration Points

### 1. Agent Creation
```python
# In agents_graph_actions.py create_agent()
async def create_agent(...):
    ...
    # Initialize agent's cache namespace
    cache = get_scan_cache(scan_id)
    cache.register_agent(state.agent_id, {
        "name": name,
        "role": agent_role,
        "task": task,
        "parent": parent_id
    })
```

### 2. Finding Discovery
```python
# In vulnerability testing agents
# Instead of just sending message to parent:
cache.register_finding({
    "title": "SQL Injection found",
    "severity": "critical",
    ...
})
# All agents can now query this immediately
```

### 3. Deduplication
```python
# Before reporting a finding
existing = cache.find_similar_finding(new_finding)
if existing:
    # Link as related, don't duplicate
    cache.link_findings(existing["id"], new_finding["id"])
else:
    cache.register_finding(new_finding)
```

### 4. Real-Time Coordination (Phase 2+)
```python
# Agent subscribes to relevant channels
await cache.subscribe("findings:critical", handle_critical_finding)
await cache.subscribe(f"agent:{agent_id}:messages", handle_message)

# Coordinator can broadcast
await cache.publish("broadcast", {"type": "pause", "reason": "user requested"})
```

---

## Migration Path

### From Current System
1. **No breaking changes** - Cache is additive
2. Existing message passing continues to work
3. Cache provides optional enhancement
4. Gradual adoption by updating prompt modules

### Deprecation Timeline
- Phase 1: Both systems coexist
- Phase 2: Prefer cache for findings, messages for commands
- Phase 3: Consider deprecating direct message passing for data sharing

---

## Performance Considerations

### File-Based (Phase 1)
- Read: ~1-5ms (SSD)
- Write: ~5-20ms (with fsync)
- Acceptable for 10-50 agents
- Bottleneck: Write contention on findings.json

### Redis (Phase 2)
- Read: ~0.1-0.5ms
- Write: ~0.1-0.5ms
- Supports 1000+ agents
- Bottleneck: Network (negligible on localhost)

### Recommendations
- Phase 1: Use write-behind caching (batch writes)
- Phase 2: Use Redis pipelining for bulk operations
- All phases: Namespace by scan_id to isolate concurrent scans

---

## Security Considerations

1. **Cache Poisoning**: Validate all cache entries before use
2. **Information Leakage**: Clear cache between scans
3. **Denial of Service**: Implement size limits per namespace
4. **Access Control**: In Phase 2+, consider per-agent permissions

---

## Open Questions

1. **Persistence**: Should findings survive container restart?
   - Current: No (container-scoped)
   - Consider: Optional persistence for long scans

2. **Multi-Scan Isolation**: How to handle concurrent scans?
   - Proposal: Namespace everything by `scan_id`

3. **Cache Invalidation**: When should cached data expire?
   - Proposal: TTL based on data type (findings: never, temp state: 1 hour)

4. **Conflict Resolution**: What if two agents find the same vuln?
   - Proposal: First-write-wins with similarity linking

---

## Next Steps

1. [ ] Review and approve Phase 1 design
2. [ ] Implement file-backed cache in `strix/cache/`
3. [ ] Add cache tools to tool registry
4. [ ] Update root_agent.jinja to document cache usage
5. [ ] Test with multi-agent Proxmox scan
6. [ ] Evaluate need for Phase 2 based on performance

---

## References

- [Redis Pub/Sub](https://redis.io/docs/manual/pubsub/)
- [SQLite Shared Cache](https://www.sqlite.org/sharedcache.html)
- [Python threading locks](https://docs.python.org/3/library/threading.html#lock-objects)
- [File locking in Python](https://docs.python.org/3/library/fcntl.html#fcntl.flock)
