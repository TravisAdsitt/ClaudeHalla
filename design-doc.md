# Claude Halla — Design Document
*A developer discovery and collaboration layer built on MCP, for organizations*

---

## Overview

Claude Halla is an MCP (Model Context Protocol) service for internal organizational use. It enables passive, opt-in discovery between developers working in Claude Code sessions. As a developer works, their session can publish a conversational signal to a shared **Wall**. Other Claude instances read the Wall and surface relevant colleagues — enabling spontaneous introductions between developers working on related problems.

The core bet: as AI-assisted development accelerates code production, the bottleneck shifts from *writing* code to *connecting* people who should be talking, and *routing* contributions to the right repositories rather than duplicating effort.

---

## Disclaimer / Liability

Claude Halla is provided as-is for internal organizational use. It is not a product of Anthropic. Organizations deploying Claude Halla are solely responsible for:
- Compliance with applicable data privacy laws and internal policies
- Access controls and data retention decisions
- Any introductions or communications that result from its use
- Ensuring informed opt-in consent from all participating users

No warranty is provided. Deploying organizations assume full responsibility for the system and its use within their environment.

---

## Problem

In large organizations:
- Developers routinely solve the same problems independently
- Code reviews and architecture discussions happen late, after patterns are set
- Discovery of relevant colleagues is largely social and accidental
- AI-assisted development is accelerating code production, making overlap more likely and harder to spot
- There is no ambient awareness of what colleagues are building right now

Claude Halla creates that ambient awareness without requiring developers to manually post to Slack or write RFCs.

---

## Core Concepts

### The Wall
The Wall is a shared, ephemeral message board. Active Claude sessions post conversational signals to it — natural-language descriptions of what the developer is working on. There is no tagging or structured schema required. When a Claude session queries the Wall, it reads the posts the way a person would scan a message board — using its own judgment to identify what's relevant to the current session.

This makes Claude's reading comprehension the matching engine. No tag-based matching algorithm is needed.

### The Registry
The Registry is the permanent layer. It stores repo URLs paired with plain-language project descriptions. An entry is created automatically when Claude detects a new git remote in the user's working directory — no manual action required. No username or owner is attached to a Registry entry; it simply records that a repo exists and what it does. When the Registry surfaces a match, the response is always "go check out that repo" rather than "go talk to this person."

### Session Signal (Wall Post)
A signal is a short, natural-language summary of what the user is currently building, posted to the Wall by their Claude session with explicit user approval.

```
[2026-02-18 14:32 | tross]
Working on retry middleware for async task queues in Node.js with BullMQ.
Trying to get exponential backoff to play nicely with job priority.
New feature for the payments pipeline.
```

Signals are:
- **Explicit** — user approves before Claude posts
- **TTL-bound** — expire after a configurable TTL, enforced by the hub regardless of session state
- **Sanitized** — natural language summaries only; no raw code, no file contents, no secrets

### Signal Archival and Project Memory
When a signal expires (session ends or TTL elapses), it is not simply deleted. It is archived and associated with a project key.

**Keying strategy:**
- **Repo work**: The git remote URL is the key. Stable, unambiguous, and shared across machines and contributors.
- **Pre-repo work**: A hash of `username + absolute directory path` serves as a provisional key. This is deterministic — the same developer in the same directory always resolves to the same key — and requires no user input. It is a known limitation that renaming the directory or working from a different machine will produce a different hash; this is an acceptable tradeoff for work that has not yet been committed to a repo.

When a developer returns to the same project, the archived signal history reloads as context and new signals append to it. This builds a project-level memory that accumulates over time without requiring manual documentation.

**Graduation from provisional to repo key**: When Claude detects that a git remote has been added to a directory that has an existing hash-keyed history, it prompts the user to migrate: *"Looks like this project now has a repo — want me to move your Claude Halla history over to that key?"* This migration is also the natural moment for the project to become a Registry candidate.

**Abandonment policy**: Hash-keyed entries with no activity for one week are flagged as potentially abandoned. After one month of inactivity they are soft-archived — hidden from active queries but not deleted. If a developer returns to the same directory after a long absence, the history is surfaced with a note that it was previously considered inactive. Hard deletion occurs after six months. These thresholds are org-configurable.

### Contribution Routing
When Claude detects that a developer is about to build something that already exists in the Registry, it surfaces the existing project and suggests contributing there instead. Claude provides the clone URL and suggests the developer implement their desired functionality as a contribution to that repository rather than building a parallel implementation.

This is a core value proposition in large organizations where teams routinely build the same internal tools independently.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Claude Halla Hub                      │
│                                                          │
│  ┌──────────────────┐     ┌──────────────────────────┐  │
│  │    The Wall       │     │      The Registry         │  │
│  │  (TTL-bound,      │     │  (permanent, repo-keyed,  │  │
│  │   persisted)      │     │   contribution-routing)   │  │
│  └──────────────────┘     └──────────────────────────┘  │
│                                                          │
└─────────────────────────────────────────────────────────┘
          ▲                            ▲
          │  MCP                       │  MCP
          │                            │
┌──────────────────┐        ┌──────────────────┐
│  Claude (Dev A)  │        │  Claude (Dev B)  │
│  tross@org       │        │  jlee@org        │
└──────────────────┘        └──────────────────┘
```

The hub can be deployed as a thin service — both Wall posts and the Registry are persisted to a lightweight database. On restart, Wall posts with remaining TTL are restored automatically. No AI infrastructure is required in the hub itself; the reasoning happens in the Claude sessions that read the Wall.

Both `read_wall` and `read_registry` support pagination to prevent large result sets from exhausting Claude's context window. Claude requests additional pages as needed until it has enough to reason about.

Responses from these tools include a `_hint` field suggesting that Claude delegate the relevance analysis to a subagent, keeping the main session's context window free:

```json
{
  "posts": [...],
  "pagination": { "page": 1, "total_pages": 4, "has_more": true },
  "_hint": "Consider delegating relevance analysis to a subagent to preserve your context window."
}
```

This pattern applies to both paginated and single-page responses — matching against even a modest number of entries is better handled out of band.

To prevent recursive subagent spawning, both tools accept a `suppress_hint` boolean parameter. When the main session delegates to a subagent, it instructs the subagent to call with `suppress_hint: true` — the hub omits `_hint` from the response and the chain stops at one level deep.

### MCP Tools Exposed by the Hub

| Tool | Description |
|------|-------------|
| `post_to_wall` | Publish a session signal to the Wall |
| `retract_post` | Remove a Wall post before it expires |
| `read_wall` | Fetch a paginated set of Wall posts for Claude to reason over |
| `read_registry` | Fetch a paginated set of Registry entries for Claude to reason over |
| `add_to_registry` | Add a repo + description to the permanent Registry |
| `update_registry_entry` | Update an existing Registry entry |
| `get_user_summary` | Fetch the current Wall post and context for a specific user |

---

## User Experience

### When Claude Posts a Signal
Claude does not post signals reactively or continuously. It posts when the session has a clear, settled picture of what the user is building. Natural triggers:

- A design document is being generated
- A new project structure is being scaffolded
- Significant, focused implementation work is underway in a defined domain
- The user explicitly asks Claude to post a signal

Claude proposes the signal text to the user before posting:

> *"You're building something that might interest others in the org. Want me to post this to Claude Halla?*
> *Draft: 'Working on retry middleware for async task queues in Node.js — exponential backoff with job priority support for the payments pipeline.'*
> *I won't share any code — just this description."*

The user can approve, edit, or skip.

### When Claude Reads the Wall
Claude reads the Wall when:
- The developer explicitly asks ("is anyone else working on something like this?")
- Claude is about to help build something and wants to check whether the same thing already exists or is being built elsewhere in the org
- A relevant new post appears on the Wall (surfaced gently, not intrusively)

Claude reads the Wall posts as a conversation — no structured query, no algorithmic scoring. It reasons about relevance the same way a person would scan a message board.

### Contribution Routing Flow
```
User is about to build feature X.
Claude checks the Registry → finds existing repo Y that covers feature X.
Claude: "Before we build this — looks like the payments-lib repo already handles
         this. Here's the repo: [link]. Want to contribute there instead?"
User: "Yes"
Claude: "Here's the clone URL. Want me to draft a feature request or
         start on the implementation for a PR?"
```

### Intro Flow
When Claude finds a relevant match on the Wall or in the Registry, it surfaces the colleague's username and a plain-language summary of what they're working on. The developer then reaches out through whatever channel they prefer.

**Match without a repo** (active Wall post):
```
Claude: "Looks like jlee is working on something related — retry logic for a
         different queue system. Here's what they posted: [summary].
         Want me to draft a message to send them?"
```

**Match with a repo** (Registry entry):
```
Claude: "There's already a project in the org that covers this — payments-lib.
         Here's the repo: [link]. Want to contribute there instead?"
```

No formal request/response handshake is required. Usernames are not private within an org, and keeping the flow lightweight reduces friction. If a Teams webhook is configured, Claude can optionally send a notification there — but this is not a requirement.

---

## Deployment

### Target Environment
Claude Halla is designed for internal organizational deployment on existing infrastructure. It does not require external services or cloud dependencies beyond what the organization already operates.

A standard deployment on an OKD/OpenShift cluster consists of:
- The Hub service (stateless Wall + persistent Registry)
- An SSO integration for identity (org credentials)
- An MCP endpoint reachable by Claude Code sessions on the org network

### Hub Design
A thin central service backed by a lightweight persistent database. Both Wall posts and the Registry are written to disk — on restart, any Wall posts with remaining TTL are restored automatically. Wall posts are expired by the hub according to their TTL regardless of whether the originating session is still active. No AI infrastructure is required in the hub itself — all reasoning happens in the Claude sessions that read the Wall.

### Remote URL Allowlist
To prevent the Registry from inadvertently indexing public or external repositories, the hub supports a configurable remote URL allowlist. Only remotes matching the allowed pattern(s) are eligible for Registry entries. This is particularly important for organizations with self-hosted git infrastructure.

```yaml
# Example configuration
allowed_remote_patterns:
  - "https://git.company.com/*"
  - "git@git.company.com:*"
```

Remotes that do not match are silently ignored — no Registry entry is created and no error is surfaced to the user.

---

## Signal Retention and Staleness

Wall posts carry a timestamp. Claude weights older posts as more stale when reasoning about relevance. The organization configures Wall retention (suggested default: 24–72 hours for active posts).

Archived signals (post-expiry) are retained in project history and are not surfaced on the Wall directly — they are only loaded when a session reconnects to the same project.

**Registry entry expiry**: Registry entries with no associated Wall activity for a configurable period are automatically soft-archived and excluded from future matches. Hard deletion follows after a second configurable period. Suggested defaults:

```yaml
registry_soft_archive_after: 180d  # six months of inactivity
registry_hard_delete_after: 365d   # one year of inactivity
```

---

## Privacy and Consent Model

| Principle | Implementation |
|-----------|---------------|
| No raw code published | Signals are natural-language summaries only |
| Explicit publish | User approves every Wall post |
| Ephemeral by default | Wall posts expire; no persistent history of session content |
| Org-scoped | All signals and Registry entries are visible only within the org tenant |
| Revocable | Developer can retract any post at any time |
| No passive surveillance | The hub does not record what was built, only active and archived signals |

---

## Out of Scope (v1)

- Real-time session sharing or pair programming
- Code exchange through the hub
- Cross-org discovery
- Public signal feeds or any non-org deployment
- Hard Microsoft Teams integration dependency
- Algorithmic or embedding-based signal matching

---

## Success Metrics

- **Intro rate**: % of sessions resulting in at least one successful intro per month
- **Contribution routing events**: How often a developer takes a suggested contribution path instead of building independently
- **Overlap reduction**: Self-reported or measured: duplicate implementations avoided
- **Opt-in rate**: % of Claude Code users in the org who post at least one Wall signal per month
- **Registry coverage**: % of internal repos with Registry entries over time
