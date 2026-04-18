# ADR 0002 — Do Not Emit FAQPage JSON-LD

- **Status:** accepted
- **Date:** 2026-04-18
- **Deciders:** initial scaffolding session (research-driven)

## Context

A natural first instinct when building a knowledge base optimized for search is to mark up question-and-answer sections with `schema.org/FAQPage` JSON-LD, in the hope of earning FAQ rich snippets in Google SERPs.

That instinct is now wrong.

Research surfaced during schema design (2026 SEO best-practice literature, including `greenserp.com/high-impact-schema-seo-guide` and multiple industry-standard guides) is consistent: Google reduced FAQ rich-snippet eligibility significantly in 2023–2024. Most FAQ schema markup no longer triggers rich results, and in some cases pages with unqualified FAQ markup are treated as low-value.

Meanwhile, the underlying *content* — genuine, searchable question-and-answer pairs phrased as likely user queries — remains valuable because:

1. It ranks organically for **People Also Ask** (PAA).
2. It serves as highly-retrievable passages for **Generative Engine Optimization** (GEO), where AI engines (ChatGPT, Perplexity, Claude, Google AI Overviews) cite passage-level chunks.
3. It improves on-page depth and dwell time.

The question is whether to keep the content while dropping the markup.

## Decision

- **Do not emit `FAQPage` JSON-LD anywhere in the repo or at render time.**
- **Keep the content.** Every lesson includes a `## Questions People Ask` section with 4–8 Q&A pairs phrased as real search queries, each answer self-contained and 40–80 words.
- The section is never labeled "FAQ" in copy. It is labeled `## Questions People Ask` — phrasing that signals the intent (search-aligned Q&A) without invoking the deprecated schema type.
- `seo.schema_org_types` in frontmatter explicitly excludes `FAQPage` from the allow-list. Valid values: `Article`, `HowTo`, `Course`, `BlogPosting`.

## Consequences

**Positive:**

- Zero risk of being penalized for low-value FAQ markup.
- PAA eligibility preserved (earned organically through content quality, not markup).
- GEO passage retrieval preserved (AI engines lift passages regardless of FAQ markup).
- Content is still fully useful for on-site Q&A retrieval by the edge function.

**Negative:**

- No FAQ rich snippet in the small number of SERPs where it might still render.
- Writers must resist the muscle memory of adding FAQPage markup.

## Compliance check

- [ ] No lesson, carousel, or scripture page contains `@type: FAQPage` in any JSON-LD block.
- [ ] `seo.schema_org_types` in lesson frontmatter does not include `FAQPage`.
- [ ] `## Questions People Ask` section is present and formatted per SCHEMA.md.

## References

- [`SCHEMA.md`](../SCHEMA.md) — structured data output section.
- 2026 SEO research citations in HANDOFF research pass.
