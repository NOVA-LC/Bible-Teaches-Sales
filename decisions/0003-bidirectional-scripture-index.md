# ADR 0003 — Bidirectional Scripture Indexing

- **Status:** accepted
- **Date:** 2026-04-18
- **Deciders:** Nova (operator), initial scaffolding session

## Context

Every lesson cites one or more scripture references as case evidence. Users, AI agents, and the edge function retrieval layer need to be able to enter the knowledge base from **either** direction:

1. **Topic-first.** "How do I coach a struggling sales rep?" → land on Lesson 01.
2. **Scripture-first.** "What does Acts 9:27 teach about business leadership?" → land on a page that surfaces Lesson 01 *and* any future lesson that also cites Acts 9:27.

The operator framed this as wiring the repo "like study notes correlated to certain scriptures so you can find it either way" — a bidirectional model.

Unidirectional (topic-only) indexing leaves the scripture-first entry point on the table, which sacrifices:

- A long-tail SEO surface (each scripture + business topic combination has measurable search volume).
- A GEO passage-retrieval surface (AI engines citing scripture-anchored answers).
- A compounding commentary effect (as the corpus grows, each verse page aggregates more commentary, increasing its authority).

## Decision

Build **bidirectional indexing** with three components:

### 1. `/scriptures/` — study-notes pages, one per verse

- Filename format: `<book-lowercase>-<chapter>-<verse>.md` (e.g. `acts-9-27.md`, `2-timothy-4-11.md`).
- Each page has YAML frontmatter, the verse text (neutral modern translation, attributed), a list of every lesson citing it, and pull-quotes from those lessons.
- Each page is its own SEO long-tail landing page and GEO passage-retrieval asset.
- When a new lesson cites an existing verse, the page is updated — it grows over time.

### 2. `/indexes/by-scripture.json` — machine-readable reverse index

Maps each scripture reference to an array of lesson IDs that cite it. Structure:

```json
{
  "Acts 9:27": ["01"],
  "2 Timothy 4:11": ["01"],
  "Proverbs 16:18": ["01"]
}
```

Edge functions query this file for O(1) scripture-to-lessons lookup instead of scanning all frontmatter.

### 3. Cross-links in body text

Lesson bodies link out to the relevant `/scriptures/<verse>.md` pages in-context. Scripture pages link into the lessons that cite them. This builds the internal linking topology that drives topical authority (see [`decisions/0006-pillar-cluster-architecture.md`](0006-pillar-cluster-architecture.md) once written).

## Consequences

**Positive:**

- Dual entry point for users and edge functions.
- Long-tail SEO per scripture page.
- GEO passage retrieval per scripture page.
- Compounding authority — each scripture page grows in commentary and authority as the corpus grows.
- Study-notes framing gives the product a living-canon quality rather than flat-blog feel.

**Negative:**

- Every new lesson requires updating 1–N scripture pages and the `by-scripture.json` index.
- Manual maintenance is tractable at low lesson count (< ~10) but should be automated by a generator script at scale. Noted as a next-step in HANDOFF.md.
- The scripture text displayed on each page must be chosen from a translation whose licensing permits reproduction. Use public-domain or permissively-licensed translations (e.g. World English Bible, ASV 1901). Note the translation on each page.

## Compliance check

For every new lesson:

- [ ] Every scripture cited in the lesson has a corresponding `/scriptures/<verse>.md` page.
- [ ] Every such page lists the lesson in its `lessons_citing` array.
- [ ] `/indexes/by-scripture.json` contains an entry for every scripture in the lesson, mapped to the lesson ID.
- [ ] Body text links to the scripture page at first citation.

## References

- [`SCHEMA.md`](../SCHEMA.md) — scriptures field and grep contract.
- [`/scriptures/`](../scriptures/) — implementation.
- [`/indexes/by-scripture.json`](../indexes/by-scripture.json) — reverse index.
