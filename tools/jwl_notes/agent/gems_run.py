"""gems_run.py — Spiritual Gems orchestrator (Phase 3a).

Drafts 4 verse comments distributed across the week's Bible reading range
for the midweek meeting's Spiritual Gems portion. Anchors comments to
Bible verses (block_type=2), one JSON output per chapter.

Architecture (v1, chained-pipeline style):
  1. discover_week → bible_reading_book + chapter_start..chapter_end
  2. Fetch each chapter's NWT HTML, extract verse text
  3. Sonnet picks the 4 strongest verses across the range
  4. For each picked verse:
     - fetch_deep_brief for the verse (NWT + context + xrefs + footnotes)
     - draft via Sonnet using verse_comment.md as system prompt
     - run per-comment gates; retry up to 5x with feedback on failure
  5. Write JSON in Bible-mode shape (matches the existing
     comments/*-spiritual-gems-*.json wire format)

CLI:
  python -m agent.gems_run --study-date 2026-05-17

This is the "chained pipeline" style — single-prompt per verse, not a
tool-using agent. verse_comment.md uses the legacy four-slot
architecture (Type-A-like), so the simpler chained approach matches.
Future v2: refactor to tool-using verse_comment_agent if needed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from jwl_notes import fetch_wol_bible_chapter  # type: ignore  # noqa: E402
from research import fetch_deep_brief, DEFAULT_UA  # type: ignore  # noqa: E402
from workers import SDKWorker, load_dotenv, _extract_json  # type: ignore  # noqa: E402
from gates import GateResult, run_per_comment_gates  # type: ignore  # noqa: E402


PROMPTS_DIR = _HERE / "prompts"
DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_DRAFT_ATTEMPTS = 5
COMMENTS_PER_BIBLE_READING = 4


# ----------------------------------------------------------------------
# Verse extraction from NWT chapter HTML
# ----------------------------------------------------------------------

_VERSE_RE = re.compile(
    r'<span\s+id="v(\d+)-(\d+)-(\d+)-\d+"\s+class="v">(.*?)</span>',
    re.DOTALL,
)


def _strip_html(s: str) -> str:
    """Mirror research._strip_inline_tags_keep_text but cleaner — for verse
    text extraction, we want plain readable NWT prose, not marker tokens."""
    # Drop the verse-number link
    s = re.sub(r'<a[^>]*class="[^"]*\bvl\b[^"]*"[^>]*>.*?</a>', " ", s, flags=re.DOTALL)
    # Strip cross-ref and footnote markers entirely (we don't need them here)
    s = re.sub(r'<a[^>]*class="[^"]*\bb\b[^"]*"[^>]*>.*?</a>', " ", s, flags=re.DOTALL)
    s = re.sub(r'<a[^>]*class="[^"]*\bfn\b[^"]*"[^>]*>.*?</a>', " ", s, flags=re.DOTALL)
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&")
           .replace("&#8217;", "'").replace("&#8220;", '"').replace("&#8221;", '"')
           .replace("&#8212;", "—").replace("&#8211;", "–")
           .replace("·", ""))
    return re.sub(r"\s+", " ", s).strip()


def extract_verses(html: str, book: int, chapter: int) -> dict[int, str]:
    """Return {verse_num: text} for one chapter."""
    parts: dict[int, list[str]] = {}
    for m in _VERSE_RE.finditer(html):
        b, c, v = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if b != book or c != chapter:
            continue
        body = _strip_html(m.group(4))
        parts.setdefault(v, []).append(body)
    return {v: " ".join(segs).strip() for v, segs in parts.items()}


# ----------------------------------------------------------------------
# Verse picker — Sonnet decides which 4 verses across the range
# ----------------------------------------------------------------------

VERSE_PICKER_SYSTEM = """You are picking the 4 verses across a Bible-reading range that will make the strongest Spiritual Gems audience comments for Tyler — a JW giving comments at a midweek meeting.

Selection criteria (in priority order):
1. **Veteran-sister-grade aha potential**: the verse contains a phrase, cross-reference opportunity, or detail that someone who's been at meetings for 20 years has likely never connected. NOT John 3:30 / Psalm 23 territory — those are too well-trodden.
2. **Phrase-lock potential**: a specific NWT phrase that can be embedded verbatim in a 30-second comment.
3. **Audience-state transformation potential**: the verse can release weight, equip action, or invert a frame for the listener IN the comment.
4. **Distribution**: spread the 4 picks across the range; don't cluster all 4 in the opening of chapter 1.

Avoid:
- Bookend doxologies that are too universal
- Verses identical in import to others nearby (pick the strongest one)
- Verses requiring deep context not present in the surrounding 2-3 verses

Return JSON only:
```json
{
  "picks": [
    {"chapter": 60, "verse": 1, "why": "one-sentence pitch — what's the aha"},
    {"chapter": 60, "verse": 5, "why": "..."},
    {"chapter": 60, "verse": 19, "why": "..."},
    {"chapter": 61, "verse": 1, "why": "..."}
  ]
}
```
"""


def pick_verses(
    worker: SDKWorker,
    book_name: str,
    book_num: int,
    chapter_verses: dict[int, dict[int, str]],
    bible_reading_range: str,
) -> list[dict]:
    """Ask Sonnet to pick 4 verses across the chapters. Returns list of
    {chapter, verse, why} dicts in order."""
    payload = {
        "book_name": book_name,
        "book_number": book_num,
        "bible_reading_range": bible_reading_range,
        "chapters": [
            {
                "chapter": chap,
                "verses": [
                    {"verse": v, "text": text}
                    for v, text in sorted(verses.items())
                ],
            }
            for chap, verses in sorted(chapter_verses.items())
        ],
        "count": COMMENTS_PER_BIBLE_READING,
    }
    result = worker._call(VERSE_PICKER_SYSTEM, payload)
    picks = result.get("picks", [])
    if not isinstance(picks, list) or len(picks) != COMMENTS_PER_BIBLE_READING:
        raise RuntimeError(
            f"Verse picker returned {len(picks)} picks, expected "
            f"{COMMENTS_PER_BIBLE_READING}: {result}"
        )
    return picks


# ----------------------------------------------------------------------
# Verse comment drafter — uses verse_comment.md as system prompt
# ----------------------------------------------------------------------

def _load_verse_prompt() -> str:
    return (PROMPTS_DIR / "verse_comment.md").read_text(encoding="utf-8")


def draft_verse_comment(
    worker: SDKWorker,
    verse_prompt: str,
    book_name: str,
    book_num: int,
    chapter: int,
    verse: int,
    verse_text: str,
    surrounding_verses: dict[str, str],
    bible_reading_range: str,
    prior_mechanics: list[str],
    prior_named_relationships: list[str],
) -> tuple[dict | None, list[GateResult]]:
    """Single verse comment with chained retry-on-gate-failure (≤5 attempts).
    Returns (comment_dict | None, gate_history)."""
    history: list[GateResult] = []
    feedback = ""
    for attempt in range(1, MAX_DRAFT_ATTEMPTS + 1):
        payload = {
            "book_name": book_name,
            "book_number": book_num,
            "chapter": chapter,
            "verse": verse,
            "verse_text": verse_text,
            "surrounding_verses": surrounding_verses,
            "bible_reading_range": bible_reading_range,
            "prior_mechanics_this_week": prior_mechanics,
            "prior_named_relationships_this_week": prior_named_relationships,
            "attempt": attempt,
            "redraft_feedback": feedback,
        }
        try:
            comment = worker._call(verse_prompt, payload)
        except Exception as e:
            history.append(GateResult(
                f"Verse {chapter}:{verse} attempt {attempt}", False,
                f"worker error: {e}",
            ))
            continue
        if "error" in comment:
            history.append(GateResult(
                f"Verse {chapter}:{verse} attempt {attempt}", False,
                f"worker self-rejected: {comment['error']}",
            ))
            feedback = f"Previous attempt rejected with: {comment['error']}"
            continue
        # Verse comments use the legacy single-prompt schema (Type-A-like).
        # Force comment_type='A' so the type-aware gates run the full set.
        comment.setdefault("comment_type", "A")
        gates = run_per_comment_gates(comment)
        history.extend(gates)
        if all(g.passed for g in gates):
            return comment, history
        failures = "; ".join(g.reason for g in gates if not g.passed)
        feedback = (
            f"Previous attempt failed these specific gates: {failures}. "
            "Return ONLY the corrected JSON object — no prose, no explanation, "
            "no preamble. Fix the listed gate failures surgically; do not "
            "rewrite the entire comment from scratch. The output must start "
            "with `{` and end with `}`."
        )
    return None, history


# ----------------------------------------------------------------------
# Assemble Bible-mode JSON (one per chapter)
# ----------------------------------------------------------------------

def assemble_gems_json(
    study_date: str,
    book_num: int,
    chapter: int,
    book_name: str,
    bible_reading_range: str,
    comments_for_chapter: list[dict],   # [{verse, content, ...}, ...]
) -> dict:
    notes = []
    for c in comments_for_chapter:
        notes.append({
            "verse": c["verse"],
            "block_type": 2,
            "title": None,
            "content": c["content"],
        })
    return {
        "_meta": {
            "study_date": study_date,
            "section": "Spiritual Gems",
            "bible_reading_range": bible_reading_range,
            "chapter": f"{book_name} {chapter}",
            "preparation_standard": (
                "Auto-generated by tools/jwl_notes/agent/gems_run.py — "
                "verse-anchored comments for Spiritual Gems, each drafted "
                "through verse_comment.md and passing all per-comment gates."
            ),
            "generated_at": datetime.utcnow().isoformat() + "Z",
        },
        "key_symbol": "nwtsty",
        "book": book_num,
        "chapter": chapter,
        "default_block_type": 2,
        "notes": notes,
    }


# ----------------------------------------------------------------------
# Main orchestration
# ----------------------------------------------------------------------

def run_gems(study_date: str, model: str = DEFAULT_MODEL) -> int:
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    # Discover the week
    from discover_week import discover  # type: ignore
    print(f"Discovering week containing {study_date}...", flush=True)
    wd = discover(study_date=study_date)
    if not wd.bible_reading_book:
        print(f"ERROR: no Bible reading discovered. Warnings: {wd.warnings}",
              file=sys.stderr)
        return 2

    book_num = wd.bible_reading_book
    book_name = wd.bible_reading_book_name or f"Book{book_num}"
    chap_start = wd.bible_reading_chapter_start
    chap_end = wd.bible_reading_chapter_end or chap_start
    chap_range = (
        f"{book_name} {chap_start}-{chap_end}" if chap_end != chap_start
        else f"{book_name} {chap_start}"
    )
    print(f"  Bible reading: {chap_range} (book #{book_num})", flush=True)

    # Fetch and extract verses for every chapter in the range
    chapter_verses: dict[int, dict[int, str]] = {}
    for chap in range(chap_start, chap_end + 1):
        print(f"  Fetching {book_name} {chap}...", flush=True)
        html = fetch_wol_bible_chapter(book_num, chap, "nwtsty")
        verses = extract_verses(html, book_num, chap)
        chapter_verses[chap] = verses
        print(f"    {len(verses)} verses extracted", flush=True)

    # Pick 4 verses with Sonnet
    worker = SDKWorker(model=model)
    print(f"\nPicking {COMMENTS_PER_BIBLE_READING} verses across "
          f"{chap_range}...", flush=True)
    try:
        picks = pick_verses(worker, book_name, book_num, chapter_verses, chap_range)
    except Exception as e:
        print(f"ERROR: verse picker failed: {e}", file=sys.stderr)
        return 1
    print("  Picked:", flush=True)
    for p in picks:
        print(f"    {book_name} {p['chapter']}:{p['verse']} — {p.get('why', '')[:120]}",
              flush=True)

    # Draft each
    verse_prompt = _load_verse_prompt()
    prior_mechanics: list[str] = []
    prior_named_relationships: list[str] = []
    drafted: list[dict] = []   # {chapter, verse, comment, history}
    failed: list[dict] = []
    for p in picks:
        chap = p["chapter"]
        verse = p["verse"]
        print(f"\n--- Drafting {book_name} {chap}:{verse} ---", flush=True)
        verses_in_chap = chapter_verses.get(chap, {})
        verse_text = verses_in_chap.get(verse, "")
        if not verse_text:
            print(f"  ✗ no verse text for {chap}:{verse}; skip", flush=True)
            failed.append({"chapter": chap, "verse": verse,
                           "reason": "verse text not found"})
            continue
        surrounding = {}
        for offset in (-2, -1, 1, 2):
            v_other = verse + offset
            if v_other in verses_in_chap:
                surrounding[f"{chap}:{v_other}"] = verses_in_chap[v_other]
        comment, history = draft_verse_comment(
            worker, verse_prompt, book_name, book_num, chap, verse,
            verse_text, surrounding, chap_range,
            prior_mechanics, prior_named_relationships,
        )
        for g in history:
            print(f"  {g}", flush=True)
        if comment is None:
            print(f"  ✗ FAILED after {MAX_DRAFT_ATTEMPTS} attempts", flush=True)
            failed.append({"chapter": chap, "verse": verse,
                           "reason": f"gates failed after {MAX_DRAFT_ATTEMPTS} attempts"})
            continue
        drafted.append({"chapter": chap, "verse": verse, "comment": comment,
                        "why": p.get("why", "")})
        # Accumulate prior state for variety across the 4 comments
        for b in comment.get("tagged_beats", []):
            m = b.get("mechanic")
            if m:
                prior_mechanics.append(m)
        ds = comment.get("domestic_scene") or {}
        if ds.get("present") and ds.get("named_relationship"):
            prior_named_relationships.append(ds["named_relationship"])

    # Assemble + write JSON per chapter
    out_paths = []
    by_chap: dict[int, list[dict]] = {}
    for d in drafted:
        by_chap.setdefault(d["chapter"], []).append({
            "verse": d["verse"], "content": d["comment"]["content"],
        })
    out_dir = _HERE.parent / "comments"
    out_dir.mkdir(parents=True, exist_ok=True)
    short_book = re.sub(r"[^a-z]", "", book_name.lower())[:6]
    for chap, comments in sorted(by_chap.items()):
        out_doc = assemble_gems_json(
            study_date, book_num, chap, book_name, chap_range, comments,
        )
        out_path = out_dir / f"{study_date}-spiritual-gems-{short_book}{chap}.json"
        out_path.write_text(
            json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        out_paths.append(out_path)
        print(f"\n✅ Wrote {out_path}", flush=True)

    print(f"\n=== Gems run done ===")
    print(f"  Drafted: {len(drafted)} / {COMMENTS_PER_BIBLE_READING}")
    print(f"  Failed: {len(failed)}")
    for f in failed:
        print(f"    ✗ {book_name} {f['chapter']}:{f['verse']} — {f['reason']}")
    print(f"  Files: {out_paths}")
    return 0 if not failed else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--study-date", required=True,
                   help="ISO date in the study week, e.g., 2026-05-17")
    p.add_argument("--model", default=DEFAULT_MODEL)
    args = p.parse_args()
    return run_gems(args.study_date, model=args.model)


if __name__ == "__main__":
    sys.exit(main())
