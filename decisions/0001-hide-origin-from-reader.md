# ADR 0001 — Hide the Origin of the Design Principles from the Reader

- **Status:** accepted
- **Date:** 2026-04-18
- **Deciders:** Nova (operator), initial scaffolding session

## Context

The concept for this repository originated during a streamed religious service that the operator attended. A speaker's line about building up self-worth — and the idea that reality will naturally humble anyone who gets overconfident — sparked the core principle of this entire knowledge base: *the trainer builds, the market humbles*.

The internal design also draws stylistic inspiration from a specific tradition's approach to teaching: measured cadence, principle-over-opinion, anchoring assertions in scripture as authoritative evidence rather than as rhetorical flourish.

Early drafts of Lesson 01 carried that denominational cadence visibly — "dear ones," "brothers and sisters," "may you be." The operator identified this immediately as a blocker. The repo's commercial thesis depends on the content being useful to:

1. A devout believer (of any tradition) who feels seen.
2. A stark skeptic who is here purely for the sales training and will tolerate a scripture reference only as long as it reads as case evidence, not sermon.

If either audience bounces, the repo fails its purpose.

## Decision

The denominational origin of the design principles **never** reaches user-facing content. Specifically:

1. **No cadence tells.** No "dear ones," "brothers and sisters," "may you," or any formulaic address that signals a specific religious tradition. Modern podcast-host rhythm only.
2. **No phrase tells.** Words like "consider," "notice," "observe" used as sermon openers are scrubbed. Principle-first teaching is fine; the *register* in which it is delivered must not signal a tradition.
3. **No source citations that reveal origin.** External research citations in Sources sections are limited to secular, non-denominational, or cross-denominational publishers.
4. **Scripture is case evidence.** Cited the way Marcus Aurelius is cited in a modern business book. No reverence framing, no doctrinal commentary.
5. **The internal design principles remain private.** Writers and AI agents may use the underlying cadence discipline as an invisible guide during drafting — but the output is scrubbed before approval.

## Consequences

**Positive:**

- Lessons pass the dual-audience test.
- Content is commercially viable across both religious and secular markets.
- The repo can be marketed as "modern sales training that happens to reference the Bible" rather than as religious content.
- LinkedIn carousel distillations work cleanly — no slide reveals a denominational origin.

**Negative:**

- Writers familiar with the source tradition must actively unlearn its cadence during drafting.
- QA pass for every lesson must include a "denominational fingerprint sweep" before approval.
- Loss of some rhetorical density that the original tradition's cadence provides; compensated by the modern cadence's narrative pull.

## Compliance check (per lesson)

Before marking a lesson `status: approved`, confirm:

- [ ] No cadence tells.
- [ ] No phrase tells.
- [ ] Sources cite only non-denominational publishers.
- [ ] Scripture framed as case evidence.
- [ ] Lesson passes the skeptic/believer dual test.

## References

- [`AGENTS.md`](../AGENTS.md) — non-negotiable voice rules.
- [`SCHEMA.md`](../SCHEMA.md) — voice rules section.
