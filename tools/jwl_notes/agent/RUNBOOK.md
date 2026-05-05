# RUNBOOK — In-session manual operation

For when the orchestrator is invoked inside a Claude Code session without `ANTHROPIC_API_KEY` set. The parent Claude session (this assistant) plays the role of the worker pool by dispatching `Agent` tool calls per paragraph.

This is a **manual fallback**. Production usage is the SDK path documented in `README.md`. Use this only to demonstrate or debug the agent system before the API key is in place.

## The contract

The orchestrator gives Claude a list of jobs. Claude:

1. **Reads the canonical prompt** for the job type (`prompts/paragraph_comment.md`, `prompts/paragraph_underlines.md`, or `prompts/critic_gate6.md`).
2. **Spawns one `Agent` tool call per job.** Each agent receives the canonical prompt as its instructions plus the per-job input payload as its first message. Multiple jobs of the same type may be dispatched **in a single message with multiple Agent tool calls** so they run in parallel.
3. **Collects each agent's JSON return** and writes it to the orchestrator's results directory (`runs/<run_id>/results/<job_id>.json`).
4. **Re-invokes the orchestrator** to run gates on the results.
5. **Repeats for any failures** — the orchestrator emits a `redraft_feedback` string for each failed paragraph; Claude dispatches a fresh agent for each, with the feedback in the payload.

## Step-by-step

### 1. Discover the work

```bash
cd tools/jwl_notes
python -m agent.build_week \
  --article-id 2026320 --key-symbol w --issue 20260300 \
  --study-date 2026-05-10 --output comments/2026-05-10-w.json \
  --dry-run-list
```

This prints the per-paragraph list. Confirm 16 paragraphs discovered, question pids mapped.

### 2. Dispatch comment workers (one paragraph at a time, or batched in parallel)

For each paragraph that has a `q_pid`, build a payload from the prompt template, then spawn the agent. Example (in Claude's voice):

```
Agent({
  "subagent_type": "general-purpose",
  "description": "Draft Tyler comment for ¶7",
  "prompt": "<contents of prompts/paragraph_comment.md>\n\n---\nUSER PAYLOAD:\n{...JSON for ¶7...}"
})
```

Agents run in parallel when dispatched in a single message. Batch 4-8 at a time.

### 3. Collect outputs, save to results

Each agent returns text containing JSON. Save the raw text to `runs/<run_id>/results/comment_p<para>.json`. Then run the gate-checker:

```bash
python -m agent.gates --self-test         # sanity-check the gates work
# (no per-result CLI yet — call the gate functions from Python or via build_week)
```

### 4. Re-dispatch failures

The gate output is structured; for any `gate.passed == False`, build a redraft payload that includes the `gate.reason` as `redraft_feedback`. Spawn a fresh agent.

Cap at 3 attempts per paragraph. If the cap is hit, mark the paragraph as failed and continue.

### 5. Critic agents (Gate 6)

For each comment that passed gates 1, 1b, 1c, 3, dispatch a **separate** agent (different `Agent` tool call, fresh context) with the critic prompt. The critic returns moved/encouraged/memorable/overall_pass.

### 6. Article-level gates

Run `gate2_variety_across_week`, `gate4_domestic_scene_quota`, `gate5_herd_moves_quota` on the assembled comment list. If any fails, that's an article-level redraft — pick the offending paragraph(s) and re-dispatch.

### 7. Assemble + write JSON

If everything passes, assemble the JSON in the shape `tools/jwl_notes/jwl_notes.py` expects (or just call `assemble_comments_json` from `build_week.py`), then write it.

## Why this is a fallback

This loop is tedious. The point of the SDK path is that Python does all this without Claude or Tyler in the loop. The runbook exists so the system is **demonstrable** in-session before the key is wired, not as a sustainable mode of operation.

Once the key is in `.env`, run the SDK path and ignore this file.
