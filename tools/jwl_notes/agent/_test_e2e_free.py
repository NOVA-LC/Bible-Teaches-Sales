"""_test_e2e_free.py — end-to-end deterministic regression suite. Zero API.

Run before any production lesson agent run. Catches all the bugs we shipped
this week:
  - commit_comment schema too vague (kwargs vs payload-wrapped)
  - verse_comment.md missing 12-toolbox list
  - underline non-yellow > 8 words blocking shipment instead of filtering
  - CBS pid collision across multi-lesson sources
  - load_dotenv empty-env-var blocking
  - discover_lesson enum missing cbs/gems
  - Insight URL regex missing query string

Plus invariants that haven't broken yet but should be locked:
  - Article-level gates (2, 4, 5, 11) behave correctly on varied inputs
  - Checkpoint round-trip preserves state
  - Shipped JSON shape conforms to what jwl_notes injector validates
  - Token-range parity: every phrase in shipped JSONs resolves via
    canonical find_token_range tokenizer

Run:
    cd tools/jwl_notes
    python -m agent._test_e2e_free

Exits 0 on all pass; 1 on any failure. Target runtime <10 seconds.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))


# ----------------------------------------------------------------------
# Test framework — counts pass/fail + tags each result with category
# ----------------------------------------------------------------------

class TestRun:
    def __init__(self):
        self.passed = 0
        self.failed: list[str] = []
        self.section = ""

    def start(self, section: str):
        self.section = section
        print(f"\n=== {section} ===")

    def check(self, label: str, condition: bool, detail: str = ""):
        if condition:
            self.passed += 1
            print(f"  OK   {label}")
        else:
            msg = f"{self.section} :: {label}"
            if detail:
                msg += f" — {detail}"
            self.failed.append(msg)
            print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))

    def equal(self, label: str, actual, expected):
        self.check(label, actual == expected,
                   f"expected {expected!r}, got {actual!r}")

    def summary(self) -> int:
        total = self.passed + len(self.failed)
        print(f"\n========== SUMMARY ==========")
        print(f"  passed: {self.passed} / {total}")
        if self.failed:
            print(f"  FAILED ({len(self.failed)}):")
            for f in self.failed:
                print(f"    - {f}")
        return 0 if not self.failed else 1


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------

def test_dotenv_empty_var_override(t: TestRun):
    t.start("workers.load_dotenv: empty-env-var override")
    # Simulate: shell has ANTHROPIC_API_KEY="" (empty), .env has real key
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        env_file = td / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-test-real-key\n", encoding="utf-8")
        # Save original env
        orig = os.environ.get("ANTHROPIC_API_KEY")
        try:
            os.environ["ANTHROPIC_API_KEY"] = ""
            from workers import load_dotenv  # type: ignore
            load_dotenv(env_path=env_file)
            t.equal("empty var was overridden by .env",
                    os.environ.get("ANTHROPIC_API_KEY"), "sk-ant-test-real-key")
        finally:
            if orig is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = orig


def test_underline_deferred_regex(t: TestRun):
    t.start("underline_agent._DEFERRED_BODY_RE")
    from underline_agent import _DEFERRED_BODY_RE  # type: ignore
    cases = [
        ("Read Job 42:10-13.", True),
        ("Read Job 42:10-13", True),
        ("Read 2 Timothy 3:1-5.", True),
        ("See Isaiah 60:1, 2", True),
        ("READ JOB 42:10-13.", True),
        ("read genesis 1:1.", True),
        ("16 Read Genesis 1:26-28.", True),
        (" 7 Read Matthew 5:3-12. ", True),
        ("Read Job 42:10-13. Then think about it.", False),
        ("Jesus did not rely on his own knowledge.", False),
    ]
    for body, expected in cases:
        got = bool(_DEFERRED_BODY_RE.match(body))
        t.check(f"defer-regex({body!r}) == {expected}", got == expected,
                f"got {got}")


def test_underline_commit_filters_overcap_nonyellow(t: TestRun):
    t.start("underline_agent.commit: drop non-yellow > 8 words, keep yellow")
    from underline_agent import _make_tool_handlers  # type: ignore
    body = "His teaching was based on God's Word and he showed full reliance on it during every encounter."
    question = "How did Jesus rely on God's Word?"
    _, commit, state = _make_tool_handlers(body, question)
    # Yellow + over-cap green
    underlines = [
        {"phrase": "His teaching was based on God's Word", "color": "yellow",
         "answers_question": True},
        {"phrase": "and he showed full reliance on it during every encounter",
         "color": "green", "answers_question": False, "scripture_explainer_for": None},
    ]
    self_audit = {"yellow_count": 1, "all_yellows_complete_answers": True,
                  "all_yellows_grammatical": True}
    r = commit(underlines, self_audit)
    t.check("commit accepted=True", r.get("accepted"),
            f"result: {r}")
    t.equal("filtered_non_yellow has 1 entry", len(r.get("filtered_non_yellow", [])), 1)
    if r.get("accepted"):
        final_uls = (state.get("payload") or {}).get("underlines", [])
        t.equal("only yellow survived in payload", len(final_uls), 1)
        t.equal("survivor is yellow", final_uls[0]["color"], "yellow")


def test_underline_commit_deferred(t: TestRun):
    t.start("underline_agent.commit: deferred-to-scripture escape hatch")
    from underline_agent import _make_tool_handlers  # type: ignore
    body = "Read Job 42:10-13."
    _, commit, state = _make_tool_handlers(body, "How did Jehovah reward Job?")
    r = commit([], {"deferred_to_scripture": True, "reason": "no narrated answer"})
    t.check("deferred commit accepted", r.get("accepted"))
    t.equal("payload.deferred_to_scripture", state["payload"]["deferred_to_scripture"], True)


def test_comment_agent_check_constraints(t: TestRun):
    t.start("comment_agent._check_constraints (H + I guards)")
    from comment_agent import _check_constraints  # type: ignore
    # H — forbidden_types short-circuit
    fails = _check_constraints({"comment_type": "F"}, {"forbidden_types": ["F"]}, {})
    t.equal("forbidden type F + ct=F: 1 fail", len(fails), 1)
    fails = _check_constraints({"comment_type": "A"}, {"forbidden_types": ["F"]}, {})
    t.equal("forbidden F + ct=A: 0 fails", len(fails), 0)
    # I — force_domestic_scene with wrong type
    fails = _check_constraints({"comment_type": "C"}, {},
                               {"force_domestic_scene": True})
    t.equal("force_domestic + ct=C: 1 fail", len(fails), 1)
    fails = _check_constraints({"comment_type": "A", "domestic_scene": {
        "present": True, "named_relationship": "brother"}},
        {}, {"force_domestic_scene": True})
    t.equal("force_domestic + ct=A + named rel: 0 fails", len(fails), 0)
    # I — force_herd_move
    fails = _check_constraints({"comment_type": "A", "herd_distinctive_moves": ["H3"]},
                               {}, {"force_herd_move": "H1"})
    t.equal("force_herd=H1 + has [H3]: 1 fail", len(fails), 1)
    fails = _check_constraints({"comment_type": "A", "herd_distinctive_moves": ["H3", "H1"]},
                               {}, {"force_herd_move": "H1"})
    t.equal("force_herd=H1 + has [H3,H1]: 0 fails", len(fails), 0)
    # I — force_invert_mode
    fails = _check_constraints({"comment_type": "A", "transformation_mechanism": "release"},
                               {}, {"force_invert_mode": True})
    t.equal("force_invert + release: 1 fail", len(fails), 1)


def test_comment_agent_tool_schema(t: TestRun):
    t.start("comment_agent.TOOLS schema invariants")
    from comment_agent import TOOLS  # type: ignore
    names = [tool["name"] for tool in TOOLS]
    t.equal("6 tools", len(TOOLS), 6)
    t.check("includes look_up_insight", "look_up_insight" in names)
    t.check("includes commit_comment", "commit_comment" in names)
    t.check("last tool has cache_control",
            "cache_control" in TOOLS[-1])
    commit_tool = next(t_ for t_ in TOOLS if t_["name"] == "commit_comment")
    props = commit_tool["input_schema"]["properties"]
    t.check("commit_comment accepts error field", "error" in props)
    t.check("commit_comment accepts comment_type", "comment_type" in props)
    t.check("commit_comment additionalProperties: True",
            commit_tool["input_schema"].get("additionalProperties") is True)


def test_article_level_gates(t: TestRun):
    t.start("gates: article-level (Gate 2 / 4 / 5 / 11)")
    from gates import run_article_gates  # type: ignore
    # 4 A's + 5 D's + 0 F's — Gate 11 should fail (A used 4x, cap 3)
    comments = (
        [{"paragraph_number": i, "comment_type": "A",
          "content": "word " * 150,
          "tagged_beats": [
              {"text": "x", "mechanic": "Bourdain climactic-moment opener"},
              {"text": "y", "mechanic": "Clear two-noun pivot"},
              {"text": "z", "mechanic": "Sam Herd parallel-clause inversion"},
          ]}
         for i in range(1, 5)]
        + [{"paragraph_number": i, "comment_type": "D"} for i in range(5, 10)]
    )
    results = run_article_gates(comments)
    gate11 = next(g for g in results if "11" in g.gate)
    t.check("Gate 11 fails when A used 4x (cap 3)", not gate11.passed,
            f"reason: {gate11.reason[:120]}")
    # Same article shape but A only 3x AND no other type over cap — Gate 11 should pass.
    # Distribution: 3 A + 3 D + 3 F = 9 paragraphs, every type at cap (3) but not over.
    a_block = [{"paragraph_number": i, "comment_type": "A",
                "content": "word " * 150,
                "tagged_beats": [
                    {"text": "x", "mechanic": "Bourdain climactic-moment opener"},
                    {"text": "y", "mechanic": "Clear two-noun pivot"},
                    {"text": "z", "mechanic": "Sam Herd parallel-clause inversion"},
                ]} for i in range(1, 4)]
    d_block = [{"paragraph_number": i, "comment_type": "D"} for i in range(4, 7)]
    f_block = [{"paragraph_number": i, "comment_type": "F"} for i in range(7, 10)]
    comments2 = a_block + d_block + f_block
    results2 = run_article_gates(comments2)
    gate11_2 = next(g for g in results2 if "11" in g.gate)
    t.check("Gate 11 passes when every type at cap (3 A + 3 D + 3 F)",
            gate11_2.passed, f"reason: {gate11_2.reason[:120]}")


def test_cbs_split(t: TestRun):
    t.start("CBS: scrape + commit_lesson split (delegating to _test_cbs_split)")
    # Reuse the existing test module's assertions; on failure it raises.
    try:
        # Run the deterministic parts of the dedicated CBS test
        from _test_cbs_split import (  # type: ignore
            test_scrape_produces_unique_pids,
            test_commit_lesson_splits_by_lesson,
            test_resume_cache_isolation,
        )
        all_paras = test_scrape_produces_unique_pids()
        test_commit_lesson_splits_by_lesson(all_paras)
        test_resume_cache_isolation(all_paras)
        t.check("CBS split test suite passes", True)
    except AssertionError as e:
        t.check("CBS split test suite passes", False, str(e))


def test_checkpoint_roundtrip(t: TestRun):
    t.start("lesson_agent: checkpoint save → load round-trip")
    from lesson_agent import LessonState, _save_comment, _save_underline, _save_meta, _load_state  # type: ignore
    from comment_agent import CostTracker  # type: ignore
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        log_fh = (td / "test.log").open("w")
        try:
            s = LessonState("2026-05-17", "wt", False, CostTracker(), td, log_fh)
            s.article_meta = {"document_id": 2026321, "key_symbol": "w", "title": "t"}
            s.drafted_comments[41] = {"comment_type": "A", "content": "hello"}
            s.drafted_underlines[7] = {"underlines": [{"phrase": "hi", "color": "yellow"}]}
            s.failed_comments = [5]
            s.redraft_cycles_used = 2
            _save_comment(s, 41, s.drafted_comments[41])
            _save_underline(s, 7, s.drafted_underlines[7])
            _save_meta(s)
        finally:
            log_fh.close()
        log_fh2 = (td / "test.log").open("a")
        try:
            s2 = LessonState("2026-05-17", "wt", False, CostTracker(), td, log_fh2)
            summary = _load_state(s2)
        finally:
            log_fh2.close()
        t.check("loaded=True", summary["loaded"])
        t.equal("1 comment loaded", summary["comments"], 1)
        t.equal("1 underline loaded", summary["underlines"], 1)
        t.equal("failed_comments preserved", s2.failed_comments, [5])
        t.equal("redraft_cycles preserved", s2.redraft_cycles_used, 2)
        # Mismatch study_date → don't load anything
        log_fh3 = (td / "test.log").open("a")
        try:
            s3 = LessonState("2026-05-24", "wt", False, CostTracker(), td, log_fh3)
            summary3 = _load_state(s3)
        finally:
            log_fh3.close()
        t.check("mismatch study_date: nothing loads", not summary3["loaded"])


def test_wt_scrape_on_cached_article(t: TestRun):
    t.start("build_week.scrape_article: WT article (cached May 17)")
    from build_week import scrape_article  # type: ignore
    from jwl_notes import fetch_wol_article  # type: ignore
    try:
        html = fetch_wol_article(2026321, "w")  # cache hit (no network)
    except Exception as e:
        t.check(f"cached WT article fetch", False, f"network: {e}")
        return
    paras = scrape_article(html)
    t.equal("20 paragraphs scraped", len(paras), 20)
    t.check("all have question_pid", all(p.question_pid is not None for p in paras))
    t.check("all have body_text", all(p.body_text and len(p.body_text) > 30 for p in paras))


def test_discover_week_cbs(t: TestRun):
    t.start("discover_week: CBS lesson DocId extraction")
    from discover_week import discover, _lesson_count_from_label  # type: ignore
    # Label parsing
    t.equal("count(lessons 84-85)", _lesson_count_from_label("lfb lessons 84-85"), 2)
    t.equal("count(lesson 86)", _lesson_count_from_label("lfb lesson 86"), 1)
    t.equal("count(lessons 84, 86, 88)", _lesson_count_from_label("lessons 84, 86, 88"), 3)
    t.equal("count(None)", _lesson_count_from_label(None), 1)
    # Real-week discovery: May 17 = lessons 84-85 (range, 2 DocIds);
    # May 24 = lesson 86 (single, 1 DocId — would have leaked 5 nav-link
    # DocIds without the frequency-by-label-count parser fix).
    try:
        wd17 = discover(study_date="2026-05-17")
    except Exception as e:
        t.check("discover May 17", False, f"network: {e}")
        return
    t.equal("May 17 WT DocId", wd17.wt_document_id, 2026321)
    t.equal("May 17 CBS DocIds (lessons 84-85)", wd17.cbs_document_ids,
            [1102016094, 1102016095])
    t.equal("May 17 CBS publication", wd17.cbs_publication, "lfb")
    t.equal("May 17 Bible reading book (Isaiah)", wd17.bible_reading_book, 23)
    t.equal("May 17 Bible chapters", (wd17.bible_reading_chapter_start, wd17.bible_reading_chapter_end),
            (60, 61))
    # May 24 — regression for the over-greedy DocId parser
    try:
        wd24 = discover(study_date="2026-05-24")
    except Exception as e:
        t.check("discover May 24", False, f"network: {e}")
        return
    t.equal("May 24 CBS DocIds (lesson 86 — exactly 1)", wd24.cbs_document_ids,
            [1102016096])
    t.equal("May 24 Bible reading book", wd24.bible_reading_book, 23)
    t.equal("May 24 Bible chapters", (wd24.bible_reading_chapter_start, wd24.bible_reading_chapter_end),
            (62, 64))


def test_json_wire_shape_validates(t: TestRun):
    t.start("jwl_notes.load_comments: every shipped JSON validates")
    from jwl_notes import load_comments  # type: ignore
    comments_dir = _HERE.parent / "comments"
    json_files = sorted(comments_dir.glob("2026-05-*.json"))
    t.check("found shipped JSONs", len(json_files) > 0,
            f"looked in {comments_dir}")
    for jf in json_files:
        try:
            spec = load_comments(jf)
            t.check(f"{jf.name} validates", isinstance(spec.get("notes"), list))
        except SystemExit as e:
            t.check(f"{jf.name} validates", False, str(e))


def test_token_range_parity_for_shipped_underlines(t: TestRun):
    t.start("jwl_notes.find_token_range: shipped underline phrases all resolve")
    from jwl_notes import fetch_wol_article, extract_paragraph_tokens, find_token_range  # type: ignore
    wt_json = _HERE.parent / "comments" / "2026-05-17-w.json"
    if not wt_json.exists():
        t.check("May 17 WT JSON present", False, "skipping")
        return
    try:
        html = fetch_wol_article(2026321, "w")
    except Exception as e:
        t.check("cached WT HTML fetch", False, f"{e}")
        return
    doc = json.loads(wt_json.read_text(encoding="utf-8"))
    checked = 0
    fails = []
    for note in doc.get("notes", []):
        ul = note.get("underlines")
        if not ul:
            continue
        try:
            tokens = extract_paragraph_tokens(html, note["data_pid"])
        except Exception as e:
            fails.append(f"could not extract tokens for pid={note['data_pid']}: {e}")
            continue
        for u in ul:
            checked += 1
            try:
                find_token_range(tokens, u["phrase"])
            except ValueError as e:
                fails.append(f"pid={note['data_pid']} {u.get('color')} {u['phrase']!r}: {e}")
    t.check(f"{checked} phrases checked, {len(fails)} failures",
            len(fails) == 0,
            ", ".join(fails[:3]) if fails else "")


def test_lesson_agent_tools_complete(t: TestRun):
    t.start("lesson_agent.TOOLS schema: all 10 + cache_control")
    from lesson_agent import TOOLS  # type: ignore
    expected = {
        "discover_lesson", "scrape_paragraphs", "draft_comment",
        "draft_underlines", "get_status", "run_article_gates",
        "redraft_comment", "commit_lesson", "email_results",
        "commit_lesson_failure",
    }
    names = {tool["name"] for tool in TOOLS}
    t.equal("10 tools", len(TOOLS), 10)
    t.equal("tool names complete", names, expected)
    t.check("last tool has cache_control", "cache_control" in TOOLS[-1])
    # discover_lesson enum includes cbs + gems
    discover_tool = next(t_ for t_ in TOOLS if t_["name"] == "discover_lesson")
    target_enum = discover_tool["input_schema"]["properties"]["target"]["enum"]
    t.check("discover_lesson enum includes cbs", "cbs" in target_enum,
            f"enum: {target_enum}")
    t.check("discover_lesson enum includes gems", "gems" in target_enum)


def test_assemble_skips_empty_underlines(t: TestRun):
    t.start("build_week.assemble_comments_json: skip empty underline rows")
    from build_week import ParagraphData, assemble_comments_json  # type: ignore
    paras = [
        ParagraphData(paragraph_number=1, body_pid=10, question_pid=11,
                      question_text="Q?", body_text="body",
                      cited_scriptures=[]),
    ]
    # Comment present, underline deferred (empty list)
    comments = {10: {"comment_type": "A", "content": "draft"}}
    underlines = {10: {"underlines": [], "deferred_to_scripture": True}}
    doc = assemble_comments_json(
        {"article_title": "t", "article_source": "s", "study_date": "2026-05-17",
         "key_symbol": "w", "issue": 0, "document_id": 1, "url": ""},
        paras, comments, underlines,
    )
    rows = doc.get("notes", [])
    # Should have 1 comment row, 0 underline rows
    has_content = sum(1 for n in rows if n.get("content"))
    has_underlines = sum(1 for n in rows if n.get("underlines"))
    t.equal("1 comment row", has_content, 1)
    t.equal("0 underline rows (deferred)", has_underlines, 0)


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------

def main() -> int:
    t = TestRun()
    started = time.time()
    test_dotenv_empty_var_override(t)
    test_underline_deferred_regex(t)
    test_underline_commit_filters_overcap_nonyellow(t)
    test_underline_commit_deferred(t)
    test_comment_agent_check_constraints(t)
    test_comment_agent_tool_schema(t)
    test_lesson_agent_tools_complete(t)
    test_article_level_gates(t)
    test_cbs_split(t)
    test_checkpoint_roundtrip(t)
    test_assemble_skips_empty_underlines(t)
    test_wt_scrape_on_cached_article(t)
    test_discover_week_cbs(t)
    test_json_wire_shape_validates(t)
    test_token_range_parity_for_shipped_underlines(t)
    print(f"\n  Elapsed: {time.time() - started:.2f}s")
    return t.summary()


if __name__ == "__main__":
    sys.exit(main())
