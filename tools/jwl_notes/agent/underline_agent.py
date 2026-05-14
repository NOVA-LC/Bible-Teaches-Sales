"""Underline agent — tool-using replacement for _draft_underlines_with_gates.

The chained pipeline calls draft_underlines() once per paragraph, gates the
result externally, and on failure restarts with a string of feedback in a
fresh context. That's 25 restarts in the worst case (May 17 burned this on
¶9, ¶11, ¶13).

This module replaces that loop with a tool-using agent. The agent has:

  - `verify_phrase_verbatim(phrase)` — checks character-exact match against
    the paragraph body. Diagnoses curly-quote / paraphrase divergence.
  - `commit_underlines(underlines, self_audit)` — runs the deterministic
    underline gates (same ones the chained pipeline uses) and returns the
    verdict. If rejected, the agent gets specific gate reasons IN ITS OWN
    CONTEXT and revises without a restart.

Two safety belts:
  - Deterministic pre-check for "Read X:Y-Z" body shapes — no SDK call.
  - Hard turn cap (MAX_TURNS).

Drop-in for build_week.py: same signature and return type as
_draft_underlines_with_gates.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from gates import GateResult, run_underline_gates  # type: ignore  # noqa: E402
from workers import load_dotenv  # type: ignore  # noqa: E402


PROMPTS_DIR = _HERE / "prompts"
MAX_TURNS = 12
DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048

# Body shapes that are just "Read X:Y-Z" — no narrated answer to underline.
# Matches: "Read Job 42:10-13.", "Read 2 Timothy 3:1-5", "See Isaiah 60:1, 2"
_DEFERRED_BODY_RE = re.compile(
    r"^\s*(?:read|see)\s+\d?\s?[a-z][a-z]+\.?\s+\d+:\d+(?:[\s,\-–]+\d+)*\.?\s*$",
    re.IGNORECASE,
)


_FATAL_ERROR_MARKERS = (
    "credit balance is too low",
    "invalid x-api-key",
    "authentication_error",
    "permission_error",
    "Your account has been disabled",
)


def _is_fatal(err: Exception) -> bool:
    return any(m in str(err) for m in _FATAL_ERROR_MARKERS)


def _load_system_prompt() -> str:
    return (PROMPTS_DIR / "underline_agent.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------
# Tool implementations — closures over the paragraph's body + question
# --------------------------------------------------------------------

_QUOTE_NORMALIZE = (
    ("’", "'"),  # right single quote
    ("‘", "'"),  # left single quote
    ("“", '"'),  # left double quote
    ("”", '"'),  # right double quote
    ("–", "-"),  # en-dash
    ("—", "-"),  # em-dash
)


def _normalize_quotes(s: str) -> str:
    for a, b in _QUOTE_NORMALIZE:
        s = s.replace(a, b)
    return s


def _make_tool_handlers(body_text: str, question_text: str):
    """Return (verify, commit, state) closures over the paragraph's body and
    question. `state['payload']` is set when commit accepts the submission."""
    state: dict[str, Any] = {"payload": None, "last_gates": []}
    body_normalized = _normalize_quotes(body_text)

    def verify(phrase: str) -> dict:
        if not isinstance(phrase, str) or not phrase:
            return {"ok": False, "reason": "phrase is empty"}
        if phrase in body_text:
            return {"ok": True}
        phrase_norm = _normalize_quotes(phrase)
        if phrase_norm in body_normalized:
            idx = body_normalized.find(phrase_norm)
            verbatim = body_text[idx:idx + len(phrase)]
            return {
                "ok": False,
                "reason": (
                    "smart-quote / apostrophe / dash mismatch — your phrase "
                    "uses different quote characters than the source. Copy "
                    "from body_paragraph_text exactly."
                ),
                "source_text_at_match": verbatim,
            }
        # Longest matching prefix — helps the agent see where it paraphrased.
        for cut in range(len(phrase), 4, -1):
            if phrase[:cut] in body_text:
                return {
                    "ok": False,
                    "reason": (
                        f"phrase diverges from source after first {cut} chars — "
                        "likely paraphrased. Re-read body_paragraph_text and "
                        "copy a real verbatim span."
                    ),
                    "longest_matching_prefix": phrase[:cut],
                }
        return {
            "ok": False,
            "reason": (
                "phrase does not appear in body_paragraph_text at all — "
                "likely paraphrased. Copy verbatim from the source."
            ),
        }

    def commit(underlines: list, self_audit: dict) -> dict:
        # Deferred-to-scripture escape hatch: empty underlines + explicit flag
        # bypasses the no-yellow-required gate. Only meaningful when the body
        # has no narrated answer (e.g., "Read Job 42:10-13").
        if not underlines and isinstance(self_audit, dict) and self_audit.get("deferred_to_scripture"):
            payload = {
                "underlines": [],
                "self_audit": self_audit,
                "deferred_to_scripture": True,
            }
            state["payload"] = payload
            state["last_gates"] = [GateResult(
                "Underline-gate (deferred to scripture)",
                True,
                f"Self-declared deferral: {self_audit.get('reason', '(no reason)')}",
            )]
            return {
                "accepted": True,
                "gate_results": [
                    {"gate": g.gate, "passed": g.passed, "reason": g.reason}
                    for g in state["last_gates"]
                ],
            }

        payload = {"underlines": underlines, "self_audit": self_audit}
        gate_results = run_underline_gates(payload, body_text, question_text)
        passed = all(g.passed for g in gate_results)
        state["last_gates"] = gate_results
        if passed:
            state["payload"] = payload
        return {
            "accepted": passed,
            "gate_results": [
                {"gate": g.gate, "passed": g.passed, "reason": g.reason}
                for g in gate_results
            ],
        }

    return verify, commit, state


# --------------------------------------------------------------------
# Tool schemas
# --------------------------------------------------------------------

TOOLS = [
    {
        "name": "verify_phrase_verbatim",
        "description": (
            "Verify that `phrase` appears character-exact in the paragraph's "
            "body_paragraph_text. Call this for EVERY candidate underline "
            "phrase BEFORE calling commit_underlines. Returns ok=true if "
            "verbatim, else explains the divergence (curly-quote mismatch, "
            "paraphrase, etc.) and where the phrase first diverged. Cheap; "
            "call liberally."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phrase": {
                    "type": "string",
                    "description": "Candidate phrase, exactly as you would underline it.",
                },
            },
            "required": ["phrase"],
        },
    },
    {
        "name": "commit_underlines",
        "description": (
            "Submit the final underline payload. Orchestrator runs the "
            "deterministic underline gates (verbatim, complete grammatical "
            "answer, non-yellow ≤8 words) and returns the verdict. If "
            "accepted=true the task is done — stop. If accepted=false, "
            "revise based on the gate reasons and call again. "
            "Deferred-to-scripture: if the body has no narrated answer "
            "(e.g., just 'Read Job 42:10-13'), commit with underlines=[] "
            "and self_audit={\"deferred_to_scripture\": true, \"reason\": \"...\"}."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "underlines": {
                    "type": "array",
                    "description": "Underline objects.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "phrase": {
                                "type": "string",
                                "description": "Verbatim phrase from body_paragraph_text.",
                            },
                            "color": {
                                "type": "string",
                                "enum": ["yellow", "green", "pink", "blue", "purple"],
                            },
                            "answers_question": {"type": "boolean"},
                            "scripture_explainer_for": {
                                "type": ["string", "null"],
                                "description": (
                                    "For green underlines that bridge a cited "
                                    "scripture: the scripture citation, e.g. 'Mark 1:22'."
                                ),
                            },
                        },
                        "required": ["phrase", "color", "answers_question"],
                    },
                },
                "self_audit": {
                    "type": "object",
                    "description": (
                        "Self-audit summary. Standard keys: yellow_count (int), "
                        "all_yellows_complete_answers (bool), "
                        "all_yellows_grammatical (bool), "
                        "non_yellow_max_word_count (int), "
                        "any_phrase_not_in_source (bool). "
                        "For deferred-to-scripture: deferred_to_scripture=true plus reason."
                    ),
                },
            },
            "required": ["underlines", "self_audit"],
        },
    },
]
# Cache the tools array across many-paragraph runs (one breakpoint = whole list)
TOOLS[-1]["cache_control"] = {"type": "ephemeral"}


# --------------------------------------------------------------------
# Main agent loop
# --------------------------------------------------------------------

def draft_underlines_with_agent(para, model: str = DEFAULT_MODEL):
    """Drop-in replacement for build_week._draft_underlines_with_gates.

    Args:
        para: ParagraphData (from build_week.py). Uses .paragraph_number,
              .body_pid, .question_text, .body_text, .cited_scriptures.
        model: SDK model name. Default sonnet-4-6 per handoff economics.

    Returns:
        (underline_payload | None, list[GateResult])
        - On success: ({"underlines": [...], "self_audit": {...}}, history)
        - On deferred: ({"underlines": [], "deferred_to_scripture": True, ...}, history)
        - On failure: (None, history)
    """
    load_dotenv()
    history: list[GateResult] = []

    body_text = para.body_text or ""
    question_text = para.question_text or ""

    # Safety belt 1: deterministic pre-check for "Read X:Y-Z" bodies.
    if _DEFERRED_BODY_RE.match(body_text):
        history.append(GateResult(
            "Underline pre-check",
            True,
            "Body is 'Read X:Y-Z' shape — deferred to scripture, no SDK call",
        ))
        return (
            {
                "underlines": [],
                "deferred_to_scripture": True,
                "self_audit": {
                    "deferred_to_scripture": True,
                    "reason": "body matches 'Read X:Y-Z' regex",
                },
            },
            history,
        )

    # SDK setup
    try:
        from anthropic import Anthropic
    except ImportError:
        history.append(GateResult(
            "Underline agent", False,
            "anthropic SDK not installed (pip install anthropic)",
        ))
        return (None, history)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        history.append(GateResult(
            "Underline agent", False,
            "ANTHROPIC_API_KEY not set in .env",
        ))
        return (None, history)

    client = Anthropic()
    system_prompt = _load_system_prompt()
    verify, commit, state = _make_tool_handlers(body_text, question_text)

    user_payload = {
        "paragraph_number": para.paragraph_number,
        "data_pid": para.body_pid,
        "question_text": question_text,
        "body_paragraph_text": body_text,
        "cited_scriptures": para.cited_scriptures,
    }
    messages: list[dict] = [{
        "role": "user",
        "content": json.dumps(user_payload, indent=2, ensure_ascii=False),
    }]

    verify_calls = 0
    commit_attempts = 0

    for turn in range(1, MAX_TURNS + 1):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                tools=TOOLS,
                messages=messages,
            )
        except Exception as e:
            history.append(GateResult(
                f"Underline agent turn {turn}", False,
                f"SDK error: {e}",
            ))
            if _is_fatal(e):
                raise SystemExit(
                    f"\n❌ FATAL: {str(e)[:200]}\n"
                    f"   Fix at https://console.anthropic.com/ then rerun."
                )
            return (None, history)

        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]

        if not tool_uses:
            text_blocks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
            history.append(GateResult(
                f"Underline agent turn {turn}", False,
                f"agent stopped without committing "
                f"(stop_reason={resp.stop_reason}): "
                f"{(' '.join(text_blocks))[:200]}",
            ))
            return (None, history)

        messages.append({"role": "assistant", "content": resp.content})

        tool_results_blocks = []
        accepted = False
        for tu in tool_uses:
            args = tu.input or {}
            if tu.name == "verify_phrase_verbatim":
                verify_calls += 1
                result = verify(args.get("phrase", ""))
            elif tu.name == "commit_underlines":
                commit_attempts += 1
                result = commit(args.get("underlines", []), args.get("self_audit", {}))
                accepted = bool(result.get("accepted"))
            else:
                result = {"error": f"unknown tool: {tu.name}"}
            tool_results_blocks.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

        messages.append({"role": "user", "content": tool_results_blocks})

        if accepted:
            for g in state["last_gates"]:
                history.append(g)
            history.append(GateResult(
                "Underline agent", True,
                f"committed in {turn} turn(s) "
                f"({verify_calls} verify, {commit_attempts} commit)",
            ))
            return (state["payload"], history)

    history.append(GateResult(
        "Underline agent", False,
        f"reached MAX_TURNS={MAX_TURNS} without accepted commit "
        f"({verify_calls} verify, {commit_attempts} commit attempts)",
    ))
    if state["last_gates"]:
        for g in state["last_gates"]:
            history.append(g)
    return (None, history)


# --------------------------------------------------------------------
# CLI for quick testing on a single paragraph
# --------------------------------------------------------------------

def _cli():
    """python -m underline_agent --question "..." --body "..." [--cited Mark 1:22]"""
    import argparse
    from dataclasses import dataclass

    @dataclass
    class _Para:
        paragraph_number: int
        body_pid: int
        question_text: str | None
        body_text: str
        cited_scriptures: list[str]

    p = argparse.ArgumentParser(description="Run underline agent on one paragraph")
    p.add_argument("--question", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--cited", action="append", default=[])
    p.add_argument("--paragraph-number", type=int, default=1)
    p.add_argument("--body-pid", type=int, default=1)
    p.add_argument("--model", default=DEFAULT_MODEL)
    args = p.parse_args()

    para = _Para(
        paragraph_number=args.paragraph_number,
        body_pid=args.body_pid,
        question_text=args.question,
        body_text=args.body,
        cited_scriptures=args.cited,
    )
    payload, history = draft_underlines_with_agent(para, model=args.model)
    print("--- Gate history ---")
    for g in history:
        print(f"  {g}")
    print("\n--- Payload ---")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload else 1


if __name__ == "__main__":
    sys.exit(_cli())
