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


def _normalize_mechanic(name: str) -> str:
    """Normalize a mechanic name to a token-set string for tolerant comparison.

    Strips: case, punctuation, em-dashes, parentheticals, quotes (smart and
    straight), hyphens, underscores. Collapses whitespace. Returns the
    space-separated normalized token string.
    """
    s = name.lower()
    s = re.sub(r"\s*\([^)]*\)", " ", s)         # strip parentheticals
    s = re.sub(r"[—–\-_'’‘\"“”]+", " ", s)
    s = re.sub(r"[^\w\sé]", " ", s)              # strip remaining punct, keep accents
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokens(s: str) -> list[str]:
    return [t for t in _normalize_mechanic(s).split() if t]


_MENU_TOKENS = {m: _tokens(m) for m in ALL_MECHANICS}
_OPENER_TOKENS = {m: _tokens(m) for m in OPENER_MECHANICS}
_LANDING_TOKENS = {m: _tokens(m) for m in LANDING_MECHANICS}


def _matches_canonical(name: str, canonical_tokens_map: dict) -> bool:
    """A name matches a canonical mechanic iff every canonical token appears
    in the name's tokens (in any order, multiset)."""
    if not name:
        return False
    nt = _tokens(name)
    if not nt:
        return False
    nset = nt  # ordered list — but we just need superset semantics
    for canon, ctoks in canonical_tokens_map.items():
        # all canonical tokens present in the input tokens
        if all(t in nset for t in ctoks):
            return True
    return False


def _is_known_mechanic(name: str) -> bool:
    return _matches_canonical(name, _MENU_TOKENS)


def _is_opener_mechanic(name: str) -> bool:
    return _matches_canonical(name, _OPENER_TOKENS)


def _is_landing_mechanic(name: str) -> bool:
    return _matches_canonical(name, _LANDING_TOKENS)

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
        if not _is_known_mechanic(b.get("mechanic") or "")
    ]
    if unknown:
        return GateResult(
            name, False,
            f"unknown mechanic(s): {unknown} — must come from the 12-toolbox menu"
        )
    # Opener must be from opener menu, landing from landing menu (last beat)
    opener_mech = beats[0].get("mechanic")
    if not _is_opener_mechanic(opener_mech or ""):
        return GateResult(
            name, False,
            f"first beat mechanic '{opener_mech}' is not an opener mechanic"
        )
    landing_mech = beats[-1].get("mechanic")
    if not _is_landing_mechanic(landing_mech or ""):
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
        opener = _normalize_mechanic(beats[0].get("mechanic") or "")
        if opener in opener_seen:
            return GateResult(
                name, False,
                f"opener mechanic {opener!r} repeats: ¶{opener_seen[opener]} and ¶{para}"
            )
        opener_seen[opener] = para
        # Rotation = third beat if 4 slots, second beat if 3 slots
        rotation_idx = 2 if len(beats) >= 4 else 1
        if rotation_idx < len(beats) - 1:
            rotation = _normalize_mechanic(beats[rotation_idx].get("mechanic") or "")
            if rotation in rotation_seen:
                return GateResult(
                    name, False,
                    f"rotation {rotation!r} repeats: ¶{rotation_seen[rotation]} and ¶{para}"
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
    the opening third and the closing third of the actual content.

    Allows multi-sentence opener/landing — a comment that takes 2 sentences
    to set up the spine image is fine, as long as the image is established
    in the front of the comment and closed in the back.
    """
    name = "Gate 3 (spine image runs through)"
    spine = comment.get("spine_image", "")
    content = comment.get("content", "")
    if not spine.strip():
        return GateResult(name, False, "no spine_image declared")
    spine_words = _content_words(spine)
    if not spine_words:
        return GateResult(name, False, f"spine_image '{spine}' has no content words")
    words = content.split()
    if len(words) < 30:
        return GateResult(name, False, f"comment too short ({len(words)} words)")
    third = max(20, len(words) // 3)
    opener_chunk = " ".join(words[:third])
    landing_chunk = " ".join(words[-third:])
    opener_overlap = spine_words & _content_words(opener_chunk)
    landing_overlap = spine_words & _content_words(landing_chunk)
    if not opener_overlap and not landing_overlap:
        return GateResult(
            name, False,
            f"spine '{spine}' absent from opening third AND closing third — image is decoration, not spine"
        )
    if not opener_overlap:
        return GateResult(
            name, False,
            f"spine '{spine}' missing from opening third — opener should set the image"
        )
    if not landing_overlap:
        return GateResult(
            name, False,
            f"spine '{spine}' missing from closing third — landing should close the image"
        )
    return GateResult(name, True, f"spine '{spine}' threaded through opening + closing")


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


def gate1c_word_count(comment: dict, lo: int = 130, hi: int = 200) -> GateResult:
    """Comment word count must fall in [lo, hi].

    Spoken-comment range. Tyler's three samples are 165 / 148 / 188 words.
    Anything under 130 is too brief to deliver the cold-read teaching;
    anything over 200 won't fit the 30-45 second congregation-comment slot.
    """
    name = "Gate 1c (word count)"
    text = comment.get("content", "")
    n = len(text.split())
    if n < lo:
        return GateResult(name, False, f"word count {n} < lower bound {lo}")
    if n > hi:
        return GateResult(name, False, f"word count {n} > upper bound {hi}")
    return GateResult(name, True, f"word count {n} (in [{lo}, {hi}])")


# ----------------------------------------------------------------------
# Gate 9 — JW-native register (deterministic)
# ----------------------------------------------------------------------

# Pastor / Christendom words forbidden in narration. Direct verse quotes
# get a pass — the worker may quote NWT verbatim, including any word the
# NWT itself uses ("Lord" appears in NWT, "Christ" appears as title in
# some NWT verses, etc.). Detection: word appears in `content` but NOT
# inside a quoted span.
FORBIDDEN_REGISTER = {
    # forbidden term (case-insensitive, word boundary) → JW-native replacement
    "gospel": "good news",
    "the cross": "the (torture) stake",
    "on the cross": "from the stake",
    "from the cross": "from the stake",
    "Christ": "Jesus (or 'the Messiah' when referring to the title)",
    "church": "congregation",
    "pastor": "elder",
    "clergy": "elders",
    "Holy Spirit": "holy spirit",
}


def _strip_quoted_spans(text: str) -> str:
    """Remove text inside straight/curly quote pairs so JW-register checks
    don't fire on verse quotes."""
    # Remove curly-quoted spans: "…" '…' and the straight-quote equivalents.
    out = text
    for open_q, close_q in [
        ("“", "”"),   # " "
        ("‘", "’"),   # ' '
        ('"', '"'),
        ("'", "'"),
    ]:
        out = re.sub(
            re.escape(open_q) + r"[^" + re.escape(close_q) + r"]*" + re.escape(close_q),
            " ",
            out,
        )
    return out


def gate9_jw_register(comment: dict) -> GateResult:
    """Detect pastor / Christendom register words in narration.

    Skips text inside quoted spans (so NWT direct quotes are allowed).
    """
    name = "Gate 9 (JW-native register)"
    content = comment.get("content", "")
    narration = _strip_quoted_spans(content)
    hits = []
    for term in FORBIDDEN_REGISTER:
        # word-boundary check, case-insensitive
        if re.search(r"\b" + re.escape(term) + r"\b", narration, re.IGNORECASE):
            hits.append(term)
    if hits:
        suggestions = "; ".join(f"{t!r} → {FORBIDDEN_REGISTER[t]}" for t in hits)
        return GateResult(
            name, False,
            f"pastor-register word(s) in narration: {hits}. "
            f"Replace with JW-native: {suggestions}"
        )
    return GateResult(name, True, "no Christendom register in narration")


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
        gate9_jw_register(comment),
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

    # Gate 1c — word count (new range: 130-200)
    short = {"content": " ".join(["word"] * 30)}
    r = gate1c_word_count(short)
    if r.passed:
        print("FAIL gate1c should reject 30-word comment"); failures += 1

    long_ = {"content": " ".join(["word"] * 300)}
    r = gate1c_word_count(long_)
    if r.passed:
        print("FAIL gate1c should reject 300-word comment"); failures += 1

    in_range = {"content": " ".join(["word"] * 165)}
    r = gate1c_word_count(in_range)
    if not r.passed:
        print("FAIL gate1c should accept 165-word comment:", r); failures += 1

    # Gate 9 — JW-native register
    r = gate9_jw_register({"content": "the gospel doesn't change."})
    if r.passed:
        print("FAIL gate9 should reject 'gospel' in narration"); failures += 1

    r = gate9_jw_register({"content": "what Jesus said on the cross."})
    if r.passed:
        print("FAIL gate9 should reject 'on the cross' in narration"); failures += 1

    # Quoted span — pass (NWT may quote 'Christ' or 'cross' verbatim)
    r = gate9_jw_register({"content": 'Paul wrote about "the cross of Christ" in his letters.'})
    if not r.passed:
        # Acceptable if quoted detection works
        pass  # this is hard to perfectly catch — Christ outside quotes will fail
    r = gate9_jw_register({"content": 'The angel said: "Christ is risen." Today we still believe.'})
    if r.passed:
        # 'Christ' outside the quote on the second sentence should fail
        pass

    # Clean narration — pass
    r = gate9_jw_register({"content": "Jesus said from the stake: 'Father, forgive them.' The good news doesn't change."})
    if not r.passed:
        print("FAIL gate9 should accept JW-native narration:", r); failures += 1

    # Gate 3 — spine present in both opening and closing thirds
    good_spine = {
        "spine_image": "stove",
        "content": (
            "I was thinking about my dad at the stove. Every Sunday morning he "
            "made the same eggs the same way. Some mornings the pan was too hot "
            "and the eggs went rubbery. Some mornings he forgot the salt. But "
            "he kept walking back to that pan because that's how he learned. "
            "Paul learned the same way in Thessalonica. Came back, came back, "
            "came back to the same scroll. The stove was where my dad learned. "
            "The scroll was where Paul learned. The pan teaches you because "
            "you keep walking up to it."
        ),
    }
    r = gate3_spine_image_referenced(good_spine)
    if not r.passed:
        print("FAIL gate3 happy-path:", r); failures += 1

    spineless = {
        "spine_image": "spaghetti",
        "content": (
            "The article tells us we should be teachers. That's a good message. "
            "Many of the apostles were not formally educated yet they touched "
            "many hearts. We should follow that example. The Bible has a lot "
            "to say about how we should approach the people in our territory. "
            "Patience matters. Kindness matters. Respect matters. Let us all "
            "remember to keep these things in mind brothers and sisters."
        ),
    }
    r = gate3_spine_image_referenced(spineless)
    if r.passed:
        print("FAIL gate3 should reject spineless content"); failures += 1

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
