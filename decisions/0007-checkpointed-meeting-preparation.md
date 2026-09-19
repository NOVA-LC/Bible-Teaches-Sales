# ADR 0007: Checkpointed meeting preparation, preserving approved quality

- Status: accepted
- Date: 2026-09-19

## Context

The operator reports excellent final Watchtower comments but excessive iteration
and quota consumption in Work sessions. The explicit goal is the same quality at
lower usage, including strict article progression: a paragraph 14 payoff must not
be spent in paragraph 10. No run trace supports attributing reported Fable/Astra
usage to this repo's separate Anthropic API pipeline.

Inspection found a concrete API defect: redraft reasons were logged but not given
to the writer, and the previous draft was deleted before repair. The old manual
runbook also prescribed fresh writers and critics per paragraph, without durable
accepted-comment locks or a whole-article reservation plan.

## Decision

Use a model-independent checkpoint workflow by default for Work/chat preparation:
full cached source and private approved examples; a complete paragraph plan;
checkpointed drafts; one consolidated independent review; one local repair per
failed paragraph. Retain accepted wording exactly. Expose unresolved failures and
block export instead of weakening gates or silently resetting retry counts.

All existing comment and article gates remain. Semantic review still belongs to
an actual reviewer; deterministic code cannot certify scripture accuracy, voice
or emotional impact. Identical source/reference/policy inputs resume; changed
inputs require an explicit new run. Export is comment-only, using the existing
injector schema. Full meeting preparation retains the underline doctrine.

Fix the SDK repair handoff separately without claiming it implements the complete
Work workflow. Keep its existing automation, targets and cost caps.

Scope meeting-preparation onboarding to `tools/jwl_notes/AGENTS.md`, its handoff,
quality prompts and runbook. Root sales schema, hidden-origin guidance and corpus
reading still apply to sales content. This clarifies the work streams under the
AGENTS.md convention of ADR 0005; it does not change the sales rules in ADRs
0001–0006 or relax the meeting voice standard.

## Consequences and verification

Approved examples and JW Library backups remain private, outside git. No paid
generation is needed for lifecycle tests. Tests cover source/reference isolation,
fingerprints, stale review rejection, accepted locks, bounded repair, article-gate
repair, export coverage and SDK handoff/durability. A current official article can
be prepared offline from saved HTML. Actual usage reduction and quality parity
must be measured on real subsequent runs; no savings percentage is promised.

The checkpoint CLI uses POSIX file locking (Linux/macOS). It does not replace
research, independent review, underlining or deterministic JW Library packaging.
