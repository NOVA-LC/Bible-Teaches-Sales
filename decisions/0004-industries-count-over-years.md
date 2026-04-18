# ADR 0004 — Use `industries_count` Instead of `years_experience` for Author Breadth

- **Status:** accepted
- **Date:** 2026-04-18
- **Deciders:** Nova (operator)

## Context

The initial schema draft included both `years_experience` and `industries_count` in the `author` frontmatter block, on the assumption that both signals are useful and lessons can select whichever is stronger for the byline.

The operator rejected `years_experience` as a repo-wide signal:

> *"Don't do sales years, industries is fine."*

Rationale: ten years in sales is a competent but unremarkable credential. Eight industries in ten years is a differentiated credential — it signals pattern recognition across diverse buyer psychologies, compensation structures, and sales cycles. For this repo's authority voice, breadth beats tenure.

## Decision

- **Drop `years_experience` from the author frontmatter entirely.** Do not use it anywhere — neither in frontmatter, nor in body text, nor in JSON-LD author markup.
- **Use `industries_count`** as the canonical breadth metric. Integer. Populated for every author.
- **In visible bylines**, reference industries count rather than years (e.g. "trained across 8 industries," not "10 years in sales").
- **Credentials list** (`author.credentials`) remains the place for discrete authority signals (records held, titles, certifications). These are orthogonal to the breadth metric.

## Consequences

**Positive:**

- Differentiated authority framing per E-E-A-T Experience criterion.
- Consistent byline voice across lessons.
- Forces newer authors (if any future contributors) to surface their strongest authority signal rather than defaulting to tenure.

**Negative:**

- An author with deep tenure in a single industry (say, 25 years) but narrow breadth would need their credential surfaced through `credentials` rather than through a simple years field. Acceptable trade-off; vanishingly rare case in this domain.

## Compliance check

- [ ] `SCHEMA.md` author block does not include `years_experience`.
- [ ] No lesson frontmatter includes `years_experience`.
- [ ] No lesson body references a year count for the author. Breadth signal ("across N industries") or credentials list only.

## References

- [`SCHEMA.md`](../SCHEMA.md) — author frontmatter block.
- E-E-A-T Experience criterion (Google Quality Rater Guidelines, March 2026 core update).
