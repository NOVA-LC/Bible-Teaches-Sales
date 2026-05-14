"""research.py — pull real study-material depth from WOL for one paragraph.

Operator's framing: "imagine you spend an hour to properly study each paragraph
of everything — all the scripture's reference material, deep research, like
everything — and you build comments and underlines as if that were true."

For each cited scripture in a paragraph, this module fetches:
  - The verse's NWT 2013 text (verbatim)
  - The 3 verses immediately before and 3 immediately after (narrative context)
  - The cross-reference targets (the actual NWT text of every `+` verse)
  - The footnote text (alternate translations, clarifying notes)

The result is a structured `DeepBrief` that a research-synth worker can read
to find THE gem the article didn't surface. The drafter then receives the
synthesized gem alongside the paragraph and produces a comment whose substance
is the gem, not the paragraph's surface argument.

This is the bridge between "AI saw the paragraph" and "AI did an hour of
study on the paragraph." It's not Insight-on-the-Scriptures lookup or
Hebrew/Greek root tracing yet — those come later. But it's a 10x research-
depth jump over what the worker had before.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterator

# Map NWT book name → book number. Covers full names + standard abbreviations
# the article paragraphs use. NWT 2013 uses these citations natively.
_NWT_BOOK_NUMS: dict[str, int] = {}
_BOOKS = [
    (1, ["Genesis", "Gen", "Ge"]),
    (2, ["Exodus", "Ex", "Exod"]),
    (3, ["Leviticus", "Lev", "Le"]),
    (4, ["Numbers", "Num", "Nu"]),
    (5, ["Deuteronomy", "Deut", "De"]),
    (6, ["Joshua", "Josh", "Jos"]),
    (7, ["Judges", "Judg", "Jg"]),
    (8, ["Ruth", "Ru"]),
    (9, ["1 Samuel", "1 Sam", "1Sa"]),
    (10, ["2 Samuel", "2 Sam", "2Sa"]),
    (11, ["1 Kings", "1 Ki", "1Ki"]),
    (12, ["2 Kings", "2 Ki", "2Ki"]),
    (13, ["1 Chronicles", "1 Chron", "1Ch"]),
    (14, ["2 Chronicles", "2 Chron", "2Ch"]),
    (15, ["Ezra", "Ezr"]),
    (16, ["Nehemiah", "Neh", "Ne"]),
    (17, ["Esther", "Esth", "Es"]),
    (18, ["Job"]),
    (19, ["Psalm", "Psalms", "Ps"]),
    (20, ["Proverbs", "Prov", "Pr"]),
    (21, ["Ecclesiastes", "Eccl", "Ec"]),
    (22, ["Song of Solomon", "Song of Sol", "Ca", "Sg"]),
    (23, ["Isaiah", "Isa"]),
    (24, ["Jeremiah", "Jer"]),
    (25, ["Lamentations", "Lam", "La"]),
    (26, ["Ezekiel", "Ezek", "Eze"]),
    (27, ["Daniel", "Dan", "Da"]),
    (28, ["Hosea", "Hos", "Ho"]),
    (29, ["Joel", "Joe"]),
    (30, ["Amos", "Am"]),
    (31, ["Obadiah", "Obad", "Ob"]),
    (32, ["Jonah", "Jon"]),
    (33, ["Micah", "Mic", "Mi"]),
    (34, ["Nahum", "Nah", "Na"]),
    (35, ["Habakkuk", "Hab"]),
    (36, ["Zephaniah", "Zeph", "Zep"]),
    (37, ["Haggai", "Hag"]),
    (38, ["Zechariah", "Zech", "Zec"]),
    (39, ["Malachi", "Mal"]),
    (40, ["Matthew", "Matt", "Mt"]),
    (41, ["Mark", "Mk"]),
    (42, ["Luke", "Lu", "Lk"]),
    (43, ["John", "Joh", "Jn"]),
    (44, ["Acts", "Ac"]),
    (45, ["Romans", "Rom", "Ro"]),
    (46, ["1 Corinthians", "1 Cor", "1Co"]),
    (47, ["2 Corinthians", "2 Cor", "2Co"]),
    (48, ["Galatians", "Gal"]),
    (49, ["Ephesians", "Eph"]),
    (50, ["Philippians", "Phil"]),
    (51, ["Colossians", "Col"]),
    (52, ["1 Thessalonians", "1 Thess", "1Th"]),
    (53, ["2 Thessalonians", "2 Thess", "2Th"]),
    (54, ["1 Timothy", "1 Tim", "1Ti"]),
    (55, ["2 Timothy", "2 Tim", "2Ti"]),
    (56, ["Titus", "Tit"]),
    (57, ["Philemon", "Phlm", "Phm"]),
    (58, ["Hebrews", "Heb"]),
    (59, ["James", "Jas"]),
    (60, ["1 Peter", "1 Pet", "1Pe"]),
    (61, ["2 Peter", "2 Pet", "2Pe"]),
    (62, ["1 John", "1 Joh", "1Jo"]),
    (63, ["2 John", "2 Joh", "2Jo"]),
    (64, ["3 John", "3 Joh", "3Jo"]),
    (65, ["Jude"]),
    (66, ["Revelation", "Rev", "Re"]),
]
for num, names in _BOOKS:
    for n in names:
        _NWT_BOOK_NUMS[n.lower()] = num

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)


def _book_to_num(name: str) -> int | None:
    return _NWT_BOOK_NUMS.get(name.lower().strip())


# ---------------------------------------------------------------------------
# Citation parsing
# ---------------------------------------------------------------------------

@dataclass
class Citation:
    book_name: str
    book_num: int
    chapter: int
    verses: list[int]

    def canonical(self) -> str:
        if len(self.verses) == 1:
            return f"{self.book_name} {self.chapter}:{self.verses[0]}"
        return f"{self.book_name} {self.chapter}:{self.verses[0]}-{self.verses[-1]}"


_CITATION_RE = re.compile(
    r"\b(\d?\s?[A-Z][a-zA-Z]+\.?)\s+(\d+):(\d+(?:[,\s\-–]+\s*\d+)*)"
)


def parse_citations(text: str) -> list[Citation]:
    """Pull citations like 'Job 1:6, 7' or '2 Tim. 4:2' or '1 Kings 3:5-13'."""
    out = []
    for m in _CITATION_RE.finditer(text):
        raw_book = m.group(1).rstrip(".").strip()
        book_num = _book_to_num(raw_book)
        if not book_num:
            continue
        try:
            chap = int(m.group(2))
        except ValueError:
            continue
        verses: list[int] = []
        for tok in re.split(r"[,\s]+", m.group(3).strip()):
            tok = tok.strip()
            if not tok:
                continue
            if "-" in tok or "–" in tok:
                a, b = re.split(r"[-–]", tok, 1)
                try:
                    a_i, b_i = int(a.strip()), int(b.strip())
                    verses.extend(range(a_i, b_i + 1))
                except ValueError:
                    pass
            else:
                try:
                    verses.append(int(tok))
                except ValueError:
                    pass
        if verses:
            out.append(Citation(raw_book, book_num, chap, verses))
    return out


# ---------------------------------------------------------------------------
# WOL fetch + cache
# ---------------------------------------------------------------------------

CACHE_DIR = Path.home() / ".cache" / "jwl_research"


def _fetch(url: str, timeout: int = 30) -> str:
    """HTTP GET with disk cache + curl primary (urllib fallback). WOL's
    CDN hangs reliably on Python urllib for some URL patterns; curl on
    the same URL completes. Same pattern lives in jwl_notes._http_get,
    agent/discover_week._fetch, agent/comment_agent._fetch_cached."""
    import subprocess
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^A-Za-z0-9]+", "_", url)[:200]
    cache_path = CACHE_DIR / f"{key}.html"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    html: str | None = None
    try:
        proc = subprocess.run(
            ["curl", "-fsSL", "--max-time", str(timeout),
             "-A", DEFAULT_UA, url],
            capture_output=True, timeout=timeout + 5,
        )
        if proc.returncode == 0 and proc.stdout:
            html = proc.stdout.decode("utf-8", errors="replace")
    except (FileNotFoundError, Exception):
        pass
    if html is None:
        req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    cache_path.write_text(html, encoding="utf-8")
    return html


def fetch_chapter_html(book_num: int, chapter: int) -> str:
    url = f"https://wol.jw.org/en/wol/b/r1/lp-e/nwtsty/{book_num}/{chapter}"
    return _fetch(url)


# ---------------------------------------------------------------------------
# Verse / footnote / cross-ref extraction
# ---------------------------------------------------------------------------

_VERSE_SEG_RE = re.compile(
    r'<span\s+id="v(\d+)-(\d+)-(\d+)-\d+"\s+class="v">(.*?)</span>',
    re.DOTALL,
)


def _strip_inline_tags_keep_text(html_fragment: str) -> str:
    """Strip HTML tags but keep the text. Preserves cross-ref '+' and footnote
    markers as text so we can detect them per-verse."""
    # Drop verse-number link `<a class="vl vx vp">N </a>`
    s = re.sub(r'<a[^>]*class="[^"]*\bvl\b[^"]*"[^>]*>.*?</a>', " ", html_fragment, flags=re.DOTALL)
    # Replace cross-ref + and footnote * with marker tokens we can find later
    s = re.sub(r'<a[^>]*class="[^"]*\bb\b[^"]*"[^>]*>.*?</a>', " [XREF] ", s, flags=re.DOTALL)
    s = re.sub(r'<a[^>]*class="[^"]*\bfn\b[^"]*"[^>]*>.*?</a>', " [FN] ", s, flags=re.DOTALL)
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace(" ", " ").replace("·", "")
           .replace("&nbsp;", " ").replace("&amp;", "&")
           .replace("&#8217;", "'").replace("&#8220;", '"').replace("&#8221;", '"')
           .replace("&#8212;", "—").replace("&#8211;", "–"))
    return re.sub(r"\s+", " ", s).strip()


def extract_verse_text(chapter_html: str, book: int, chapter: int, verse: int) -> str:
    """Return the verse's NWT 2013 text (markers preserved as [XREF]/[FN] tokens)."""
    parts = []
    for m in _VERSE_SEG_RE.finditer(chapter_html):
        b, c, v, body = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        if b == book and c == chapter and v == verse:
            parts.append(_strip_inline_tags_keep_text(body))
    return " ".join(parts).strip()


def _extract_anchors_with_class(body: str, class_token: str) -> list[str]:
    """Find <a> tags inside `body` whose class attribute contains `class_token`
    (as a whitespace-separated word). Returns hrefs in source order, dedup.
    Tolerant to attribute ordering: href may appear before OR after class.
    """
    urls: list[str] = []
    # Pull every <a ...> ... </a>; check class + extract href regardless of order
    for am in re.finditer(r'<a\s+([^>]+)>', body):
        attrs = am.group(1)
        cls = re.search(r'class="([^"]*)"', attrs)
        href = re.search(r'href="([^"]+)"', attrs)
        if not (cls and href):
            continue
        if class_token in cls.group(1).split():
            h = href.group(1)
            if h not in urls:
                urls.append(h)
    return urls


def extract_verse_xref_urls(chapter_html: str, book: int, chapter: int, verse: int) -> list[str]:
    """Return relative URLs of cross-references appearing in this verse."""
    urls: list[str] = []
    for m in _VERSE_SEG_RE.finditer(chapter_html):
        b, c, v, body = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        if b == book and c == chapter and v == verse:
            for h in _extract_anchors_with_class(body, "b"):
                if h not in urls:
                    urls.append(h)
    return urls


def extract_verse_footnote_urls(chapter_html: str, book: int, chapter: int, verse: int) -> list[str]:
    """Return relative URLs of footnotes appearing in this verse."""
    urls: list[str] = []
    for m in _VERSE_SEG_RE.finditer(chapter_html):
        b, c, v, body = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        if b == book and c == chapter and v == verse:
            for h in _extract_anchors_with_class(body, "fn"):
                if h not in urls:
                    urls.append(h)
    return urls


# ---------------------------------------------------------------------------
# Cross-ref / footnote target fetching
# ---------------------------------------------------------------------------

_BOOK_NUM_TO_NAME = {num: names[0] for num, names in _BOOKS}


def fetch_xref_targets(xref_url: str) -> list[dict]:
    """Fetch a cross-reference popover URL and parse the target verses + text.

    Cross-reference popovers use the same `<span id="v{book}-{chap}-{verse}-{sub}" class="v">`
    structure as chapter pages. We extract every verse-segment, group by
    (book, chap, verse), and concatenate the sub-segments.

    Returns a list of {"citation": "Isaiah 51:17", "text": "Awake! Awake! ..."}
    """
    full = f"https://wol.jw.org{xref_url}" if xref_url.startswith("/") else xref_url
    try:
        html = _fetch(full)
    except Exception:
        return []
    # Group verse sub-segments by (book, chap, verse)
    parts: dict[tuple[int, int, int], list[str]] = {}
    order: list[tuple[int, int, int]] = []
    for m in _VERSE_SEG_RE.finditer(html):
        b, c, v, body = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        key = (b, c, v)
        if key not in parts:
            parts[key] = []
            order.append(key)
        parts[key].append(_strip_inline_tags_keep_text(body))
    out: list[dict] = []
    for key in order:
        b, c, v = key
        book_name = _BOOK_NUM_TO_NAME.get(b, f"Book{b}")
        out.append({
            "citation": f"{book_name} {c}:{v}",
            "text": " ".join(parts[key]).strip()[:400],
        })
    return out


def fetch_footnote_text(fn_url: str) -> str:
    """Fetch a footnote popover URL and return the footnote text."""
    full = f"https://wol.jw.org{fn_url}" if fn_url.startswith("/") else fn_url
    try:
        html = _fetch(full)
    except Exception:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    # Footnote popovers typically show "Or ..." / "Lit., ..." / etc.
    # Return up to 500 chars of the body
    return text[:500]


# ---------------------------------------------------------------------------
# Deep brief assembly
# ---------------------------------------------------------------------------

@dataclass
class VerseStudy:
    citation: str           # "Job 1:6"
    text: str               # NWT verbatim with [XREF]/[FN] markers preserved
    context_before: list[dict] = field(default_factory=list)   # [{"citation": "Job 1:5", "text": "..."}, ...]
    context_after: list[dict] = field(default_factory=list)
    cross_refs: list[dict] = field(default_factory=list)       # [{"citation": "...", "text": "..."}, ...]
    footnotes: list[str] = field(default_factory=list)


@dataclass
class DeepBrief:
    paragraph_text: str
    cited_studies: list[VerseStudy] = field(default_factory=list)


def fetch_deep_brief(
    paragraph_text: str,
    explicit_citations: list[str] | None = None,
    context_window: int = 3,
    max_xrefs_per_verse: int = 5,
    max_footnotes_per_verse: int = 3,
) -> DeepBrief:
    """Pull a per-paragraph deep brief from WOL.

    `explicit_citations` overrides citation parsing. Use this when the
    paragraph object already has a list of cited scriptures from the
    article HTML (avoids re-parsing the paragraph text)."""
    brief = DeepBrief(paragraph_text=paragraph_text)

    if explicit_citations:
        cites: list[Citation] = []
        for c in explicit_citations:
            cites.extend(parse_citations(c))
    else:
        cites = parse_citations(paragraph_text)

    seen: set[tuple[int, int, int]] = set()
    for cite in cites:
        chap_html = fetch_chapter_html(cite.book_num, cite.chapter)
        for v in cite.verses:
            key = (cite.book_num, cite.chapter, v)
            if key in seen:
                continue
            seen.add(key)
            text = extract_verse_text(chap_html, cite.book_num, cite.chapter, v)
            if not text:
                continue
            study = VerseStudy(citation=f"{cite.book_name} {cite.chapter}:{v}", text=text)
            # Surrounding context
            for off in range(-context_window, 0):
                ctx = extract_verse_text(chap_html, cite.book_num, cite.chapter, v + off)
                if ctx:
                    study.context_before.append({"citation": f"{cite.book_name} {cite.chapter}:{v+off}", "text": ctx})
            for off in range(1, context_window + 1):
                ctx = extract_verse_text(chap_html, cite.book_num, cite.chapter, v + off)
                if ctx:
                    study.context_after.append({"citation": f"{cite.book_name} {cite.chapter}:{v+off}", "text": ctx})
            # Cross-refs
            for xurl in extract_verse_xref_urls(chap_html, cite.book_num, cite.chapter, v)[:max_xrefs_per_verse]:
                targets = fetch_xref_targets(xurl)
                study.cross_refs.extend(targets)
            # Footnotes
            for furl in extract_verse_footnote_urls(chap_html, cite.book_num, cite.chapter, v)[:max_footnotes_per_verse]:
                fn = fetch_footnote_text(furl)
                if fn:
                    study.footnotes.append(fn)
            brief.cited_studies.append(study)
    return brief


# ---------------------------------------------------------------------------
# CLI for quick inspection
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse, sys
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--citation", required=True, help="e.g., 'Job 1:6, 7' or 'Isa 60:1'")
    p.add_argument("--paragraph", default="(no paragraph text)", help="Optional paragraph context")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    brief = fetch_deep_brief(args.paragraph, explicit_citations=[args.citation])
    if args.json:
        print(json.dumps(asdict(brief), indent=2, ensure_ascii=False))
        return 0
    print(f"Citation: {args.citation}")
    print(f"Studies fetched: {len(brief.cited_studies)}")
    for vs in brief.cited_studies:
        print(f"\n  {vs.citation}: {vs.text[:150]}")
        if vs.context_before:
            print(f"    context_before: {[c['citation'] for c in vs.context_before]}")
        if vs.context_after:
            print(f"    context_after: {[c['citation'] for c in vs.context_after]}")
        if vs.cross_refs:
            print(f"    cross_refs ({len(vs.cross_refs)}):")
            for x in vs.cross_refs[:4]:
                print(f"      {x['citation']}: {x['text'][:120]}")
        if vs.footnotes:
            print(f"    footnotes: {len(vs.footnotes)}")
            for f in vs.footnotes[:2]:
                print(f"      {f[:200]}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
