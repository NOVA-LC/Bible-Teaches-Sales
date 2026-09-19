# Meeting preparation instructions

For Watchtower, CBS, Spiritual Gems and JW Library tooling, start here and read
`agent/HANDOFF.md`. The root sales-lesson schema, hidden-origin rule and sales
corpus onboarding govern sales lessons, not congregation comments. When changing
both tracks, follow both contracts. See ADR 0007 for this scope decision.

## Preserve the result; reduce repeated work

The operator explicitly approves the finished Watchtower comments as phenomenal.
Preserve their depth, warmth, scripture work, illustrations and emotional effect.
Do not simplify the voice or weaken a gate to reduce usage. Reuse two or three
operator-approved comments as private reference examples; never commit a backup,
private reference packet, credentials or runtime state.

For Watchtower Work/chat preparation (including Fable/Astra), use `agent/RUNBOOK.md` and
`python -m agent.prep_session`. This is the default Watchtower session workflow. CBS and Spiritual Gems retain
their existing workflows; the new engine supports one Watchtower document only. The existing
SDK automation remains available for explicitly requested API runs. Do not run a
paid API job just to test a workflow change.

Read `agent/SKILL_ROUTING.md` for the scoped skill policy and current production
rule precedence. Load applicable installed skills once at the appropriate stage;
do not make every skill or optional review panel part of each paragraph's context.
Inspect `python -m agent.prep_session status --run-dir <session>` before resuming.

Read `voice/drafting-recipe.md`, `agent/prompts/comment_agent.md`, the selected type
prompts and `agent/prompts/critic_gate6.md` once per preparation session/policy
version. Reuse that context and saved source research; do not reread the entire
sales corpus or spawn a fresh writer/critic for every paragraph by default.

Before prose, read the complete article and save a paragraph plan: each question,
its particular teaching/angle, and points reserved for later paragraphs. A good
paragraph 14 payoff must stay out of paragraph 10. Allocate types and required
article-level features in the plan, checking feasibility before expensive drafting.
Type B requires a real user-provided experience; never invent one to fill a quota.

Draft the article from that plan, checkpoint it, then perform one consolidated
independent quality review. Existing structural gates and all substantive quality
criteria still apply. Repair only explicit failures with the old draft and exact
reason supplied. Accepted comments are frozen. One repair per failed paragraph;
if still failing, stop with the precise unresolved defect. Do not silently ship,
weaken the standard, reset the run to bypass the cap, or enter an endless loop.

A checkpoint is reusable only for identical source, approved references and policy.
Python validates workflow and deterministic gates; it cannot establish semantic
accuracy, emotional impact or independence of a reviewer. Review judgments must be
honest and evidence-based, never manufactured to satisfy a JSON schema.

The new checkpoint export contains comments only. Full meeting preparation still
requires the existing underline doctrine and verification; do not call a
comment-only export complete weekly preparation. Packaging must preserve accepted
wording, including multiple notes anchored to a shared study question.

## Changes and verification

Use a feature branch, stage named files, preserve accepted ADRs, update the relevant
HANDOFF. Regression tests must exercise behavior and use fake models/local inputs:

```bash
cd tools/jwl_notes
python -m unittest agent.test_prep_session agent.test_prep_inputs agent.test_redraft_handoff agent.test_prep_skill_policy
python -m agent._test_e2e_free
```

Keep failures and unmeasured claims visible. Offline success is not evidence of a
percentage quota saving or proof that a model preserved the approved voice.
