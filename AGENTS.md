# AGENTS.md

> **This file is the onboarding contract for any AI agent or human contributor joining this repository. Read every linked document in full before proposing, editing, or publishing content. Take as long as you need. Do not begin work until you have internalized what follows — the voice rules, the hidden-origin directive, the dual-audience test, the schema, and every lesson already in the repo.**

This repository is governed by an open standard ([AGENTS.md](https://agents.md), stewarded by the Agentic AI Foundation under the Linux Foundation, adopted by 60,000+ repositories). Codex, Claude Code, Cursor, Aider, Continue, and adjacent agents read this file at session start.

---

## What this repo is

A static knowledge base of modern sales training lessons. Each lesson pairs a two-thousand-year-old case study with contemporary sales mechanics (primarily Jeremy Miner's NEPQ methodology) and distills into LinkedIn-ready carousels. The content feeds AI edge functions and RAG pipelines that serve training responses in real time to sales trainers, managers, solo reps, and the family members who encourage them.

Primary demographic targets: **men 17–48** and **women 36–87**.

---

## Required reading before starting work

You must read these documents in full, in this order, before editing or adding content:

1. [`README.md`](README.md) — repo purpose and consumption contract.
2. [`SCHEMA.md`](SCHEMA.md) — canonical lesson structure, frontmatter, section anchors, SEO/GEO rules.
3. [`TAXONOMY.md`](TAXONOMY.md) — controlled vocabulary for every tag field.
4. Every file in [`/decisions/`](decisions/) — architectural decision records. These capture **the thinking behind the design**, not just the output. Understand each decision's context before proposing changes.
5. Every file in [`/lessons/`](lessons/) — the existing teaching corpus. You cannot write a new lesson that stays on-voice without having absorbed the current canon.
6. [`HANDOFF.md`](HANDOFF.md) — living session state. Tells you what the last session did, what's in progress, what to avoid.

**If this takes hours, that is correct.** The operator of this repo has explicitly asked that every agent thoroughly read and understand every teaching and the thinking behind it before beginning a new session. Quality of output depends on depth of context. Do not skim.

---

## Non-negotiable voice rules

These are not preferences. They are contracts. Violating them invalidates the work.

1. **No denominational fingerprint ever reaches the reader.** The repo's design principles draw from a faith tradition; the *output* does not. No cadence tells, no phrase tells, no source citations that reveal the origin. See [`decisions/0001-hide-origin-from-reader.md`](decisions/0001-hide-origin-from-reader.md).
2. **Scripture is case evidence, not doctrine.** Cite it the way Ryan Holiday cites Marcus Aurelius. A devout believer and a stark skeptic must both find the lesson useful.
3. **Modern cadence.** Podcast-host rhythm. Short sentences allowed. No "dear ones," no "brothers and sisters," no "may you be," no "consider this" as sermon-opener.
4. **Specific by call, by moment, by name.** Never generic. "On Tuesday's Peterson call, you slowed down on the second objection" — not "you've got a great attitude."
5. **Democratization beat mandatory.** Every lesson includes the `## Note on Position` section: anyone in any role (solo rep, husband, mother, new hire) can run the principle. Close alone OR help others. Commendation is a behavior, not a rank.
6. **The market humbles. The trainer builds.** Do not confuse the two jobs in any lesson.

---

## Dual tests every lesson must pass

Before marking a lesson `status: approved`, run it against both tests.

**Test 1 — Skeptic/Believer.** A devout believer should feel seen. A stark skeptic who is reading the lesson purely for the sales training should find the scripture references tolerable enough to finish the piece and extract value. If either audience bounces, revise.

**Test 2 — Dual Demographic.** Does a 22-year-old male D2D rep get value? Does a 58-year-old female real-estate agent get value? Both. If one audience finds it "not for them," revise.

---

## How to add a lesson

1. Confirm the topic is not already covered by scanning [`index.json`](index.json) and [`/indexes/by-topic.json`](indexes/by-topic.json).
2. Copy the frontmatter block from [`SCHEMA.md`](SCHEMA.md) and fill in every field. No empty frontmatter keys — use `null` or `[]` for deliberate nulls.
3. Follow the canonical section order in [`SCHEMA.md`](SCHEMA.md). Section names are the stable anchor contract — do not rename, do not reorder.
4. Apply the GEO production rules: statistics every 150–200 words, at least one named-expert quotation, every H2 section passage-retrieval safe.
5. Write the matching carousel in `/carousels/` using the same slug.
6. Add or update scripture pages in `/scriptures/` for every verse cited.
7. Update [`index.json`](index.json) and every reverse index in [`/indexes/`](indexes/).
8. Use only tags defined in [`TAXONOMY.md`](TAXONOMY.md). If a new tag is needed, add it to the taxonomy first.
9. Run the dual tests. Mark `status: approved` only after passing.
10. Update [`HANDOFF.md`](HANDOFF.md) with what you did.

---

## When to create an ADR

Create a new file in [`/decisions/`](decisions/) any time you:

- Change the schema or taxonomy structurally.
- Make a choice that closes off other choices (e.g., "we don't use X because Y").
- Adopt or drop an external standard.
- Change a voice rule or editorial constraint.

ADR format: see existing files in [`/decisions/`](decisions/). Status progresses: `proposed` → `accepted` → `superseded`. Accepted ADRs are never rewritten — they are superseded by a new ADR that references them.

---

## How to update HANDOFF.md

[`HANDOFF.md`](HANDOFF.md) is updated at the **end of every substantive work session** (and always before closing). It is kept under roughly 2,000 tokens. It contains:

- `Current state` — what is live in the repo right now.
- `Last session summary` — what just changed and why.
- `Decisions made this session` — links to any new ADRs.
- `In progress / blocked` — what's mid-flight.
- `Next steps` — the next 1–3 concrete actions.
- `What to avoid` — traps the next agent should not walk into.

---

## Commands

This is a content repo. There is no build step, no test suite, no package manager. The "commands" are editorial:

- `git status` — check for untracked content.
- `git add <file>` — stage named files only. Never `git add -A` (risks committing drafts or scratch notes).
- `git commit` — clear, past-tense, present-action message describing what the commit does.
- `git push -u origin <branch>` — push to the working branch.

Always work on the branch specified by the current session's task brief. Never push to `main` directly.

---

## Repository structure

```
AGENTS.md                       # this file — AI onboarding contract
CLAUDE.md                       # thin pointer to AGENTS.md
HANDOFF.md                      # living session state
README.md                       # human-facing repo intro
SCHEMA.md                       # lesson structure contract
TAXONOMY.md                     # controlled vocabulary
llms.txt                        # AI crawler discovery map
index.json                      # machine-readable lesson catalog
decisions/                      # ADRs — the thinking
indexes/                        # auto-generatable reverse indexes
lessons/                        # full lessons
scriptures/                     # scripture-first study-notes pages
carousels/                      # slide-ready distillations
```

---

## Governance lineage

This AGENTS.md is informed by:

- [AGENTS.md open standard](https://agents.md/) — Linux Foundation / Agentic AI Foundation.
- Claude Code context management best practices — session handoff patterns.
- Architecture Decision Records (Cognitect / Michael Nygard tradition).
- 2026 Google Quality Rater Guidelines (E-E-A-T emphasis, Experience-first).
- Princeton/Georgia Tech GEO research (statistics +41%, quotations +28% for AI citation).

When these sources evolve, update this file and log the change as an ADR.
