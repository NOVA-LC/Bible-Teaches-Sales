# ADR 0008: Apply skills at the task boundary

**Status:** Accepted for the feature branch; integration follows the PR.
**Date:** 2026-09-19
**Extends:** ADR 0007; it does not rewrite prior decisions.

## Context

The operator requested an inventory of all available skills and implementation
where viable. Finished Watchtower quality is already approved; repeated context,
contradictory production guidance and late discovery of impossible plans can
create avoidable iteration. Available skills also cover unrelated systems and
deliverables, so activating all of them would add requirements without benefit.

## Decision

Keep the full inventory private. Put a thin portable projection in
`tools/jwl_notes/agent/SKILL_ROUTING.md`, reached by scoped onboarding and embedded
in preparation packets. Use installed skills for their actual tasks. Optional
panels and external systems do not become mandatory preparation dependencies.

Current generator limits take precedence over historical production settings in
the voice recipe for Work/chat Watchtower preparation. Voice craft, scripture
depth, substantive review and the full-answer underline doctrine are preserved.

Run existing article gates on the paragraph plan as well as finished drafts.
Save traceable research and supplied experiences, validate plan references, and
bind that context into request fingerprints. Require Type B experience and Type H
research before drafting. Preserve rejection reasons and inspect next actions
through a read-only status command. No gate or metadata proves semantic truth.

## Consequences and verification

Plan shape now includes explicit type and planned feature metadata. Context has
an optional CLI input; omitting it supplies empty lists. Existing checkpoint
fingerprints intentionally fail when the policy changes; old runs stay intact
and require their matching code revision. No automatic reset replenishes repairs.
New tests exercise early rejection, typed drafts, context reuse/invalidation,
read-only inspection and durable failure history. Existing SDK/CBS/Gems workflows
are unchanged. Offline tests do not establish model quality parity or savings.
