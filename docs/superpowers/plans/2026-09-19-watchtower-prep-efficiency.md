# Watchtower preparation efficiency

User-approved objective: preserve the phenomenal finished comments while reducing repeated reading, whole-article rewrites and lost context. Preserve existing quality gates, scriptural grounding, voice and article progression. Actual Fable/Astra usage traces are unavailable; savings must not be invented.

1. Add an offline checkpoint engine (`agent/prep_session.py`) with source/policy fingerprints, whole-article plan, private approved references, exact review hashes, accepted-comment locks, one local repair per failed paragraph, and gated export. Write deterministic lifecycle tests first.
2. Repair SDK redraft handoff (`lesson_agent.py`, `comment_agent.py`): include existing draft and precise reason, retain checkpoints during failure, persist attempt count before dispatch, and provide complete article context. Regression tests must use mocked drafting, never paid model calls.
3. Add a local source/reference adapter (`prep_inputs.py`): scrape saved official HTML, extract only explicitly selected publication notes from a local JW Library backup, and preserve cached inputs. Test using synthetic backups.
4. Route weekly preparation to scoped instructions and document commands, quality review, resumption and failure behavior. Record the workflow choice in ADR 0007; preserve sales-content governance.
5. Run offline regression suites and a current-article preparation smoke test. Obtain a bounded independent review, fix material defects, then commit named files and publish a feature branch/PR. Do not merge or run paid generation.

Review basis: no accepted-comment mutation, no stale verdicts, no silent missing paragraphs, no future-payoff leakage accepted without explicit semantic review, and no weakening of existing gates. Semantic quality still requires a model/human review; Python cannot certify theology or voice. New export handles comments only; underline generation remains separate.
