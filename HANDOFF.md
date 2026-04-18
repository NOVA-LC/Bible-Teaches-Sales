# HANDOFF

> Updated at the end of every substantive work session. Read this before starting a new session. Keep under ~2,000 tokens. If something in here conflicts with [`AGENTS.md`](AGENTS.md), AGENTS.md wins.

**Last updated:** 2026-04-18
**Last session branch:** `claude/general-session-IdCnz`
**Last commit hash:** (set on next commit)

---

## Current state

The repo is in initial scaffolding phase. Governance, schema, and the first
approved lesson are live. No pillar lessons yet. No reverse indexes yet
populated beyond Lesson 01.

Files live:

- `AGENTS.md` — AI onboarding contract.
- `CLAUDE.md` — thin pointer to AGENTS.md.
- `HANDOFF.md` — this file.
- `README.md` — repo purpose.
- `SCHEMA.md` — canonical lesson structure, SEO/GEO rules.
- `TAXONOMY.md` — controlled vocabulary.
- `llms.txt` — AI crawler discovery map.
- `index.json` — lesson catalog.
- `/decisions/` — 5 ADRs covering origin-hiding, no-FAQPage-schema, bidirectional scripture index, industries-over-years, AGENTS.md adoption.
- `/lessons/01-commendation-before-commission.md` — approved, Nova authored.
- `/carousels/01-commendation-before-commission.md` — 11-slide distillation.
- `/scriptures/` — 4 verse pages for Acts 4:36, Acts 9:27, 2 Timothy 4:11, Proverbs 16:18.
- `/indexes/` — by-scripture, by-topic, by-audience reverse indexes.

---

## Last session summary

Built from empty repo. Key decisions made and logged as ADRs:

- Origin of the repo concept (JW branch-streamed meeting) is hidden from user-facing content. Scripture is case evidence, not doctrine. Design influences stay private.
- No FAQPage JSON-LD — Google deprecated rich-snippet eligibility. `## Questions People Ask` content kept for organic PAA + GEO.
- Bidirectional scripture indexing adopted: `/scriptures/` study-notes pages plus `/indexes/by-scripture.json` reverse lookup.
- Schema uses `industries_count` instead of `years_experience` for author breadth signal (Nova: 8 industries, 2 world records).
- AGENTS.md adopted as onboarding standard (Linux Foundation). HANDOFF.md + ADRs complete the governance triad.

Lesson 01 drafted, reviewed with the operator across 4 revision rounds, approved. Covers: self-worth as the upstream variable of tonality; Barnabas vouching for Saul (Acts 9:27) and mentoring John Mark (2 Timothy 4:11); NEPQ's connection and situation stages; democratization beat (any role, close alone or help others).

Research passes completed this session:

- 2026 SEO + structured-data best practices (FAQ schema deprecated; Article/HowTo/Course still rewarded; JSON-LD preferred).
- GEO / AI-citation optimization (Princeton/GA Tech: statistics +41%, quotations +28%; passage-level retrieval; llms.txt emerging standard).
- E-E-A-T March 2026 core update (Experience is the primary differentiator).
- Bidirectional indexing patterns for static markdown knowledge bases.
- AGENTS.md / CLAUDE.md / ADR patterns for AI session handoff.

---

## Decisions made this session

- [`decisions/0001-hide-origin-from-reader.md`](decisions/0001-hide-origin-from-reader.md)
- [`decisions/0002-no-faqpage-schema.md`](decisions/0002-no-faqpage-schema.md)
- [`decisions/0003-bidirectional-scripture-index.md`](decisions/0003-bidirectional-scripture-index.md)
- [`decisions/0004-industries-count-over-years.md`](decisions/0004-industries-count-over-years.md)
- [`decisions/0005-agents-md-over-ad-hoc-onboarding.md`](decisions/0005-agents-md-over-ad-hoc-onboarding.md)

---

## In progress / blocked

Nothing blocked. Nothing mid-flight. The scaffold is complete.

---

## Next steps

In priority order:

1. **Lesson 02** — operator has not yet named the topic. Most likely candidates based on conversation: (a) the tonality mechanic in more depth, (b) "what to say after a lost deal," (c) a pillar-page synthesis of the trainer's full operating model.
2. **Pillar page** — once 3–4 clusters exist, produce the pillar lesson aggregating them. Target 2,500+ words. Use `content_type: pillar`.
3. **Generate reverse indexes via script** — the current `/indexes/*.json` files are hand-written. Write a small generator that rebuilds them from lesson frontmatter on every push. Not urgent; do this when lesson count hits ~5.
4. **Scripture page expansion** — add pages for any newly cited verse on each new lesson.
5. **Hosting + JSON-LD rendering layer** — when the operator builds the public-facing site / dashboard, the frontmatter feeds JSON-LD emitted at render time. Coordinate with the edge-function implementation to confirm field contract.

---

## What to avoid

- **Do not reveal the origin.** The denominational source of the design principles never shows up in user-facing copy. If a draft has a cadence tell, rewrite it. See [`decisions/0001-hide-origin-from-reader.md`](decisions/0001-hide-origin-from-reader.md).
- **Do not emit FAQPage JSON-LD.** See [`decisions/0002-no-faqpage-schema.md`](decisions/0002-no-faqpage-schema.md).
- **Do not skip the `## Note on Position` section.** Every lesson includes the democratization beat — any role, close alone or help others.
- **Do not use `years_experience` in frontmatter.** Dropped in favor of `industries_count`.
- **Do not `git add -A`.** Stage files by name only to avoid committing drafts or scratch notes.
- **Do not skim the existing lessons before writing a new one.** The operator has explicitly asked that every agent absorb the full canon first.
- **Do not write new lessons without running the skeptic/believer + dual-demographic tests.** A lesson that fails either test cannot be marked `status: approved`.
