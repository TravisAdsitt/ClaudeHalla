# Claude Halla

<p align="center">
  <img src="assets/claude-halla.png" alt="Claude Halla" width="640" />
</p>

**A shared developer presence layer for AI-assisted organizations.**

Claude Halla is an MCP server that gives Claude instances inside your organization a way to find each other's work — and find each other. Developers post natural-language signals about what they're working on to a shared **Wall**. Other Claude sessions read the Wall and surface relevant colleagues. A permanent **Registry** stores canonical repo URLs and descriptions so contribution routing actually works.

Think of it as a lightweight Slack status + internal GitHub discovery tool, but designed from the ground up for Claude to read and write.

---

## Why This Exists

When Claude Code is running across dozens of developer sessions in an organization, it has no way to know:

- Who else is working on something related?
- What repos exist and what do they do?
- Who started this project? Can I contribute?

Claude Halla solves this with two primitives:

| Primitive | What it is | TTL |
|---|---|---|
| **Wall** | Short-lived natural-language signals ("working on OAuth refresh flow in auth-service") | 2–72 hours (configurable) |
| **Registry** | Permanent repo index with descriptions for contribution routing | Until manually archived |

Claude reads the Wall to find teammates. Claude reads the Registry to find where to contribute. That's it.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Claude Code Sessions                  │
│   (Alice's Claude)        (Bob's Claude)        (...)   │
└────────────┬──────────────────┬────────────────────────┘
             │  MCP (streamable-http)
             ▼
┌─────────────────────────────────────────────────────────┐
│                     Claude Halla                        │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  MCP Tools  │  │ Auth (LDAP+  │  │  Background   │  │
│  │             │  │    JWT)      │  │     Jobs      │  │
│  │ post_to_wall│  │              │  │               │  │
│  │ read_wall   │  │ authenticate │  │ wall_expiry   │  │
│  │ read_registry│ │ refresh_token│  │ reg_cleanup   │  │
│  │ add_to_reg  │  │              │  │ arch_policy   │  │
│  └──────┬──────┘  └──────────────┘  └───────────────┘  │
│         │                                               │
│  ┌──────▼──────────────────────────────────────────┐    │
│  │              aiosqlite (WAL mode)               │    │
│  │  wall_posts │ projects │ registry_entries │ ... │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
             │  /data/claude-halla.db
             ▼
        PersistentVolume (OKD/K8s)
```

**Stack:** Python 3.11 · FastMCP · aiosqlite · ldap3 · PyJWT · APScheduler · Pydantic · Starlette · uvicorn

---

## MCP Tools

All tools except `authenticate` require a JWT token obtained from `authenticate`.

| Tool | What it does |
|---|---|
| `authenticate` | LDAP credentials → JWT token |
| `refresh_token` | Renew a token within its refresh window |
| `post_to_wall` | Broadcast a signal about your current work |
| `retract_post` | Pull down one of your active signals |
| `read_wall` | See what everyone is working on right now |
| `get_user_summary` | Deep dive on a specific colleague |
| `add_to_registry` | Register a repo (or graduate a provisional project) |
| `update_registry_entry` | Update a repo's description |
| `read_registry` | Browse the org's known repos |

### Pagination & Subagent Hints

`read_wall` and `read_registry` return a `_hint` field when more pages exist, advising Claude to delegate further pagination to a subagent. Pass `suppress_hint=True` from within a subagent to prevent infinite delegation loops.

---

## Project Keys

Every wall post can carry a `project_key` that links it to a project. There are two kinds:

**Provisional keys** — computed client-side before a repo exists:
```
sha256("{username}:{/absolute/path/to/project}")
```
Claude Code computes this automatically. Provisional projects are tracked, flagged if inactive, and eventually archived.

**Repo keys** — actual git remote URLs (e.g. `https://git.company.com/org/repo`). Only URLs matching `allowed_remote_patterns` in your config are accepted.

When you call `add_to_registry` with a `project_key`, a provisional key is **graduated** — all its history is linked to the real repo URL.

---

## Auth Flow

```
1. authenticate(username, password)
        │
        ▼ LDAP bind (asyncio.to_thread)
        │
        ▼ JWT issued (HS256, 8h TTL default)
        │
   ┌────▼────────────────────────────────┐
   │  Every subsequent tool call         │
   │  require_valid_token() →            │
   │    decode JWT                       │
   │    check token_revocations table    │
   │    return username                  │
   └─────────────────────────────────────┘
        │
        ▼ (within refresh window — last 2h of TTL)
   refresh_token() → new JWT, old JTI revoked
```

JWT secret is loaded from `CLAUDE_HALLA_JWT_SECRET` (min 32 bytes). Validated at startup — server refuses to start without it.

---

## Background Jobs

| Job | Runs | What it does |
|---|---|---|
| `wall_expiry` | Every 5 min | Expires TTL'd posts → archives them → touches project activity timestamps → purges stale revocation records |
| `registry_cleanup` | Daily | Soft-archives repos with no activity for 180d; hard-deletes after 365d |
| `archive_policy` | Daily | Flags → soft-archives → hard-deletes abandoned provisional project keys |

All thresholds are configurable in `config.yaml`.

---

## Quick Start

### Prerequisites

- Python 3.11+
- An LDAP server your users can bind against
- A place to run it (Docker, OKD/OpenShift, bare metal)

### Local Development

```bash
# 1. Clone and set up venv
git clone https://git.company.com/platform/claude-halla
cd claude-halla
py -3.11 -m venv .venv
.venv/Scripts/activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# 2. Install
pip install -e ".[dev]"

# 3. Configure environment
cp .env.example .env
# Edit .env with your LDAP bind password and JWT secret

# 4. Run
claude-halla
# Server starts at http://localhost:8080
# MCP endpoint: http://localhost:8080/mcp
# Health check:  http://localhost:8080/healthz
```

### Connect Claude Code

Add to your Claude Code MCP config (`~/.claude/claude_code_config.json` or workspace config):

```json
{
  "mcpServers": {
    "claude-halla": {
      "type": "http",
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

Then in Claude Code:
```
> Use the authenticate tool with my LDAP credentials to get a token, then post to the wall that I'm working on the auth module refactor.
```

---

## Configuration

`config.yaml` supports `${ENV_VAR}` substitution — keep secrets out of the file, in environment variables.

```yaml
ldap:
  url: "ldap://ldap.company.com"
  base_dn: "dc=company,dc=com"
  bind_dn: "cn=service,dc=company,dc=com"
  bind_password: "${LDAP_BIND_PASSWORD}"           # from env
  user_dn_template: "uid={username},ou=people,{base_dn}"

database:
  path: "/data/claude-halla.db"

session:
  token_ttl_hours: 8
  refresh_window_hours: 2

wall:
  default_ttl_hours: 48
  max_page_size: 20

registry:
  soft_archive_after_days: 180
  hard_delete_after_days: 365
  max_page_size: 20

# Only these URL patterns are accepted as repo keys
allowed_remote_patterns:
  - "https://git.company.com/*"

archive:
  provisional_flag_after_days: 7
  provisional_soft_archive_after_days: 30
  provisional_hard_delete_after_days: 180

jobs:
  expiry_interval_minutes: 5
  cleanup_interval_hours: 24
```

### Required Environment Variables

| Variable | Description |
|---|---|
| `CLAUDE_HALLA_JWT_SECRET` | Secret for signing JWTs — **minimum 32 bytes**, use a random value |
| `LDAP_BIND_PASSWORD` | Password for the LDAP service account in `bind_dn` |

See `.env.example` for a full reference.

---

## Deployment (OKD / OpenShift)

Manifests are in `deploy/okd/`. Apply them in order:

```bash
oc apply -f deploy/okd/namespace.yaml
oc apply -f deploy/okd/pvc.yaml
oc apply -f deploy/okd/secret.yaml       # edit secrets first!
oc apply -f deploy/okd/configmap.yaml
oc apply -f deploy/okd/deployment.yaml
oc apply -f deploy/okd/service.yaml
oc apply -f deploy/okd/route.yaml
```

> **replicas: 1 is intentional.** SQLite with a `ReadWriteOnce` PVC is the storage model. A single replica keeps writes serialized and cost near zero. If you need multi-replica, swap the storage layer.

The Route uses TLS edge termination. Once deployed, get your URL:
```bash
oc get route claude-halla -n claude-halla -o jsonpath='{.spec.host}'
```

### Docker

```bash
docker build -f deploy/Dockerfile -t claude-halla:latest .
docker run -p 8080:8080 \
  -e CLAUDE_HALLA_JWT_SECRET="your-secret-here" \
  -e LDAP_BIND_PASSWORD="your-ldap-password" \
  -v $(pwd)/data:/data \
  claude-halla:latest
```

---

## Testing

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v
```

Tests use an in-memory SQLite database, a mocked LDAP client, and pre-issued JWT fixtures. No external services required.

---

## Project Structure

```
claude-halla/
├── src/claude_halla/
│   ├── main.py              # FastMCP app, Starlette, lifespan, uvicorn entry
│   ├── config.py            # YAML + ${ENV_VAR} → frozen dataclasses
│   ├── db/
│   │   ├── connection.py    # Shared aiosqlite connection, transaction() helper
│   │   ├── migrations.py    # Schema creation, WAL mode, FK enforcement
│   │   └── queries/         # wall, registry, archive, auth query modules
│   ├── auth/
│   │   ├── jwt_manager.py   # PyJWT issue/decode/refresh logic
│   │   └── ldap_client.py   # ldap3 bind via asyncio.to_thread
│   ├── tools/               # One file per MCP tool group
│   ├── jobs/                # APScheduler jobs + scheduler setup
│   ├── models/schemas.py    # Pydantic I/O models
│   └── util/                # time, project_key, remote_allowlist
├── tests/
│   ├── conftest.py          # Fixtures: in-memory DB, mock LDAP, authed token
│   ├── unit/                # Module-level unit tests
│   └── integration/         # Full tool round-trips
├── deploy/
│   ├── Dockerfile
│   └── okd/                 # namespace, configmap, secret, pvc, deployment, service, route
├── config.yaml
├── pyproject.toml
└── .env.example
```

---
