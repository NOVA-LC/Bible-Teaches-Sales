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

MAX_ATTEMPTS = 3


def _draft_with_gates(
    para: ParagraphData,
    article_meta: dict,
    prior_comments: list[dict],
    worker,
    log_path: Path,
) -> tuple[dict | None, list[GateResult]]:
    """Try to produce a comment that passes per-comment gates + the critic.
    Returns (comment_or_None, gate_history)."""
    history: list[GateResult] = []
    feedback = ""
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
        payload = {
            "article_title": article_meta["article_title"],
            "article_source": article_meta["article_source"],
            "study_date": article_meta["study_date"],
            "paragraph_number": para.paragraph_number,
            "body_pid": para.body_pid,
            "question_pid": para.question_pid,
            "question_text": para.question_text,
            "body_paragraph_text": para.body_text,
            "prior_mechanics_this_week": sorted(set(prior_mechs)),
            "prior_named_relationships_this_week": sorted(set(prior_rels)),
            "prior_herd_moves_this_week": sorted(set(prior_herd)),
            "attempt": attempt,
            "redraft_feedback": feedback,
        }
        try:
            comment = worker.draft_comment(payload)
        except Exception as e:
            history.append(GateResult(
                f"draft attempt {attempt}", False, f"worker error: {e}"
            ))
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
    p.add_argument("--article-id", type=int, required=True,
                   help="WOL DocumentId (e.g., 2026320)")
    p.add_argument("--key-symbol", default="w",
                   help="Publication key symbol (w, mwb, etc.)")
    p.add_argument("--issue", type=int, required=True,
                   help="Issue tag, e.g., 20260300")
    p.add_argument("--study-date", required=True,
                   help="ISO date, e.g., 2026-05-10")
    p.add_argument("--article-title", default=None,
                   help="Override article title (else fetched from page)")
    p.add_argument("--article-source", default=None,
                   help="e.g., 'The Watchtower (Study), March 2026'")
    p.add_argument("--output", type=Path, required=True,
                   help="Output comments JSON path")
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
