"""_test_cbs_split.py — deterministic CBS split-logic regression test.

Zero API calls. Uses cached lfb HTML for May 17 (lessons 84 + 85) plus
stubbed comment/underline payloads to exercise:

  1. scrape_cbs_lesson produces UNIQUE body_pids across lessons (so the
     resume-cache + state.drafted_comments dict doesn't collide and
     return the wrong lesson's draft for a same-pid paragraph in
     another lesson).
  2. ParagraphData.source_lesson_doc_id is set correctly.
  3. ParagraphData.original_body_pid preserves the real pid that the
     JW Library injector anchors to.
  4. commit_lesson handler splits state.drafted_comments by source
     lesson DocId and writes ONE JSON per lesson, each anchored to its
     own DocId, with original body_pids restored.
  5. No cross-contamination: lesson 84's comments only appear in
     lesson 84's JSON; same for lesson 85.

Run:
    cd tools/jwl_notes
    python -m agent._test_cbs_split

Exits 0 on all assertions pass; non-zero on any failure.

This test exists because shipping the pid-collision bug burned ~$1.77
on a broken run that produced duplicate-content paragraphs. The test
runs in <1 second on cached data and catches the regression at $0.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from jwl_notes import fetch_wol_article  # type: ignore  # noqa: E402
from lesson_agent import (  # type: ignore  # noqa: E402
    scrape_cbs_lesson,
    LessonState,
    _make_tool_handlers,
)
from comment_agent import CostTracker  # type: ignore  # noqa: E402


LESSON_84_DOC = 1102016094
LESSON_85_DOC = 1102016095
STUDY_DATE = "2026-05-17"


def _stub_comment(body_pid: int, paragraph_number: int, comment_type: str = "C") -> dict:
    """Build a stub comment. Default Type C avoids Type-A-only gates
    (mechanics tagged, spine image). Article-level gates pass when types
    are varied (Gate 11 cap is 3 per type) and at least one comment has
    a Herd move (Gate 5 relaxed_min with 0 A/B comments = 1)."""
    return {
        "comment_type": comment_type,
        "content": f"STUB comment for paragraph {paragraph_number} (synthetic body_pid={body_pid}). " * 8,
        "memorable_line": f"stub line for ¶{paragraph_number}",
        "audience_state_at_open": f"stub open state for paragraph {paragraph_number}",
        "transformation_mechanism": "release",
        "audience_state_at_close": f"stub close state for paragraph {paragraph_number}",
        "herd_distinctive_moves": ["H1"] if paragraph_number in (1, 5) else [],
        "paragraph_number": paragraph_number,
        "body_pid": body_pid,
        "question_pid": body_pid,
    }


# 9 paragraphs across 3 types, max 3 each (Gate 11 cap=3)
_STUB_TYPE_BY_PARA = {
    1: "C", 2: "D", 3: "F",
    4: "C", 5: "D", 6: "F",
    7: "C", 8: "D", 9: "F",
}


def _stub_underline(body_pid: int, paragraph_number: int) -> dict:
    return {
        "underlines": [
            {"phrase": f"stub yellow phrase for ¶{paragraph_number}",
             "color": "yellow", "answers_question": True},
        ],
        "self_audit": {
            "yellow_count": 1, "all_yellows_complete_answers": True,
            "all_yellows_grammatical": True, "non_yellow_max_word_count": 0,
            "any_phrase_not_in_source": False,
        },
    }


def assert_eq(label: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"FAIL [{label}]: expected {expected!r}, got {actual!r}")
    print(f"  OK  [{label}] = {actual!r}")


def assert_true(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"FAIL [{label}]{(' — ' + detail) if detail else ''}")
    print(f"  OK  [{label}]")


def test_scrape_produces_unique_pids() -> list:
    """Lessons 84 + 85 both have original body_pids 3,4,5,6. After
    scrape_cbs_lesson + visible-number offset (as scrape_paragraphs does
    in production), synthetic body_pids must be unique AND visible
    paragraph numbers must be unique across the run."""
    print("\n=== TEST 1: scrape produces unique synthetic body_pids ===")
    h84 = fetch_wol_article(LESSON_84_DOC, "lfb")
    h85 = fetch_wol_article(LESSON_85_DOC, "lfb")
    p84 = scrape_cbs_lesson(h84, LESSON_84_DOC, lesson_number=84)
    p85 = scrape_cbs_lesson(h85, LESSON_85_DOC, lesson_number=85)
    assert_eq("lesson 84 paragraph count", len(p84), 4)
    assert_eq("lesson 85 paragraph count", len(p85), 5)
    # Apply the visible-number offset that lesson_agent.scrape_paragraphs
    # applies in production (so paragraph_number is unique across lessons)
    for p in p85:
        p.paragraph_number += len(p84)
    all_paras = p84 + p85
    visible_nums = [p.paragraph_number for p in all_paras]
    assert_eq("visible paragraph_numbers", visible_nums, [1, 2, 3, 4, 5, 6, 7, 8, 9])
    all_pids = [p.body_pid for p in all_paras]
    assert_true(
        "all body_pids unique across lessons",
        len(set(all_pids)) == len(all_pids),
        f"got pids: {all_pids}",
    )
    # Original body_pids should preserve the real source pids
    orig_84 = sorted(p.original_body_pid for p in p84)
    orig_85 = sorted(p.original_body_pid for p in p85)
    assert_eq("lesson 84 original pids", orig_84, [3, 4, 5, 6])
    assert_eq("lesson 85 original pids", orig_85, [3, 4, 5, 6, 7])
    # source_lesson_doc_id set correctly
    for p in p84:
        assert_eq(f"¶{p.paragraph_number} source_doc_id", p.source_lesson_doc_id, LESSON_84_DOC)
    for p in p85:
        assert_eq(f"¶{p.paragraph_number} source_doc_id (l85)", p.source_lesson_doc_id, LESSON_85_DOC)
    return all_paras


def test_commit_lesson_splits_by_lesson(all_paras: list) -> None:
    """commit_lesson handler should write ONE JSON per source lesson DocId,
    each with original body_pids and no cross-contamination."""
    print("\n=== TEST 2: commit_lesson splits CBS output by lesson ===")
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Set up LessonState with the 9 scraped paragraphs
        log_path = td_path / "gates.log"
        log_fh = log_path.open("w", encoding="utf-8")
        state = LessonState(
            study_date=STUDY_DATE, target="cbs", email_enabled=False,
            cost_tracker=CostTracker(), run_dir=td_path, log_fh=log_fh,
        )
        state.paragraphs = all_paras
        state.paragraph_by_num = {p.paragraph_number: p for p in all_paras}
        state.article_meta = {
            "document_id": LESSON_84_DOC,
            "key_symbol": "lfb",
            "issue": 0,
            "title": "Congregation Bible Study — lfb lessons 84-85",
            "source": "Congregation Bible Study (lfb lessons 84-85)",
            "url": f"https://wol.jw.org/en/wol/d/r1/lp-e/{LESSON_84_DOC}",
        }
        # Stub all 9 drafts using the synthetic body_pids (as the lesson
        # agent would after a successful run). Types varied so article-
        # level gates pass.
        for p in all_paras:
            ctype = _STUB_TYPE_BY_PARA.get(p.paragraph_number, "C")
            state.drafted_comments[p.body_pid] = _stub_comment(
                p.body_pid, p.paragraph_number, ctype
            )
            state.drafted_underlines[p.body_pid] = _stub_underline(
                p.body_pid, p.paragraph_number
            )

        # Patch the global _HERE in lesson_agent so the output dir lands
        # under the temp dir (commit_lesson writes to _HERE.parent/"comments")
        import lesson_agent as la  # type: ignore
        orig_here = la._HERE
        la._HERE = td_path / "agent"   # so _HERE.parent / "comments" = td_path/"comments"
        (la._HERE).mkdir(parents=True, exist_ok=True)
        try:
            handlers = _make_tool_handlers(state)
            result = handlers["commit_lesson"]()
        finally:
            la._HERE = orig_here
            log_fh.close()

        assert_true("commit_lesson returned ok=True", result.get("ok"),
                    f"result: {result}")
        written_paths = result.get("written_paths") or []
        assert_eq("written_paths count", len(written_paths), 2)
        # Map output filenames to lessons
        out_dir = td_path / "comments"
        files_by_doc = {}
        for path_str in written_paths:
            p = Path(path_str)
            assert_true(f"output file exists: {p.name}", p.exists())
            doc = json.loads(p.read_text(encoding="utf-8"))
            files_by_doc[doc["document_id"]] = (p, doc)
        assert_eq("doc IDs in output", sorted(files_by_doc.keys()),
                  [LESSON_84_DOC, LESSON_85_DOC])

        # Lesson 84 JSON: should have exactly 4 paragraphs' worth of notes
        # (comment + underline rows for ¶1-¶4), all anchored to lesson 84
        # body_pids 3-6 (the ORIGINAL pids, not synthetic).
        p84_path, p84_doc = files_by_doc[LESSON_84_DOC]
        assert_eq("lesson 84 document_id in JSON", p84_doc["document_id"], LESSON_84_DOC)
        assert_eq("lesson 84 key_symbol", p84_doc["key_symbol"], "lfb")
        comments_84 = [n for n in p84_doc["notes"] if n.get("content")]
        underlines_84 = [n for n in p84_doc["notes"] if n.get("underlines")]
        assert_eq("lesson 84 comment count", len(comments_84), 4)
        assert_eq("lesson 84 underline-row count", len(underlines_84), 4)
        # Verify original body_pids (3,4,5,6) — NOT synthetic
        comment_pids_84 = sorted(n["data_pid"] for n in comments_84)
        ul_pids_84 = sorted(n["data_pid"] for n in underlines_84)
        assert_eq("lesson 84 comment data_pids", comment_pids_84, [3, 4, 5, 6])
        assert_eq("lesson 84 underline data_pids", ul_pids_84, [3, 4, 5, 6])
        # Cross-contamination check: each comment's content should reference
        # the right paragraph_number (1-4 for lesson 84)
        para_nums_84 = sorted(n["paragraph"] for n in comments_84)
        assert_eq("lesson 84 paragraph_numbers", para_nums_84, [1, 2, 3, 4])

        # Lesson 85 JSON: 5 paragraphs, original pids 3,4,5,6,7
        p85_path, p85_doc = files_by_doc[LESSON_85_DOC]
        assert_eq("lesson 85 document_id in JSON", p85_doc["document_id"], LESSON_85_DOC)
        comments_85 = [n for n in p85_doc["notes"] if n.get("content")]
        underlines_85 = [n for n in p85_doc["notes"] if n.get("underlines")]
        assert_eq("lesson 85 comment count", len(comments_85), 5)
        assert_eq("lesson 85 underline-row count", len(underlines_85), 5)
        comment_pids_85 = sorted(n["data_pid"] for n in comments_85)
        ul_pids_85 = sorted(n["data_pid"] for n in underlines_85)
        assert_eq("lesson 85 comment data_pids", comment_pids_85, [3, 4, 5, 6, 7])
        assert_eq("lesson 85 underline data_pids", ul_pids_85, [3, 4, 5, 6, 7])
        para_nums_85 = sorted(n["paragraph"] for n in comments_85)
        assert_eq("lesson 85 paragraph_numbers", para_nums_85, [5, 6, 7, 8, 9])

        # Critical: no cross-contamination. Each comment's content should
        # reference its own paragraph_number (the stub format includes it).
        for n in comments_84:
            assert_true(
                f"lesson 84 ¶{n['paragraph']} content references its own number",
                f"paragraph {n['paragraph']} " in n["content"],
                f"content: {n['content'][:120]}",
            )
        for n in comments_85:
            assert_true(
                f"lesson 85 ¶{n['paragraph']} content references its own number",
                f"paragraph {n['paragraph']} " in n["content"],
                f"content: {n['content'][:120]}",
            )

        # Bonus: the synthetic body_pids should NOT appear anywhere in the
        # output JSON — only original pids should anchor notes.
        flat_84_pids = {n["data_pid"] for n in p84_doc["notes"]}
        flat_85_pids = {n["data_pid"] for n in p85_doc["notes"]}
        assert_true(
            "no synthetic pids leaked into lesson 84 JSON",
            all(pid < 100 for pid in flat_84_pids),
            f"pids: {flat_84_pids}",
        )
        assert_true(
            "no synthetic pids leaked into lesson 85 JSON",
            all(pid < 100 for pid in flat_85_pids),
            f"pids: {flat_85_pids}",
        )


def test_resume_cache_isolation(all_paras: list) -> None:
    """Synthetic body_pids in state.drafted_comments should NOT collide
    across lessons. Specifically: looking up lesson 84's original pid 3
    must NOT return lesson 85's original pid 3 (or vice versa).
    """
    print("\n=== TEST 3: resume-cache isolation between lessons ===")
    cache = {p.body_pid: p for p in all_paras}
    # For each lesson, look up the same original_body_pid; they MUST resolve
    # to different ParagraphData objects.
    lesson_84_para_pid3 = next(p for p in all_paras
                               if p.source_lesson_doc_id == LESSON_84_DOC
                               and p.original_body_pid == 3)
    lesson_85_para_pid3 = next(p for p in all_paras
                               if p.source_lesson_doc_id == LESSON_85_DOC
                               and p.original_body_pid == 3)
    assert_true("lesson 84 ¶ with orig_pid=3 is in cache",
                lesson_84_para_pid3.body_pid in cache)
    assert_true("lesson 85 ¶ with orig_pid=3 is in cache",
                lesson_85_para_pid3.body_pid in cache)
    assert_true(
        "lesson 84 ¶3 and lesson 85 ¶3 have DIFFERENT synthetic body_pids",
        lesson_84_para_pid3.body_pid != lesson_85_para_pid3.body_pid,
        f"L84 synthetic: {lesson_84_para_pid3.body_pid}, "
        f"L85 synthetic: {lesson_85_para_pid3.body_pid}",
    )
    # Cache lookup must return the right one
    assert_true("cache[L84 synthetic] returns L84 para",
                cache[lesson_84_para_pid3.body_pid] is lesson_84_para_pid3)
    assert_true("cache[L85 synthetic] returns L85 para",
                cache[lesson_85_para_pid3.body_pid] is lesson_85_para_pid3)


def main() -> int:
    try:
        all_paras = test_scrape_produces_unique_pids()
        test_commit_lesson_splits_by_lesson(all_paras)
        test_resume_cache_isolation(all_paras)
    except AssertionError as e:
        print(f"\n❌ FAILED: {e}")
        return 1
    print("\n✅ All CBS split-logic assertions pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
