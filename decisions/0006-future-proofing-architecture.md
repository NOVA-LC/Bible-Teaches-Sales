# ADR 0006 — Future-Proofing Architecture Sweep

- **Status:** accepted
- **Date:** 2026-04-18
- **Deciders:** Nova (operator), initial scaffolding session (research-driven)

## Context

The operator requested a deep research pass to future-proof the codebase "for any possible future use case" before proceeding with lesson authorship. The current scaffold (governance triad + schema + taxonomy + llms.txt + ADRs 0001-0005) is sound for the v1 use case (feeding an AI edge function with modern sales lessons) but does not yet anticipate the full range of reasonable future use cases.

This ADR captures, in one coordinated sweep, the architectural decisions needed to leave future options open without paying upfront complexity cost. Each sub-decision references the research that informed it.

Future use cases anticipated:

1. **Multi-channel publishing** — same lesson rendered as blog post, LinkedIn carousel, email sequence, video script, podcast outline, TikTok script, book chapter, course module.
2. **Internationalization** — translating lessons into Spanish, Portuguese, French, etc.
3. **AI fine-tuning** — using the corpus as training data for a branded sales-coach model.
4. **Vector search / RAG chunking** — embedding every passage for retrieval.
5. **Interactive content** — MDX components for live NEPQ examples, embedded video, self-assessment tools.
6. **Content lifecycle over time** — lessons get updated, superseded, deprecated; need versioning.
7. **Multi-author contribution** — additional trainers and coaches contribute under governance.
8. **Monetization tiers** — some lessons become gated premium or licensed content.
9. **Analytics / telemetry** — tracking which lessons get retrieved, which slides get shared, which questions get asked.
10. **Content authenticity** — signed, tamper-evident provenance for AI-era publishing.
11. **Static-site generator rendering** — Astro, Next.js, Hugo, Docusaurus all as future targets.
12. **Derivative-asset generation** — agents that autonomously produce the carousel, video script, email sequence from a lesson.

## Decisions

### 6.1 Markdown-first, MDX-compatible (not MDX-required)

**Research finding:** MDX is a cornerstone for modern interactive docs (Docusaurus, Next.js, Tinybird's 2026 docs overhaul). But plain Markdown is more universally parseable, greppable, and AI-retrievable.

**Decision:** Authoring format is plain `.md`. No `.mdx` files in v1. However, the schema and lint contract permit future `.mdx` siblings for lessons that add interactive components, provided every `.mdx` lesson also provides an `.md` fallback that strips the interactivity. Edge-function retrieval always prefers the `.md`.

**Rationale:** Keeps v1 universally consumable while leaving MDX as a zero-cost future option. No upfront complexity.

### 6.2 Chunking contract aligned with RAG research

**Research finding:** 256-512 tokens per chunk is the sweet spot. Align chunk boundaries with semantic boundaries (paragraphs, sections, list items, table rows). Markdown structure preserved inside chunks reasons better than flattened text. January 2026 systematic analysis found chunk overlap provided no measurable benefit — recommendation has shifted away from default overlap.

**Decision:**

- Declared chunking strategy: `semantic_by_h2_with_fallback`. Edge functions split on H2 headings first; if any H2 section exceeds 600 tokens, they sub-chunk on paragraph boundaries within that section.
- Target range per H2 section: 200-500 tokens where practical. `## Hook` sections may be under 200 (acceptable). `## Case Study` and `## Payoff` may exceed 500 for narrative reasons (acceptable with sub-chunking).
- No chunk overlap by default (per 2026 research).
- Each chunk has a stable ID: `<lesson-id>#<section-slug>` (e.g. `01#hook`, `01#case-study`). Sub-chunks append `.1`, `.2`, etc.
- Markdown tables and numbered lists remain intact within chunks — do not split them.

### 6.3 Versioning discipline (SemVer for content)

**Research finding:** SemVer maps cleanly to content lifecycles. Conventional commits + automated release tooling (semantic-release, Changesets) are mature.

**Decision:** Each lesson's `version` field follows MAJOR.MINOR.PATCH:

- **MAJOR** — lesson fundamentally rewritten or its core claim changed. Must log a superseded ADR if the change reflects a principle shift.
- **MINOR** — new section added, significant expansion, new scripture cited, new carousel slide added.
- **PATCH** — copy edits, typo fixes, citation URL updates, metadata corrections.

New frontmatter fields:

- `supersedes: null | "<lesson-id>@<version>"` — for MAJOR rewrites that replace prior canon.
- `changelog: []` — array of `{ version, date, change }` entries.

### 6.4 Internationalization path

**Research finding:** Two canonical patterns — folder-based (`/lessons/<lang>/<slug>.md`) and suffix-based (`<slug>.<lang>.md`). Folder-based wins for most static-site generator compatibility (Hugo, Next.js i18n routing, Docusaurus).

**Decision:**

- v1 is English-only. No folder moves yet — avoids unnecessary migration cost.
- Every lesson declares `language: "en"` in frontmatter.
- Translation tracking fields reserved: `translation_of: null`, `translations: []`.
- When second language arrives, the migration is: move `/lessons/*.md` → `/lessons/en/*.md`, add `/lessons/<new-lang>/*.md`, update edge-function path resolution. Documented migration path here is the future-proofing.

### 6.5 AI fine-tuning dataset compatibility

**Research finding:** OpenAI / Anthropic / open-source fine-tuning expects JSONL chat format. Each line is a training example with `messages: [{role, content}, ...]`. 4096 token limit per example.

**Decision:**

- Reserve `/datasets/` directory (created later, not now). Each export emits `<lesson-id>.jsonl` with the lesson rendered as one or more chat-format training examples.
- Frontmatter fields added: `fine_tuning_safe: true`, `instruction_style: ""` (e.g. "therapeutic-inquiry", "narrative-teaching", "carousel-copy").
- The 5 diagnostic questions in each `## Mechanic` section are structured deliberately to be lifted as instruction-tuning examples: user = rep's complaint, assistant = diagnostic question.

### 6.6 Content lifecycle states (expanded)

**Decision:** Lesson `status` field values expanded:

- `draft` — in progress, not yet reviewed.
- `review` — reviewed, awaiting approval.
- `approved` — live, canonical.
- `superseded` — replaced by a newer lesson; still accessible via its URL for link integrity.
- `deprecated` — still accessible, actively discouraged (e.g. methodology no longer endorsed).
- `archived` — removed from active retrieval, kept for history.

Edge functions retrieve only `approved` lessons by default. The `superseded` / `deprecated` states exist to preserve URL stability for SEO without polluting retrieval.

### 6.7 Author and AI-assistance disclosure (E-E-A-T)

**Research finding:** Google's March 2026 core update made Experience the primary E-E-A-T differentiator. Disclosure of AI assistance is increasingly expected for trust.

**Decision:** Add to author frontmatter:

- `co_authors: []` — for future multi-author lessons.
- `ai_assisted: true | false` — transparency flag. Any lesson drafted with AI involvement marks this true. Does not diminish authority; the lesson still passes human review before approval.
- `human_reviewed: true | false` — confirms a human editorial pass.

### 6.8 Access tier (monetization readiness)

**Decision:** Add `access_tier: "public"` field. Valid values:

- `public` — free, indexable.
- `premium` — gated, requires auth.
- `enterprise` — licensed to specific orgs.
- `licensed` — third-party licensed content.

For v1 all lessons are `public`. The field reserves the option without forcing implementation.

Paired with `preview_only_sections: []` — which H2 section names render in a paywall preview. Empty array = full lesson available at current tier.

### 6.9 Derivative-asset manifest

**Decision:** Add `derivatives` block to frontmatter, declaring what output channels this lesson targets:

```yaml
derivatives:
  carousel: "carousels/01-commendation-before-commission.md"
  video_script: null
  email_sequence: null
  podcast_outline: null
  course_module: null
  tiktok_script: null
```

When an agent produces a new derivative, it populates the corresponding path. The null values are the forward declaration — they tell future agents which derivatives are still available to produce.

### 6.10 Content provenance

**Research finding:** C2PA (Coalition for Content Provenance and Authenticity) is the emerging standard for tamper-evident content provenance. Google Pixel 10 shipped with native C2PA support in 2026. For text-only markdown, git commit signing provides equivalent guarantees today.

**Decision:**

- Git commit signing is the v1 provenance method. Operator should configure GPG or SSH commit signing at their discretion.
- Frontmatter field added: `provenance_method: "git-signed"`. Reserved for future values: `c2pa-signed`, `multi-signed`.
- When image or video carousel assets are added, they should carry C2PA Content Credentials. Documented future path; not urgent.

### 6.11 Vector embedding reservations

**Decision:** Reserve embedding fields in frontmatter for future population by the edge-function indexing layer:

```yaml
embedding:
  model: null                    # e.g. "text-embedding-3-small"
  dimensions: null
  indexed_at: null               # ISO timestamp of last embedding
  content_hash: null             # hash of lesson body — triggers re-embedding when content changes
```

These are populated at indexing time by the edge function, not by the author.

### 6.12 Content model declaration

**Decision:** Add `content_model` field at top of frontmatter. Valid values:

- `lesson` — the primary teaching unit.
- `carousel` — LinkedIn-ready distillation.
- `scripture_page` — study-notes page for a specific verse.
- `pillar` — long-form aggregator of multiple clusters.
- `adr` — architectural decision record (no frontmatter, but conceptually a content model).

This future-proofs multi-type headless-CMS exposure. A GraphQL or REST layer can filter by `content_model` cleanly.

### 6.13 Licensing

**Decision:** DEFERRED — requires operator input.

Options:

- **All rights reserved (proprietary)** — default for commercial knowledge bases. Protects against redistribution; enables paid licensing.
- **CC-BY-4.0** — allows redistribution with attribution; good for viral reach and SEO, bad for monetization.
- **CC-BY-NC-4.0** — allows non-commercial reuse with attribution; compromise between reach and protection.
- **Custom EULA** — bespoke terms for commercial knowledge base.

**Recommendation based on repo purpose:** All rights reserved for the repository (protects commercial IP), with per-lesson override via `license` frontmatter field if specific lessons should be distributed differently (e.g. a lead-magnet lesson licensed CC-BY for broad reach). `LICENSE` file at repo root to be added once the operator decides.

Until decided: no `LICENSE` file is added, and every lesson frontmatter carries `license: "all-rights-reserved"` as a conservative default.

### 6.14 Accessibility targets

**Research finding:** WCAG 3.0 is in draft (March 2026 working draft, 174 outcomes) but won't reach Recommendation status until 2028-2029. No binding compliance yet. Best practice for knowledge-base content today is WCAG 2.2 AA with a reading-level target.

**Decision:**

- Target reading level: Flesch-Kincaid grade 8-10. Matches the modern podcast-host voice and maximizes audience accessibility.
- Optional frontmatter field: `reading_level: null | <number>` — populated if the author runs a check.
- No image alt text field yet (no images in v1). When images arrive, `images: [{ path, alt, caption, c2pa_signed }]`.

## Consequences

**Positive:**

- Every reasonable future use case has a reserved field, a documented migration path, or both.
- No upfront complexity cost — most new fields default to `null` or sensible defaults in v1.
- Schema is explicitly versioned. When it changes materially, a new ADR supersedes this one.
- Edge-function retrieval, fine-tuning export, i18n migration, monetization gating, derivative generation, and provenance signing all have clear implementation paths when the operator needs them.

**Negative:**

- Frontmatter block grew. Authors now fill more fields per lesson. Mitigation: most fields default to null/false/empty; the SCHEMA.md template shows the full block with comments explaining what to leave alone.
- Risk of over-engineering — some reserved fields may never be used. Mitigation: reserved fields cost only the tokens to parse them; negligible.
- Licensing is unresolved and blocks the conservative-default approach. Operator decision required before first external distribution.

## Follow-up actions

1. Update `SCHEMA.md` to reflect the new frontmatter block in full.
2. Update `TAXONOMY.md` to add controlled vocabulary for `access_tier`, `content_model`, `instruction_style`, expanded `status` states.
3. Update `HANDOFF.md` with this research pass and new decisions.
4. Author Lesson 01 with the future-proofed frontmatter.
5. Ask operator for licensing decision before any external distribution.

## References

- Cosmic JS / Hygraph / Pantheon — headless CMS patterns.
- Unstructured / Weaviate / Firecrawl — 2026 RAG chunking research.
- semantic-release / Changesets — content versioning automation.
- OpenAI chat fine-tuning format documentation.
- W3C WCAG 3.0 working draft, March 2026.
- C2PA Content Credentials specification 2.3.
- MDX / Docusaurus / Tinybird 2026 implementation.
- Decap CMS / MkDocs i18n folder conventions.
