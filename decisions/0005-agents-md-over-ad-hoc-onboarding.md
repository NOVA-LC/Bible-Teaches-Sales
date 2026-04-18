# ADR 0005 — Adopt AGENTS.md as the AI Onboarding Standard

- **Status:** accepted
- **Date:** 2026-04-18
- **Deciders:** Nova (operator), initial scaffolding session (research-driven)

## Context

The operator explicitly requested that every AI agent joining this repo "thoroughly read and understand every teaching and the thoughts behind it before beginning a new session — idc if it takes them hours." This is a non-trivial operational requirement. It means:

1. Every agent needs a deterministic, discoverable onboarding doc.
2. That doc must enumerate required reading (every lesson, every decision, schema, taxonomy).
3. The doc must survive session-to-session handoff.
4. It must be portable across AI platforms (Claude Code, OpenAI Codex, Cursor, Aider, Continue).

Options considered:

- **Ad-hoc onboarding prompts** pasted at session start. Fragile, unversioned, drifts across sessions, incompatible across platforms.
- **README only.** Overloads the human-facing doc with agent-specific instructions; existing README best practice is to keep it short and user-oriented.
- **CLAUDE.md only.** Claude Code reads this automatically. But not portable to other platforms.
- **AGENTS.md.** Open standard stewarded by the Agentic AI Foundation under the Linux Foundation. Adopted by 60,000+ repositories including OpenAI, Apache Airflow, Temporal. Read automatically by Codex, Claude Code, Cursor, Aider, Continue, and adjacent coding agents.

## Decision

Adopt a three-document governance triad:

### 1. `AGENTS.md` — the onboarding contract

Lives at repo root. Read by every AI agent at session start per the open standard at https://agents.md. Contains:

- Repo purpose.
- Required reading list (explicit, enumerated — every lesson, every ADR, schema, taxonomy, handoff).
- Non-negotiable voice rules.
- Dual-audience and dual-demographic tests.
- Process: how to add a lesson, when to create an ADR, how to update HANDOFF.md.
- Repository structure map.

### 2. `HANDOFF.md` — living session state

Updated at the end of every substantive work session. Kept under ~2,000 tokens. Contains: current state, last session summary, decisions made this session, in-progress, next steps, what to avoid. Serves the session-to-session handoff pattern documented in Claude Code best practices and elsewhere.

### 3. `/decisions/` — ADR log

One ADR per architectural decision. Status progression: `proposed` → `accepted` → `superseded`. Accepted ADRs are never rewritten — they are superseded by new ADRs that reference them. Captures the **thinking** behind each decision, which is what the operator needs new agents to "understand the thoughts behind" on start.

### Supporting files

- `CLAUDE.md` — one-page pointer to `AGENTS.md` so Claude Code's default context-load behavior funnels into the same source of truth as every other platform.
- `llms.txt` at repo root — separately serves AI crawler discovery (not the same role as AGENTS.md, which is for coding agents).

## Consequences

**Positive:**

- Every AI agent, regardless of platform, gets the same onboarding contract.
- New session onboarding is deterministic and enumerable.
- The operator's "read everything before starting" requirement becomes a checklist, not a hope.
- Decision history (ADRs) lets new agents trace the reasoning behind current constraints rather than re-derive or re-debate them.
- Session state (HANDOFF.md) prevents context loss across sessions.

**Negative:**

- Governance overhead: AGENTS.md, HANDOFF.md, and ADRs must be kept current. Stale governance docs are worse than none — they actively mislead.
- Enforcement depends on agent compliance with AGENTS.md. Agents that don't read it will drift. Mitigation: the operator spot-checks outputs against the voice rules in AGENTS.md; drift triggers a reset.

## Compliance check

- [ ] `AGENTS.md` exists at repo root, links to every required-reading doc.
- [ ] `CLAUDE.md` exists and points to `AGENTS.md`.
- [ ] `HANDOFF.md` updated on every substantive session.
- [ ] New ADR created for every architectural decision that closes off other choices.

## References

- [AGENTS.md open standard](https://agents.md/) — Agentic AI Foundation, Linux Foundation.
- Claude Code best practices — session handoff patterns.
- Cognitect / Michael Nygard — Architecture Decision Records tradition.
