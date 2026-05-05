# Autonomous Weekly Prep Agent

Closes the trust gap. Tyler shouldn't have to QA every comment — the orchestrator does, in code.

## What this is

Per-paragraph fan-out: one fresh agent per paragraph (comment + underlines), plus a separate critic agent for Gate 6, all coordinated by a Python orchestrator that enforces the six-gate Pre-Ship Self-Audit (`Mandate 4` in `voice/drafting-recipe.md`). If any gate cannot be made to pass within 3 attempts, **the orchestrator refuses to write the JSON.** No silent shipping.

```
┌─────────────────┐   per-paragraph   ┌───────────────────┐
│  build_week.py  │──── fan-out ─────▶│ comment workers   │
│  (orchestrator) │                   │ (one per ¶, fresh)│
└────────┬────────┘                   └────────┬──────────┘
         │                                     │ tagged JSON
         │            ┌────────────────────────┘
         │            ▼
         │   ┌─────────────────┐    Gate 6     ┌───────────────────┐
         │   │  gates.py       │────fan-out───▶│ critic worker     │
         │   │  (6 gates)      │               │ (separate context)│
         │   └────────┬────────┘               └───────────────────┘
         │            │ pass/fail per-gate
         ▼            ▼
   refuses to        retries up to 3x
   write if any      with explicit feedback
   gate fails        from the failed gate
```

## Setup (one-time)

1. **Rotate your Anthropic API key** if it was ever exposed (e.g., pasted in chat). Console: <https://console.anthropic.com/> → API Keys.
2. **Install dependencies:** `pip install anthropic`
3. **Drop the rotated key into `.env`:**
   ```
   cp tools/jwl_notes/agent/.env.example tools/jwl_notes/agent/.env
   $EDITOR tools/jwl_notes/agent/.env   # paste the key
   ```
   `.env` is gitignored. Never commit it.

## Usage

### Generate a week's prep autonomously

```
cd tools/jwl_notes
python -m agent.build_week \
  --article-id 2026320 \
  --key-symbol w \
  --issue 20260300 \
  --study-date 2026-05-10 \
  --article-title "Improve Your 'Art of Teaching' in the Ministry" \
  --article-source "The Watchtower (Study), March 2026" \
  --output comments/2026-05-10-w.json
```

Output:
- On full success: writes `comments/2026-05-10-w.json` and prints `✅ All gates passed.`
- On any failure: prints `❌ REFUSED TO SHIP` and lists which paragraphs failed which gates. The gate log lives at `agent/runs/<study-date>-<key>-<docid>/gates.log`.

### Inject + verify + email (existing pipeline)

```
python jwl_notes.py \
  --input ../../UserdataBackup_*.jwlibrary \
  --output /tmp/jwl_run/2026-05-10-w.jwlibrary \
  --comments comments/2026-05-10-w.json \
  --verify
```

Then email via the Resend script (or wrap into `agent/email.py` later).

## Files

| File | Purpose |
|---|---|
| `build_week.py` | Orchestrator — scrapes WOL article, fans out per-paragraph workers, runs gates, assembles JSON |
| `gates.py` | The six gates as deterministic functions (run `python -m agent.gates --self-test`) |
| `workers.py` | Two backends: `SDKWorker` (production, requires API key) and `InSessionWorker` (manual fallback for use inside Claude Code) |
| `prompts/paragraph_comment.md` | Canonical prompt — every comment-drafting worker receives this verbatim |
| `prompts/paragraph_underlines.md` | Canonical prompt for underline workers |
| `prompts/critic_gate6.md` | Canonical prompt for the Gate 6 critic worker (must be a different worker from the drafter) |
| `RUNBOOK.md` | Manual operation if running inside Claude Code without an API key |
| `.env.example` | Template for `.env`. Real `.env` is gitignored. |
| `runs/` | Per-run gate logs and intermediate state (gitignored) |

## Why an orchestrator instead of "trust the AI"

Read this conversation backwards: v3, v4, v5, v6, v7, v8, v9, v10. Eight rounds, each one because Tyler caught something the AI shipped without checking. The AI cannot be trusted to enforce the mandates conversationally — there's no mechanism preventing it from rationalizing "good enough."

The orchestrator removes that decision from the AI. Each gate is binary. The script either ships output that passes all gates or refuses to ship. There is no middle ground in which the AI can decide for you.

What the API key buys is **architecture-as-discipline**, not "more effort from the model." Same model, same effort — but no skip-the-gate option.
