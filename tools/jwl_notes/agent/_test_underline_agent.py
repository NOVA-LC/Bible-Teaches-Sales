"""End-to-end battery for the underline agent.

Tests 1-5 each call the real Anthropic SDK against a real or constructed
paragraph and check the agent recovers / produces sane output.

Test 6 runs every produced phrase through jwl_notes.find_token_range
(the canonical tokenizer the injector uses) — proves the agent's output
won't fail at injection time.

Run:
    cd tools/jwl_notes
    python -m agent._test_underline_agent
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))   # jwl_notes
sys.path.insert(0, str(_HERE))          # agent

from underline_agent import draft_underlines_with_agent  # noqa: E402
from build_week import scrape_article  # noqa: E402
from jwl_notes import (  # noqa: E402
    fetch_wol_article,
    extract_paragraph_tokens,
    find_token_range,
)


@dataclass
class _Para:
    paragraph_number: int
    body_pid: int
    question_text: str | None
    body_text: str
    cited_scriptures: list[str]


def _show(title, history, payload):
    print(f"\n===== {title} =====")
    for g in history:
        sigil = "OK" if g.passed else "FAIL"
        print(f"  [{sigil}] {g.gate}: {g.reason}")
    print("  PAYLOAD:", json.dumps(payload, indent=2, ensure_ascii=False) if payload else "None")


def test_real_paragraph(html, paragraphs, target_para_num):
    """Test 1: feed the agent a REAL article paragraph and verify output."""
    para_data = next(p for p in paragraphs if p.paragraph_number == target_para_num)
    para = _Para(
        paragraph_number=para_data.paragraph_number,
        body_pid=para_data.body_pid,
        question_text=para_data.question_text,
        body_text=para_data.body_text,
        cited_scriptures=para_data.cited_scriptures,
    )
    print(f"\n--- TEST: REAL paragraph #{target_para_num} (body_pid={para.body_pid}) ---")
    print(f"  Q: {para.question_text}")
    print(f"  Body[:200]: {para.body_text[:200]!r}")
    print(f"  Cited: {para.cited_scriptures}")
    payload, history = draft_underlines_with_agent(para)
    _show(f"REAL ¶{target_para_num} result", history, payload)
    if payload is None:
        return False, payload, para
    return True, payload, para


def test_curly_quotes():
    """Test 2: body has curly apostrophe; agent should diagnose + correct."""
    body = "His teaching was based on God’s Word and he showed full reliance on it."
    para = _Para(
        paragraph_number=99,
        body_pid=999,
        question_text="How did Jesus show he relied on God’s Word when teaching?",
        body_text=body,
        cited_scriptures=[],
    )
    print(f"\n--- TEST: curly-quote diagnostic recovery ---")
    print(f"  body uses U+2019 right-single-quote in 'God’s'")
    payload, history = draft_underlines_with_agent(para)
    _show("Curly-quote result", history, payload)
    if not payload:
        return False, None, para
    # Confirm at least one yellow phrase actually contains the curly apostrophe
    yellows = [u for u in payload.get("underlines", []) if u.get("color") == "yellow"]
    has_curly = any("’" in u.get("phrase", "") for u in yellows)
    print(f"  yellow phrase contains U+2019? {has_curly}")
    return has_curly, payload, para


def test_agent_side_deferral():
    """Test 3: body that bypasses the regex pre-check but has no narrated answer.
    Agent must self-defer via the escape hatch."""
    body = "Read Job 42:10-13. Notice how Jehovah responds to a faithful servant."
    # The regex requires the body to be ONLY "Read X:Y-Z" — this body has extra
    # narration so the pre-check won't fire. The agent must reason that the
    # actual answer to a typical question lives in the cited verses, not the body.
    para = _Para(
        paragraph_number=11,
        body_pid=111,
        question_text="How did Jehovah respond to Job?",
        body_text=body,
        cited_scriptures=["Job 42:10-13"],
    )
    print(f"\n--- TEST: agent-side deferral (regex bypassed) ---")
    print(f"  body: {body!r}")
    payload, history = draft_underlines_with_agent(para)
    _show("Agent-side deferral result", history, payload)
    if not payload:
        return False, None, para
    deferred = payload.get("deferred_to_scripture") or payload.get("self_audit", {}).get("deferred_to_scripture")
    print(f"  Agent declared deferred? {bool(deferred)}")
    return bool(deferred), payload, para


def test_token_range_parity(payloads_with_paras):
    """Test 4: every phrase in every payload must resolve via find_token_range.
    Closes the asymmetric-strictness gap between agent's `in body_text` check
    and the injector's canonical tokenizer."""
    print(f"\n--- TEST: find_token_range parity (canonical tokenizer) ---")
    # Only test phrases against real article HTML — synthetic paragraphs have
    # no corresponding HTML in WOL. We use the article HTML from the real
    # paragraph test (paragraphs sourced from scrape_article).
    failures = []
    checked = 0
    for tag, payload, para, article_html in payloads_with_paras:
        if not payload or not payload.get("underlines"):
            continue
        if article_html is None:
            continue
        try:
            tokens = extract_paragraph_tokens(article_html, para.body_pid)
        except ValueError as e:
            failures.append(f"  [{tag}] could not extract tokens for body_pid={para.body_pid}: {e}")
            continue
        for u in payload["underlines"]:
            phrase = u.get("phrase", "")
            checked += 1
            try:
                start, end = find_token_range(tokens, phrase)
                print(f"  OK [{tag}] {u.get('color')}: {phrase!r} -> tokens[{start}:{end+1}]")
            except ValueError as e:
                failures.append(f"  FAIL [{tag}] {u.get('color')} phrase {phrase!r}: {e}")
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f)
    print(f"\n  Phrases checked: {checked} | failures: {len(failures)}")
    return len(failures) == 0


def main():
    print("Fetching May 10 WT article (DocId 2026320, cached if possible)...")
    article_html = fetch_wol_article(2026320, "w")
    paragraphs = scrape_article(article_html)
    print(f"  scraped {len(paragraphs)} paragraphs.")

    results = {}
    payloads_for_parity = []

    # Test 1: real article paragraph (¶3 has a clear multi-component question)
    ok, payload, para = test_real_paragraph(article_html, paragraphs, target_para_num=3)
    results["real_p3"] = ok
    payloads_for_parity.append(("real_p3", payload, para, article_html))

    # Also test ¶7 — multi-yellow paragraph that shipped 3 underlines on May 10
    ok, payload, para = test_real_paragraph(article_html, paragraphs, target_para_num=7)
    results["real_p7"] = ok
    payloads_for_parity.append(("real_p7", payload, para, article_html))

    # Test 2: curly-quote recovery (synthetic — no article HTML for parity check)
    ok, payload, para = test_curly_quotes()
    results["curly_quotes"] = ok

    # Test 3: agent-side deferral (synthetic)
    ok, payload, para = test_agent_side_deferral()
    results["agent_deferral"] = ok

    # Test 4: token-range parity for real-article payloads
    results["token_parity"] = test_token_range_parity(payloads_for_parity)

    print("\n\n========== SUMMARY ==========")
    for name, ok in results.items():
        sigil = "OK  " if ok else "FAIL"
        print(f"  [{sigil}] {name}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
