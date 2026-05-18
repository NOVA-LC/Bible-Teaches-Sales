# HANDOFF — jwl_notes/agent

> This file covers the **autonomous WT/midweek/CBS comment generator** under `tools/jwl_notes/agent/`. It is NOT the root `HANDOFF.md` (that one is for the `/lessons/` writing track). Two separate work streams.
>
> Read this before starting a new session on the comment pipeline.

**Last updated:** 2026-05-15
**Branch:** `claude/jwl-notes-injector-YnbfN`
**Pipeline version:** v5 (tool-using agents, Phase 3 shipped)

---

## Current state — three working targets, all on the lesson agent

| Target | Drafter | Output | Status |
|---|---|---|---|
| `wt` | Sunday Watchtower study | `comments/<date>-w.json` | ✅ Shipped May 17 (20/20 comments at $5.72, +$0.29 retry for ¶14/¶19) |
| `cbs` | Congregation Bible Study (lfb lessons) | `comments/<date>-lfb-<lesson_doc_id>.json` (one per lesson) | ✅ Code shipped + 73-assertion regression suite passing; first clean production run pending |
| `gems` | Spiritual Gems verse comments | `comments/<date>-spiritual-gems-<bookchapter>.json` (one per chapter) | ✅ Shipped May 17 (4/4 verse comments at $0.57) |

CLI:
```bash
python -m agent.lesson_agent --study-date 2026-05-24 --target wt
python -m agent.lesson_agent --study-date 2026-05-24 --target cbs
python -m agent.lesson_agent --study-date 2026-05-24 --target gems
```

Auto-resume is on by default. Add `--fresh` to wipe checkpoint state. `--paragraphs N,M` for cheap slices.

---

## Architecture

```
                          ┌────────────────────────────┐
                          │  python -m agent.lesson_agent │
                          │  --study-date YYYY-MM-DD     │
                          │  --target {wt|cbs|gems}      │
                          └─────────────┬─────────────┘
                                        ↓
   ┌────────────── LESSON AGENT (lesson_agent.py) ─────────────────┐
   │ Article-level orchestrator. 10 tools, 100-turn budget,         │
   │ $20 article-level kill switch, 5-cycle redraft cap.            │
   │ Auto-resume from disk; per-paragraph checkpoint after commit.  │
   │ For target=gems: short-circuits to gems_run.run_gems.          │
   │ For target=cbs: per-lesson JSON output (synthetic pid offset). │
   └────────────────┬─────────────────────────────┬─────────────────┘
                    ↓ per paragraph                ↓ per paragraph
   ┌── COMMENT AGENT (comment_agent.py) ──┐  ┌── UNDERLINE AGENT (underline_agent.py) ──┐
   │ 6 tools: suggest_type, fetch_research,│  │ 2 tools: verify_phrase_verbatim,         │
   │  look_up_insight, check_register,    │  │  commit_underlines.                       │
   │  score_with_critic, commit_comment.  │  │ Deterministic regex pre-check kills      │
   │ Critic OUT of commit (Flip 1) —      │  │  "Read X:Y-Z" deferred paragraphs        │
   │  opt-in via score_with_critic.       │  │  at zero cost.                            │
   │ commit_comment pre-gates forbidden_  │  │ Non-yellow > 8 words silently filtered   │
   │  types + extra_constraints + the     │  │  at commit time (Flip from May 14 push:  │
   │  per-comment gates (1/1b/1c/3/9/10). │  │  yellows ship even if non-yellow doesn't │
   │ 20-turn budget per paragraph.        │  │  fit). 12-turn budget per paragraph.     │
   └───────────────────────────────────────┘  └───────────────────────────────────────────┘
```

For `gems`:
```
GEMS_RUN (gems_run.py) — chained pipeline (single-prompt style)
  1. discover_week → Bible reading range (book, chapters)
  2. Fetch each chapter HTML, extract verse text
  3. Sonnet picker chooses 4 verses across the range
  4. verse_comment.md drafter per verse with ≤5 chained retries
  5. One Bible-mode JSON per chapter
```

---

## Discipline — before any production API run

**Run `python -m agent._test_e2e_free`.** ~86 seconds, $0, 73 assertions across:

- `load_dotenv` empty-env override
- Underline `_DEFERRED_BODY_RE` (10 union cases)
- Underline commit: non-yellow > 8 words filter
- Underline commit: deferred-to-scripture escape hatch
- Comment agent `_check_constraints` (forbidden_types + 3 force_* guards)
- Comment agent TOOLS schema invariants
- Lesson agent TOOLS schema + enum (includes cbs/gems)
- Article-level Gate 11 cap boundary
- CBS scrape + commit_lesson split (delegates to `_test_cbs_split`)
- Lesson agent checkpoint save→load round-trip
- `assemble_comments_json` skip-empty-underlines (injector crash prevention)
- WT scrape on cached May 17 article
- Discover week: WT + CBS DocIds (both weeks) + Bible reading
- Every shipped `comments/*.json` validates via `jwl_notes.load_comments`
- Token-range parity: every shipped underline phrase resolves via `find_token_range`

If anything fails, fix the test/code first — do NOT burn API trying to debug at runtime.

There's also `_test_cbs_split.py` (47 assertions, ~2s) for the CBS-specific regression.

---

## Files

```
tools/jwl_notes/agent/
├── lesson_agent.py        # whole-lesson orchestrator agent (Phase 2/3)
├── comment_agent.py       # per-paragraph tool-using comment drafter
├── underline_agent.py     # per-paragraph tool-using underline picker
├── gems_run.py            # Spiritual Gems verse-mode (chained pipeline)
├── build_week.py          # legacy chained-pipeline orchestrator (kept for compat)
├── discover_week.py       # week metadata (WT DocId + workbook + CBS lessons + Bible reading)
├── research.py            # WOL deep-brief fetcher (NWT + xrefs + footnotes)
├── workers.py             # SDKWorker — used by comment_agent for suggest_type + critique
├── gates.py               # 11 deterministic gates + run_per_comment_gates / run_article_gates / run_underline_gates
├── email_run.py           # Resend digest sender (called by weekly-prep.yml)
├── _test_e2e_free.py      # comprehensive regression suite — RUN BEFORE ANY PRODUCTION RUN
├── _test_cbs_split.py     # CBS-specific regression test (47 assertions, ~2s)
├── prompts/
│   ├── comment_agent.md          # 473-line system prompt for the comment agent (B1-B2-R1-R2-N1 from review)
│   ├── lesson_agent.md           # ~200-line system prompt for the lesson agent
│   ├── underline_agent.md        # underline doctrine + tool-use protocol
│   ├── verse_comment.md          # gems verse drafter (chained pipeline)
│   ├── _shared_core.md           # universal non-negotiables (mandate 1-5)
│   ├── select_comment_type.md    # type selector (suggest_type tool wraps this)
│   ├── critic_gate6.md           # critic worker prompt
│   ├── paragraph_comment.md      # legacy chained drafter (still loaded by build_week)
│   ├── paragraph_underlines.md   # legacy chained underline drafter
│   └── types/A..H_*.md           # 6 typed drafters (loaded by comment_agent system prompt)
├── runs/<date>-<target>-lesson/  # per-run state + gates.log (gitignored)
│   ├── gates.log                  # full gate trace for the run
│   └── state/                     # checkpoint for auto-resume
│       ├── meta.json
│       ├── comments/<body_pid>.json
│       └── underlines/<body_pid>.json
├── .env                           # ANTHROPIC_API_KEY + RESEND_* (gitignored)
├── README.md
└── RUNBOOK.md
```

---

## What was shipped this week (May 14-15)

### Phase 1 — Comment agent (replaces `_draft_with_gates`)
- 6 tools: `suggest_type`, `fetch_research`, `look_up_insight`, `check_register`, `score_with_critic`, `commit_comment`
- Critic OUT of commit (opt-in via `score_with_critic`) — saves $0.10-0.30 per draft revision
- `commit_comment` pre-gates: `forbidden_types`, `force_domestic_scene`, `force_herd_move`, `force_invert_mode`, `experience_seed` for Type B
- Dual-variant `commit_comment` input: full payload OR `{"error": "..."}` for self-declared give-up
- 20-turn budget; auto-resume; `--use-agent-comments` flag on `build_week.py`

### Phase 2 — Lesson agent (whole-article orchestrator)
- 10 tools incl. `get_status`, `redraft_comment`, `run_article_gates`, `commit_lesson_failure`
- $20 article-level kill switch (hard); 5-cycle article-redraft cap
- Per-paragraph checkpoint to disk; auto-resume on next run; `--fresh` flag to wipe
- Article-level redraft heuristics for Gate 4/5/11 failures
- Cost rollup: shared `CostTracker` passed into both subagents; per-article spend rolls up

### Phase 3 — Multi-target (`cbs`, `gems`) + production hardening
- `--target gems` via standalone `gems_run.py` — 4 verse comments distributed across Bible reading chapters (Sonnet picker + verse_comment.md drafter)
- `--target cbs` via lesson_agent with CBS-aware `scrape_cbs_lesson` and per-lesson JSON output (synthetic body_pid offset prevents resume-cache collisions across lessons; original pids restored at JSON-write time)
- `discover_week` extended: `cbs_document_ids`, `cbs_lesson_label`, `cbs_publication`
- CBS DocId parser uses frequency + label-count filter (nav-link DocIds excluded)
- Curl-fallback HTTP fetch lifted to `jwl_notes.py`, `research.py`, `discover_week.py`, `comment_agent.py` (urllib hangs reliably on WOL search/meetings/some article URLs)
- Comprehensive regression suite — `_test_e2e_free.py`

---

## Cost expectations (May 17 actual)

| Run | Comments | Cost |
|---|---|---|
| WT full article | 18/20 first pass, 20/20 after retry | $5.72 + $0.29 retry = **$6.01** |
| CBS lesson 84 only (lesson 85 broken by pid-collision bug, since fixed) | 4 paragraphs | $1.77 |
| Gems | 4 verse comments | $0.57 |
| **Total May 17** | | **~$8.35** |

Expected May 24 production cost (all three targets clean): **$7-10** total. Lesson agent's $20-per-article kill switch covers individual-target overruns.

---

## Known issues / next priorities

1. **mwb LAC discussion parts** — the workbook's "Living as Christians" section has talk-style items (Local Needs, Apply Yourself). The `--target mwb` path is not wired; the workbook HTML doesn't match the WT-style scraper, and most LAC items aren't audience-comment moments anyway. Skip unless you specifically want Apply-Yourself-discussion comments.
2. **Comment agent MAX_TURNS=20 sometimes tight** — saw 2/20 paragraphs hit cap on May 17 WT. Tolerance band (0-3 failed = conditional ship) absorbed it. Could bump to 25 if it bites again.
3. **Cross-paragraph gem memory** — agent doesn't currently remember what aha/cross-ref it used in previous paragraphs of the same article. Variety is enforced at type + mechanic + relationship + Herd-move levels via prior_state; gem-content variety is not. Deferred to v2.
4. **`weekly-prep.yml` cron** — currently invokes `agent.build_week` (chained pipeline). Should be swapped to `agent.lesson_agent` with the three-target sequence. See "Cron wiring" section below.

---

## What to avoid

- **Don't run a full WT article to "test" a code fix.** Run `_test_e2e_free.py` first ($0). Then a 1-paragraph slice (`--paragraphs N`, ~$0.20) to verify the wire. Only then full run. This rule cost ~$4 to learn the hard way.
- **Don't commit `.env`** — `ANTHROPIC_API_KEY` and `RESEND_API_KEY` are operator-rotatable secrets.
- **Don't try to recover failed paragraphs by bootstrapping state from the shipped JSON.** The shipped JSON doesn't carry `comment_type`/`tagged_beats`/`domestic_scene` metadata; bootstrap will mis-tag and trigger article-level gate cascades. If a paragraph fails on a real run, call the comment agent directly (standalone retry pattern — see May 17 ¶14/¶19 retry).
- **Don't change the default model from `claude-sonnet-4-6`** in `workers.py` or any agent file — operator explicitly chose Sonnet for the pipeline economics.
- **Don't relax Mandate 5 / Gate 10** to make builds pass. A clean-but-empty comment that doesn't transform the listener is a failure, not a pass.
- **Don't bypass the non-yellow filter in `underline_agent.commit`.** Yellow (the answer) is the only required color; non-yellow phrases over 8 words are silently dropped — that's the doctrine after the May 14 push.

---

## Cron wiring (weekly-prep.yml)

Production cron should invoke the lesson agent three times in sequence:

```yaml
- name: Pre-flight regression suite (zero API)
  working-directory: tools/jwl_notes
  run: python -m agent._test_e2e_free

- name: Generate WT prep JSON
  working-directory: tools/jwl_notes
  env: { ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }} }
  run: python -m agent.lesson_agent --study-date "${{ steps.study_date.outputs.study_date }}" --target wt

- name: Generate CBS prep JSON(s)
  working-directory: tools/jwl_notes
  env: { ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }} }
  run: python -m agent.lesson_agent --study-date "${{ steps.study_date.outputs.study_date }}" --target cbs

- name: Generate Spiritual Gems verse comments
  working-directory: tools/jwl_notes
  env: { ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }} }
  run: python -m agent.lesson_agent --study-date "${{ steps.study_date.outputs.study_date }}" --target gems

- name: Email all generated JSONs via Resend
  working-directory: tools/jwl_notes
  env: { RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}, RESEND_FROM: ${{ secrets.RESEND_FROM }}, RESEND_TO: ${{ secrets.RESEND_TO }} }
  run: python agent/email_run.py --study-date "$STUDY_DATE" --comments-glob "comments/${STUDY_DATE}-*.json"
```

See the actual `.github/workflows/weekly-prep.yml` for the full workflow.

---

## Agent SDK migration (Phase 1/2/3) — complete

The five-step migration documented in the prior HANDOFF version:
- ✅ Step 1: `agent_v1.py` with one tool (proven concept; superseded by full agents)
- ✅ Step 2-3: `check_register` + `score_with_critic` tools (in `comment_agent.py`)
- ✅ Step 4: `commit_comment` tool with deterministic-gate verdict
- ✅ Step 5: `_draft_with_gates` replaced by `comment_agent.draft_comment_with_agent` (behind `--use-agent-comments` flag on `build_week.py`; lesson agent uses it natively)
- ✅ Phase 2 bonus: whole-article lesson agent (`lesson_agent.py`)
- ✅ Phase 3 bonus: `cbs` + `gems` targets, regression suite, curl-fallback HTTP across all fetchers
