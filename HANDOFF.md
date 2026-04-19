# HANDOFF

> Updated at the end of every substantive work session. Read this before starting a new session. Keep under ~2,000 tokens. If something in here conflicts with [`AGENTS.md`](AGENTS.md), AGENTS.md wins.

**Last updated:** 2026-04-18
**Last session branch:** `claude/general-session-IdCnz`
**Schema version:** v2.0

---

## Current state

The repo is in late scaffolding phase. Governance triad is live, schema is future-proofed (v2.0), ADRs 0001-0006 accepted. Lesson 01 body is approved by the operator but not yet written to disk with final frontmatter. No reverse indexes populated yet.

Files live:

- `AGENTS.md` — AI onboarding contract.
- `CLAUDE.md` — thin pointer to AGENTS.md.
- `HANDOFF.md` — this file.
- `README.md` — repo purpose.
- `SCHEMA.md` — v2.0 canonical lesson structure, SEO/GEO/chunking/derivatives rules.
- `TAXONOMY.md` — controlled vocabulary (expanded for access tiers, status lifecycle, provenance, instruction styles, languages, chunking).
- `llms.txt` — AI crawler discovery map.
- `/decisions/0001-0006` — six ADRs covering origin-hiding, no-FAQPage-schema, bidirectional scripture index, industries-over-years, AGENTS.md adoption, and the future-proofing sweep.

Directories created but empty: `/lessons/`, `/carousels/`, `/scriptures/`, `/indexes/`. `index.json` not yet written.

---

## Last session summary

Built governance foundation and schema from empty repo across ~6 revision rounds with the operator.

**Key decisions logged as ADRs:**

- [0001](decisions/0001-hide-origin-from-reader.md) — Hide denominational origin from user-facing content. Scripture is case evidence, not doctrine.
- [0002](decisions/0002-no-faqpage-schema.md) — Do not emit FAQPage JSON-LD. Keep `## Questions People Ask` content for organic PAA + GEO.
- [0003](decisions/0003-bidirectional-scripture-index.md) — Bidirectional scripture indexing via `/scriptures/` pages + `/indexes/by-scripture.json`.
- [0004](decisions/0004-industries-count-over-years.md) — Schema uses `industries_count` not `years_experience` for author breadth.
- [0005](decisions/0005-agents-md-over-ad-hoc-onboarding.md) — Adopt AGENTS.md (Linux Foundation standard) as the AI onboarding contract.
- [0006](decisions/0006-future-proofing-architecture.md) — Future-proofing sweep. MDX path, RAG chunking contract, SemVer for content, i18n migration path, fine-tuning export, lifecycle states, access tiers, derivative manifest, C2PA path, embedding reservations, content model typing, accessibility targets.

**Research passes completed:**

- 2026 SEO + structured-data best practices.
- GEO / AI-citation optimization (Princeton/GA Tech: statistics +41%, quotations +28%).
- E-E-A-T March 2026 core update (Experience is primary differentiator).
- Bidirectional indexing patterns for static markdown.
- AGENTS.md / CLAUDE.md / ADR patterns for AI session handoff.
- Headless CMS / content-as-data future-proofing.
- i18n folder structure conventions.
- AI fine-tuning JSONL format.
- C2PA content provenance.
- MDX interactive components.
- RAG chunking strategy (256-512 tokens, semantic boundaries, no overlap).
- WCAG 3.0 timeline.
- SemVer + editorial workflow.

**Lesson 01 body approved** across 4 revision rounds with the operator. Covers: self-worth as the upstream variable of tonality; Barnabas vouching for Saul (Acts 9:27) and mentoring John Mark (2 Timothy 4:11); NEPQ's connection and situation stages; democratization beat (any role, close alone or help others). Author: Nova. Frontmatter not yet written.

---

## Decisions made this session

All six ADRs linked above.

---

## In progress / blocked

**In progress:** writing Lesson 01 with the future-proofed v2.0 frontmatter.

**Blocked / awaiting operator decision:**

- **Licensing.** ADR 0006 section 6.13 defers this. Operator must choose repo-level license (all-rights-reserved vs CC-BY vs CC-BY-NC vs custom). Default until decided: every lesson frontmatter carries `license: "all-rights-reserved"`. No `LICENSE` file at repo root yet.

---

## Next steps

In priority order:

1. **Finish Lesson 01** — write to `/lessons/01-commendation-before-commission.md` with full v2.0 frontmatter, approved body, plus new `## Questions People Ask` section.
2. **Write Carousel 01** — `/carousels/01-commendation-before-commission.md`, 11 slides per approved distillation.
3. **Write 4 scripture pages** — `/scriptures/acts-4-36.md`, `acts-9-27.md`, `2-timothy-4-11.md`, `proverbs-16-18.md` with study-notes frontmatter.
4. **Write reverse indexes** — `/indexes/by-scripture.json`, `by-topic.json`, `by-audience.json`.
5. **Write `index.json`** at repo root — machine-readable lesson catalog.
6. **Commit and push** final content batch.
7. **Resolve license decision** with operator.
8. **Lesson 02** — topic TBD.
9. **Generator script** for reverse indexes (automate when lesson count hits ~5).

---

## What to avoid

- **Do not reveal the origin.** See [`decisions/0001-hide-origin-from-reader.md`](decisions/0001-hide-origin-from-reader.md).
- **Do not emit FAQPage JSON-LD.** See [`decisions/0002-no-faqpage-schema.md`](decisions/0002-no-faqpage-schema.md).
- **Do not skip the `## Note on Position` section.**
- **Do not use `years_experience` in frontmatter.** Dropped in favor of `industries_count`.
- **Do not drop any v2.0 frontmatter keys.** Use `null` / `[]` / sensible defaults for deliberately empty values.
- **Do not `git add -A`.** Stage files by name.
- **Do not skim the existing corpus before writing a new lesson.** The operator has explicitly asked that every agent absorb the full canon first.
- **Do not write new lessons without running the skeptic/believer + dual-demographic tests.**
- **Do not mark a lesson `approved` without the `ai_assisted` flag set honestly.**
- **Do not distribute any lesson externally until licensing is resolved with the operator.**
