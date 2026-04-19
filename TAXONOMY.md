# Taxonomy

Controlled vocabulary for every tag field in lesson frontmatter. If a tag
isn't listed here, it doesn't exist yet — add it here before using it in
a lesson.

## topics

Thematic tags. What is the lesson fundamentally about?

- `self-worth` — the internal posture of the seller
- `commendation` — specific, named affirmation as a practice
- `trainer-development` — how trainers and managers show up
- `coaching` — 1:1 and small-group coaching mechanics
- `tonality` — voice, pace, cadence, inflection
- `objection-handling` — responses to prospect pushback
- `prospecting` — top-of-funnel behaviors
- `discovery` — diagnostic / question-led selling
- `closing` — the ask, the commitment, the call to action
- `retention` — keeping reps and customers
- `mindset` — cognitive framing and narrative rehearsal
- `posture` — status, authority, frame control
- `family-support` — non-professional encouragers of salespeople
- `solo-operator` — reps with no team around them
- `leadership-lineage` — building leaders who build leaders

## mechanics

The concrete sales mechanic the lesson teaches.

- `commendation` — specific named affirmation
- `self-commendation` — running the affirmation loop on yourself
- `tonality-control` — deliberate voice/pace modulation
- `pause-discipline` — holding silence
- `reframing` — shifting the interpretation of a situation
- `problem-awareness-questions` — NEPQ stage 3
- `consequence-questions` — NEPQ stage 5
- `therapeutic-inquiry` — low-pressure, discovery-style questioning
- `status-transfer` — prospect persuading themselves
- `posture-from-authority` — internal authority showing up in delivery
- `loss-aversion` — leveraging cost of inaction
- `anchoring` — setting the reference point
- `pattern-interrupt` — breaking an expected conversational rhythm

## nepq_stages

The Jeremy Miner NEPQ (Neuro-Emotional Persuasion Questioning) stages. Use
these exact strings.

- `connection`
- `situation`
- `problem_awareness`
- `solution_awareness`
- `consequence`
- `commitment`

## scriptures

Primary text citations. Use the form `Book Chapter:Verse` or
`Book Chapter:Verse-Verse`. Book names use full form (no abbreviations) for
greppability: `Acts`, `2 Timothy`, `Proverbs`, `Ephesians`,
`1 Thessalonians`, `Matthew`, `Luke`, `John`, etc.

## figures

Historical figures referenced. Use the most common modern spelling.

- `Barnabas`
- `Saul` / `Paul` (use both when both names appear in the same arc)
- `John Mark`
- `Peter`
- `Jesus`
- `Moses`
- `David`
- `Solomon`
- `Nehemiah`
- `Esther`
- `Ruth`
- `Deborah`
- `Joseph` (son of Jacob — disambiguate from Joseph/Barnabas in body)

## audiences

Who the lesson is for. Multiple values allowed.

- `trainer` — sales trainers and enablement staff
- `sales-manager` — first-line people managers
- `director` — second-line leaders and above
- `solo-rep` — individual contributor reps without a team
- `team-rep` — individual contributor reps on a team
- `new-hire` — first 90 days
- `veteran` — 3+ years selling
- `family-supporter` — spouse, parent, sibling of a salesperson
- `founder` — owner-operators and founder-sellers
- `recruiter` — talent acquisition and onboarding
- `coach` — external sales coaches and consultants

## use_cases

When/where to pull the lesson. Multiple values allowed. These map to the
edge function's trigger taxonomy.

- `coaching-1on1` — structured 1:1 between trainer and rep
- `morning-huddle-reframe` — stand-up / team meeting material
- `self-talk-before-hard-call` — solo operator prep
- `encouraging-someone-in-sales` — family / friend support
- `after-a-lost-deal` — post-loss debrief
- `after-a-win` — celebration and codification
- `onboarding-week-one` — new hire first week
- `onboarding-day-one` — new hire first day
- `quota-pressure-midmonth` — mid-cycle motivation
- `monthend-pressure` — end-of-cycle closing
- `objection-rehearsal` — practice session
- `ride-along-debrief` — post-call coaching
- `pipeline-review` — forecast / pipeline conversation

## demographics.primary

Target demographic combinations. Format: `<gender>-<age-range>`.

- `male-17-48`
- `female-17-48`
- `male-36-87`
- `female-36-87`
- `male-48-87`
- `female-17-48`

## content_model

The top-level type of the file. Determines which consumers (edge function, JSON-LD, paywall, fine-tuning export) should index it.

- `lesson` — primary teaching unit in `/lessons/`
- `carousel` — LinkedIn-ready distillation in `/carousels/`
- `scripture_page` — study-notes page in `/scriptures/`
- `pillar` — long-form aggregator in `/lessons/` with `content_type: pillar`
- `adr` — architectural decision record in `/decisions/` (conceptual; no frontmatter)

## content_type

Pillar / cluster designation for SEO topology.

- `pillar` — long-form hub page, 2,500+ words, aggregates clusters
- `cluster` — supporting article linked to a pillar
- `standalone` — neither pillar nor cluster, for now

## status

Lesson lifecycle states.

- `draft` — in progress, not yet reviewed
- `review` — reviewed, awaiting approval
- `approved` — live, canonical; edge functions retrieve these by default
- `superseded` — replaced by a newer lesson; URL preserved for link integrity
- `deprecated` — still accessible, actively discouraged (methodology no longer endorsed)
- `archived` — removed from active retrieval, kept for history

## access_tier

Monetization / access-control primitive.

- `public` — free, indexable, full retrieval
- `premium` — gated, requires authentication
- `enterprise` — licensed to specific organizations
- `licensed` — third-party licensed content with bespoke terms

## license

Per-lesson license override. Repo-level default is all-rights-reserved.

- `all-rights-reserved` — default; no redistribution without permission
- `CC-BY-4.0` — redistribution with attribution
- `CC-BY-NC-4.0` — non-commercial redistribution with attribution
- `CC-BY-SA-4.0` — redistribution with attribution and share-alike
- `custom` — see accompanying `LICENSE-<lesson-id>.md` for bespoke terms

## provenance_method

How content authenticity is signed/verified.

- `git-signed` — git commit signing (v1 default)
- `c2pa-signed` — Coalition for Content Provenance and Authenticity credentials
- `multi-signed` — both git and C2PA

## fine_tuning.instruction_style

The pedagogical voice that training examples from this lesson exemplify.

- `therapeutic-inquiry` — NEPQ-style diagnostic questioning
- `narrative-teaching` — story-led, case-study-first teaching
- `carousel-copy` — punchy declarative slide-length insights
- `coaching-1on1` — trainer-to-rep one-on-one dialogue
- `objection-reframe` — response to prospect pushback
- `self-talk-prep` — solo operator internal monologue

## seo.search_intent

- `informational` — user wants to learn
- `navigational` — user wants to find a specific resource
- `transactional` — user wants to buy or sign up
- `commercial` — user is comparing options

## seo.schema_org_types

Valid values (JSON-LD emitted at render time):

- `Article` — default
- `HowTo` — use when lesson contains an ordered, repeatable procedure
- `Course` — use only on pillar lessons that aggregate multiple clusters
- `BlogPosting` — use sparingly; prefer `Article`

**Never** use `FAQPage`. Google deprecated most FAQ rich snippet eligibility
in 2023-2024. The `## Questions People Ask` section serves People Also Ask
and AI citation organically without markup.

## language

ISO 639-1 two-letter codes. v1 is English-only; other codes are reserved.

- `en` — English (v1)
- `es` — Spanish (reserved)
- `pt` — Portuguese (reserved)
- `fr` — French (reserved)

## chunking.strategy

Edge-function chunking approach for RAG retrieval.

- `semantic_by_h2_with_fallback` — split on H2 headings; sub-chunk on paragraph boundaries if H2 section exceeds max_tokens_per_chunk
- `semantic_by_paragraph` — reserved for future use with dense prose
- `fixed_size` — reserved; not recommended (research shows semantic boundaries beat fixed sizing)

## Canonical spellings (do not drift)

For grep consistency:

- **NEPQ** (not "N.E.P.Q." or "nepq" in body — frontmatter uses lowercase
  `nepq_stages`)
- **Jeremy Miner** (full name on first mention per lesson)
- **7th Level** (not "Seventh Level" or "7thLevel")
- **Neuro-Emotional Persuasion Questioning** (first mention, spelled out)
- **People Also Ask** (capitalized, proper noun)
- **E-E-A-T** (with hyphens, not "EEAT")
- **Generative Engine Optimization / GEO**
- **tonality, pacing, cadence** (the three Miner terms appear together)
