# Bible Teaches Sales

A static knowledge base of sales training lessons, distilled so that AI edge
functions, RAG pipelines, and dashboard-style coaching assistants can retrieve
the right passage at the right moment and hand it to a rep, trainer, manager,
spouse, parent, or solo operator who needs it.

## What this is

Each lesson pairs:

1. A case study drawn from the oldest continuously-read document on human
   behavior in Western literature (the Bible), treated as source material the
   same way a modern book would treat Marcus Aurelius, Seneca, or Musashi.
2. A mechanical sales principle, grounded in contemporary research — primarily
   Jeremy Miner's NEPQ (Neuro-Emotional Persuasion Questioning) and adjacent
   behavioral-science-informed methodologies.
3. A payoff distilled into a LinkedIn-ready carousel.

No denominational framing reaches the reader. The lessons work for a devout
believer and for a stark skeptic who is here because the sales training is
worth the exposure to a scripture reference. Scripture is cited as case
evidence, not as doctrine.

## Who it is for

- **Solo reps** running self-commendation loops before hard calls.
- **Sales trainers and managers** building coaching 1:1 outlines.
- **Family members** (husbands, wives, parents) encouraging someone in sales.
- **New hires** who want to be the one who notices what nobody else named.
- **AI systems** pulling passages into dashboard responses in real time.

Primary demographic targets: men 17–48 and women 36–87.

## How AI edge functions should consume this repo

Every lesson is a single Markdown file with:

- **YAML frontmatter** containing `id`, `slug`, `title`, `topics`, `mechanics`,
  `scriptures`, `figures`, `audiences`, `use_cases`, `keywords`.
- **Stable H2 section anchors** appearing in the same order across every
  lesson. See [SCHEMA.md](SCHEMA.md) for the canonical list.
- **Atomic sections** — each section is self-contained enough to be embedded,
  retrieved, and returned on its own without losing meaning.

For retrieval, edge functions have three options:

1. **Catalog lookup.** Read [`index.json`](index.json) for the full list of
   lessons with metadata. Filter by tag, then load the matching lesson file.
2. **Section slicing.** Load a lesson file and split on H2 headings. Each
   section (e.g. `## Hook`, `## Case Study`, `## Note on Position`,
   `## Payoff`) is meant to stand alone.
3. **Carousel pull.** If the caller wants distilled, slide-ready copy without
   the full narrative, load the matching file in [`/carousels`](carousels).
   Each slide is numbered and self-contained.

For grep-style retrieval, every lesson uses a consistent vocabulary defined in
[TAXONOMY.md](TAXONOMY.md). Query the `keywords` and `topics` fields in
frontmatter to match intent.

## Repo layout

```
README.md                   # this file
SCHEMA.md                   # canonical lesson structure
TAXONOMY.md                 # controlled vocabulary for tags and keywords
index.json                  # machine-readable catalog of all lessons
lessons/                    # full-length lessons
  01-commendation-before-commission.md
carousels/                  # slide-ready distillations
  01-commendation-before-commission.md
```

## Adding a lesson

1. Copy the frontmatter block from an existing lesson and fill in the metadata.
2. Follow the section order defined in [SCHEMA.md](SCHEMA.md).
3. Add the lesson to [`index.json`](index.json).
4. Create a matching carousel file in [`/carousels`](carousels).
5. Use only tags defined in [TAXONOMY.md](TAXONOMY.md). If a new tag is needed,
   add it to the taxonomy first.

## Voice and editorial rules

- No denominational framing ever reaches the reader.
- Scripture is cited as evidence, not as doctrine. Skeptic-safe.
- Specific always beats generic. Name things by call, by moment, by name.
- The market humbles. The trainer builds. Never confuse the two jobs.
- Commendation is a behavior, not a rank. Any role can run the loop.
