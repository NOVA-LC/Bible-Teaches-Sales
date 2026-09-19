# Work/chat preparation: one article plan, one review, local repairs

Use this workflow for single-article Watchtower preparation inside Work/chat without an API key. Python
makes no model calls: the session model writes the plan/comments and a separate
reviewer evaluates the consolidated article. It replaces the old default of
fresh writer and critic calls per paragraph. Existing SDK automation is separate. CBS and Spiritual Gems retain their
existing workflows; this checkpoint export does not support multiple documents
or Bible verse anchors.

The approved final voice is the quality target. Read the scoped `../AGENTS.md` and
canonical quality instructions once. Keep two or three approved examples nearby.
Use [SKILL_ROUTING.md](SKILL_ROUTING.md) to select applicable skills and resolve
the older recipe's production settings against the current generator.
Reuse source research across paragraphs. Fetch/verify additional scripture or
historical evidence only when a planned insight needs it; never invent evidence
or remove depth just to avoid research. Save relevant findings with URLs in the
local run's input folder, and supply them to the writer and reviewer.

## 1. Save the inputs once

Commands below run from `tools/jwl_notes`. Use an ignored parent folder such as
`agent/runs/2026-09-20/`, with `inputs/` for input files and a separate `session/`
for checkpoints. The initial session directory must be empty or absent.

Save the official article HTML as `inputs/article.html` and verify its identity,
date and visible paragraph/question mapping. Existing `discover_week` and
`jwl_notes.fetch_wol_article` can fetch the official source; do not refetch it on
every retry. Write `inputs/metadata.json` with these fields (values are illustrative):

```json
{"article_title":"Article title","article_source":"The Watchtower—Study Edition, July 2026","study_date":"2026-09-20","key_symbol":"w","issue":20260700,"document_id":2026483,"url":"https://www.jw.org/en/library/magazines/..."}
```

```bash
python -m agent.prep_inputs article \
  --html agent/runs/2026-09-20/inputs/article.html \
  --metadata-json agent/runs/2026-09-20/inputs/metadata.json \
  --output agent/runs/2026-09-20/inputs/article.json
```

Optional: extract **only** the approved article's notes from a local backup:

```bash
python -m agent.prep_inputs references --backup /path/to/approved.jwlibrary \
  --document-id 2026483 --key-symbol w \
  --output agent/runs/2026-09-20/inputs/all-approved.json
```

Select two or three representative approved comments into `inputs/references.json`
(a JSON array of strings). Keep exact wording. The importer reads the original
backup without changing it; it does not assume all other notes are approved.
Never commit these inputs. Omit `--reference-json` only when none are available.

When using additional research or real personal experiences, save
`inputs/context.json` before preparation. Research records contain `id`, `claim`,
`source_url`, `evidence`, and `kind` (`quotation`, `paraphrase`, or `inference`).
Experience records contain `id`, the supplied `text`, and a traceable `source`.
Only include evidence that was actually obtained and experiences actually supplied
by the operator; never lift a first-person prompt example into personal history.

```json
{"research":[{"id":"r1","claim":"The supported finding","source_url":"https://example.org/source","evidence":"Short exact support or a faithful sourced summary","kind":"paraphrase"}],"experiences":[{"id":"e1","text":"The actual user-provided experience","source":"Locator for the originating user message or approved note"}]}
```

The example above describes the shape, not usable evidence. Add
`--context-json inputs/context.json` (using the actual full path) to `prepare`.
Omit that flag when neither input is needed; both lists default to empty. The
engine validates records but the reviewer must verify their truth and provenance.
Every writer/reviewer/repair packet includes this saved context and its fingerprint.

```bash
python -m agent.prep_session prepare \
  --article-json agent/runs/2026-09-20/inputs/article.json \
  --reference-json agent/runs/2026-09-20/inputs/references.json \
  --run-dir agent/runs/2026-09-20/session
```

Identical `prepare` resumes and recreates request packets. Supply the same context
and references on resume. Changed source, references, context, prompt policy or
gate code refuses reuse: use a new run after explaining
the change. Never reset solely to get another repair allowance. Checkpoint locking
uses POSIX `fcntl` (Linux/macOS). Shared question anchors are intentional; printed
paragraph numbers and question `data-pid` are different identifiers.

## 2. Plan the entire progression before drafting

Read `session/draft-request.json`: full source, references and canonical prompts.
Save `inputs/plan.json` as an array covering every question-bearing paragraph:

```json
[{"paragraph_number":10,"purpose":"The teaching developed here","angle":"The distinct contribution of this comment","comment_type":"F","herd_distinctive_moves":["H1"],"evidence_ids":[],"reserved_for_later":[{"paragraph_number":14,"point":"The later payoff to preserve"}]}]
```

The example is one row; the real plan must cover the whole article. Reserve future
points explicitly. Plan type variety, mechanics, scenes and required features
before prose, without manufacturing experiences. The engine refuses more than 18
question-bearing paragraphs under the existing six-type/three-per-type cap. If
Type B has no authentic experience seed, usable capacity can be lower; resolve
that policy conflict upfront rather than drafting an impossible distribution.

Each row requires a valid `comment_type`. The existing article gates run against
the plan: use the canonical `tagged_beats`, `domestic_scene`, and
`herd_distinctive_moves` fields wherever needed to allocate the required features.
The same gates still check completed drafts; planned metadata cannot prove the
finished content contains those features. A Type B row needs `experience_id`
matching a saved experience; Type H needs nonempty `evidence_ids` matching saved
research. Other rows may reference research too. Drafts and repairs must retain
their planned types. Resolve the plan before drafting; it becomes immutable with
the first submitted draft. Only selected standalone type prompts are included
after planning; the common prompt remains the complete quality contract.

```bash
python -m agent.prep_session plan --run-dir agent/runs/2026-09-20/session \
  --input agent/runs/2026-09-20/inputs/plan.json
```

## 3. Draft once and checkpoint

Write `inputs/drafts.json` as an array of full canonical comment payloads, each
with its integer `paragraph_number`. See the output schema in
`prompts/comment_agent.md` and its type prompt. Do not substitute content-only
objects: structural quality metadata is still required. Reuse researched sources
and exact scripture wording; the code does not supply missing research.

```bash
python -m agent.prep_session draft --run-dir agent/runs/2026-09-20/session \
  --input agent/runs/2026-09-20/inputs/drafts.json
```

Partial draft batches are supported to survive context limits. Deterministic
failures are printed before acceptance. Fix a specific invalid field or failing
comment, not the entire set. Complete coverage is required before quality review.
Do not cycle speculative drafts in pursuit of an abstract score.

## 4. One consolidated independent review

Give a reviewer the current `session/review-request.json`, approved references,
canonical quality standard and the saved research. It contains the complete
article, plan, drafts, accepted comments, article-gate failures and exact response
shape. Review actual accuracy, paragraph fit, future-point reservations, voice,
depth and all seven existing critic criteria. All checks must be literal booleans;
provide concrete evidence and pinpoint every failure. Do not rubber-stamp.
The additional `evidence_supported` check verifies that the actual claims follow
from supplied research and that personal experiences have authentic provenance.
It must not treat a source URL or populated field as proof.

Save its response as `inputs/review.json`, preserving `input_sha256` exactly:

```bash
python -m agent.prep_session review --run-dir agent/runs/2026-09-20/session \
  --input agent/runs/2026-09-20/inputs/review.json
```

Every pending paragraph requires a verdict. Stale/partial reviews are rejected.
When article gates pass, positive verdicts freeze exact comments. If article gates
fail, identify the affected paragraphs with failed verdicts; positive comments
remain pending until the global defect is fixed, preventing an unrepairable lock.

## 5. Repair only named failures, then export

`session/repair-request.json` supplies each old draft and precise failed checks.
Preserve successful wording, insights and emotional effect. Submit only the failed
paragraphs in `inputs/repairs.json`:

```bash
python -m agent.prep_session repair --run-dir agent/runs/2026-09-20/session \
  --input agent/runs/2026-09-20/inputs/repairs.json
```

One repair submission per failed paragraph is persisted before validation. A
malformed or still-failing repair blocks export; it never silently consumes the
old accepted text or opens an unlimited retry loop. Re-review the pending repairs
using the **new** review-request hash, with all accepted comments still in context.
Do not redraft locked comments. If a repair reveals a necessary change to a locked
comment, stop and explain the specific conflict rather than overriding its lock.

```bash
python -m agent.prep_session export --run-dir agent/runs/2026-09-20/session \
  --output agent/runs/2026-09-20/comments.json
```

Export requires complete coverage, passing current gates, unchanged accepted
payloads and no unresolved failures. Output uses the existing injector wire shape;
wording remains exact. **This is comment-only output**, with no underlines. Use the
existing underline workflow when full weekly preparation is requested, preserving
the full-answer underline doctrine. Injection/packaging is deterministic; don't
ask another writer to polish accepted comments during packaging.

Before resuming, inspect the saved state without rewriting it:

```bash
python -m agent.prep_session status --run-dir agent/runs/2026-09-20/session
```

It reports the next command, missing drafts, pending review, accepted paragraphs,
unresolved defects, consumed repairs and checkpoint operation counts. The
`events` in `state.json` retain original failure reasons after a successful repair.
Counts cover saved operations only, not rejected calls, model work or tokens.
The `export` next action means comments are eligible for export; it does not claim
underlines or packaging are complete. A blocker must be resolved explicitly;
status never clears one or grants another repair attempt.

This policy revision invalidates earlier fingerprints. Keep prior runs intact;
their original code/policy revision can still resume them. Never reset a run to
replenish its repair allowance. Record any measured usage separately outside git.
No percentage savings or identical model quality has been established by the
offline regression tests. The old API pipeline is not proof of what consumed a
Fable/Astra session's quota.
