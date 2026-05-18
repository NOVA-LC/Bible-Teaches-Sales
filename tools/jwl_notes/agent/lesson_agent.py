"""lesson_agent.py — whole-lesson orchestrator agent.

Replaces most of build_week.main(). Owns the full lesson: discovery →
scrape → per-paragraph drafting (via comment + underline subagents) →
article-level gate enforcement → assemble + write JSON → optional email.

Architecture: composition. The lesson agent never drafts content itself.
It orchestrates two subagents (comment_agent, underline_agent) per
paragraph and decides article-level redrafts when gates fail.

Cost: one shared CostTracker passed into every subagent call so the
$20/article kill switch sees real token spend (not estimates).

CLI:
    python -m agent.lesson_agent --study-date 2026-05-17 [--target wt|mwb] [--email]

Returns 0 on shipped lesson; 1 on commit_lesson_failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from gates import (  # type: ignore  # noqa: E402
    GateResult,
    run_article_gates as gates_run_article_gates,
)
from jwl_notes import fetch_wol_article  # type: ignore  # noqa: E402
from build_week import (  # type: ignore  # noqa: E402
    ParagraphData,
    scrape_article,
    assemble_comments_json,
    GATE11_HARD_CAP,
    _issue_month_year,
)
import re as _re


def scrape_cbs_lesson(html: str, doc_id: int, lesson_number: int | None = None) -> list[ParagraphData]:
    """Scrape a CBS lfb lesson into ParagraphData. lfb structure differs from
    WT:
      - 4 body paragraphs per lesson, class="sb"
      - 1 shared 'Questions:' block (class="sc")
      - Cited scriptures listed in a final class="sc" paragraph

    Each body paragraph gets the lesson-wide question block + the parsed
    cited scriptures. The comment anchor (data_pid) is the sb paragraph's
    own pid (CBS comments display inline at the paragraph).
    """
    # Pull all <p> with data-pid + class
    paragraphs: list[ParagraphData] = []
    sb_re = _re.compile(
        r'<p[^>]+id="p\d+"[^>]+data-pid="(\d+)"[^>]+class="sb"[^>]*>(.*?)</p>',
        _re.DOTALL,
    )
    sc_re = _re.compile(
        r'<p[^>]+id="p\d+"[^>]+data-pid="(\d+)"[^>]+class="sc"[^>]*>(.*?)</p>',
        _re.DOTALL,
    )
    # Find the lesson-wide "Questions" block + cited scriptures
    question_text = None
    cited_scriptures: list[str] = []
    for m in sc_re.finditer(html):
        body = m.group(2)
        text = _re.sub(r"<[^>]+>", " ", body)
        text = _re.sub(r"\s+", " ", text).strip()
        if text.lower().startswith("questions:"):
            question_text = text
        elif text and not text.startswith("“"):
            # Heuristic: cited scriptures are the sc paragraphs that aren't
            # memory-verse quotes (which start with curly quote) or Questions.
            # Pull explicit Bible refs from the text.
            for ref_m in _re.finditer(
                r"\b(\d?\s?[A-Z][a-z]+\.?\s+\d+:\d+(?:[-–]\d+)?(?:,\s*\d+(?:[-–]\d+)?)*)",
                text,
            ):
                cited_scriptures.append(ref_m.group(1).strip())

    # Body paragraphs — extract each sb paragraph's text and build ParagraphData.
    # CBS spans multiple lessons; each lesson has its own data-pid namespace
    # (lesson 84 and lesson 85 both have body_pids 3,4,5,6). To prevent
    # cache-key collisions in the lesson agent's state.drafted_comments
    # (which is keyed by body_pid), we use a SYNTHETIC body_pid that
    # encodes the source DocId. original_body_pid preserves the real pid
    # so the JW Library injector anchors to the correct paragraph.
    pid_offset = (doc_id % 100000) * 1000  # unique per lesson DocId
    for visible_num, m in enumerate(sb_re.finditer(html), start=1):
        original_pid = int(m.group(1))
        synthetic_pid = pid_offset + original_pid
        body_html = m.group(2)
        body_text = _re.sub(r"<[^>]+>", " ", body_html)
        body_text = _re.sub(r"\s+", " ", body_text).strip()
        # Strip leading paragraph number if present
        body_text = _re.sub(r"^\d+\s+", "", body_text)
        paragraphs.append(ParagraphData(
            paragraph_number=visible_num,
            body_pid=synthetic_pid,
            # CBS doesn't have per-paragraph question_pid. Use synthetic
            # body_pid as the question anchor too — comment renders at the
            # paragraph itself in JW Library (matches how CBS audience
            # comments work: response to lesson-wide questions about this
            # specific paragraph).
            question_pid=synthetic_pid,
            question_text=question_text or f"(CBS lesson {lesson_number or doc_id} — comment on this paragraph)",
            body_text=body_text,
            cited_scriptures=cited_scriptures,
            source_lesson_doc_id=doc_id,
            original_body_pid=original_pid,
        ))
    return paragraphs
from comment_agent import (  # type: ignore  # noqa: E402
    CostTracker,
    draft_comment_with_agent,
)
from underline_agent import draft_underlines_with_agent  # type: ignore  # noqa: E402
from workers import load_dotenv  # type: ignore  # noqa: E402


PROMPTS_DIR = _HERE / "prompts"
MAX_TURNS = 100
DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
ARTICLE_COST_KILL_USD = 20.0
ARTICLE_REDRAFT_CYCLE_CAP = 5


# ----------------------------------------------------------------------
# Checkpoint / resume — persist drafts so re-runs don't burn API on
# already-committed paragraphs. State layout:
#   <run_dir>/state/
#     meta.json                # article_meta, failed_*, redraft_cycles_used
#     comments/<body_pid>.json # one per drafted comment
#     underlines/<body_pid>.json
# ----------------------------------------------------------------------

def _state_dir(state) -> Path:
    return state.run_dir / "state"


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically: temp file + rename. Avoids partial writes
    if the process is killed mid-write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    tmp.replace(path)


def _save_meta(state) -> None:
    _atomic_write_json(_state_dir(state) / "meta.json", {
        "study_date": state.study_date,
        "target": state.target,
        "article_meta": state.article_meta,
        "failed_comments": sorted(state.failed_comments),
        "failed_underlines": sorted(state.failed_underlines),
        "redraft_cycles_used": state.redraft_cycles_used,
        "saved_at": datetime.utcnow().isoformat() + "Z",
    })


def _save_comment(state, body_pid: int, comment: dict) -> None:
    _atomic_write_json(_state_dir(state) / "comments" / f"{body_pid}.json", comment)
    _save_meta(state)


def _save_underline(state, body_pid: int, payload: dict) -> None:
    _atomic_write_json(_state_dir(state) / "underlines" / f"{body_pid}.json", payload)
    _save_meta(state)


def _delete_comment(state, body_pid: int) -> None:
    p = _state_dir(state) / "comments" / f"{body_pid}.json"
    if p.exists():
        p.unlink()


def _load_state(state) -> dict:
    """Populate state.drafted_comments / drafted_underlines / failed_* /
    article_meta / redraft_cycles_used from a previous run's saved state.
    Returns a summary dict for logging."""
    sd = _state_dir(state)
    summary = {"loaded": False, "comments": 0, "underlines": 0,
               "failed_comments": 0, "failed_underlines": 0,
               "redraft_cycles": 0}
    if not sd.exists():
        return summary
    meta_path = sd / "meta.json"
    if not meta_path.exists():
        # State dir exists but no meta — nothing trustworthy to load.
        return summary
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return summary
    # Only load if it's the same run (study_date + target match). In
    # production the run_dir path includes both, so a mismatch shouldn't
    # happen — but the check is cheap insurance against operator error
    # (e.g., manually pointing at the wrong dir).
    if (meta.get("study_date") != state.study_date
            or meta.get("target") != state.target):
        return summary
    state.article_meta = meta.get("article_meta") or state.article_meta
    state.failed_comments = list(meta.get("failed_comments", []))
    state.failed_underlines = list(meta.get("failed_underlines", []))
    state.redraft_cycles_used = meta.get("redraft_cycles_used", 0)
    cdir = sd / "comments"
    if cdir.exists():
        for f in cdir.glob("*.json"):
            try:
                bp = int(f.stem)
                state.drafted_comments[bp] = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
    udir = sd / "underlines"
    if udir.exists():
        for f in udir.glob("*.json"):
            try:
                bp = int(f.stem)
                state.drafted_underlines[bp] = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
    summary.update({
        "loaded": True,
        "comments": len(state.drafted_comments),
        "underlines": len(state.drafted_underlines),
        "failed_comments": len(state.failed_comments),
        "failed_underlines": len(state.failed_underlines),
        "redraft_cycles": state.redraft_cycles_used,
    })
    return summary

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
    return (PROMPTS_DIR / "lesson_agent.md").read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# Lesson state — the single source of truth that get_status reads
# ----------------------------------------------------------------------

class LessonState:
    """Mutable state the lesson agent accumulates. Closures over this in
    the tool handlers; get_status() reads from this verbatim."""

    def __init__(self, study_date: str, target: str, email_enabled: bool,
                 cost_tracker: CostTracker, run_dir: Path, log_fh,
                 paragraph_filter: list[int] | None = None):
        self.study_date = study_date
        self.target = target
        self.email_enabled = email_enabled
        self.cost_tracker = cost_tracker
        self.run_dir = run_dir
        self.log_fh = log_fh
        # Test/debug aid: when set, scrape_paragraphs filters to this subset
        # so the agent works on a slice. None = whole article.
        self.paragraph_filter = set(paragraph_filter) if paragraph_filter else None

        # Discovery + scrape outputs
        self.article_meta: dict | None = None
        self.paragraphs: list[ParagraphData] = []
        self.paragraph_by_num: dict[int, ParagraphData] = {}

        # Drafts so far
        self.drafted_comments: dict[int, dict] = {}     # body_pid -> comment
        self.drafted_underlines: dict[int, dict] = {}   # body_pid -> ul payload
        self.failed_comments: list[int] = []            # paragraph numbers
        self.failed_underlines: list[int] = []
        self.redraft_cycles_used: int = 0

        # Termination state
        self.committed_path: str | None = None
        self.failed_reason: str | None = None

    def log(self, msg: str) -> None:
        try:
            self.log_fh.write(msg + "\n")
            self.log_fh.flush()
        except Exception:
            pass
        print(msg, flush=True)


# ----------------------------------------------------------------------
# Tool implementations
# ----------------------------------------------------------------------

def _make_tool_handlers(state: LessonState):
    """Return (handlers_dict, terminator_flag). All handlers close over
    the lesson state, which is the single source of truth."""

    def _compute_forbidden_types() -> list[str]:
        from collections import Counter
        counts = Counter(
            (c.get("comment_type", "A") or "A").upper().strip()
            for c in state.drafted_comments.values()
        )
        return sorted(t for t, n in counts.items() if n >= GATE11_HARD_CAP)

    def _compute_prior_state(skip_body_pid: int | None = None) -> dict:
        """Build prior_state for the comment agent. Optionally skip one
        paragraph (used by redraft so the paragraph being redrafted
        doesn't count against itself)."""
        from collections import Counter
        comments = [
            c for bp, c in state.drafted_comments.items() if bp != skip_body_pid
        ]
        prior_types = [
            (c.get("comment_type", "A") or "A").upper().strip()
            for c in comments
        ]
        counts = Counter(prior_types)
        forbidden = sorted(t for t, n in counts.items() if n >= GATE11_HARD_CAP)
        mechs, rels, herd = [], [], []
        for c in comments:
            mechs.extend(b.get("mechanic") for b in c.get("tagged_beats", []) if b.get("mechanic"))
            ds = c.get("domestic_scene") or {}
            if ds.get("present") and ds.get("named_relationship"):
                rels.append(ds["named_relationship"])
            herd.extend(c.get("herd_distinctive_moves") or [])
        return {
            "prior_types_used_this_article": prior_types,
            "prior_mechanics_this_week": sorted(set(mechs)),
            "prior_named_relationships_this_week": sorted(set(rels)),
            "prior_herd_moves_this_week": sorted(set(herd)),
            "forbidden_types": forbidden,
        }

    def discover_lesson(study_date: str | None = None,
                        target: str | None = None) -> dict:
        from discover_week import discover  # local import to avoid hard dep
        sd = study_date or state.study_date
        tgt = target or state.target
        try:
            wd = discover(study_date=sd)
        except Exception as e:
            return {"ok": False, "reason": f"discover failed: {e}"}
        warnings = list(wd.warnings)
        if tgt == "wt":
            if wd.wt_document_id is None:
                return {"ok": False, "reason": "no WT DocumentId discovered",
                        "warnings": warnings}
            meta = {
                "document_id": wd.wt_document_id,
                "key_symbol": "w",
                "issue": wd.wt_issue or 0,
                "title": wd.wt_title,
                "source": f"The Watchtower (Study), {_issue_month_year(wd.wt_issue) if wd.wt_issue else 'unknown issue'}",
                "url": wd.wt_url,
                "theme_scripture": wd.wt_theme_scripture,
                "week_label": wd.week_label,
            }
        elif tgt == "cbs":
            # Congregation Bible Study — needs lfb (or current CBS publication)
            # lesson DocIds discovered from the workbook.
            if not wd.cbs_document_ids:
                return {"ok": False,
                        "reason": "no CBS lesson DocIds discovered from workbook",
                        "warnings": warnings}
            meta = {
                # Use the FIRST lesson's DocId as the canonical anchor; scrape
                # will fetch both lessons under cbs_document_ids.
                "document_id": wd.cbs_document_ids[0],
                "key_symbol": wd.cbs_publication or "lfb",
                "issue": 0,
                "title": f"Congregation Bible Study — {wd.cbs_lesson_label or 'this week'}",
                "source": f"Congregation Bible Study ({wd.cbs_publication or 'lfb'} {wd.cbs_lesson_label or ''})".strip(),
                "url": f"https://wol.jw.org/en/wol/d/r1/lp-e/{wd.cbs_document_ids[0]}",
                "theme_scripture": None,
                "week_label": wd.week_label,
                "cbs_document_ids": wd.cbs_document_ids,  # all lessons for scrape
                "cbs_lesson_label": wd.cbs_lesson_label,
            }
        elif tgt == "gems":
            # Spiritual Gems — Bible reading range. The lesson agent doesn't
            # draft paragraph comments here; it dispatches to gems_run for
            # verse drafting. We still return meta so the agent can decide.
            if not wd.bible_reading_book:
                return {"ok": False,
                        "reason": "no Bible reading discovered for Spiritual Gems",
                        "warnings": warnings}
            chap_label = (
                f"{wd.bible_reading_book_name} {wd.bible_reading_chapter_start}"
                f"-{wd.bible_reading_chapter_end}"
                if wd.bible_reading_chapter_end != wd.bible_reading_chapter_start
                else f"{wd.bible_reading_book_name} {wd.bible_reading_chapter_start}"
            )
            meta = {
                "document_id": 0,  # gems writes per-chapter Bible-mode JSON
                "key_symbol": "nwtsty",
                "issue": 0,
                "title": f"Spiritual Gems — {chap_label}",
                "source": f"Spiritual Gems — Bible reading {chap_label}",
                "url": None,
                "theme_scripture": None,
                "week_label": wd.week_label,
                "bible_reading_book": wd.bible_reading_book,
                "bible_reading_book_name": wd.bible_reading_book_name,
                "bible_reading_chapter_start": wd.bible_reading_chapter_start,
                "bible_reading_chapter_end": wd.bible_reading_chapter_end,
            }
        else:  # mwb (legacy / not currently supported via lesson_agent)
            if wd.mwb_document_id is None:
                return {"ok": False, "reason": "no mwb DocumentId discovered",
                        "warnings": warnings}
            meta = {
                "document_id": wd.mwb_document_id,
                "key_symbol": "mwb",
                "issue": wd.mwb_issue or 0,
                "title": f"Midweek Meeting — {wd.week_label}",
                "source": f"Our Christian Life and Ministry — Meeting Workbook ({_issue_month_year(wd.mwb_issue) if wd.mwb_issue else 'unknown issue'})",
                "url": wd.mwb_url,
                "theme_scripture": None,
                "week_label": wd.week_label,
            }
        state.article_meta = meta
        return {"ok": True, **meta, "warnings": warnings}

    def scrape_paragraphs(document_id: int | None = None,
                          key_symbol: str | None = None) -> dict:
        if state.article_meta is None and document_id is None:
            return {"ok": False, "reason": "no article_meta — call discover_lesson first"}
        did = document_id or state.article_meta["document_id"]
        ks = key_symbol or state.article_meta.get("key_symbol", "w")
        try:
            # CBS target: fetch each lesson DocId separately, concatenate
            # ParagraphData lists (re-numbering visible paragraph numbers
            # across lessons so the lesson agent sees them as 1..N).
            if state.target == "cbs":
                lesson_ids = (state.article_meta or {}).get("cbs_document_ids") or [did]
                all_paragraphs: list[ParagraphData] = []
                visible_offset = 0
                for lesson_idx, lesson_did in enumerate(lesson_ids, start=1):
                    lesson_html = fetch_wol_article(lesson_did, ks)
                    lp = scrape_cbs_lesson(lesson_html, lesson_did, lesson_idx)
                    for p in lp:
                        p.paragraph_number += visible_offset
                    all_paragraphs.extend(lp)
                    visible_offset += len(lp)
                paragraphs = all_paragraphs
            else:
                html = fetch_wol_article(did, ks)
                paragraphs = scrape_article(html)
        except Exception as e:
            return {"ok": False, "reason": f"scrape failed: {e}"}
        # Apply the test/debug paragraph filter if set on the LessonState
        # (used by --paragraphs CLI flag for cheap slice smoke tests).
        if state.paragraph_filter is not None:
            paragraphs = [p for p in paragraphs if p.paragraph_number in state.paragraph_filter]
        state.paragraphs = paragraphs
        state.paragraph_by_num = {p.paragraph_number: p for p in paragraphs}
        return {
            "ok": True,
            "paragraph_count": len(paragraphs),
            "paragraphs": [
                {
                    "paragraph_number": p.paragraph_number,
                    "body_pid": p.body_pid,
                    "question_pid": p.question_pid,
                    "has_question": p.question_pid is not None,
                    "question_text": (p.question_text or "")[:200],
                    "body_text_preview": (p.body_text or "")[:160],
                    "cited_scriptures": p.cited_scriptures,
                }
                for p in paragraphs
            ],
        }

    def draft_comment(paragraph_number: int,
                      extra_constraints: dict | None = None) -> dict:
        if paragraph_number not in state.paragraph_by_num:
            return {"ok": False, "reason": f"unknown paragraph_number {paragraph_number}"}
        para = state.paragraph_by_num[paragraph_number]
        if para.question_pid is None:
            return {"ok": False, "reason": f"¶{paragraph_number} has no question_pid; no comment needed"}
        # Resume-cache hit: return without calling the subagent.
        if para.body_pid in state.drafted_comments:
            cached = state.drafted_comments[para.body_pid]
            return {
                "ok": True, "accepted": True, "from_cache": True,
                "comment_type": cached.get("comment_type"),
                "memorable_line": cached.get("memorable_line"),
                "word_count": len((cached.get("content") or "").split()),
            }
        prior_state = _compute_prior_state()
        article_meta_full = {
            "article_title": state.article_meta.get("title"),
            "article_source": state.article_meta.get("source"),
            "study_date": state.study_date,
        }
        try:
            comment, history = draft_comment_with_agent(
                para, article_meta_full, prior_state,
                extra_constraints=extra_constraints,
                cost_tracker=state.cost_tracker,
            )
        except SystemExit as e:
            # Fatal billing/auth — propagate up
            raise
        state.log(f"\n  draft_comment ¶{paragraph_number}:")
        for g in history:
            state.log(f"    {g}")
        if comment is None:
            if paragraph_number not in state.failed_comments:
                state.failed_comments.append(paragraph_number)
            return {"ok": False, "accepted": False,
                    "reason": "comment agent gave up; see gates.log",
                    "gate_history_tail": [str(g) for g in history[-5:]]}
        state.drafted_comments[para.body_pid] = comment
        # Persist immediately so a kill/crash doesn't lose this draft.
        try:
            _save_comment(state, para.body_pid, comment)
        except Exception as save_err:
            state.log(f"    ⚠ checkpoint save failed (non-fatal): {save_err}")
        # If this paragraph had previously failed, clear the entry
        if paragraph_number in state.failed_comments:
            state.failed_comments.remove(paragraph_number)
        return {
            "ok": True,
            "accepted": True,
            "comment_type": comment.get("comment_type"),
            "memorable_line": comment.get("memorable_line"),
            "word_count": len((comment.get("content") or "").split()),
        }

    def draft_underlines(paragraph_number: int) -> dict:
        if paragraph_number not in state.paragraph_by_num:
            return {"ok": False, "reason": f"unknown paragraph_number {paragraph_number}"}
        para = state.paragraph_by_num[paragraph_number]
        # Resume-cache hit: return without calling the subagent.
        if para.body_pid in state.drafted_underlines:
            cached = state.drafted_underlines[para.body_pid]
            return {
                "ok": True, "accepted": True, "from_cache": True,
                "deferred_to_scripture": bool(cached.get("deferred_to_scripture")),
                "underline_count": len(cached.get("underlines", [])),
            }
        try:
            payload, history = draft_underlines_with_agent(
                para, cost_tracker=state.cost_tracker,
            )
        except SystemExit:
            raise
        state.log(f"\n  draft_underlines ¶{paragraph_number}:")
        for g in history:
            state.log(f"    {g}")
        if payload is None:
            if paragraph_number not in state.failed_underlines:
                state.failed_underlines.append(paragraph_number)
            return {"ok": False, "accepted": False,
                    "reason": "underline agent gave up; see gates.log"}
        state.drafted_underlines[para.body_pid] = payload
        try:
            _save_underline(state, para.body_pid, payload)
        except Exception as save_err:
            state.log(f"    ⚠ checkpoint save failed (non-fatal): {save_err}")
        if paragraph_number in state.failed_underlines:
            state.failed_underlines.remove(paragraph_number)
        return {
            "ok": True,
            "accepted": True,
            "deferred_to_scripture": bool(payload.get("deferred_to_scripture")),
            "underline_count": len(payload.get("underlines", [])),
        }

    def get_status() -> dict:
        from collections import Counter
        type_dist = Counter(
            (c.get("comment_type", "A") or "A").upper().strip()
            for c in state.drafted_comments.values()
        )
        # Pending = paragraphs with question_pid that have neither been drafted
        # nor marked failed
        drafted_nums = {
            p.paragraph_number for p in state.paragraphs
            if p.body_pid in state.drafted_comments
        }
        pending_comments = [
            p.paragraph_number for p in state.paragraphs
            if p.question_pid is not None
            and p.paragraph_number not in drafted_nums
            and p.paragraph_number not in state.failed_comments
        ]
        pending_underlines = [
            p.paragraph_number for p in state.paragraphs
            if p.body_pid not in state.drafted_underlines
            and p.paragraph_number not in state.failed_underlines
        ]
        spend = state.cost_tracker.estimated_cost_usd()
        return {
            "drafted_comments": sorted(
                p.paragraph_number for p in state.paragraphs
                if p.body_pid in state.drafted_comments
            ),
            "drafted_underlines": sorted(
                p.paragraph_number for p in state.paragraphs
                if p.body_pid in state.drafted_underlines
            ),
            "failed_comments": sorted(state.failed_comments),
            "failed_underlines": sorted(state.failed_underlines),
            "pending_comments": sorted(pending_comments),
            "pending_underlines": sorted(pending_underlines),
            "prior_types_used": [
                (c.get("comment_type", "A") or "A").upper().strip()
                for c in state.drafted_comments.values()
            ],
            "type_distribution": dict(type_dist),
            "forbidden_types": _compute_forbidden_types(),
            "redraft_cycles_used": state.redraft_cycles_used,
            "estimated_cost_usd": round(spend, 3),
            "cost_kill_remaining_usd": round(ARTICLE_COST_KILL_USD - spend, 3),
            "tracker_summary": state.cost_tracker.summary(),
        }

    def run_article_gates() -> dict:
        comments = list(state.drafted_comments.values())
        results = gates_run_article_gates(comments)
        return {
            "all_passed": all(g.passed for g in results),
            "results": [
                {"gate": g.gate, "passed": g.passed, "reason": g.reason}
                for g in results
            ],
        }

    def redraft_comment(paragraph_number: int,
                        extra_constraints: dict | None = None,
                        reason: str = "(no reason given)") -> dict:
        if state.redraft_cycles_used >= ARTICLE_REDRAFT_CYCLE_CAP:
            return {"ok": False, "accepted": False,
                    "reason": f"redraft cycle cap ({ARTICLE_REDRAFT_CYCLE_CAP}) reached"}
        state.redraft_cycles_used += 1
        state.log(
            f"\n  redraft_comment ¶{paragraph_number} (cycle "
            f"{state.redraft_cycles_used}/{ARTICLE_REDRAFT_CYCLE_CAP}): "
            f"{reason}"
        )
        if paragraph_number not in state.paragraph_by_num:
            return {"ok": False, "reason": f"unknown paragraph_number {paragraph_number}"}
        para = state.paragraph_by_num[paragraph_number]
        # Remove the existing comment so forbidden_types is recomputed without
        # this paragraph's own type counting against it. Also delete from disk
        # so a checkpoint-resume doesn't restore the rejected draft.
        state.drafted_comments.pop(para.body_pid, None)
        try:
            _delete_comment(state, para.body_pid)
        except Exception:
            pass
        prior_state = _compute_prior_state()
        article_meta_full = {
            "article_title": state.article_meta.get("title"),
            "article_source": state.article_meta.get("source"),
            "study_date": state.study_date,
        }
        try:
            comment, history = draft_comment_with_agent(
                para, article_meta_full, prior_state,
                extra_constraints=extra_constraints,
                cost_tracker=state.cost_tracker,
            )
        except SystemExit:
            raise
        for g in history:
            state.log(f"    {g}")
        if comment is None:
            if paragraph_number not in state.failed_comments:
                state.failed_comments.append(paragraph_number)
            return {"ok": False, "accepted": False,
                    "reason": "comment agent gave up on redraft"}
        state.drafted_comments[para.body_pid] = comment
        try:
            _save_comment(state, para.body_pid, comment)
        except Exception as save_err:
            state.log(f"    ⚠ checkpoint save failed (non-fatal): {save_err}")
        if paragraph_number in state.failed_comments:
            state.failed_comments.remove(paragraph_number)
        return {
            "ok": True,
            "accepted": True,
            "redraft_cycle": state.redraft_cycles_used,
            "comment_type": comment.get("comment_type"),
        }

    def commit_lesson() -> dict:
        # Pre-conditions
        comments = list(state.drafted_comments.values())
        article_results = gates_run_article_gates(comments)
        if not all(g.passed for g in article_results):
            failing = [g.reason for g in article_results if not g.passed]
            return {"ok": False, "reason": "article-level gates failing",
                    "gate_failures": failing}
        # All paragraphs with questions must be drafted-or-failed
        unresolved = [
            p.paragraph_number for p in state.paragraphs
            if p.question_pid is not None
            and p.body_pid not in state.drafted_comments
            and p.paragraph_number not in state.failed_comments
        ]
        if unresolved:
            return {"ok": False, "reason": f"unresolved paragraphs: {unresolved}"}

        # CBS spans multiple source-lesson DocIds — each lesson must ship
        # its own JSON anchored to its own DocId. Detect by presence of
        # source_lesson_doc_id on any paragraph; split accordingly.
        cbs_groups: dict[int, list] = {}
        single_paragraphs = []
        for para in state.paragraphs:
            if para.source_lesson_doc_id is not None:
                cbs_groups.setdefault(para.source_lesson_doc_id, []).append(para)
            else:
                single_paragraphs.append(para)

        out_dir = _HERE.parent / "comments"
        out_dir.mkdir(parents=True, exist_ok=True)
        written_paths = []
        total_note_count = 0
        total_underline_count = 0

        if cbs_groups:
            # Multi-lesson CBS — one JSON per lesson, anchored to that lesson's DocId
            for lesson_doc_id, lesson_paras in cbs_groups.items():
                # Build per-lesson drafted dicts keyed by original_body_pid
                # so assemble_comments_json writes the right anchor.
                lesson_comments: dict[int, dict] = {}
                lesson_underlines: dict[int, dict] = {}
                rekeyed_paras = []
                for p in lesson_paras:
                    rkey = p.original_body_pid
                    # Rebuild a ParagraphData with body_pid + question_pid
                    # set to the ORIGINAL pid (what the injector expects).
                    rekeyed_paras.append(ParagraphData(
                        paragraph_number=p.paragraph_number,
                        body_pid=p.original_body_pid,
                        question_pid=p.original_body_pid,
                        question_text=p.question_text,
                        body_text=p.body_text,
                        cited_scriptures=p.cited_scriptures,
                        source_lesson_doc_id=p.source_lesson_doc_id,
                        original_body_pid=p.original_body_pid,
                    ))
                    if p.body_pid in state.drafted_comments:
                        c = dict(state.drafted_comments[p.body_pid])
                        # Update embedded body_pid/question_pid to original
                        c["body_pid"] = p.original_body_pid
                        c["question_pid"] = p.original_body_pid
                        lesson_comments[p.original_body_pid] = c
                    if p.body_pid in state.drafted_underlines:
                        lesson_underlines[p.original_body_pid] = state.drafted_underlines[p.body_pid]
                lesson_meta = {
                    "article_title": state.article_meta.get("title"),
                    "article_source": state.article_meta.get("source"),
                    "study_date": state.study_date,
                    "key_symbol": state.article_meta.get("key_symbol", "lfb"),
                    "issue": 0,
                    "document_id": lesson_doc_id,
                    "url": f"https://wol.jw.org/en/wol/d/r1/lp-e/{lesson_doc_id}",
                }
                out_doc = assemble_comments_json(
                    lesson_meta, rekeyed_paras, lesson_comments, lesson_underlines,
                )
                ks = state.article_meta.get("key_symbol", "lfb")
                out_path = out_dir / f"{state.study_date}-{ks}-{lesson_doc_id}.json"
                out_path.write_text(
                    json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                written_paths.append(str(out_path))
                total_note_count += sum(1 for n in out_doc.get("notes", []) if n.get("content"))
                total_underline_count += sum(
                    len(n.get("underlines", []) or []) for n in out_doc.get("notes", [])
                )
            state.committed_path = ", ".join(written_paths)
            return {
                "ok": True,
                "written_paths": written_paths,
                "note_count": total_note_count,
                "underline_count": total_underline_count,
                "comments_skipped": sorted(state.failed_comments),
                "underlines_skipped": sorted(state.failed_underlines),
            }

        # Standard single-source path (WT)
        out_doc = assemble_comments_json(
            article_meta={
                "article_title": state.article_meta.get("title"),
                "article_source": state.article_meta.get("source"),
                "study_date": state.study_date,
                "key_symbol": state.article_meta.get("key_symbol"),
                "issue": state.article_meta.get("issue"),
                "document_id": state.article_meta.get("document_id"),
                "url": state.article_meta.get("url"),
            },
            paragraphs=state.paragraphs,
            drafted_comments=state.drafted_comments,
            drafted_underlines=state.drafted_underlines,
        )
        out_path = out_dir / f"{state.study_date}-{state.article_meta.get('key_symbol', 'w')}.json"
        out_path.write_text(
            json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        state.committed_path = str(out_path)
        note_count = sum(1 for n in out_doc.get("notes", []) if n.get("content"))
        underline_count = sum(
            len(n.get("underlines", []) or []) for n in out_doc.get("notes", [])
        )
        return {
            "ok": True,
            "written_path": str(out_path),
            "note_count": note_count,
            "underline_count": underline_count,
            "comments_skipped": sorted(state.failed_comments),
            "underlines_skipped": sorted(state.failed_underlines),
        }

    def email_results(json_path: str | None = None) -> dict:
        if not state.email_enabled:
            return {"sent": False, "reason": "email_enabled=False"}
        if not os.environ.get("RESEND_API_KEY"):
            return {"sent": False, "reason": "RESEND_API_KEY not set (not configured)"}
        path = json_path or state.committed_path
        if not path:
            return {"sent": False, "reason": "no committed JSON path (call commit_lesson first)"}
        # Spawn email_run.py the same way the GH Actions workflow does
        import subprocess
        try:
            proc = subprocess.run(
                [sys.executable, str(_HERE / "email_run.py"),
                 "--study-date", state.study_date,
                 "--comments-glob", path],
                capture_output=True, timeout=120,
            )
            return {
                "sent": proc.returncode == 0,
                "stdout": proc.stdout.decode("utf-8", errors="replace")[-500:],
                "stderr": proc.stderr.decode("utf-8", errors="replace")[-500:] if proc.returncode != 0 else "",
            }
        except Exception as e:
            return {"sent": False, "reason": f"email subprocess failed: {e}"}

    def commit_lesson_failure(reason: str) -> dict:
        state.failed_reason = reason
        state.log(f"\n❌ LESSON FAILURE: {reason}")
        return {"committed_failure": True, "reason": reason}

    handlers = {
        "discover_lesson": discover_lesson,
        "scrape_paragraphs": scrape_paragraphs,
        "draft_comment": draft_comment,
        "draft_underlines": draft_underlines,
        "get_status": get_status,
        "run_article_gates": run_article_gates,
        "redraft_comment": redraft_comment,
        "commit_lesson": commit_lesson,
        "email_results": email_results,
        "commit_lesson_failure": commit_lesson_failure,
    }
    return handlers


# ----------------------------------------------------------------------
# Tool schemas
# ----------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "name": "discover_lesson",
        "description": (
            "Discover the lesson(s) for the study week. Returns "
            "document_id, key_symbol, issue, title, source, url, warnings, "
            "plus target-specific extras. Call FIRST. On failure, call "
            "commit_lesson_failure. Targets:\n"
            "  wt — Sunday Watchtower study article\n"
            "  cbs — Congregation Bible Study (lfb lessons referenced by "
            "the workbook; returns cbs_document_ids list)\n"
            "  gems — Spiritual Gems (Bible reading range; the lesson "
            "agent dispatches gems_run for verse drafting)\n"
            "  mwb — legacy midweek workbook scrape (not currently supported)"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "study_date": {"type": "string", "description": "ISO date inside the study week. Defaults to the date the lesson agent was invoked with."},
                "target": {"type": "string", "enum": ["wt", "mwb", "cbs", "gems"], "description": "Which publication. Defaults to the target the lesson agent was invoked with."},
            },
        },
    },
    {
        "name": "scrape_paragraphs",
        "description": "Fetch and parse the article HTML. Returns the ordered "
                       "paragraph list (paragraph_number, body_pid, question_pid, "
                       "question_text, body_text_preview, cited_scriptures). "
                       "Call AFTER discover_lesson.",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer", "description": "Optional override; defaults to discovery result."},
                "key_symbol": {"type": "string", "description": "Optional override; defaults to 'w' or 'mwb'."},
            },
        },
    },
    {
        "name": "draft_comment",
        "description": "Invoke the comment agent for one paragraph. Returns "
                       "{ok, accepted, comment_type, memorable_line, word_count}. "
                       "extra_constraints (optional): force_domestic_scene (bool), "
                       "force_herd_move ('H1'..'H5'), force_invert_mode (bool), "
                       "experience_seed (string, only when picking Type B). "
                       "forbidden_types is computed automatically from prior types.",
        "input_schema": {
            "type": "object",
            "properties": {
                "paragraph_number": {"type": "integer"},
                "extra_constraints": {"type": "object"},
            },
            "required": ["paragraph_number"],
        },
    },
    {
        "name": "draft_underlines",
        "description": "Invoke the underline agent for one paragraph. Returns "
                       "{ok, accepted, deferred_to_scripture, underline_count}. "
                       "Regex pre-check fires first for 'Read X:Y-Z' bodies — "
                       "returns deferred at zero cost.",
        "input_schema": {
            "type": "object",
            "properties": {
                "paragraph_number": {"type": "integer"},
            },
            "required": ["paragraph_number"],
        },
    },
    {
        "name": "get_status",
        "description": "Return the lesson agent's internal state: drafted_comments, "
                       "drafted_underlines, failed_*, pending_*, type_distribution, "
                       "forbidden_types, redraft_cycles_used, estimated_cost_usd, "
                       "cost_kill_remaining_usd. Cheap; call liberally to prevent "
                       "context drift over 100 turns.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_article_gates",
        "description": "Run gates 2/4/5/11 (mechanic variety, domestic-scene quota, "
                       "Herd-move quota, type variety) on the comments drafted so far. "
                       "Returns {all_passed, results}. Call after all paragraphs are "
                       "drafted; re-call after each redraft cycle.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "redraft_comment",
        "description": "Re-invoke the comment agent on a specific paragraph with "
                       "constraints to fix a failing article-level gate. Counts "
                       "against the 5-cycle redraft budget. 'reason' is logged for "
                       "audit. The existing comment for this paragraph is dropped "
                       "before the redraft so forbidden_types is recomputed without "
                       "self-counting.",
        "input_schema": {
            "type": "object",
            "properties": {
                "paragraph_number": {"type": "integer"},
                "extra_constraints": {"type": "object"},
                "reason": {"type": "string"},
            },
            "required": ["paragraph_number", "reason"],
        },
    },
    {
        "name": "commit_lesson",
        "description": "Assemble drafted comments + underlines into the wire JSON "
                       "and write it. Pre-conditions: article-level gates all pass, "
                       "no unresolved paragraphs. Returns "
                       "{ok, written_path, note_count, underline_count, "
                       "comments_skipped, underlines_skipped}.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "email_results",
        "description": "Send the committed JSON via Resend (if configured). "
                       "Returns {sent, ...}. RESEND_API_KEY unset is not an error "
                       "— returns sent=False with a reason.",
        "input_schema": {
            "type": "object",
            "properties": {
                "json_path": {"type": "string", "description": "Defaults to the committed path."},
            },
        },
    },
    {
        "name": "commit_lesson_failure",
        "description": "Terminator for irrecoverable runs. Records the reason in "
                       "gates.log and stops the loop. Use for discovery failure, "
                       ">3 failed comments past redraft budget, cost ceiling, or "
                       "article gates that can't be made to pass within 5 redrafts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
            },
            "required": ["reason"],
        },
        "cache_control": {"type": "ephemeral"},
    },
]


# ----------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------

def run_lesson(study_date: str, target: str = "wt",
               email_enabled: bool = False,
               model: str = DEFAULT_MODEL,
               paragraph_filter: list[int] | None = None,
               fresh: bool = False) -> int:
    """Run the lesson agent end-to-end. Returns process exit code."""
    load_dotenv()

    # Gems target is structurally different (verse anchors, not paragraph
    # anchors; uses verse_comment.md prompt; writes one JSON per chapter).
    # Dispatch to gems_run.run_gems and return its exit code directly.
    if target == "gems":
        from gems_run import run_gems  # type: ignore
        return run_gems(study_date=study_date, model=model)

    try:
        from anthropic import Anthropic
    except ImportError:
        print("ERROR: anthropic SDK not installed (pip install anthropic)",
              file=sys.stderr)
        return 2

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    # Set up run directory + log
    run_dir = _HERE / "runs" / f"{study_date}-{target}-lesson"
    run_dir.mkdir(parents=True, exist_ok=True)
    # Optional fresh-start: wipe persisted state so the run starts from
    # scratch (default is to auto-resume any saved drafts).
    if fresh:
        import shutil
        shutil.rmtree(run_dir / "state", ignore_errors=True)
    log_path = run_dir / "gates.log"
    # Append mode preserves prior gates.log across resumes.
    log_fh = log_path.open("a", encoding="utf-8")

    cost_tracker = CostTracker()
    state = LessonState(
        study_date=study_date,
        target=target,
        email_enabled=email_enabled,
        cost_tracker=cost_tracker,
        run_dir=run_dir,
        log_fh=log_fh,
        paragraph_filter=paragraph_filter,
    )

    # Auto-resume: load any saved state from a previous run.
    resume_summary = _load_state(state)
    if resume_summary["loaded"] and (resume_summary["comments"] or resume_summary["underlines"]):
        state.log(
            f"=== RESUMED from saved state: "
            f"{resume_summary['comments']} comments, "
            f"{resume_summary['underlines']} underlines, "
            f"{resume_summary['failed_comments']} failed comments, "
            f"{resume_summary['failed_underlines']} failed underlines, "
            f"{resume_summary['redraft_cycles']} redraft cycles used ==="
        )

    handlers = _make_tool_handlers(state)
    client = Anthropic()
    system_prompt = _load_system_prompt()

    user_payload = {
        "study_date": study_date,
        "target": target,
        "key_symbol_default": "w" if target == "wt" else "mwb",
        "email_enabled": email_enabled,
    }

    messages: list[dict] = [{
        "role": "user",
        "content": json.dumps(user_payload, indent=2, ensure_ascii=False),
    }]

    state.log(f"=== Lesson agent start: study_date={study_date} target={target} ===")

    for turn in range(1, MAX_TURNS + 1):
        # Cost kill switch
        spend = cost_tracker.estimated_cost_usd()
        if spend >= ARTICLE_COST_KILL_USD:
            state.log(f"\n❌ COST KILL: spend ${spend:.2f} >= ${ARTICLE_COST_KILL_USD:.2f}")
            state.failed_reason = f"cost ceiling: ${spend:.2f}"
            break

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
            state.log(f"\n  Lesson agent turn {turn} SDK error: {e}")
            if _is_fatal(e):
                state.failed_reason = f"FATAL: {str(e)[:200]}"
                log_fh.close()
                raise SystemExit(
                    f"\n❌ FATAL: {str(e)[:200]}\n"
                    f"   Fix at https://console.anthropic.com/ then rerun."
                )
            state.failed_reason = f"SDK error: {e}"
            break

        cost_tracker.add_usage(getattr(resp, "usage", None))
        cost_tracker.turn_count = turn

        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]

        if not tool_uses:
            text_blocks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
            state.log(
                f"\n  Lesson agent turn {turn}: stopped without tool call "
                f"(stop_reason={resp.stop_reason}): {(' '.join(text_blocks))[:300]}"
            )
            state.failed_reason = "agent stopped without committing"
            break

        messages.append({"role": "assistant", "content": resp.content})

        tool_results_blocks = []
        terminated = False
        for tu in tool_uses:
            name = tu.name
            args = tu.input or {}
            handler = handlers.get(name)
            if handler is None:
                result = {"error": f"unknown tool: {name}"}
            else:
                try:
                    result = handler(**args)
                except TypeError as e:
                    result = {
                        "error": f"bad input to {name}: {e}",
                        "received_keys": sorted(list(args.keys())) if isinstance(args, dict) else None,
                    }
                except SystemExit:
                    raise
                except Exception as e:
                    if _is_fatal(e):
                        state.failed_reason = f"FATAL: {str(e)[:200]}"
                        log_fh.close()
                        raise SystemExit(
                            f"\n❌ FATAL: {str(e)[:200]}\n"
                            f"   Fix at https://console.anthropic.com/ then rerun."
                        )
                    result = {"error": f"{name} raised: {e}"}
            tool_results_blocks.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })
            # Terminators
            if name == "commit_lesson" and result.get("ok"):
                terminated = True
            if name == "commit_lesson_failure":
                terminated = True

        messages.append({"role": "user", "content": tool_results_blocks})

        if terminated:
            break

    final_spend = cost_tracker.estimated_cost_usd()
    state.log(f"\n=== Lesson agent end. Cost: {cost_tracker.summary()} ===")
    log_fh.close()

    if state.committed_path:
        print(f"\n✅ Lesson shipped → {state.committed_path}", flush=True)
        print(f"   Cost: ~${final_spend:.2f}", flush=True)
        print(f"   Gate log: {log_path}", flush=True)
        return 0
    else:
        print(f"\n❌ Lesson failed: {state.failed_reason or 'turn budget exhausted'}",
              flush=True, file=sys.stderr)
        print(f"   Cost: ~${final_spend:.2f}", flush=True, file=sys.stderr)
        print(f"   Gate log: {log_path}", flush=True, file=sys.stderr)
        return 1


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--study-date", required=True,
                   help="ISO date in the JW study week, e.g., 2026-05-17")
    p.add_argument("--target", choices=["wt", "mwb", "cbs", "gems"], default="wt",
                   help="Which lesson to draft: wt (Sunday Watchtower study), "
                        "cbs (midweek Congregation Bible Study — lfb lessons), "
                        "gems (Spiritual Gems verse comments for the week's "
                        "Bible reading), mwb (midweek workbook — legacy, may "
                        "not scrape correctly).")
    p.add_argument("--email", action="store_true",
                   help="Email the JSON via Resend after commit (requires RESEND_API_KEY)")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"Model for the lesson agent (default {DEFAULT_MODEL})")
    p.add_argument("--paragraphs", default=None,
                   help="Comma-separated paragraph numbers to process (slice). "
                        "Default: all. Useful for cheap smoke tests / paragraph-"
                        "specific regression testing. E.g. --paragraphs 1,2,11")
    p.add_argument("--fresh", action="store_true",
                   help="Wipe any saved state in the run dir before starting. "
                        "Default is auto-resume — drafts saved from a previous "
                        "run are loaded and the agent skips already-drafted "
                        "paragraphs at zero API cost.")
    args = p.parse_args()
    pfilter: list[int] | None = None
    if args.paragraphs:
        pfilter = [int(x.strip()) for x in args.paragraphs.split(",") if x.strip()]
    return run_lesson(
        study_date=args.study_date,
        target=args.target,
        email_enabled=args.email,
        model=args.model,
        paragraph_filter=pfilter,
        fresh=args.fresh,
    )


if __name__ == "__main__":
    sys.exit(main())
