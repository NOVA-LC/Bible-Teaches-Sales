#!/usr/bin/env python3
"""jwl_notes.py — inject Study Notes + colored underlines into a JW Library backup.

Phase 1: paragraph notes (always supported).
Phase 2: underlines via UserMark + BlockRange rows (added May 2026).

Schema convention (derived empirically from Tyler's userData.db, May 2026):
    For Watchtower study articles, a paragraph-anchored note is:
        BlockType        = 1
        BlockIdentifier  = the paragraph's WOL `data-pid`
        UserMarkId       = NULL (free-floating; no highlight required)

    This places the note in the per-paragraph note slot in JW Library.

    The `data-pid` is *not* the visible paragraph number. In the modern
    Watchtower layout (2026 study issues, e.g. DocumentId 2026280) the
    visible paragraphs are body <p> elements with `class=""` and
    `data-rel-pid="[<question-pid>]"`. The note must anchor to the
    body-paragraph data-pid, not the question's data-pid.

    Older articles (pre-2024-ish) attached notes to the `class="qu"`
    question block or `class="sd"` review-box block; in either case
    BlockType=1 and BlockIdentifier=data-pid still holds. Some of
    Tyler's older notes additionally have a UserMark (highlight)
    pointing at the same Identifier; the note itself still uses
    BlockType=1 + BlockIdentifier=data-pid.

    Bible verse notes (KeySymbol='nwtsty', etc.) use BlockType=2 with
    BlockIdentifier=verse-number; this tool does not currently emit
    those — pass an explicit `block_type` per note if needed.

Workflow:
    1. Export a backup from JW Library on any device.
    2. Run this tool against the .jwlibrary file.
    3. Import the new file in JW Library.

Example:
    python jwl_notes.py \\
        --input  MyBackup.jwlibrary \\
        --output MyBackup-with-notes.jwlibrary \\
        --comments comments/2026-05-03.json

Comments JSON shape (current):

    {
      "issue": 20260200,
      "key_symbol": "w",
      "document_id": 2026280,
      "title_contains": "Are You Prepared",
      "default_block_type": 1,
      "notes": [
        {
          "paragraph": 2,        # visible paragraph number (informational)
          "data_pid": 8,         # WOL data-pid — the actual anchor
          "block_type": 1,       # optional override; defaults to default_block_type
          "title": null,
          "content": "..."
        }
      ]
    }

Backward compat: a top-level `block` field on each note is still accepted
and treated as `data_pid` (which is what the wire schema actually wants).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import tempfile
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


# JW Library UserMark.ColorIndex mapping (palette as of JW Library 2024+).
# Confirmed against Tyler's userData.db: he uses all six slots (1..6).
# See voice/color-semantics.md for Tyler's semantic system.
COLOR_INDEX = {
    "yellow": 1,
    "green": 2,
    "blue": 3,
    "pink": 4,
    "red": 4,    # Tyler's "red = stop in tracks" maps to JWL pink slot
    "orange": 5,
    "purple": 6,
}

# KeySymbols where Locations are anchored by (BookNumber, ChapterNumber)
# instead of (IssueTagNumber, DocumentId). Bible publications use BlockType=2
# with BlockIdentifier=verse-number for per-verse notes.
BIBLE_KEY_SYMBOLS = frozenset({"nwtsty", "nwt", "bi10", "Rbi8", "rNWT", "rbi8"})

USERMARK_STYLE_UNDERLINE = 0  # vs. 1 = full highlight box
USERMARK_VERSION = 1

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_anchor(note: dict, default_block_type: int) -> tuple[int, int]:
    """Return (block_type, block_identifier) for a note dict.

    Accepts:
    - `verse` (int) — Bible verse mode; default block_type=2
    - `data_pid` (int) — workbook/article paragraph mode; default block_type=1
    - `block` (int) — legacy alias for data_pid
    """
    if "verse" in note and isinstance(note["verse"], int):
        ident = note["verse"]
        bt = note.get("block_type", 2)
    elif "data_pid" in note and isinstance(note["data_pid"], int):
        ident = note["data_pid"]
        bt = note.get("block_type", default_block_type)
    elif "block" in note and isinstance(note["block"], int):
        ident = note["block"]
        bt = note.get("block_type", default_block_type)
    else:
        raise ValueError("note must include 'verse' (int), 'data_pid' (int), or legacy 'block' (int)")
    if not isinstance(bt, int) or bt not in (1, 2):
        raise ValueError(f"block_type must be 1 or 2, got {bt!r}")
    return bt, ident


def load_comments(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        spec = json.load(f)
    is_bible_mode = "book" in spec and "chapter" in spec
    if is_bible_mode:
        if not isinstance(spec["book"], int):
            sys.exit("'book' must be an integer (Bible book number 1..66)")
        if not isinstance(spec["chapter"], int):
            sys.exit("'chapter' must be an integer")
    elif "issue" not in spec:
        sys.exit(
            "comments file must include either 'issue' (paragraph mode — Watchtower / mwb / "
            "study book) or 'book'+'chapter' (Bible verse mode — nwtsty)"
        )
    if "notes" not in spec or not isinstance(spec["notes"], list) or not spec["notes"]:
        sys.exit("comments file must include a non-empty 'notes' array")
    default_bt = spec.get("default_block_type", 2 if is_bible_mode else 1)
    if default_bt not in (1, 2):
        sys.exit(f"default_block_type must be 1 or 2, got {default_bt!r}")
    for i, n in enumerate(spec["notes"]):
        try:
            _resolve_anchor(n, default_bt)
        except ValueError as e:
            sys.exit(f"note #{i}: {e}")
        has_content = isinstance(n.get("content"), str) and n["content"].strip()
        underlines = n.get("underlines") or []
        if not isinstance(underlines, list):
            sys.exit(f"note #{i}: 'underlines' must be an array if present")
        if not has_content and not underlines:
            sys.exit(f"note #{i}: must include 'content' (string) or 'underlines' (array) — both empty")
        for j, u in enumerate(underlines):
            if not isinstance(u.get("phrase"), str) or not u["phrase"].strip():
                sys.exit(f"note #{i} underline #{j}: 'phrase' must be a non-empty string")
            color = u.get("color", "yellow").lower()
            if color not in COLOR_INDEX:
                sys.exit(
                    f"note #{i} underline #{j}: unknown color {color!r}; "
                    f"known: {sorted(COLOR_INDEX)}"
                )
    return spec


def _http_get(url: str, timeout: int = 30) -> str:
    """HTTP GET with curl primary, urllib fallback. WOL's CDN hangs reliably
    on Python urllib for some URL patterns (meetings, search, certain
    article DocIds — same TLS keep-alive / chunked-transfer issue). curl
    on the same URL completes fine. Same pattern lives in
    agent/discover_week.py and agent/comment_agent.py."""
    import subprocess
    try:
        proc = subprocess.run(
            ["curl", "-fsSL", "--max-time", str(timeout),
             "-A", DEFAULT_UA, url],
            capture_output=True, timeout=timeout + 5,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout.decode("utf-8", errors="replace")
    except FileNotFoundError:
        pass  # curl not on PATH
    except Exception:
        pass
    # Fallback: urllib
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_wol_article(document_id: int, key_symbol: str = "w",
                      cache_dir: Path | None = None) -> str:
    """Fetch a WOL article HTML, caching to disk to avoid repeat hits."""
    cache_dir = cache_dir or (Path.home() / ".cache" / "jwl_notes")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{key_symbol}_{document_id}.html"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    url = f"https://wol.jw.org/en/wol/d/r1/lp-e/{document_id}"
    html = _http_get(url)
    cache_path.write_text(html, encoding="utf-8")
    return html


def fetch_wol_bible_chapter(book: int, chapter: int, key_symbol: str = "nwtsty",
                            cache_dir: Path | None = None) -> str:
    """Fetch a WOL Bible chapter HTML, caching to disk."""
    cache_dir = cache_dir or (Path.home() / ".cache" / "jwl_notes")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{key_symbol}_b_{book}_{chapter}.html"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    url = f"https://wol.jw.org/en/wol/b/r1/lp-e/{key_symbol}/{book}/{chapter}"
    html = _http_get(url)
    cache_path.write_text(html, encoding="utf-8")
    return html


# Canonical JW Library tokenization regex.
#
# Verified verbatim against sircharlo's jwl-backup-merger (line 2076 of
# jw-backup-merger.py), which is the reference implementation for resolving
# BlockRange.StartToken / EndToken back to displayed text. JW Library's
# native renderer applies this same tokenization when computing token offsets
# for highlights and notes.
#
# Empirical proof: ¶1 of DocId 2026320 ("Improve Your Art of Teaching")
# tokenizes as: position 32 = "This", position 94 = "Paul" — matching what
# JW Library renders when given BlockRange rows pointing at those offsets.
#
# Pattern semantics:
#   \w+(?:['.:-]\w+)*   — a word, optionally with embedded ' . : - separators
#                          (so "Mark" "28:19" "mild-tempered" "U.S.A" survive
#                          as single tokens; "father's" survives as one)
#   [^\s\w​]       — any single non-word non-whitespace non-ZWSP char
#                          (so . , ; : ? ! ( ) " " " — etc. each become
#                          their own token)
_TOKEN_PATTERN = re.compile(r"\w+(?:['.:-]\w+)*|[^\s\w​]")


def jw_tokenize(text: str) -> list[str]:
    """Tokenize text the same way JW Library does for BlockRange offsets.

    Verified against sircharlo's reference implementation. Use this for
    BOTH the source-text token list AND the search-phrase token list — they
    must use the same tokenizer or alignment fails.
    """
    return _TOKEN_PATTERN.findall(text)


class _PExtractor(HTMLParser):
    """Extract a paragraph's visible text the same way JW Library does.

    Mirrors sircharlo's PExtractor (lines 35-80 of jw-backup-merger.py) — the
    reference implementation for resolving JW Library token offsets:

      1. If `pid` is given, only emit text inside the matching <p data-pid="N">.
         If `pid` is None, emit text from the entire fed fragment.
      2. Skip text inside <span|sup class="parNum"> (paragraph number markers).
      3. Skip text inside <span|sup class="verseNum"> (verse number markers).
      4. Skip text inside <span|sup class="chapterNum"> (chapter number markers).
      5. Strip raised-bullet "·" characters (JW Library doesn't count them).
      6. Keep ALL other text content — including citation-link text
         ("Matt. 28:19, 20"), footnote markers, cross-reference symbols.
    """
    def __init__(self, pid=None):
        super().__init__()
        self.pid = str(pid) if pid is not None else None
        self.found = pid is None
        self.in_parNum = False
        self.in_verseNum = False
        self.in_chapterNum = False
        self.text = ""

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "p" and self.pid is not None:
            if d.get("data-pid") == self.pid:
                self.found = True
        elif self.found and tag in ("span", "sup"):
            classes = d.get("class", "").split()
            if "parNum" in classes:
                self.in_parNum = True
            if "verseNum" in classes:
                self.in_verseNum = True
            if "chapterNum" in classes:
                self.in_chapterNum = True

    def handle_endtag(self, tag):
        if tag == "p" and self.pid is not None and self.found:
            self.found = False
        elif tag in ("span", "sup"):
            self.in_parNum = False
            self.in_verseNum = False
            self.in_chapterNum = False

    def handle_data(self, data):
        if (self.found
                and not self.in_parNum
                and not self.in_verseNum
                and not self.in_chapterNum):
            data = data.replace("·", "")
            if data:
                self.text += data


def extract_paragraph_tokens(html: str, data_pid: int) -> list[str]:
    """Return the list of tokens for a paragraph, by data_pid.

    Uses the canonical JW Library extractor + tokenizer pipeline. The returned
    indices are exactly what BlockRange.StartToken / EndToken expect.
    """
    parser = _PExtractor(pid=data_pid)
    parser.feed(html)
    if not parser.text:
        raise ValueError(f"data-pid {data_pid} not found in article HTML")
    return jw_tokenize(parser.text)


def extract_verse_tokens(html: str, book: int, chapter: int, verse: int) -> list[str]:
    """Return the list of tokens for a Bible verse, by (book, chapter, verse).

    The WOL chapter HTML wraps each verse in <span id="vBOOK-CH-VS-N" class="v">
    sub-segments. The verse number is rendered as <a class="vl vx vp">N </a> at
    the start of segment 1; we strip that link so it doesn't contribute tokens
    (parallel to PExtractor skipping <span class="verseNum">).

    Cross-reference symbols (+) and footnote text are left in — JW Library
    counts those as tokens (per the canonical regex).
    """
    seg_pat = re.compile(
        rf'<span\s+id="v{book}-{chapter}-{verse}-\d+"\s+class="v">(.*?)</span>',
        re.DOTALL,
    )
    segs = seg_pat.findall(html)
    if not segs:
        raise ValueError(f"Bible verse v{book}-{chapter}-{verse}-* not found in chapter HTML")
    combined = " ".join(segs)
    # Strip the verse-number link (vl class) — JW Library treats it like
    # <span class="verseNum"> in PExtractor and skips it entirely.
    combined = re.sub(r'<a[^>]*class="[^"]*\bvl\b[^"]*"[^>]*>.*?</a>', ' ',
                      combined, flags=re.DOTALL)
    parser = _PExtractor()
    parser.feed(combined)
    return jw_tokenize(parser.text)


_WORD_TOKEN_RE = re.compile(r"\w")


def _is_word_token(t: str) -> bool:
    """True iff token contains any word-character (so 'art' yes, ',' no)."""
    return bool(_WORD_TOKEN_RE.search(t))


def find_token_range(tokens: list[str], phrase: str) -> tuple[int, int]:
    """Locate a phrase in a token list.

    Tokenizes the phrase with the same rule as the source, then matches:
        1. Strict (case-sensitive) sublist match.
        2. Case-insensitive sublist match.
        3. Punctuation-skipping match — phrase word-tokens align to source
           word-tokens; punctuation tokens in the source (footnote markers
           '*', cross-reference '+', commas, etc.) that fall between phrase
           words are absorbed into the returned range. Mirrors how JW Library
           expands a drag-selection over inline footnote/xref symbols.
    Returns (start_token, end_token) — 0-indexed, inclusive.
    Raises ValueError if not found.
    """
    phrase_tokens = jw_tokenize(phrase)
    n = len(phrase_tokens)
    if n == 0:
        raise ValueError("empty phrase")
    if n > len(tokens):
        raise ValueError(
            f"phrase has {n} tokens but source has only {len(tokens)}: {phrase!r}"
        )

    # 1. Strict
    for i in range(len(tokens) - n + 1):
        if tokens[i:i + n] == phrase_tokens:
            return (i, i + n - 1)

    # 2. Case-insensitive
    lt = [t.lower() for t in tokens]
    lp = [t.lower() for t in phrase_tokens]
    for i in range(len(lt) - n + 1):
        if lt[i:i + n] == lp:
            return (i, i + n - 1)

    # 3. Punctuation-skipping (case-insensitive). Phrase word-tokens must
    #    align with source word-tokens; punctuation in source between them
    #    is allowed and included in the returned range.
    phrase_word_tokens = [(i, t.lower()) for i, t in enumerate(phrase_tokens)
                          if _is_word_token(t)]
    if phrase_word_tokens:
        # Phrase punctuation positions must still match in the source — but
        # we only loosely require them, so simplest: match only on word tokens.
        first_w = phrase_word_tokens[0][1]
        for start in range(len(tokens)):
            if not _is_word_token(tokens[start]) or tokens[start].lower() != first_w:
                continue
            j = start
            pi = 0
            last_word_match = start
            ok = True
            while pi < len(phrase_word_tokens) and j < len(tokens):
                tok = tokens[j]
                if _is_word_token(tok):
                    if tok.lower() == phrase_word_tokens[pi][1]:
                        last_word_match = j
                        pi += 1
                        j += 1
                    else:
                        ok = False
                        break
                else:
                    # punctuation in source — skip over (it'll fall inside the
                    # returned range as long as it's between phrase word tokens)
                    j += 1
            if ok and pi == len(phrase_word_tokens):
                return (start, last_word_match)

    raise ValueError(
        f"phrase not found: {phrase!r}\n"
        f"  phrase tokens: {phrase_tokens}\n"
        f"  source tokens: {' '.join(tokens[:40])}{'…' if len(tokens) > 40 else ''}"
    )


def insert_underline(
    conn: sqlite3.Connection,
    location_id: int,
    data_pid: int,
    color: str,
    start_token: int,
    end_token: int,
    block_type: int = 1,
) -> tuple[int, int]:
    """Insert a UserMark + BlockRange pair. Returns (UserMarkId, BlockRangeId)."""
    color_index = COLOR_INDEX[color.lower()]
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO UserMark (ColorIndex, LocationId, StyleIndex, UserMarkGuid, Version)
        VALUES (?, ?, ?, ?, ?)
        """,
        (color_index, location_id, USERMARK_STYLE_UNDERLINE,
         str(uuid.uuid4()).upper(), USERMARK_VERSION),
    )
    user_mark_id = cur.lastrowid
    cur.execute(
        """
        INSERT INTO BlockRange (BlockType, Identifier, StartToken, EndToken, UserMarkId)
        VALUES (?, ?, ?, ?, ?)
        """,
        (block_type, data_pid, start_token, end_token, user_mark_id),
    )
    return (user_mark_id, cur.lastrowid)


def existing_underline_anchors(conn: sqlite3.Connection, location_id: int) -> set[tuple[int, int, int, int]]:
    """Set of (BlockType, Identifier, StartToken, EndToken) already highlighted at this Location."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT br.BlockType, br.Identifier, br.StartToken, br.EndToken
        FROM BlockRange br
        JOIN UserMark u ON u.UserMarkId = br.UserMarkId
        WHERE u.LocationId = ? AND br.StartToken IS NOT NULL
        """,
        (location_id,),
    )
    return {tuple(row) for row in cur.fetchall()}


def insert_underlines_for_note(
    conn: sqlite3.Connection,
    location_id: int,
    identifier: int,
    block_type: int,
    underlines: list[dict],
    article_html: str,
    existing: set[tuple[int, int, int, int]],
    *,
    bible_book: int | None = None,
    bible_chapter: int | None = None,
) -> tuple[list[tuple[int, int]], list[tuple[int, int, int, int]], list[str]]:
    """Insert all underlines for one paragraph or verse. Returns (inserted, skipped, errors).

    For paragraph mode (block_type=1), `identifier` is the paragraph's data-pid.
    For Bible mode (block_type=2), `identifier` is the verse number; `bible_book`
    and `bible_chapter` must be provided so the verse text can be located in the
    chapter HTML.
    """
    if not underlines:
        return ([], [], [])
    if block_type == 2:
        if bible_book is None or bible_chapter is None:
            return ([], [], [f"verse {identifier}: Bible book/chapter required for verse underlines"])
        try:
            tokens = extract_verse_tokens(article_html, bible_book, bible_chapter, identifier)
        except ValueError as e:
            return ([], [], [f"verse {identifier}: {e}"])
    else:
        tokens = extract_paragraph_tokens(article_html, identifier)
    inserted: list[tuple[int, int]] = []
    skipped: list[tuple[int, int, int, int]] = []
    errors: list[str] = []
    label = f"verse {identifier}" if block_type == 2 else f"data_pid={identifier}"
    for u in underlines:
        try:
            start, end = find_token_range(tokens, u["phrase"])
        except ValueError as e:
            errors.append(f"{label}: {e}")
            continue
        anchor = (block_type, identifier, start, end)
        if anchor in existing:
            skipped.append(anchor)
            continue
        ids = insert_underline(conn, location_id, identifier, u.get("color", "yellow"),
                               start, end, block_type)
        inserted.append(ids)
        existing.add(anchor)
    return (inserted, skipped, errors)


def ensure_location(
    conn: sqlite3.Connection,
    key_symbol: str,
    *,
    issue: int | None = None,
    document_id: int | None = None,
    book: int | None = None,
    chapter: int | None = None,
    title_contains: str | None = None,
) -> tuple[dict, bool]:
    """Look up Location, or create one if missing. Returns (loc_dict, created_bool).

    JW Library only writes a Location row when a publication item is OPENED on
    a device. This function inserts a missing Location row using the metadata
    from the comments JSON, so the tool can inject notes/highlights into
    articles the user hasn't tapped into yet (provided the publication itself
    is downloaded — JW Library still needs the source content to render).

    Auto-created rows are minimal: KeySymbol + (IssueTagNumber + DocumentId)
    OR (BookNumber + ChapterNumber); MepsLanguage=0; Type inferred from
    KeySymbol (1 for 'w' Watchtower, 0 for everything else).
    """
    try:
        loc = find_location(
            conn, key_symbol,
            issue=issue, document_id=document_id, book=book, chapter=chapter,
            title_contains=title_contains,
        )
        return (loc, False)
    except SystemExit:
        pass

    # Per Location table CHECK constraints (verified against userData.db schema, May 2026):
    #   Type = 0  → publication article (DocumentId set) OR Bible chapter (Book+Chapter set)
    #   Type = 1  → whole Bible book (rare; not what we inject against)
    #   Type = 2/3 → mediator audio/video
    # We always use Type=0 for both modes — Watchtower articles, mwb workbook items,
    # CBS book chapters, and Bible chapters are all Type=0.
    cur = conn.cursor()
    if book is not None and chapter is not None:
        cur.execute(
            """INSERT INTO Location
               (KeySymbol, BookNumber, ChapterNumber, IssueTagNumber, MepsLanguage, Type)
               VALUES (?, ?, ?, 0, 0, 0)""",
            (key_symbol, book, chapter),
        )
    else:
        cur.execute(
            """INSERT INTO Location
               (KeySymbol, IssueTagNumber, DocumentId, MepsLanguage, Type)
               VALUES (?, ?, ?, 0, 0)""",
            (key_symbol, issue or 0, document_id),
        )
    new_id = cur.lastrowid
    return (
        {
            "LocationId": new_id,
            "KeySymbol": key_symbol,
            "DocumentId": document_id,
            "BookNumber": book,
            "ChapterNumber": chapter,
            "Title": None,
        },
        True,
    )


def find_location(
    conn: sqlite3.Connection,
    key_symbol: str,
    *,
    issue: int | None = None,
    document_id: int | None = None,
    book: int | None = None,
    chapter: int | None = None,
    title_contains: str | None = None,
) -> dict:
    """Locate a Location row by either paragraph mode or Bible-verse mode.

    Paragraph mode: pass `issue` (and optionally `document_id` / `title_contains`).
    Bible mode: pass `book` and `chapter` (KeySymbol typically 'nwtsty').
    """
    cur = conn.cursor()

    if book is not None and chapter is not None:
        cur.execute(
            """
            SELECT LocationId, BookNumber, ChapterNumber, MepsLanguage, Type, Title, KeySymbol
            FROM Location
            WHERE KeySymbol = ? AND BookNumber = ? AND ChapterNumber = ?
            """,
            (key_symbol, book, chapter),
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        if not rows:
            sys.exit(
                f"No Bible Location for KeySymbol={key_symbol!r} BookNumber={book} ChapterNumber={chapter}. "
                "Open the chapter once in JW Library, then export a fresh backup."
            )
        # Multiple Locations on the same chapter is rare but happens (different MepsLanguages).
        # Prefer one with MepsLanguage=0 (English default) when ambiguous.
        if len(rows) > 1:
            preferred = [r for r in rows if r.get("MepsLanguage") == 0]
            if preferred:
                rows = preferred
        return rows[0]

    if issue is None:
        sys.exit("find_location requires either (issue, ...) or (book, chapter)")

    cur.execute(
        """
        SELECT LocationId, DocumentId, Title, MepsLanguage, Type, KeySymbol
        FROM Location
        WHERE KeySymbol = ? AND IssueTagNumber = ?
        """,
        (key_symbol, issue),
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    if not rows:
        sys.exit(
            f"No Location rows for KeySymbol={key_symbol!r} IssueTagNumber={issue}. "
            "Open the article once on a JW Library device, then export a fresh backup."
        )

    if document_id is not None:
        rows = [r for r in rows if r["DocumentId"] == document_id]
    elif title_contains:
        needle = title_contains.lower()
        rows = [r for r in rows if r["Title"] and needle in r["Title"].lower()]

    if len(rows) == 0:
        sys.exit("No Location row matched the document filter.")
    if len(rows) > 1:
        print(
            "Multiple candidate articles matched. Narrow with --document-id or --title-contains:",
            file=sys.stderr,
        )
        for r in rows:
            print(f"  DocumentId={r['DocumentId']:>5}  Title={r['Title']!r}", file=sys.stderr)
        sys.exit(2)
    return rows[0]


def existing_anchors(conn: sqlite3.Connection, location_id: int) -> set[tuple[int, int]]:
    """Set of (BlockType, BlockIdentifier) pairs already noted at this Location."""
    cur = conn.cursor()
    cur.execute(
        "SELECT BlockType, BlockIdentifier FROM Note "
        "WHERE LocationId = ? AND BlockIdentifier IS NOT NULL",
        (location_id,),
    )
    return {(row[0], row[1]) for row in cur.fetchall()}


def insert_notes(
    conn: sqlite3.Connection,
    location_id: int,
    notes: list[dict],
    default_block_type: int,
) -> tuple[list[int], list[tuple[int, int]]]:
    """Insert Note rows for entries with content. Underline-only entries are skipped here."""
    existing = existing_anchors(conn, location_id)
    cur = conn.cursor()
    now = now_iso()
    inserted: list[int] = []
    skipped: list[tuple[int, int]] = []
    for n in notes:
        content = n.get("content")
        if not (isinstance(content, str) and content.strip()):
            continue  # underline-only entry, no Note row to write
        bt, ident = _resolve_anchor(n, default_block_type)
        if (bt, ident) in existing:
            skipped.append((bt, ident))
            continue
        cur.execute(
            """
            INSERT INTO Note
                (Guid, UserMarkId, LocationId, Title, Content,
                 LastModified, Created, BlockType, BlockIdentifier)
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                location_id,
                n.get("title"),
                content,
                now,
                now,
                bt,
                ident,
            ),
        )
        inserted.append(cur.lastrowid)
    return inserted, skipped


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def bump_last_modified(conn: sqlite3.Connection) -> None:
    """Bump the global LastModified timestamp inside userData.db.

    The LastModified table is a single TEXT row that JW Library uses to decide
    whether an imported backup's data is newer than the device's current data.
    Without bumping this, JW Library silently drops imported rows that would
    conflict with newer device-side state — even when the rows themselves are
    valid and would otherwise merge cleanly.

    Discovered the hard way: a v1 injection merged because the device had no
    later activity, but a v2 injection against a fresher backup got dropped
    because Tyler had tapped new articles between export and import — pushing
    the device's effective LastModified ahead of my (un-bumped) backup's.
    """
    cur = conn.cursor()
    cur.execute("UPDATE LastModified SET LastModified = ?", (now_iso(),))


def update_manifest(manifest_path: Path, db_path: Path) -> None:
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)
    backup = manifest.get("userDataBackup")
    if not backup:
        sys.exit("manifest.json has no userDataBackup section — not a JW Library backup.")
    backup["hash"] = sha256_file(db_path)
    backup["lastModifiedDate"] = now_iso()
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def repackage(work_dir: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in sorted(work_dir.rglob("*")):
            if entry.is_file():
                zf.write(entry, entry.relative_to(work_dir))
    tmp.replace(output)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Inject Study Notes + colored underlines into a .jwlibrary backup."
    )
    p.add_argument("--input", required=True, type=Path, help="source .jwlibrary file")
    p.add_argument("--output", required=True, type=Path, help="destination .jwlibrary file")
    p.add_argument("--comments", required=True, type=Path,
                   help="JSON file describing the notes and underlines")
    p.add_argument("--document-id", type=int, default=None, help="exact DocumentId to target")
    p.add_argument("--title-contains", type=str, default=None,
                   help="substring match on Location.Title")
    p.add_argument("--article-html", type=Path, default=None,
                   help="local cached WOL article HTML; default fetches from wol.jw.org")
    p.add_argument("--verify", action="store_true",
                   help="after writing output, simulate JW Library's merge to confirm "
                        "all new rows survive (uses verify_merge.py)")
    args = p.parse_args()

    if not args.input.exists():
        sys.exit(f"input not found: {args.input}")

    spec = load_comments(args.comments)
    is_bible_mode = "book" in spec and "chapter" in spec
    key_symbol = spec.get("key_symbol", "nwtsty" if is_bible_mode else "w")
    default_bt = spec.get("default_block_type", 2 if is_bible_mode else 1)

    issue = int(spec["issue"]) if "issue" in spec else None
    document_id = args.document_id if args.document_id is not None else spec.get("document_id")
    title_contains = args.title_contains or spec.get("title_contains")
    book = spec.get("book")
    chapter = spec.get("chapter")

    needs_article = any(n.get("underlines") for n in spec["notes"])
    article_html: str | None = None
    if needs_article:
        if args.article_html:
            article_html = args.article_html.read_text(encoding="utf-8")
        elif is_bible_mode:
            print(f"Fetching WOL Bible chapter for {key_symbol} {book}/{chapter}…")
            article_html = fetch_wol_bible_chapter(book, chapter, key_symbol)
        elif document_id:
            print(f"Fetching WOL article for DocumentId={document_id}…")
            article_html = fetch_wol_article(document_id, key_symbol)
        else:
            sys.exit("comments include underlines but no document_id/book+chapter or --article-html provided")

    with tempfile.TemporaryDirectory(prefix="jwl_notes_") as td:
        work = Path(td)
        with zipfile.ZipFile(args.input, "r") as zf:
            zf.extractall(work)

        db_path = work / "userData.db"
        manifest_path = work / "manifest.json"
        if not db_path.exists() or not manifest_path.exists():
            sys.exit("input is not a valid .jwlibrary backup (missing userData.db or manifest.json).")

        conn = sqlite3.connect(db_path)
        try:
            if is_bible_mode:
                loc, created = ensure_location(conn, key_symbol, book=book, chapter=chapter)
                created_tag = " [auto-created]" if created else ""
                print(
                    f"Targeting Bible Location: LocationId={loc['LocationId']} "
                    f"KeySymbol={key_symbol!r} Book={book} Chapter={chapter}{created_tag}"
                )
            else:
                loc, created = ensure_location(
                    conn, key_symbol,
                    issue=issue, document_id=document_id, title_contains=title_contains,
                )
                created_tag = " [auto-created]" if created else ""
                print(
                    f"Targeting LocationId={loc['LocationId']} "
                    f"DocumentId={loc.get('DocumentId')} Title={loc.get('Title')!r}{created_tag}"
                )
            inserted_notes, skipped_notes = insert_notes(
                conn, loc["LocationId"], spec["notes"], default_bt
            )

            inserted_underlines: list[tuple[int, int]] = []
            skipped_underlines: list[tuple[int, int, int, int]] = []
            underline_errors: list[str] = []
            if article_html is not None:
                existing_uls = existing_underline_anchors(conn, loc["LocationId"])
                for n in spec["notes"]:
                    underlines = n.get("underlines") or []
                    if not underlines:
                        continue
                    bt, ident = _resolve_anchor(n, default_bt)
                    ins, skp, errs = insert_underlines_for_note(
                        conn, loc["LocationId"], ident, bt,
                        underlines, article_html, existing_uls,
                        bible_book=book, bible_chapter=chapter,
                    )
                    inserted_underlines.extend(ins)
                    skipped_underlines.extend(skp)
                    underline_errors.extend(errs)

            # Bump the global LastModified timestamp so JW Library treats this
            # imported backup as "newer" than the current device state.
            if inserted_notes or inserted_underlines or created:
                bump_last_modified(conn)

            conn.commit()
        finally:
            conn.close()

        if skipped_notes:
            print(f"Skipped notes (already present): {skipped_notes}")
        print(f"Inserted {len(inserted_notes)} note(s); NoteIds={inserted_notes}")

        if article_html is not None:
            if skipped_underlines:
                print(f"Skipped underlines (already present): {len(skipped_underlines)}")
            print(f"Inserted {len(inserted_underlines)} underline(s)")
            for err in underline_errors:
                print(f"  ⚠ {err}", file=sys.stderr)

        wrote_anything = bool(inserted_notes) or bool(inserted_underlines)
        if not wrote_anything:
            sys.exit("Nothing new to write. No output produced.")

        update_manifest(manifest_path, db_path)
        repackage(work, args.output)
        print(f"Wrote {args.output}")

    if args.verify:
        print("\n--- Verifying merge ---")
        try:
            from verify_merge import verify
        except ImportError:
            sys.path.insert(0, str(Path(__file__).parent))
            from verify_merge import verify
        if not verify(args.input, args.output):
            print("\nVerification FAILED. The output backup has rows that JW Library "
                  "would silently drop on Restore. Do not import this file as-is.",
                  file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
