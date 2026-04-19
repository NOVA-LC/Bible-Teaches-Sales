# Lesson Schema

Every lesson in `/lessons/` follows this exact structure. Edge functions, RAG pipelines, grep queries, the SEO/GEO pipeline, the fine-tuning export pipeline, and the derivative-asset generators all depend on it. Do not drift.

Schema version: **v2.0** (incorporates [ADR 0006 Future-Proofing Sweep](decisions/0006-future-proofing-architecture.md) alongside ADRs 0001-0005).

## File naming

```
lessons/<two-digit-id>-<slug>.md
carousels/<two-digit-id>-<slug>.md
scriptures/<book-lowercase>-<chapter>-<verse>.md
```

Slugs are lowercase, hyphen-separated, chosen for the focus keyword's search intent. IDs are zero-padded two-digit integers, assigned sequentially.

When `.mdx` lessons are added in the future (for interactive components), an `.md` fallback **must** sit alongside the `.mdx` file and strip the interactivity. Edge-function retrieval always prefers the `.md`.

## Frontmatter

YAML frontmatter is required. Every field below must be present. Use `null` or `[]` for deliberately empty values — never omit a key. The frontmatter feeds seven downstream consumers:

1. Edge-function retrieval layer (RAG)
2. JSON-LD generator (schema.org markup at render time)
3. Social/share card generator (OG tags, Twitter cards)
4. Fine-tuning dataset exporter (JSONL for training)
5. Derivative-asset agents (carousel, video script, email, etc.)
6. Internal-link / cluster-topology graph
7. Access-control / paywall logic

```yaml
---
# === Identity ===
content_model: lesson           # lesson | carousel | scripture_page | pillar | adr
id: "01"
slug: commendation-before-commission
title: "The Commendation Before the Commission"
subtitle: "Why the best closers on your floor were built before they were sharpened."
language: "en"                  # ISO 639-1 code
status: approved                # draft | review | approved | superseded | deprecated | archived
version: "1.0.0"                # SemVer — see versioning discipline below
created: "2026-04-18"
updated: "2026-04-18"

# === Lifecycle / succession ===
supersedes: null                # "<lesson-id>@<version>" if this lesson replaces a prior canonical lesson
superseded_by: null             # populated when this lesson is replaced
changelog: []                   # array of { version, date, change } entries
translation_of: null            # lesson id this is a translation of (null if original)
translations: []                # array of { language, path } for translated versions

# === Pillar / cluster architecture ===
content_type: cluster           # pillar | cluster | standalone
pillar_parent: null             # lesson id of the pillar page this supports (if cluster)
cluster_children: []            # lesson ids of cluster pages supporting this pillar
related_lessons: []             # array of lesson ids — drives cluster topology + SEO juice

# === E-E-A-T signals (Google March 2026 core update) ===
author:
  name: ""
  credentials: []               # verifiable expertise — records held, titles, certifications
  industries_count: 0           # canonical breadth metric — see decisions/0004
  first_hand_claim: ""          # "I was there, I did this" sentence — the Experience signal
co_authors: []                  # array of { name, credentials, contribution_summary }
ai_assisted: true               # disclosure flag — true if AI helped draft
human_reviewed: true            # human editorial pass completed
reviewed_by: ""                 # optional second pair of eyes
last_reviewed: ""               # ISO date of last factual review

# === Content classification (controlled vocab — see TAXONOMY.md) ===
topics: []                      # thematic tags
mechanics: []                   # sales mechanics taught
nepq_stages: []                 # connection | situation | problem_awareness | solution_awareness | consequence | commitment
scriptures: []                  # primary text citations (book chapter:verse)
figures: []                     # historical figures referenced
audiences: []                   # who this lesson is for
use_cases: []                   # when/where to pull this lesson
demographics:
  primary: []                   # e.g. [male-17-48, female-36-87]

# === SEO ===
seo:
  focus_keyword: ""             # primary phrase targeted
  secondary_keywords: []        # 3-7 supporting phrases
  long_tail_keywords: []        # blog-style long-tail phrases
  search_intent: ""             # informational | navigational | transactional | commercial
  meta_title: ""                # <=60 chars, focus keyword in first 50
  meta_description: ""          # 150-160 chars, focus keyword once, click-worthy
  og_title: ""
  og_description: ""
  og_image: ""
  twitter_card: "summary_large_image"
  canonical_url: ""
  schema_org_types: ["Article"] # Article | HowTo | Course | BlogPosting — NEVER FAQPage
  reading_time_minutes: 0
  word_count: 0
  reading_level: null           # Flesch-Kincaid grade, target 8-10

# === GEO (Generative Engine Optimization) ===
# Princeton/GA Tech research: statistics +41%, quotations +28% → top AI citation levers.
geo:
  ai_citable_summary: ""        # 40-60 word standalone summary a model can lift verbatim
  key_claims: []                # the 3-5 bold claims this lesson makes, each citation-ready
  citable_statistics: []        # stats with attribution — every 150-200 words of body ideally
  authoritative_citations: []   # external sources cited in body (URL + publisher)
  expert_quotations: []         # direct quotes from named experts
  passage_retrieval_safe: true  # confirms every H2 section stands alone as a passage

# === Distillation pointers ===
distill:
  carousel: null                # relative path to carousel file
  pull_quotes: []               # extracted quotable lines
  pull_statistics: []           # extracted stats with source

# === Derivatives (multi-channel publishing manifest) ===
derivatives:
  carousel: null                # path when produced, null when reserved
  video_script: null
  email_sequence: null
  podcast_outline: null
  course_module: null
  tiktok_script: null
  book_chapter: null

# === Fine-tuning readiness ===
fine_tuning:
  safe: true                    # okay to include in training export
  instruction_style: ""         # e.g. "therapeutic-inquiry", "narrative-teaching"
  export_path: null             # datasets/<id>.jsonl once generated

# === RAG / embedding (populated by indexer, not by author) ===
embedding:
  model: null                   # e.g. "text-embedding-3-small"
  dimensions: null
  indexed_at: null              # ISO timestamp of last embedding
  content_hash: null            # hash of lesson body; triggers re-embedding on change

# === Access control / monetization ===
access_tier: "public"           # public | premium | enterprise | licensed
preview_only_sections: []       # H2 section names rendered in paywall preview
license: "all-rights-reserved"  # per-lesson override of repo license

# === Content authenticity / provenance ===
provenance_method: "git-signed" # git-signed | c2pa-signed | multi-signed

# === Chunking hints (for RAG) ===
chunking:
  strategy: "semantic_by_h2_with_fallback"
  max_tokens_per_chunk: 500
  overlap_tokens: 0             # 2026 research: no benefit from overlap by default

# === Freeform retrieval hints ===
keywords: []                    # grep/search hints beyond SEO (plain-text matching)
---
```

## Canonical section order

Every lesson uses these H2 headings, in this order. Section names are the stable anchor contract — do not rename, do not reorder. Edge functions split lessons on these exact headings, and each H2 section must be **passage-retrieval safe** (self-contained enough to be cited by an AI model without the rest of the lesson).

1. `## Hook` — one-to-three-line scroll-stopper.
2. `## Setup` — the common mistake or unseen premise.
3. `## Case Study` — the biblical figure / story, told cinematically, treated as case evidence not doctrine.
4. `## Pivot` — direct translation to the reader's floor / life / role.
5. `## Mechanic` — the contemporary sales mechanism (NEPQ, tonality, etc.) and the concrete practice the reader runs.
6. `## Objection` — the predictable pushback, answered.
7. `## Note on Position` — the democratization beat: any role (solo rep, husband, mother, new hire) can run this. Close alone or help others. Always included.
8. `## Payoff` — the crystallized principle, earned by the journey above.
9. `## Distillation` — carousel-ready slides, numbered in bold markdown.
10. `## Questions People Ask` — 4-8 Q&A pairs phrased as likely search queries. Answers 40-80 words, each self-contained. **Not marked up with FAQPage schema** (deprecated) — content exists to rank organically for People Also Ask and to feed AI citation.
11. `## Sources` — secular/non-denominational research base plus primary text citations.

## Voice rules

- No denominational fingerprint ever reaches the reader.
- Scripture is case evidence, not doctrine.
- Modern cadence. Podcast-host rhythm. Short sentences allowed.
- Specific by call, by moment, by name. Never generic.
- Dual test: does a 22-year-old male D2D rep get value AND does a 58-year-old female real-estate agent get value? If not, revise.

## Versioning discipline (SemVer for content)

Per [ADR 0006](decisions/0006-future-proofing-architecture.md):

- **MAJOR (x.0.0)** — lesson fundamentally rewritten or core claim changed. Requires a superseded ADR if the change reflects a principle shift. `supersedes` field set.
- **MINOR (1.x.0)** — new section added, significant expansion, new scripture cited, new carousel slide added. `changelog` entry required.
- **PATCH (1.0.x)** — copy edits, typo fixes, citation URL updates, metadata corrections. `changelog` entry optional.

## Chunking contract (RAG)

- Strategy: `semantic_by_h2_with_fallback`. Edge functions split on H2 headings first; if any H2 section exceeds 600 tokens, sub-chunk on paragraph boundaries within that section.
- Target per H2 section: 200-500 tokens where practical.
- Stable chunk IDs: `<lesson-id>#<section-slug>` (e.g. `01#hook`, `01#case-study`). Sub-chunks append `.1`, `.2`, etc.
- No chunk overlap by default (January 2026 research: no measurable benefit).
- Markdown tables and numbered lists remain intact within chunks.

## SEO production rules

- `meta_title` includes the focus keyword in the first 50 characters.
- `meta_description` includes the focus keyword exactly once, naturally.
- `slug` reflects the focus keyword's search-intent phrasing.
- H2 anchors slug cleanly (the section name IS the anchor).
- `related_lessons` populated on every lesson once 3+ lessons exist.
- Pillar lessons get `content_type: pillar` and 2,500+ words.
- Cluster lessons link back to their pillar via `pillar_parent` AND in body text with the pillar's focus keyword as anchor text.

## GEO production rules *(getting cited by AI)*

From peer-reviewed research (Princeton/GA Tech) on what gets lifted into AI-generated answers.

- **Statistics density:** include at least one verifiable, attributed statistic per 150-200 words of body. Pull into `geo.citable_statistics` with source.
- **Expert quotations:** include at least one named-expert direct quote per lesson. Pull into `geo.expert_quotations`.
- **Authoritative citations:** link to external authoritative sources in body. Pull into `geo.authoritative_citations`.
- **Passage independence:** every H2 section must be lift-able as a standalone citation. No "as we said above," no orphan pronouns.
- **AI-citable summary:** 40-60 word block a model can quote verbatim when asked about the topic.
- **Key claims:** 3-5 declarative sentences, each strong enough to be cited alone. Avoid hedging. AI favors confident, attributable assertions.

## Structured data output *(JSON-LD, emitted at render time)*

- **Article schema** is the default for every lesson.
- **HowTo schema** is added when a lesson contains a clear step sequence.
- **Course schema** is added for pillar lessons that aggregate clusters.
- **DO NOT emit FAQPage schema.** See [ADR 0002](decisions/0002-no-faqpage-schema.md).
- JSON-LD is the required format. Microdata and RDFa are not used.

## E-E-A-T production rules

Google's March 2026 core update made Experience the primary differentiator. Every lesson must show:

- **Experience:** first-hand claim in `author.first_hand_claim` naming the specific environment, role, or outcome the author lived through.
- **Expertise:** credentials listed in `author.credentials`.
- **Authoritativeness:** external citations in `geo.authoritative_citations` from recognized publishers, academic sources, or named experts.
- **Trustworthiness:** `last_reviewed` date kept current; corrections logged in `changelog`; AI assistance disclosed via `ai_assisted` flag.

## Fine-tuning export rules

- Only lessons with `fine_tuning.safe: true` and `status: approved` export.
- Each lesson exports to one or more JSONL training examples in OpenAI chat format.
- Each example ≤ 4096 tokens.
- The 5 diagnostic questions in `## Mechanic` sections are deliberately structured as instruction-tuning pairs (user = rep complaint, assistant = diagnostic question).

## Derivative-asset rules

When an agent produces a derivative (carousel, video script, email, podcast, course module, TikTok, book chapter):

1. Populate the corresponding path in `derivatives`.
2. Each derivative carries the same voice rules and dual-audience tests as the source lesson.
3. Each derivative links back to the source lesson in its own frontmatter (`source_lesson: "<lesson-id>"`).

## Internationalization path

v1 is English-only. All lessons declare `language: "en"`. When a second language arrives:

1. Move all `/lessons/*.md` → `/lessons/en/*.md`.
2. Add `/lessons/<new-lang>/*.md` with the same slugs.
3. Each translated lesson sets `translation_of: "<original-lesson-id>"`.
4. Each original lesson gets entries in `translations: [{language, path}]`.
5. Edge-function path resolution updates to language-aware routing.

Until then, the `translation_of` and `translations` fields sit reserved.

## Accessibility targets

- Reading level: Flesch-Kincaid grade 8-10 target. Populate `seo.reading_level` if measured.
- WCAG 2.2 AA for rendered output.
- WCAG 3.0 compliance target when it ships (~2028-2029).
- Image alt text mandatory when images arrive (not in v1).

## llms.txt contract

`llms.txt` at repo root (Jeremy Howard / Answer.AI proposed standard, 2024). Update whenever a new pillar or approved lesson is added.

## Grep / retrieval contract

- Section headings use the exact strings above (case-sensitive).
- Scripture citations in body use `Book Chapter:Verse` format (e.g. `Acts 9:27`).
- NEPQ-related terms use the canonical spellings in TAXONOMY.md.
- Carousel slides in `## Distillation` numbered with bold markdown (`**1.**`, `**2.**`).
- Statistics in body use `<number>% ... — <source>` pattern for lightweight regex extraction.

## Schema evolution

When this schema changes materially, a new ADR supersedes [ADR 0006](decisions/0006-future-proofing-architecture.md) and the schema version bumps (currently v2.0). Lessons authored under prior schema versions remain valid; migration is a separate governance call.
