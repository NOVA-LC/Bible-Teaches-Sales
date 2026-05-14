#!/usr/bin/env python3
"""build_week.py — autonomous weekly prep orchestrator.

For a given Watchtower / midweek article, fan out one worker per
paragraph (comment + underlines), run all six gates as deterministic
code, and assemble the comments JSON. Refuses to write JSON if any
gate cannot be made to pass within the attempt cap — no silent shipping.

Usage (production, after .env has ANTHROPIC_API_KEY):

    python -m agent.build_week \\
        --article-id 2026320 \\
        --key-symbol w \\
        --issue 20260300 \\
        --study-date 2026-05-10 \\
        --output ../comments/2026-05-10-w.json

Usage (in-session demo, prints job payloads):

    python -m agent.build_week --article-id 2026320 ... --backend in_session

The output JSON has the exact shape that jwl_notes.py expects.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Make sibling imports work whether invoked as module or script
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))  # so we can import jwl_notes
sys.path.insert(0, str(_HERE))         # so we can import gates / workers

from jwl_notes import (  # noqa: E402
    fetch_wol_article,
    extract_paragraph_tokens,
    _PExtractor,
)
from gates import (  # noqa: E402
    GateResult,
    run_per_comment_gates,
    run_article_gates,
    run_underline_gates,
    gate6_critic,
)
from workers import get_worker, load_dotenv  # noqa: E402

# ----------------------------------------------------------------------
# Article scraping — pull body paragraphs + their printed questions
# ----------------------------------------------------------------------

import re


@dataclass
class ParagraphData:
    paragraph_number: int
    body_pid: int
    question_pid: int | None
    question_text: str | None
    body_text: str
    cited_scriptures: list[str]


def scrape_article(html: str) -> list[ParagraphData]:
    """Return per-paragraph data for the article, ordered by visible
    paragraph number. Each entry includes the printed question (if any)
    that this paragraph answers."""
    # Map question pid -> question text
    qu_pat = re.compile(
        r'<p\s+id="p\d+"\s+data-pid="(\d+)"\s+class="qu">(.*?)</p>',
        re.DOTALL,
    )
    questions = {}
    for m in qu_pat.finditer(html):
        qpid = int(m.group(1))
        # strip tags
        from html.parser import HTMLParser

        class S(HTMLParser):
            def __init__(self):
                super().__init__()
                self.t = []
            def handle_data(self, d):
                self.t.append(d)
        sp = S(); sp.feed(m.group(2))
        questions[qpid] = re.sub(r"\s+", " ", "".join(sp.t)).strip()

    # Map body pid -> question pid
    body_pat = re.compile(
        r'<p\s+id="p\d+"\s+data-pid="(\d+)"\s+data-rel-pid="\[(\d+)\]"',
        re.DOTALL,
    )
    body_to_q = {}
    for m in body_pat.finditer(html):
        body_to_q[int(m.group(1))] = int(m.group(2))

    # Body paragraphs in source order
    body_order_pat = re.compile(r'<p\s+id="p\d+"\s+data-pid="(\d+)"\s+data-rel-pid=', re.DOTALL)
    seen = []
    for m in body_order_pat.finditer(html):
        pid = int(m.group(1))
        if pid not in seen:
            seen.append(pid)

    out = []
    for visible_num, body_pid in enumerate(seen, start=1):
        p = _PExtractor(pid=body_pid)
        p.feed(html)
        body_text = " ".join(p.text.split())
        # Strip leading paragraph number ("16 Some may feel..." -> "Some may feel...")
        body_text = re.sub(r"^\d+\s+", "", body_text)
        q_pid = body_to_q.get(body_pid)
        q_text = questions.get(q_pid) if q_pid else None
        # Cited scriptures inside the paragraph (rough — citation links in body)
        cited = re.findall(
            r'<a[^>]*class="b"[^>]*>(.*?)</a>',
            re.search(
                rf'<p\s+id="p\d+"\s+data-pid="{body_pid}"[^>]*>(.*?)</p>',
                html, re.DOTALL,
            ).group(1) if re.search(
                rf'<p\s+id="p\d+"\s+data-pid="{body_pid}"[^>]*>(.*?)</p>',
                html, re.DOTALL,
            ) else "",
            re.DOTALL,
        )
        cited = [re.sub(r"<[^>]+>", "", c).strip() for c in cited]
        out.append(ParagraphData(
            paragraph_number=visible_num,
            body_pid=body_pid,
            question_pid=q_pid,
            question_text=q_text,
            body_text=body_text,
            cited_scriptures=cited,
        ))
    return out


# ----------------------------------------------------------------------
# The retry loop — up to MAX_ATTEMPTS per paragraph
# ----------------------------------------------------------------------

MAX_ATTEMPTS = 25  # raised from 3 per operator: "should never fail, should keep
                   # doing till it makes a good comment." Cap is high enough that
                   # a paragraph either passes by attempt ~25 or the prompt/gate
                   # has a bug. Safety: prevents infinite loops from runaway cost
                   # if a gate becomes impossible to satisfy.

# Mirror Gate 11's hard_cap: once a comment type has been used this many times
# in the current article, the orchestrator forbids the selector from picking
# it again. Gate 11 fails when a type's count > 3 — so we block at 3 to keep
# the next pick under cap. Soft-cap warnings (>2) do NOT trigger forbidding.
GATE11_HARD_CAP = 3


# Errors that no amount of retrying can fix — abort the run instead of
# burning attempts. These come from the SDK as exception messages.
_FATAL_ERROR_MARKERS = (
    "credit balance is too low",  # billing exhausted
    "invalid x-api-key",            # auth failure
    "authentication_error",
    "permission_error",
    "Your account has been disabled",
)


def _is_fatal_worker_error(err: Exception) -> bool:
    msg = str(err)
    return any(marker in msg for marker in _FATAL_ERROR_MARKERS)


def _issue_month_year(issue: int | None) -> str:
    """20260300 → 'March 2026'."""
    if not issue:
        return ""
    s = str(issue)
    if len(s) != 8:
        return s
    year, month = int(s[:4]), int(s[4:6])
    months = ["", "January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    return f"{months[month]} {year}" if 1 <= month <= 12 else s


def _draft_with_gates(
    para: ParagraphData,
    article_meta: dict,
    prior_comments: list[dict],
    worker,
    log_path: Path,
) -> tuple[dict | None, list[GateResult]]:
    """Try to produce a comment that passes per-comment gates + the critic.

    Free-thinking pipeline per paragraph:
      1. Phase 0 (Python) — fetch_deep_brief: pull NWT verse text + 3-verse
         context window + up to 5 cross-ref targets + footnotes for every
         scripture cited in the paragraph. This is real study material.
      2. Phase 1 (Sonnet) — worker.select_comment_type: picks A/B/C/D/F/H
         based on paragraph type, research-brief gem candidates, and
         prior types used in the article (variety constraint).
      3. Phase 2 (Sonnet) — worker.draft_typed_comment(type): drafts the
         comment in the chosen type's specific shape with the research
         brief as input.
      4. Per-comment gates (type-aware).
      5. Gate 6 critic (separate worker call).

    Returns (comment_or_None, gate_history)."""
    from .research import fetch_deep_brief  # type: ignore

    history: list[GateResult] = []
    feedback = ""

    # Phase 0 — pull the deep brief ONCE per paragraph (cached on disk)
    try:
        brief = fetch_deep_brief(
            para.body_text,
            explicit_citations=para.cited_scriptures or None,
        )
        brief_serialized = [
            {
                "citation": vs.citation,
                "text": vs.text[:500],
                "context_before": vs.context_before[-3:],
                "context_after": vs.context_after[:3],
                "cross_refs": vs.cross_refs[:5],
                "footnotes": vs.footnotes[:2],
            }
            for vs in brief.cited_studies
        ]
        history.append(GateResult(
            "Research brief", True,
            f"{len(brief.cited_studies)} verse(s), "
            f"{sum(len(vs.cross_refs) for vs in brief.cited_studies)} cross-refs total"
        ))
    except Exception as e:
        history.append(GateResult(
            "Research brief", False, f"fetch failed: {e}; drafting without brief"
        ))
        brief_serialized = []

    prior_types = [c.get("comment_type", "A") for c in prior_comments if c.get("comment_type")]

    # Article-level Gate 11 enforcement: any type already at the hard cap is
    # forbidden for this paragraph's selector. Without this, the selector's
    # soft variety language gets overridden by paragraph-local fit (May 17
    # picked Type F four times — caps at 3 — because each F was locally apt).
    from collections import Counter
    _type_counts = Counter(prior_types)
    forbidden_types = sorted(
        t for t, n in _type_counts.items() if n >= GATE11_HARD_CAP
    )

    for attempt in range(1, MAX_ATTEMPTS + 1):
        prior_mechs = []
        prior_rels = []
        prior_herd = []
        for c in prior_comments:
            prior_mechs.extend(b.get("mechanic") for b in c.get("tagged_beats", []))
            ds = c.get("domestic_scene") or {}
            if ds.get("present") and ds.get("named_relationship"):
                prior_rels.append(ds["named_relationship"])
            prior_herd.extend(c.get("herd_distinctive_moves") or [])
        base_payload = {
            "article_title": article_meta["article_title"],
            "article_source": article_meta["article_source"],
            "study_date": article_meta["study_date"],
            "paragraph_number": para.paragraph_number,
            "body_pid": para.body_pid,
            "question_pid": para.question_pid,
            "question_text": para.question_text,
            "body_paragraph_text": para.body_text,
            "cited_scriptures": para.cited_scriptures,
            "research_brief": brief_serialized,
            "prior_mechanics_this_week": sorted(set(prior_mechs)),
            "prior_named_relationships_this_week": sorted(set(prior_rels)),
            "prior_herd_moves_this_week": sorted(set(prior_herd)),
            "prior_types_used_this_article": prior_types,
            "forbidden_types": forbidden_types,
            "attempt": attempt,
            "redraft_feedback": feedback,
        }

        # Phase 1 — select comment type (cheaper; one call before drafting)
        try:
            selection = worker.select_comment_type(base_payload)
            chosen_type = (selection.get("chosen_type") or "A").upper().strip()
            if chosen_type not in {"A", "B", "C", "D", "F", "H"}:
                chosen_type = "A"
            # Defensive: if the selector picked a forbidden type anyway,
            # coerce to the first allowed alternative so Gate 11 can't fail
            # mid-article. Selector should respect forbidden_types, but we
            # don't trust soft constraints.
            if chosen_type in forbidden_types:
                allowed = [t for t in ("A", "F", "D", "H", "B", "C")
                           if t not in forbidden_types]
                if allowed:
                    history.append(GateResult(
                        f"Type selector attempt {attempt}", True,
                        f"selector picked forbidden {chosen_type!r} "
                        f"(forbidden={forbidden_types}); coerced to {allowed[0]}"
                    ))
                    chosen_type = allowed[0]
                else:
                    history.append(GateResult(
                        f"Type selector attempt {attempt}", True,
                        f"all types at cap (forbidden={forbidden_types}); "
                        f"keeping {chosen_type} — Gate 11 will fail"
                    ))
            else:
                history.append(GateResult(
                    f"Type selector attempt {attempt}", True,
                    f"chose {chosen_type}: {selection.get('rationale', '')[:120]}"
                ))
        except Exception as e:
            if _is_fatal_worker_error(e):
                raise SystemExit(
                    "\n❌ FATAL: " + str(e)[:200] +
                    "\n   Fix at https://console.anthropic.com/ then rerun."
                )
            history.append(GateResult(
                f"Type selector attempt {attempt}", False,
                f"selector error: {e}; defaulting to A"
            ))
            chosen_type = "A"
            selection = {"chosen_type": "A"}

        draft_payload = {**base_payload, "type_selection": selection}

        # Phase 2 — draft in the chosen type's shape
        try:
            comment = worker.draft_typed_comment(chosen_type, draft_payload)
            # Always tag the output with the chosen type for downstream gates
            comment["comment_type"] = chosen_type
        except Exception as e:
            history.append(GateResult(
                f"draft attempt {attempt}", False, f"worker error: {e}"
            ))
            if _is_fatal_worker_error(e):
                history.append(GateResult(
                    "FATAL", False,
                    "billing or auth error — no retry will fix this. Aborting."
                ))
                raise SystemExit(
                    "\n❌ FATAL: " + str(e)[:200] +
                    "\n   Fix at https://console.anthropic.com/ then rerun."
                )
            continue
        if "error" in comment:
            history.append(GateResult(
                f"draft attempt {attempt}", False,
                f"worker self-rejected: {comment['error']}"
            ))
            feedback = f"Previous attempt rejected with: {comment['error']}"
            continue
        # Per-comment gates
        gates = run_per_comment_gates(comment)
        history.extend(gates)
        if not all(g.passed for g in gates):
            failure_summary = "; ".join(g.reason for g in gates if not g.passed)
            feedback = (
                f"Previous attempt failed gates: {failure_summary}. "
                "Fix these specifically and try again."
            )
            continue
        # Gate 6 — critic (separate worker)
        critic_result = gate6_critic(
            comment={**comment, "paragraph_number": para.paragraph_number},
            paragraph_data={
                "question_text": para.question_text,
                "body_paragraph_text": para.body_text,
            },
            critic_call=worker.critique,
        )
        history.append(critic_result)
        if not critic_result.passed:
            feedback = (
                f"Previous attempt failed Gate 6: {critic_result.reason}"
            )
            continue
        comment["paragraph_number"] = para.paragraph_number
        comment["body_pid"] = para.body_pid
        comment["question_pid"] = para.question_pid
        return comment, history
    # Exhausted attempts
    return None, history


def _draft_underlines_with_gates(
    para: ParagraphData,
    worker,
) -> tuple[dict | None, list[GateResult]]:
    """Produce the underline payload for this paragraph; gate-check it."""
    history: list[GateResult] = []
    feedback = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        payload = {
            "paragraph_number": para.paragraph_number,
            "data_pid": para.body_pid,
            "question_text": para.question_text,
            "body_paragraph_text": para.body_text,
            "cited_scriptures": para.cited_scriptures,
            "attempt": attempt,
            "redraft_feedback": feedback,
        }
        try:
            ul = worker.draft_underlines(payload)
        except Exception as e:
            history.append(GateResult(
                f"underline attempt {attempt}", False, f"worker error: {e}"
            ))
            if _is_fatal_worker_error(e):
                raise SystemExit(
                    "\n❌ FATAL: " + str(e)[:200] +
                    "\n   Fix at https://console.anthropic.com/ then rerun."
                )
            continue
        if "error" in ul:
            history.append(GateResult(
                f"underline attempt {attempt}", False,
                f"worker rejected: {ul['error']}"
            ))
            feedback = f"Previous attempt rejected with: {ul['error']}"
            continue
        gates = run_underline_gates(ul, para.body_text, para.question_text or "")
        history.extend(gates)
        if not all(g.passed for g in gates):
            failure_summary = "; ".join(g.reason for g in gates if not g.passed)
            feedback = (
                f"Previous attempt failed gates: {failure_summary}. "
                "Re-pick phrases — yellows must verbatim-appear in the source "
                "AND fully grammatically answer the printed question."
            )
            continue
        return ul, history
    return None, history


# ----------------------------------------------------------------------
# Assembly into the JSON shape jwl_notes.py expects
# ----------------------------------------------------------------------

def assemble_comments_json(
    article_meta: dict,
    paragraphs: list[ParagraphData],
    drafted_comments: dict[int, dict],
    drafted_underlines: dict[int, dict],
) -> dict:
    """Build the wire JSON shape (matching tools/jwl_notes/comments/*.json)."""
    notes = []
    for para in paragraphs:
        comment = drafted_comments.get(para.body_pid)
        underlines = drafted_underlines.get(para.body_pid)
        # Note row (anchored to the QUESTION pid for inline rendering)
        if comment and para.question_pid is not None:
            notes.append({
                "paragraph": para.paragraph_number,
                "data_pid": para.question_pid,
                "block_type": 1,
                "title": None,
                "content": comment["content"],
            })
        # Underline row (anchored to the BODY pid)
        if underlines:
            notes.append({
                "paragraph": para.paragraph_number,
                "data_pid": para.body_pid,
                "block_type": 1,
                "underlines": underlines["underlines"],
            })
    return {
        "_meta": {
            "study_date": article_meta["study_date"],
            "article_title": article_meta["article_title"],
            "source": article_meta["article_source"],
            "url": article_meta.get("url", ""),
            "preparation_standard": (
                "Auto-generated by tools/jwl_notes/agent/build_week.py — "
                "every note passed Mandate 4 (six-gate Pre-Ship Self-Audit). "
                "Comments anchor to question data-pid; underlines anchor to "
                "body paragraph data-pid."
            ),
            "generated_at": datetime.utcnow().isoformat() + "Z",
        },
        "key_symbol": article_meta["key_symbol"],
        "issue": article_meta["issue"],
        "document_id": article_meta["document_id"],
        "default_block_type": 1,
        "notes": notes,
    }


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--study-date", required=True,
                   help="ISO date in the JW study week, e.g., 2026-05-17. "
                        "If only --study-date is given, all article metadata "
                        "is auto-discovered via agent.discover_week.")
    p.add_argument("--article-id", type=int, default=None,
                   help="WOL DocumentId override (skips auto-discovery)")
    p.add_argument("--key-symbol", default=None,
                   help="Publication key symbol (default 'w' for the WT study)")
    p.add_argument("--issue", type=int, default=None,
                   help="Issue tag override, e.g., 20260300")
    p.add_argument("--target", choices=["wt", "mwb"], default="wt",
                   help="Which publication to draft for: wt (Sunday Watchtower) "
                        "or mwb (midweek workbook). Default: wt.")
    p.add_argument("--article-title", default=None,
                   help="Override article title (else fetched from page)")
    p.add_argument("--article-source", default=None,
                   help="e.g., 'The Watchtower (Study), March 2026'")
    p.add_argument("--output", type=Path, default=None,
                   help="Output comments JSON path. Default: "
                        "comments/<study-date>-<key-symbol>.json")
    p.add_argument("--backend", choices=["auto", "sdk", "in_session"],
                   default="auto",
                   help="Worker backend (default auto: SDK if key present)")
    p.add_argument("--paragraphs", default=None,
                   help="Comma-separated paragraph numbers to process "
                        "(default: all). E.g. --paragraphs 1,3,7")
    p.add_argument("--dry-run-list", action="store_true",
                   help="Print discovered paragraphs and exit")
    args = p.parse_args()

    load_dotenv()

    # Auto-discover anything the operator didn't supply.
    if args.article_id is None or args.key_symbol is None or args.issue is None:
        from discover_week import discover  # local import to avoid hard dep
        print(f"Auto-discovering materials for study week containing "
              f"{args.study_date} ...", flush=True)
        wd = discover(study_date=args.study_date)
        for w in wd.warnings:
            print(f"  ⚠ discovery warning: {w}", file=sys.stderr)
        if args.target == "wt":
            if wd.wt_document_id is None:
                print("ERROR: WT DocumentId could not be discovered. "
                      "Pass --article-id manually.", file=sys.stderr)
                return 2
            args.article_id = args.article_id or wd.wt_document_id
            args.key_symbol = args.key_symbol or "w"
            args.issue = args.issue or wd.wt_issue or 0
            args.article_title = args.article_title or wd.wt_title
            args.article_source = args.article_source or (
                f"The Watchtower (Study), "
                f"{_issue_month_year(wd.wt_issue) if wd.wt_issue else 'unknown issue'}"
            )
        else:  # mwb
            if wd.mwb_document_id is None:
                print("ERROR: mwb DocumentId could not be discovered. "
                      "Pass --article-id manually.", file=sys.stderr)
                return 2
            args.article_id = args.article_id or wd.mwb_document_id
            args.key_symbol = args.key_symbol or "mwb"
            args.issue = args.issue or wd.mwb_issue or 0
            args.article_title = args.article_title or f"Midweek Meeting — {wd.week_label}"
            args.article_source = args.article_source or (
                f"Our Christian Life and Ministry — "
                f"Meeting Workbook ({_issue_month_year(wd.mwb_issue) if wd.mwb_issue else 'unknown issue'})"
            )
        print(f"  → DocId={args.article_id}  key_symbol={args.key_symbol}  "
              f"issue={args.issue}", flush=True)
        print(f"  → title: {args.article_title!r}", flush=True)

    if args.output is None:
        out_dir = _HERE.parent / "comments"
        args.output = out_dir / f"{args.study_date}-{args.key_symbol}.json"

    print(f"Fetching WOL article DocumentId={args.article_id} ...", flush=True)
    html = fetch_wol_article(args.article_id, args.key_symbol)

    paragraphs = scrape_article(html)
    if args.paragraphs:
        wanted = {int(x) for x in args.paragraphs.split(",")}
        paragraphs = [p for p in paragraphs if p.paragraph_number in wanted]
    print(f"Discovered {len(paragraphs)} body paragraph(s).", flush=True)

    if args.dry_run_list:
        for p in paragraphs:
            print(f"  ¶{p.paragraph_number} body_pid={p.body_pid} "
                  f"q_pid={p.question_pid}: {(p.question_text or '(no question)')[:80]}")
        return 0

    article_meta = {
        "article_title": args.article_title or f"DocId {args.article_id}",
        "article_source": args.article_source or "",
        "study_date": args.study_date,
        "key_symbol": args.key_symbol,
        "issue": args.issue,
        "document_id": args.article_id,
        "url": f"https://wol.jw.org/en/wol/d/r1/lp-e/{args.article_id}",
    }

    run_dir = _HERE / "runs" / f"{args.study_date}-{args.key_symbol}-{args.article_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "gates.log"
    log_fh = log_path.open("w", encoding="utf-8")

    try:
        worker = get_worker(args.backend, run_dir=run_dir)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    drafted_comments: dict[int, dict] = {}
    drafted_underlines: dict[int, dict] = {}
    failed_comments: list[int] = []
    failed_underlines: list[int] = []

    for para in paragraphs:
        print(f"\n--- ¶{para.paragraph_number} (body pid {para.body_pid}) ---",
              flush=True)
        log_fh.write(f"\n=== ¶{para.paragraph_number} ===\n")

        # Comment (only if there's a printed question to answer)
        if para.question_pid is not None:
            comment, history = _draft_with_gates(
                para, article_meta,
                list(drafted_comments.values()),
                worker, log_path,
            )
            for g in history:
                print(f"  {g}", flush=True)
                log_fh.write(f"{g}\n")
            if comment is None:
                failed_comments.append(para.paragraph_number)
                print(f"  ✗ COMMENT GAVE UP after {MAX_ATTEMPTS} attempts",
                      flush=True)
            else:
                drafted_comments[para.body_pid] = comment

        # Underlines (always)
        ul, ul_history = _draft_underlines_with_gates(para, worker)
        for g in ul_history:
            print(f"  {g}", flush=True)
            log_fh.write(f"{g}\n")
        if ul is None:
            failed_underlines.append(para.paragraph_number)
        else:
            drafted_underlines[para.body_pid] = ul

    # Article-level gates
    print("\n--- Article-level gates ---", flush=True)
    article_gates = run_article_gates(list(drafted_comments.values()))
    for g in article_gates:
        print(f"  {g}", flush=True)
        log_fh.write(f"{g}\n")
    log_fh.close()

    blockers = [g for g in article_gates if not g.passed]
    if failed_comments or failed_underlines or blockers:
        print(
            f"\n❌ REFUSED TO SHIP\n"
            f"  Failed comments: {failed_comments or 'none'}\n"
            f"  Failed underlines: {failed_underlines or 'none'}\n"
            f"  Article-level blockers: "
            f"{[g.reason for g in blockers] or 'none'}\n"
            f"  Gate log: {log_path}\n",
            file=sys.stderr,
        )
        return 1

    out_doc = assemble_comments_json(
        article_meta, paragraphs, drafted_comments, drafted_underlines,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\n✅ All gates passed. Wrote {args.output}")
    print(f"   Gate log: {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
