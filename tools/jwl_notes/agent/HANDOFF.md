# HANDOFF — jwl_notes/agent

> This file covers the **autonomous WT/midweek/CBS comment generator** under `tools/jwl_notes/agent/`. It is NOT the root `HANDOFF.md` (that one is for the `/lessons/` writing track). Two separate work streams.
>
> Read this before starting a new session on the comment pipeline.

**Last updated:** 2026-05-14
**Branch:** `claude/jwl-notes-injector-YnbfN`
**Pipeline version:** v4 (typed free-thinking)

---

## Current state

The v4 typed pipeline ran end-to-end on the May 17 WT ("Trust in the Sovereign Ruler of the Universe", DocId 2026321) and **refused to ship**. The *comment* drafter is solid; the *underline* drafter and one article-level gate are the bottlenecks.

### What works
- **Research pass** (`research.py`) — fetches NWT verse text + 3-verse context + up to 5 cross-refs + footnotes from WOL for every cited scripture. Verified on Isa 60:1, Job 1:6-8, John 9:1-7.
- **Type selector + typed drafters** (`prompts/select_comment_type.md` + `prompts/types/A-H_*.md`) — Sonnet 4.6 picks A/B/C/D/F/H per paragraph, then a type-specific drafter renders. Selector showed real contextual judgment on May 17 (F for grief, H for Hebrew idiom, D for verse chains).
- **Mandate 5 / Gate 10** — audience-state transformation (release/equip/invert) enforced.
- **Article-level gates** — Gate 2 (opener variety, soft cap 2), Gate 4 (domestic-scene quota), Gate 5 (Herd-move quota) all passed on May 17.
- **Critic (Gate 6)** — moved/encouraged/memorable check, approved every comment.
- **Fast-fail on billing/auth errors** — no more 25-retry-loops on dead credentials.

### What broke on the May 17 run
- **Gate 11 (comment-type variety)** — Type F used 4× on ¶[1, 2, 9, 14], cap is 3. Selector has soft variety language but no hard `forbidden_types` constraint passed through from orchestrator.
- **Underline failures on ¶9, ¶11, ¶13** — 25 retries each. ¶11's body literally just says "Read Job 42:10-13" with no narrated answer phrase to extract; the underline worker correctly self-rejected all 25 attempts. ¶18/¶19/¶20 also showed non-yellow phrases exceeding the 8-word cap and yellows that paraphrase instead of verbatim-quoting.
- **Citation parser misses HTML-only refs** — ¶2 cited 2 Tim 3:1 but parser returned 0 verses. Citations embedded only in `<a class="b">` markup (no plain-text "2 Tim 3:1") aren't picked up.

### What landed clean on May 17
¶3, 4, 5, 6, 7, 8, 10, 14, 15, 16, 17, 18, 19, 20 — all gates green including critic. Type distribution actually rich: A, B, C, D, F, H all used.

---

## Files

```
tools/jwl_notes/agent/
├── build_week.py          # orchestrator — 4-phase typed pipeline per paragraph
├── discover_week.py       # finds WT/midweek/CBS DocIds for a given week
├── research.py            # WOL deep-brief fetcher (NWT + xrefs + footnotes)
├── workers.py             # SDKWorker (anthropic SDK) + draft_typed_comment()
├── gates.py               # 11 gates (Mandate 1-5 + Gate 10 + Gate 11 variety)
├── email_run.py           # Resend digest sender
├── prompts/
│   ├── _shared_core.md             # universal non-negotiables (5 mandates)
│   ├── select_comment_type.md      # phase 1 — picks A/B/C/D/F/H
│   ├── types/A..H_*.md             # phase 2 — type-specific drafters
│   ├── paragraph_comment.md        # legacy single-prompt drafter (kept for compat)
│   ├── paragraph_underlines.md     # underline drafter — NOT yet Mandate-5'd
│   ├── verse_comment.md            # Spiritual Gems verse-mode (not wired)
│   └── critic_gate6.md             # audience critic
├── runs/2026-05-17-w-2026321/      # last run artifacts (gates.log)
├── .env                             # ANTHROPIC_API_KEY (gitignored — keep it that way)
├── README.md
└── RUNBOOK.md
```

---

## Next steps (priority order)

1. **Hard `forbidden_types` passthrough (cheap, 30 min).** In `build_week.py`, track types used so far; once a type hits Gate 11's soft cap (2), pass `forbidden_types=["F"]` to `worker.select_comment_type()`. Update `select_comment_type.md` to honor it as a hard constraint, not a preference. This alone would have landed May 17.

2. **Underline pipeline rework (the big one).** Currently `draft_underlines()` uses the legacy single-prompt path — Mandate 5 doesn't apply. Need:
   - Detect "Read X:Y-Z" paragraphs (body has no narrated answer) and return `{"deferred_to_scripture": true}` instead of looping 25 times
   - Wrap underline drafter in the typed-prompt + shared-core architecture
   - Add per-type underline rules (Type D = highlight verse-chain progressions, Type H = highlight the corrected idiom, etc.)

3. **Fix citation parser** — when paragraph body has `<a class="b" href="...">` markup links, extract scripture refs from the `data-anchor` / parsed URL too, not just plain text.

4. **Wire verse-mode for Spiritual Gems.** `verse_comment.md` exists; `build_week.py` has no `--target spiritual-gems` mode. Need a separate orchestrator path that takes a verse string and runs research → verse-specific drafter → gates.

5. **Checkpoint/resume.** Right now an article-level Gate 11 fail tosses 20 paragraphs of work. Pickle the per-paragraph drafts after each phase so a Gate 11 fail can retry just the offending paragraph instead of restarting.

6. **(Future, when rich)** Migrate to Claude Agent SDK — chained pipeline → real agent that loops with tools (`fetch_research`, `check_register`, `score_with_critic`, `commit_comment`). See "Agent SDK baby steps" below.

---

## Agent SDK baby steps (deferred)

When ready to migrate from chained pipeline → real agent:

1. **Step 1** — `agent_v1.py`: 1 file, 1 tool (`fetch_research`), `client.beta.messages.tool_runner()` with sonnet-4-6 + adaptive thinking. ~40 lines. Verify Claude decides when to fetch.
2. **Step 2** — Add `check_register` tool (wraps Gate 9). Claude can now self-correct JW-register drift.
3. **Step 3** — Add `score_with_critic` tool (wraps Gate 6). Loop: research → draft → self-critic → revise.
4. **Step 4** — Add `commit_comment` tool. When Claude is satisfied, it calls this; Python writes to disk; loop terminates.
5. **Step 5** — Swap `_draft_with_gates` in `build_week.py` to call the agent per paragraph. Article-level gates stay in Python.

Reference: claude-api skill (Python managed-agents README) was loaded this session.

---

## Operator open questions

- **"What apps do I need? I hate running in terminal."** — Tyler asked for a non-terminal way to run this. Options to discuss: (a) a tiny FastAPI + HTML form he hits from his phone, (b) a Streamlit one-page app, (c) wrap in a Mac menubar/iOS Shortcut that hits a hosted endpoint. Not started.
- **API key in `.env`** — operator-rotatable. Must stay gitignored — never commit. (Do not paste the literal value into any tracked file, including this handoff.)

---

## What to avoid

- **Don't commit `.env`** — `ANTHROPIC_API_KEY` and `RESEND_API_KEY` are operator-rotatable secrets.
- **Don't add error handling around the underline 25-retry loop** without fixing the root cause (paragraph-has-no-answer detection). The retries were burning $$.
- **Don't change the default model from `claude-sonnet-4-6`** in `workers.py` — operator explicitly chose Sonnet for the pipeline phase. Opus is reserved for the future agent SDK migration.
- **Don't reach for `claude-opus-4-7`** in this codebase yet — pipeline economics assume Sonnet.
- **Don't relax Mandate 5 / Gate 10** to make builds pass. Operator's whole point: comments must *do something* to the audience. A clean-but-empty comment is a failure, not a pass.
- **Don't replace the typed prompts with a single "do everything" prompt.** The 6-type split was specifically requested after operator flagged that single-prompt outputs were "just templates not free thinking."
