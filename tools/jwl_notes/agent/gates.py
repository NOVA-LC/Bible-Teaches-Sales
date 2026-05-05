"""Six-gate Pre-Ship Self-Audit for Tyler comments.

Each gate is a deterministic function over either:
- a single comment payload (gates 1, 3), or
- the full set of comments for an article (gates 2, 4, 5), or
- a comment + a critic worker (gate 6).

Gates return a `GateResult` with `passed: bool` and `reason: str`. The
orchestrator collects results, redraft-prompts the worker for any failure,
and refuses to write the final JSON if any gate cannot be made to pass
within the attempt cap.

Run `python -m agent.gates --self-test` for the deterministic checks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


# ----------------------------------------------------------------------
# Mechanic taxonomy — must match the menu in prompts/paragraph_comment.md
# ----------------------------------------------------------------------

OPENER_MECHANICS = {
    "Brown positioning declaration",
    "Tippett formative-origin question",
    "Bourdain climactic-moment opener",
    "Hormozi sound-bite claim",
    "Brené Brown you-know-how relational",
    "Reinmueller did-you-notice debrief",
    "Two-question pre-empt",
    "Cook conditional invitation",
    "Lösch historical-frame compression",
}

LABEL_MECHANICS = {
    "Voss labeling",
    "Perel name-the-unnamed-dimension",
    "Bourdain self-implication",
    "Mr. Rogers possession-without-condition",
    "Noumair voiced-objection",
    "Permission-by-uncertainty",
}

ROTATION_MECHANICS = {
    "Morrison frame refusal",
    "Peterson archetypal compression",
    "Clear two-noun pivot",
    "Miner reframed question",
    "Holiday obstacle-becomes-path",
    "Hormozi compression-expansion",
    "Schafer concession-pivot",
}

LANDING_MECHANICS = {
    "Sam Herd parallel-clause inversion",
    "Mr. Rogers possession-without-condition",
    "Bourdain preposition-pivot",
    "Naval pursuit-order reframe",
    "Holiday Marcus-style aphorism",
    "Herd temporal-axis inversion",
    "Cook conditional invitation",
}

ALL_MECHANICS = (
    OPENER_MECHANICS | LABEL_MECHANICS | ROTATION_MECHANICS | LANDING_MECHANICS
)

# Tyler-overused openers — banned even though the underlying mechanic exists
FORBIDDEN_OPENING_PHRASES = [
    "Look at",
    "Notice",
    "You ever had",
]

NAMED_RELATIONSHIPS = {
    "brother", "sister", "mom", "mother", "dad", "father", "grandma",
    "grandmother", "grandpa", "grandfather", "uncle", "aunt", "cousin",
    "neighbor", "neighbour", "wife", "husband", "son", "daughter",
    "kid", "child", "boss", "coworker", "co-worker", "roommate",
    "parents", "parent",
}

HERD_MOVE_CODES = {"H1", "H2", "H3", "H4", "H5"}


# ----------------------------------------------------------------------
# Result type
# ----------------------------------------------------------------------

@dataclass
class GateResult:
    gate: str
    passed: bool
    reason: str

    def __str__(self) -> str:
        sigil = "✅" if self.passed else "❌"
        return f"{sigil} {self.gate}: {self.reason}"


# ----------------------------------------------------------------------
# Gate 1 — Mechanics tagged & valid
# ----------------------------------------------------------------------

def gate1_mechanics_tagged(comment: dict) -> GateResult:
    """Every beat must be tagged with a mechanic from the toolbox.

    Minimum 3 beats (opener, rotation, landing). Slot-2 label is optional.
    """
    name = "Gate 1 (mechanics tagged)"
    beats = comment.get("tagged_beats", [])
    if not isinstance(beats, list) or len(beats) < 3:
        return GateResult(name, False, f"need ≥3 tagged beats, got {len(beats)}")
    unknown = [
        b.get("mechanic") for b in beats
        if b.get("mechanic") not in ALL_MECHANICS
    ]
    if unknown:
        return GateResult(
            name, False,
            f"unknown mechanic(s): {unknown} — must come from the 12-toolbox menu"
        )
    # Opener must be from opener menu, landing from landing menu (last beat)
    opener_mech = beats[0].get("mechanic")
    if opener_mech not in OPENER_MECHANICS:
        return GateResult(
            name, False,
            f"first beat mechanic '{opener_mech}' is not an opener mechanic"
        )
    landing_mech = beats[-1].get("mechanic")
    if landing_mech not in LANDING_MECHANICS:
        return GateResult(
            name, False,
            f"last beat mechanic '{landing_mech}' is not a landing mechanic"
        )
    return GateResult(name, True, f"{len(beats)} beats tagged with valid mechanics")


# ----------------------------------------------------------------------
# Gate 2 — Variety across the week
# ----------------------------------------------------------------------

def gate2_variety_across_week(comments: list[dict]) -> GateResult:
    """No opener mechanic and no rotation mechanic may repeat across notes.

    Landing mechanics are allowed to repeat (Herd parallel-clause is the
    default landing) but the *specific phrasing* of the landing should
    vary — that's harder to check programmatically; the critic catches it.
    """
    name = "Gate 2 (variety across week)"
    opener_seen, rotation_seen = {}, {}
    for c in comments:
        beats = c.get("tagged_beats", [])
        if not beats:
            continue
        para = c.get("paragraph_number", "?")
        opener = beats[0].get("mechanic")
        if opener in opener_seen:
            return GateResult(
                name, False,
                f"opener mechanic '{opener}' repeats: ¶{opener_seen[opener]} and ¶{para}"
            )
        opener_seen[opener] = para
        # Rotation = third beat if 4 slots, second beat if 3 slots
        rotation_idx = 2 if len(beats) >= 4 else 1
        if rotation_idx < len(beats) - 1:
            rotation = beats[rotation_idx].get("mechanic")
            if rotation in rotation_seen:
                return GateResult(
                    name, False,
                    f"rotation '{rotation}' repeats: ¶{rotation_seen[rotation]} and ¶{para}"
                )
            rotation_seen[rotation] = para
    return GateResult(
        name, True,
        f"{len(opener_seen)} unique openers + {len(rotation_seen)} unique rotations"
    )


# ----------------------------------------------------------------------
# Gate 3 — Spine image referenced in opener AND landing
# ----------------------------------------------------------------------

_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "but", "in", "on", "at",
    "to", "for", "with", "by", "from", "as", "is", "was", "be",
    "been", "are", "were", "this", "that", "these", "those", "it",
    "his", "her", "their", "your", "our", "my",
}


def _content_words(text: str) -> set[str]:
    """Lowercase, tokenize on word boundaries, drop stopwords/short tokens."""
    toks = re.findall(r"[A-Za-z][A-Za-z'-]+", text.lower())
    return {t for t in toks if t not in _STOPWORDS and len(t) > 2}


def gate3_spine_image_referenced(comment: dict) -> GateResult:
    """The named spine_image must appear (by content-word overlap) in both
    the opener and the landing of the actual content."""
    name = "Gate 3 (spine image runs through)"
    spine = comment.get("spine_image", "")
    content = comment.get("content", "")
    if not spine.strip():
        return GateResult(name, False, "no spine_image declared")
    spine_words = _content_words(spine)
    if not spine_words:
        return GateResult(name, False, f"spine_image '{spine}' has no content words")
    sentences = [s.strip() for s in re.split(r"[.!?]+", content) if s.strip()]
    if len(sentences) < 2:
        return GateResult(name, False, "comment has fewer than 2 sentences")
    opener = sentences[0]
    landing = sentences[-1]
    opener_overlap = spine_words & _content_words(opener)
    landing_overlap = spine_words & _content_words(landing)
    if not opener_overlap and not landing_overlap:
        return GateResult(
            name, False,
            f"spine '{spine}' not present in opener OR landing — image is decoration, not spine"
        )
    if not opener_overlap:
        return GateResult(
            name, False,
            f"spine '{spine}' missing from opener — opener should set the image"
        )
    if not landing_overlap:
        return GateResult(
            name, False,
            f"spine '{spine}' missing from landing — landing should close the image"
        )
    return GateResult(name, True, f"spine '{spine}' present in opener + landing")


# ----------------------------------------------------------------------
# Gate 4 — Domestic-scene quota across the article
# ----------------------------------------------------------------------

def gate4_domestic_scene_quota(
    comments: list[dict], min_required: int = 2
) -> GateResult:
    """Across the article's notes, at least `min_required` must contain a
    real named-relationship domestic scene."""
    name = "Gate 4 (domestic-scene quota)"
    qualifying = []
    for c in comments:
        ds = c.get("domestic_scene", {})
        if not isinstance(ds, dict) or not ds.get("present"):
            continue
        rel = (ds.get("named_relationship") or "").lower().strip()
        # Strip parenthetical or punctuation suffixes
        rel_root = re.split(r"[\s(,]", rel, 1)[0]
        if rel_root in NAMED_RELATIONSHIPS:
            qualifying.append((c.get("paragraph_number"), rel))
        else:
            # caller claimed present but relationship isn't named/recognized
            pass
    if len(qualifying) < min_required:
        return GateResult(
            name, False,
            f"only {len(qualifying)} note(s) with named-relationship domestic scenes "
            f"({qualifying}); need ≥{min_required}"
        )
    return GateResult(
        name, True,
        f"{len(qualifying)} domestic-scene notes: {qualifying}"
    )


# ----------------------------------------------------------------------
# Gate 5 — Herd distinctive-move quota
# ----------------------------------------------------------------------

def gate5_herd_moves_quota(
    comments: list[dict], min_required: int = 2
) -> GateResult:
    """Across the article, at least `min_required` notes must deploy one of
    the H1-H5 distinctive Herd moves."""
    name = "Gate 5 (Herd distinctive-move quota)"
    notes_with_herd_move = []
    for c in comments:
        moves = c.get("herd_distinctive_moves", []) or []
        valid = [m for m in moves if m in HERD_MOVE_CODES]
        if valid:
            notes_with_herd_move.append((c.get("paragraph_number"), valid))
    if len(notes_with_herd_move) < min_required:
        return GateResult(
            name, False,
            f"only {len(notes_with_herd_move)} note(s) deploy H1-H5 "
            f"({notes_with_herd_move}); need ≥{min_required}"
        )
    return GateResult(
        name, True,
        f"{len(notes_with_herd_move)} notes deploy Herd moves: {notes_with_herd_move}"
    )


# ----------------------------------------------------------------------
# Per-comment forbidden-phrase / forbidden-opener checks
# (sub-gates that run inside Gate 1's family)
# ----------------------------------------------------------------------

def gate1b_no_forbidden_openers(comment: dict) -> GateResult:
    """The opener must not start with one of the overused phrases."""
    name = "Gate 1b (no forbidden opener phrases)"
    content = comment.get("content", "")
    first_sentence = content.split(".")[0].strip()
    for phrase in FORBIDDEN_OPENING_PHRASES:
        if first_sentence.lower().startswith(phrase.lower()):
            return GateResult(
                name, False,
                f"opener begins with forbidden phrase '{phrase}': {first_sentence!r}"
            )
    return GateResult(name, True, "opener does not start with overused phrase")


def gate1c_word_count(comment: dict, lo: int = 60, hi: int = 130) -> GateResult:
    """Comment word count must fall in [lo, hi]."""
    name = "Gate 1c (word count)"
    text = comment.get("content", "")
    n = len(text.split())
    if n < lo:
        return GateResult(name, False, f"word count {n} < lower bound {lo}")
    if n > hi:
        return GateResult(name, False, f"word count {n} > upper bound {hi}")
    return GateResult(name, True, f"word count {n} (in [{lo}, {hi}])")


# ----------------------------------------------------------------------
# Gate 6 — Critic agent (movement / encouragement / memorability)
# ----------------------------------------------------------------------

def gate6_critic(
    comment: dict,
    paragraph_data: dict,
    critic_call: Callable[[dict], dict],
) -> GateResult:
    """Spawn a separate critic worker. `critic_call` is a callable that
    takes the critic input dict and returns the critic JSON.

    The orchestrator owns `critic_call` (which dispatches via SDK or
    in-session Agent). This function is dispatch-agnostic.
    """
    name = "Gate 6 (audience critic)"
    critic_input = {
        "paragraph_number": comment.get("paragraph_number"),
        "question_text": paragraph_data.get("question_text"),
        "body_paragraph_text": paragraph_data.get("body_paragraph_text"),
        "comment_content": comment.get("content"),
        "claimed_rotation": comment.get("rotation"),
        "claimed_spine_image": comment.get("spine_image"),
        "claimed_memorable_line": comment.get("memorable_line"),
    }
    try:
        verdict = critic_call(critic_input)
    except Exception as e:
        return GateResult(name, False, f"critic call failed: {e}")
    if not verdict.get("overall_pass"):
        return GateResult(
            name, False,
            f"critic rejected: moved={verdict.get('moved')}, "
            f"encouraged={verdict.get('encouraged')}, "
            f"memorable={verdict.get('memorable')} — "
            f"redraft guidance: {verdict.get('redraft_guidance')}"
        )
    return GateResult(
        name, True,
        f"critic approved (moved={verdict.get('moved')}, "
        f"encouraged={verdict.get('encouraged')}, "
        f"memorable={verdict.get('memorable')})"
    )


# ----------------------------------------------------------------------
# Underline gates (called for each underline-worker output)
# ----------------------------------------------------------------------

def gate_underline_yellow_fully_answers(
    underline_payload: dict, body_text: str, question_text: str
) -> GateResult:
    """Each yellow must appear verbatim in the body text. Audit must
    self-attest grammatical completeness."""
    name = "Underline-gate (yellows are full grammatical answers)"
    underlines = underline_payload.get("underlines", [])
    yellows = [u for u in underlines if u.get("color") == "yellow"]
    if not yellows:
        return GateResult(name, False, "no yellow underlines found")
    audit = underline_payload.get("self_audit", {})
    if not audit.get("all_yellows_complete_answers"):
        return GateResult(name, False, "self_audit says yellows are not complete answers")
    if not audit.get("all_yellows_grammatical"):
        return GateResult(name, False, "self_audit says yellows are not grammatical")
    for u in underlines:
        phrase = u.get("phrase", "")
        if phrase not in body_text:
            return GateResult(
                name, False,
                f"phrase {phrase!r} not verbatim in source paragraph "
                "(check curly apostrophes / quotes)"
            )
    return GateResult(
        name, True,
        f"{len(yellows)} yellow(s), all verbatim in source"
    )


def gate_underline_non_yellow_word_cap(
    underline_payload: dict, max_words: int = 8
) -> GateResult:
    """Non-yellow phrases must be ≤ max_words."""
    name = "Underline-gate (non-yellow word cap)"
    for u in underline_payload.get("underlines", []):
        if u.get("color") == "yellow":
            continue
        n = len(u.get("phrase", "").split())
        if n > max_words:
            return GateResult(
                name, False,
                f"non-yellow phrase exceeds {max_words} words ({n}): {u.get('phrase')!r}"
            )
    return GateResult(name, True, f"all non-yellow phrases ≤ {max_words} words")


# ----------------------------------------------------------------------
# Aggregation helpers
# ----------------------------------------------------------------------

def run_per_comment_gates(comment: dict) -> list[GateResult]:
    """Run gates that operate on a single comment in isolation."""
    return [
        gate1_mechanics_tagged(comment),
        gate1b_no_forbidden_openers(comment),
        gate1c_word_count(comment),
        gate3_spine_image_referenced(comment),
    ]


def run_article_gates(comments: list[dict]) -> list[GateResult]:
    """Run gates that operate over the whole article."""
    return [
        gate2_variety_across_week(comments),
        gate4_domestic_scene_quota(comments),
        gate5_herd_moves_quota(comments),
    ]


def run_underline_gates(payload: dict, body_text: str, question_text: str
                        ) -> list[GateResult]:
    return [
        gate_underline_yellow_fully_answers(payload, body_text, question_text),
        gate_underline_non_yellow_word_cap(payload),
    ]


# ----------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------

def _self_test() -> int:
    """Lightweight smoke test of the deterministic gates."""
    failures = 0

    # Gate 1 — happy path
    good = {
        "tagged_beats": [
            {"text": "x", "mechanic": "Bourdain climactic-moment opener"},
            {"text": "y", "mechanic": "Voss labeling"},
            {"text": "z", "mechanic": "Clear two-noun pivot"},
            {"text": "w", "mechanic": "Sam Herd parallel-clause inversion"},
        ],
        "spine_image": "spaghetti",
        "content": "I make spaghetti every Sunday. My brother does not. The spaghetti is the difference.",
    }
    r = gate1_mechanics_tagged(good)
    if not r.passed:
        print("FAIL gate1 happy-path:", r); failures += 1

    bad = {"tagged_beats": [{"text": "x", "mechanic": "Made-up mechanic"}]}
    r = gate1_mechanics_tagged(bad)
    if r.passed:
        print("FAIL gate1 should reject unknown mechanic"); failures += 1

    # Gate 1b — forbidden opener
    forbid = {"content": "Look at what Jesus said in Luke 6. Then notice the next part."}
    r = gate1b_no_forbidden_openers(forbid)
    if r.passed:
        print("FAIL gate1b should reject 'Look at' opener"); failures += 1

    # Gate 1c — word count
    short = {"content": " ".join(["word"] * 30)}
    r = gate1c_word_count(short)
    if r.passed:
        print("FAIL gate1c should reject 30-word comment"); failures += 1

    long_ = {"content": " ".join(["word"] * 200)}
    r = gate1c_word_count(long_)
    if r.passed:
        print("FAIL gate1c should reject 200-word comment"); failures += 1

    # Gate 3 — spine present in both opener and landing
    r = gate3_spine_image_referenced(good)
    if not r.passed:
        print("FAIL gate3 happy-path:", r); failures += 1

    spineless = {
        "spine_image": "spaghetti",
        "content": "The article says we should be teachers. The Bible agrees.",
    }
    r = gate3_spine_image_referenced(spineless)
    if r.passed:
        print("FAIL gate3 should reject spine-not-in-opener"); failures += 1

    # Gate 2 — variety
    two_same = [
        {"paragraph_number": 1, "tagged_beats": [
            {"text": "x", "mechanic": "Bourdain climactic-moment opener"},
            {"text": "y", "mechanic": "Clear two-noun pivot"},
            {"text": "z", "mechanic": "Sam Herd parallel-clause inversion"},
        ]},
        {"paragraph_number": 2, "tagged_beats": [
            {"text": "x", "mechanic": "Bourdain climactic-moment opener"},
            {"text": "y", "mechanic": "Morrison frame refusal"},
            {"text": "z", "mechanic": "Sam Herd parallel-clause inversion"},
        ]},
    ]
    r = gate2_variety_across_week(two_same)
    if r.passed:
        print("FAIL gate2 should detect repeated opener"); failures += 1

    # Gate 4 — domestic scene
    notes = [
        {"paragraph_number": 1, "domestic_scene": {
            "present": True, "named_relationship": "brother",
            "scene_summary": "Sunday dinner"
        }},
        {"paragraph_number": 3, "domestic_scene": {
            "present": True, "named_relationship": "grandma",
            "scene_summary": "kitchen ring"
        }},
        {"paragraph_number": 5, "domestic_scene": {
            "present": False, "named_relationship": None
        }},
    ]
    r = gate4_domestic_scene_quota(notes)
    if not r.passed:
        print("FAIL gate4 happy-path:", r); failures += 1

    too_few = [{"paragraph_number": 1, "domestic_scene": {
        "present": True, "named_relationship": "brother", "scene_summary": "x"
    }}]
    r = gate4_domestic_scene_quota(too_few)
    if r.passed:
        print("FAIL gate4 should reject single domestic-scene note"); failures += 1

    # Gate 5 — Herd quota
    herd_ok = [
        {"paragraph_number": 1, "herd_distinctive_moves": ["H1"]},
        {"paragraph_number": 2, "herd_distinctive_moves": ["H3", "H5"]},
        {"paragraph_number": 3, "herd_distinctive_moves": []},
    ]
    r = gate5_herd_moves_quota(herd_ok)
    if not r.passed:
        print("FAIL gate5 happy-path:", r); failures += 1

    # Underline gates
    body = 'Some may feel that they cannot improve their teaching skills because they have limited secular education or natural ability.'
    ul_good = {
        "underlines": [
            {"phrase": "have limited secular education or natural ability",
             "color": "yellow", "answers_question": True}
        ],
        "self_audit": {
            "yellow_count": 1,
            "all_yellows_complete_answers": True,
            "all_yellows_grammatical": True,
        }
    }
    r = gate_underline_yellow_fully_answers(ul_good, body, "Why?")
    if not r.passed:
        print("FAIL underline-yellow happy-path:", r); failures += 1

    ul_bad_phrase = {
        "underlines": [
            {"phrase": "this phrase does not appear",
             "color": "yellow", "answers_question": True}
        ],
        "self_audit": {
            "yellow_count": 1,
            "all_yellows_complete_answers": True,
            "all_yellows_grammatical": True,
        }
    }
    r = gate_underline_yellow_fully_answers(ul_bad_phrase, body, "Why?")
    if r.passed:
        print("FAIL underline should reject phrase-not-in-source"); failures += 1

    if failures == 0:
        print("All gate self-tests passed.")
        return 0
    print(f"\n{failures} gate self-test failure(s).")
    return 1


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    print("Run with --self-test")
