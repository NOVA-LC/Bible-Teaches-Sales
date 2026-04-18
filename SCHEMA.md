# Lesson Schema

Every lesson in `/lessons/` follows this exact structure. Edge functions,
RAG pipelines, grep queries, and the SEO/GEO pipeline all depend on it.
Do not drift.

## File naming

```
lessons/<two-digit-id>-<slug>.md
carousels/<two-digit-id>-<slug>.md
```

Slugs are lowercase, hyphen-separated, chosen for the focus keyword's search
intent. IDs are zero-padded two-digit integers, assigned sequentially.

## Frontmatter

YAML frontmatter is required. Every field below must be present. Use `null`
or `[]` for deliberately empty values — never omit a key. The frontmatter
feeds three downstream consumers: (1) the edge-function retrieval layer,
(2) the JSON-LD generator that emits schema.org markup at render time,
(3) the social/share card generator.

```yaml
---
# === Identity ===
id: "01"
slug: commendation-before-commission
title: "The Commendation Before the Commission"
subtitle: "Why the best closers on your floor were built before they were sharpened."
status: approved              # draft | review | approved | archived
version: "1.0"
created: "2026-04-18"
updated: "2026-04-18"

# === Pillar / cluster architecture ===
content_type: cluster         # pillar | cluster | standalone
pillar_parent: ""             # lesson id of the pillar page this supports (if cluster)
cluster_children: []          # lesson ids of cluster pages supporting this pillar

# === E-E-A-T signals (Google March 2026 core update) ===
author:
  name: ""
  credentials: []             # verifiable expertise — certifications, records, titles
  industries_count: 0         # breadth metric — preferred over years in this repo
  first_hand_claim: ""        # "I was there, I did this" sentence — the E-E-A-T signal
reviewed_by: ""               # optional second pair of eyes
last_reviewed: ""             # ISO date of last factual review

# === Content classification (controlled vocab — see TAXONOMY.md) ===
topics: []                    # thematic tags
mechanics: []                 # sales mechanics taught
nepq_stages: []               # connection | situation | problem_awareness | solution_awareness | consequence | commitment
scriptures: []                # primary text citations (book chapter:verse)
figures: []                   # historical figures referenced
audiences: []                 # who this lesson is for
use_cases: []                 # when/where to pull this lesson
demographics:
  primary: []

# === Distillation pointers ===
distill:
  carousel: ""                # relative path to carousel file
  pull_quotes: []             # array of extracted quotable lines (see GEO rule below)
  pull_statistics: []         # array of { statistic, source } objects (see GEO rule below)

# === SEO ===
seo:
  focus_keyword: ""           # primary phrase targeted
  secondary_keywords: []      # 3-7 supporting phrases
  long_tail_keywords: []      # blog-style long-tail phrases
  search_intent: ""           # informational | navigational | transactional | commercial
  meta_title: ""              # <=60 chars, focus keyword in first 50
  meta_description: ""        # 150-160 chars, focus keyword once, click-worthy
  og_title: ""
  og_description: ""
  og_image: ""
  twitter_card: "summary_large_image"
  canonical_url: ""
  schema_org_types: ["Article"]  # Article | HowTo | Course | BlogPosting — NEVER FAQPage (see note)
  reading_time_minutes: 0
  word_count: 0

# === GEO (Generative Engine Optimization) ===
# Based on Princeton/Georgia Tech research: statistics +41%, quotations +28%
# are the two highest-leverage techniques for AI citation.
geo:
  ai_citable_summary: ""      # 40-60 word standalone summary a model can lift verbatim
  key_claims: []              # the 3-5 bold claims this lesson makes, each citation-ready
  citable_statistics: []      # stats with attribution — every 150-200 words of body ideally
  authoritative_citations: [] # external sources cited in body (URL + publisher)
  expert_quotations: []       # direct quotes from named experts
  passage_retrieval_safe: true # confirms every H2 section stands alone as a passage

# === Internal linking ===
related_lessons: []           # array of lesson ids — drives cluster topology + SEO juice

# === Freeform retrieval hints ===
keywords: []                  # grep/search hints beyond SEO (plain-text matching)
---
```

## Canonical section order

Every lesson uses these H2 headings, in this order. Section names are the
stable anchor contract — do not rename them, do not reorder them. Edge
functions split lessons on these exact headings, and each H2 section must
be **passage-retrieval safe** (self-contained enough to be cited by an AI
model without the rest of the lesson).

1. `## Hook` — one-to-three-line scroll-stopper.
2. `## Setup` — the common mistake or unseen premise.
3. `## Case Study` — the biblical figure / story, told cinematically,
   treated as case evidence not doctrine.
4. `## Pivot` — direct translation to the reader's floor / life / role.
5. `## Mechanic` — the contemporary sales mechanism (NEPQ, tonality, etc.)
   and the concrete practice the reader runs.
6. `## Objection` — the predictable pushback, answered.
7. `## Note on Position` — the democratization beat: any role (solo rep,
   husband, mother, new hire) can run this. Close alone or help others.
   Always included.
8. `## Payoff` — the crystallized principle, earned by the journey above.
9. `## Distillation` — carousel-ready slides, numbered in bold markdown.
10. `## Questions People Ask` — 4-8 Q&A pairs phrased as likely search
    queries. Answers 40-80 words, each self-contained. **Not marked up
    with FAQPage schema** (deprecated) — content exists to rank organically
    for People Also Ask and to feed AI citation.
11. `## Sources` — secular/non-denominational research base plus primary
    text citations.

## Voice rules

- No denominational fingerprint ever reaches the reader.
- Scripture is case evidence, not doctrine.
- Modern cadence. Podcast-host rhythm. Short sentences allowed.
- Specific by call, by moment, by name. Never generic.
- Dual test: does a 22-year-old male D2D rep get value AND does a 58-year-old
  female real-estate agent get value? If not, revise.

## SEO production rules

- `meta_title` includes the focus keyword in the first 50 characters.
- `meta_description` includes the focus keyword exactly once, naturally.
- `slug` reflects the focus keyword's search-intent phrasing.
- H2 anchors slug cleanly (the section name IS the anchor).
- `related_lessons` populated on every lesson once 3+ lessons exist.
- Pillar lessons get `content_type: pillar` and 2,500+ words.
- Cluster lessons link back to their pillar via `pillar_parent` AND in body
  text with the pillar's focus keyword as anchor text.

## GEO production rules *(getting cited by AI)*

These rules come from peer-reviewed research (Princeton/GA Tech) on what
actually gets lifted into AI-generated answers.

- **Statistics density:** include at least one verifiable, attributed
  statistic per 150-200 words of body. Pull each into `citable_statistics`
  in frontmatter with its source.
- **Expert quotations:** include at least one named-expert direct quote per
  lesson. Pull into `expert_quotations` in frontmatter.
- **Authoritative citations:** link to external authoritative sources in
  body. Pull into `authoritative_citations`.
- **Passage independence:** every H2 section must be lift-able as a
  standalone citation. No "as we said above," no orphan pronouns referring
  to the previous section.
- **AI-citable summary:** the `geo.ai_citable_summary` field is a 40-60
  word block a model can quote verbatim when asked "what is [topic]?"
- **Key claims:** 3-5 declarative sentences, each strong enough to be
  cited alone. Avoid hedging ("may," "can sometimes"). AI favors confident,
  attributable assertions.

## Structured data output *(JSON-LD, emitted at render time)*

- **Article schema** is the default for every lesson.
- **HowTo schema** is added when a lesson contains a clear step sequence
  (e.g. "5 diagnostic questions to ask in a 1:1").
- **Course schema** is added for pillar lessons that aggregate clusters.
- **DO NOT emit FAQPage schema.** Google reduced FAQ rich snippet
  eligibility in 2023-2024 and most FAQ markup no longer triggers rich
  results. The `## Questions People Ask` content still serves PAA and GEO;
  schema markup for it is wasted or penalized.
- JSON-LD is the required format. Microdata and RDFa are not used.

## E-E-A-T production rules

Google's March 2026 core update made Experience the primary differentiator.
Every lesson must show:

- **Experience:** first-hand claim in `author.first_hand_claim` that names
  the specific environment, role, or outcome the author lived through.
- **Expertise:** credentials listed in `author.credentials`.
- **Authoritativeness:** external citations in `geo.authoritative_citations`
  from recognized publishers, academic sources, or named experts.
- **Trustworthiness:** `last_reviewed` date kept current; corrections
  logged in version history.

## llms.txt contract

The repo root contains an `llms.txt` file (Jeremy Howard / Answer.AI
proposed standard, 2024). This file gives RAG frameworks, Cursor, Aider,
Continue, and adjacent AI developer tools a curated, Markdown-formatted map
of the highest-value lessons. Update `llms.txt` whenever a new pillar or
approved lesson is added.

## Grep / retrieval contract

- Section headings use the exact strings above (case-sensitive).
- Scripture citations in body text use the form `Book Chapter:Verse`
  (e.g. `Acts 9:27`, `2 Timothy 4:11`) to be greppable.
- NEPQ-related terms use the canonical spellings in TAXONOMY.md.
- Carousel slides in `## Distillation` are numbered with bold markdown
  (`**1.**`, `**2.**`, ...) so extractors can split cleanly.
- Statistics in body use the pattern `<number>% ... — <source>` so a
  lightweight regex can extract them for GEO pipelines.
