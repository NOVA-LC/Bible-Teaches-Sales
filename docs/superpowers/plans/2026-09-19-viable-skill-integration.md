# Viable skill integration

**Source and scope:** The operator requested an inventory of all available skills
and implementation where viable, following PR #3. Existing approved comment
quality and paragraph continuity remain the target; reduce repeat work. This
authorizes implementation on the feature branch and updating the PR. It does
not authorize a merge, paid model runs, or publishing private skill contents.

**Architecture:** Keep personal skills in their installed host. A compact,
portable repository routing document supplies only relevant working principles.
The existing Watchtower checkpoint engine enforces plan feasibility and preserves
the supporting context. Other content tracks retain their own contracts.

**Boundaries:** Existing quality gates and approved wording remain unchanged.
Python validates structure and workflow, not truth or model quality. No numerical
quota-saving claim. All source/reference/experience/run data remains private.

**Decision:** Loading every installed skill for every paragraph would repeat
irrelevant context and activate workflows that need unrelated systems. Use
task-scoped routing, deterministic preflight, and one independent code review.
Skills with missing prerequisites remain conditional, not falsely implemented.

EASY PATH: Add a blanket instruction to use every skill.
RIGHT PATH: Map all skills, implement relevant behavior, and test its boundaries.
WHY IT WINS: It makes preparation more reliable without changing the approved
voice or importing unrelated requirements into comments.

## Implementation and evidence

- [x] Inventory the advertised catalog, preserve duplicate identities and source
  hashes in a private report; mark draft expert profiles and external-service
  prerequisites honestly. Do not install unrelated plugins.
- [x] Add `tools/jwl_notes/agent/SKILL_ROUTING.md` and route onboarding to it.
  Scope the old recipe's production rules as historical for this Work workflow.
- [x] Extend `prep_session.prepare(..., context=None)` with saved research and
  user-provided experiences, included in fingerprints and all request packets.
  Validate record IDs, source locators, evidence, and optional plan references.
- [x] Validate complete plan type assignments using the existing article gates;
  require a real supplied experience ID for Type B and sourced evidence for H.
  Draft types must match their plan. Do not remove any final prose checks.
- [x] Add read-only `status` and persisted checkpoint events: next command,
  coverage, accepted locks, consumed repairs and original rejection reasons.
  These are workflow counts, not token or model-call measurements.
- [x] Reproduce the missing behaviors with offline tests, then implement them.
  Run `python -m unittest agent.test_prep_session agent.test_prep_inputs
  agent.test_redraft_handoff agent.test_prep_skill_policy` from `tools/jwl_notes`.
- [x] Review the exact diff independently and update handoffs and CI.
  The reviewer found no critical or important issues in `603e923..2f05432`
  and independently passed all eight new tests. The complete targeted suite
  passed 35 tests; the existing free suite passed 72/72.
- Publication: update PR #3 from this verified tree and check its remote hash/CI.
  Save the private inventory report with the final publication evidence. These
  external results are recorded in the PR and private report after readback.

**Migration:** New policy fingerprints intentionally reject older checkpoints;
keep original run folders intact. The earlier commit can still resume its own
checkpoints. Do not reset a run to replenish repairs. This workflow is new in
the still-open PR, so update its fixture plans and documented CLI together.

**Completion evidence:** Offline behavior tests, actual reviewer findings and
resolution, published tree match, and the PR's CI result. Actual savings and
voice parity require the next real preparation, not a synthetic fixture.
