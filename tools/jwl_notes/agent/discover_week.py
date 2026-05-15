"""discover_week.py — robust next-week material discovery.

For a single study-week date (any day in the JW Sun-Sat week, ISO format),
fetch the canonical WOL meetings page and parse out everything the
orchestrator needs to generate a week of prep:

  - Watchtower study article: DocumentId, title, theme scripture, issue
  - Midweek workbook week page: DocumentId
  - Bible reading: book number + chapter range
  - LAC parts: title + type ("Discussion" vs "Talk" vs "Local Needs")
  - Spiritual Gems target verses (if discoverable)

Critically: this NEVER computes DocIds by arithmetic. The "increment by 1"
rule breaks at issue boundaries (e.g., W27→W28 in 2026 jumped WT 2026368
→ 2026400). Always parse the meetings page.

Run as:
    python -m agent.discover_week --study-date 2026-05-17
    python -m agent.discover_week --iso-year 2026 --iso-week 20
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field, asdict
from html.parser import HTMLParser
from pathlib import Path

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)

# Bible book names → NWT book numbers
BIBLE_BOOK_NUMBERS = {
    "genesis": 1, "gen": 1, "exodus": 2, "ex": 2, "exod": 2,
    "leviticus": 3, "lev": 3, "numbers": 4, "num": 4,
    "deuteronomy": 5, "deut": 5, "joshua": 6, "josh": 6,
    "judges": 7, "judg": 7, "ruth": 8, "1 samuel": 9, "1 sam": 9,
    "2 samuel": 10, "2 sam": 10, "1 kings": 11, "1 ki": 11,
    "2 kings": 12, "2 ki": 12, "1 chronicles": 13, "1 chron": 13,
    "2 chronicles": 14, "2 chron": 14, "ezra": 15, "nehemiah": 16, "neh": 16,
    "esther": 17, "esth": 17, "job": 18, "psalm": 19, "psalms": 19, "ps": 19,
    "proverbs": 20, "prov": 20, "ecclesiastes": 21, "eccl": 21,
    "song of solomon": 22, "song of sol": 22, "ca": 22,
    "isaiah": 23, "isa": 23, "jeremiah": 24, "jer": 24,
    "lamentations": 25, "lam": 25, "ezekiel": 26, "ezek": 26,
    "daniel": 27, "dan": 27, "hosea": 28, "hos": 28,
    "joel": 29, "amos": 30, "obadiah": 31, "obad": 31,
    "jonah": 32, "micah": 33, "mic": 33, "nahum": 34, "nah": 34,
    "habakkuk": 35, "hab": 35, "zephaniah": 36, "zeph": 36,
    "haggai": 37, "hag": 37, "zechariah": 38, "zech": 38,
    "malachi": 39, "mal": 39, "matthew": 40, "matt": 40, "mt": 40,
    "mark": 41, "mk": 41, "luke": 42, "lu": 42, "john": 43, "joh": 43,
    "acts": 44, "ac": 44, "romans": 45, "rom": 45, "ro": 45,
    "1 corinthians": 46, "1 cor": 46, "2 corinthians": 47, "2 cor": 47,
    "galatians": 48, "gal": 48, "ephesians": 49, "eph": 49,
    "philippians": 50, "phil": 50, "colossians": 51, "col": 51,
    "1 thessalonians": 52, "1 thess": 52, "1 th": 52,
    "2 thessalonians": 53, "2 thess": 53, "2 th": 53,
    "1 timothy": 54, "1 tim": 54, "2 timothy": 55, "2 tim": 55,
    "titus": 56, "tit": 56, "philemon": 57, "phlm": 57,
    "hebrews": 58, "heb": 58, "james": 59, "jas": 59,
    "1 peter": 60, "1 pet": 60, "2 peter": 61, "2 pet": 61,
    "1 john": 62, "1 jo": 62, "2 john": 63, "2 jo": 63,
    "3 john": 64, "3 jo": 64, "jude": 65, "revelation": 66, "rev": 66,
    "re": 66,
}


# ----------------------------------------------------------------------
# Data shape
# ----------------------------------------------------------------------

@dataclass
class LACPart:
    number: int
    title: str
    is_discussion: bool          # True iff this is a Discussion-type part (worth pre-prepared notes)


@dataclass
class WeekDiscovery:
    """Everything build_week.py needs to generate a week's prep."""
    study_date: str              # ISO date inside the week (Sun preferred)
    iso_year: int
    iso_week: int
    week_label: str              # "May 11-17"
    meetings_url: str

    # Watchtower study (Sunday meeting)
    wt_document_id: int | None = None
    wt_title: str | None = None
    wt_theme_scripture: str | None = None
    wt_issue: int | None = None              # YYYYMMOO derived from DocId
    wt_url: str | None = None

    # Midweek workbook
    mwb_document_id: int | None = None
    mwb_url: str | None = None
    mwb_issue: int | None = None             # YYYYMMOO derived from DocId
    bible_reading_book: int | None = None    # NWT book number
    bible_reading_book_name: str | None = None
    bible_reading_chapter_start: int | None = None
    bible_reading_chapter_end: int | None = None

    # LAC parts (only Discussion-type produce notes)
    lac_parts: list[LACPart] = field(default_factory=list)

    # Congregation Bible Study (CBS — separate publication, usually lfb)
    cbs_publication: str | None = None       # e.g., "lfb"
    cbs_document_ids: list[int] = field(default_factory=list)  # one per lesson
    cbs_lesson_label: str | None = None      # e.g., "lessons 84-85"

    # Errors / warnings encountered during discovery
    warnings: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------
# Fetch helper
# ----------------------------------------------------------------------

def _fetch(url: str, timeout: int = 30) -> str:
    """HTTP GET. WOL's meetings + search endpoints hang reliably on Python
    urllib (curl on the same URL completes — likely a TLS keep-alive /
    chunked-transfer interaction). Try curl as primary, urllib fallback.

    Mirrors the pattern in comment_agent._fetch_cached. Article/chapter
    fetches in jwl_notes.fetch_wol_article + research.py don't hit this
    bug (different URL pattern) and stay on urllib.
    """
    import subprocess
    # Try curl first
    try:
        proc = subprocess.run(
            ["curl", "-fsSL", "--max-time", str(timeout),
             "-A", DEFAULT_UA, url],
            capture_output=True, timeout=timeout + 5,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout.decode("utf-8", errors="replace")
    except FileNotFoundError:
        pass  # curl not on PATH — fall through to urllib
    except Exception:
        pass  # network blip — fall through to urllib
    # Fallback: urllib
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ----------------------------------------------------------------------
# Issue parsing (DocId → YYYYMMOO issue tag)
# ----------------------------------------------------------------------

def _wt_issue_from_docid(docid: int) -> int | None:
    """Watchtower DocIds: 7-digit YYYY followed by 3-digit issue index.
    The issue's first article tends to be DocId YYYYNNN where NNN is in
    the 280-440 range; we can't recover the issue's month directly from
    DocId alone — but we can map by fetching the article page and reading
    the issue date. For the auto-discovery shape, return a placeholder
    based on the article's data-publication-month if discoverable.
    Fallback: caller supplies issue, or inject step uses 0."""
    return None  # caller will discover from article HTML in step below


def _parse_issue_from_wt_html(html: str) -> int | None:
    """Find the YYYYMMOO issue tag inside a Watchtower article page.
    The pages embed a `wYY Month` marker (e.g., 'w26 March') in the
    citation block — most reliable signal across the site."""
    m = re.search(
        r'\bw(\d{2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b',
        html, re.IGNORECASE,
    )
    if m:
        yy = int(m.group(1))
        full_year = 2000 + yy
        month = m.group(2).lower()
        month_num = ["", "january", "february", "march", "april", "may", "june",
                     "july", "august", "september", "october", "november", "december"
                    ].index(month)
        return int(f"{full_year}{month_num:02d}00")
    return None


def _parse_mwb_issue_from_docid(docid: int) -> int | None:
    """mwb DocIds follow 2020YY{NNN} where YY is the year tag and NNN is
    the index. We can derive YYYYMMOO from the bimonthly issue tag the
    page uses internally. Fetch and look for `mwb26 May` markers."""
    return None  # discover from page HTML instead


def _parse_mwb_issue_from_html(html: str, year_hint: int) -> int | None:
    """The mwb page header text says e.g. 'mwb26 May p. 4' — parse that."""
    m = re.search(r'mwb(\d{2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)',
                  html)
    if not m:
        return None
    yy = int(m.group(1))
    full_year = 2000 + yy
    month = m.group(2).lower()
    month_num = ["", "january","february","march","april","may","june",
                 "july","august","september","october","november","december"
                ].index(month)
    # mwb is bimonthly; the issue tag is YYYYMM00 for the FIRST month of the bimonthly,
    # but Tyler's existing mwb files use the actual month. Use the discovered month.
    return int(f"{full_year}{month_num:02d}00")


# ----------------------------------------------------------------------
# Parse Bible reading from mwb workbook page
# ----------------------------------------------------------------------

def _parse_bible_reading(mwb_html: str) -> tuple[str | None, int | None, int | None, int | None]:
    """Return (book_name, book_number, chap_start, chap_end) or all None."""
    # The page has an h2/h3-ish heading with "ISAIAH 60-61" or "GENESIS 1-3"
    m = re.search(
        r'<(?:h\d|strong)[^>]*>\s*([A-Z][A-Z\s]*?)\s+(\d+)(?:-(\d+))?\s*</(?:h\d|strong)>',
        mwb_html,
    )
    if not m:
        # Fallback: look for "Bible reading" section text
        m = re.search(
            r'Bible\s+[Rr]eading[^<]*<[^>]+>([A-Z][A-Z]+)\s+(\d+)(?:-(\d+))?',
            mwb_html,
        )
    if not m:
        return (None, None, None, None)
    raw_book = m.group(1).strip().lower()
    chap_start = int(m.group(2))
    chap_end = int(m.group(3)) if m.group(3) else chap_start
    book_num = BIBLE_BOOK_NUMBERS.get(raw_book) or BIBLE_BOOK_NUMBERS.get(raw_book.split()[0])
    if not book_num:
        # Try title-case lookup
        book_num = BIBLE_BOOK_NUMBERS.get(raw_book.title().lower())
    return (raw_book.title(), book_num, chap_start, chap_end)


# ----------------------------------------------------------------------
# Parse LAC parts from mwb workbook page
# ----------------------------------------------------------------------

class _LACSectionParser(HTMLParser):
    """Walk the mwb workbook HTML and pull the numbered LAC items.
    Each item appears as `<h3>N. Title</h3>` after a `LIVING AS CHRISTIANS`
    section marker; the discussion type appears in the metadata text below."""

    def __init__(self):
        super().__init__()
        self.in_lac = False
        self.in_strong = False
        self.in_h3 = False
        self.h3_buf = []
        self.parts: list[tuple[int, str]] = []
        self.preamble = ""

    def handle_starttag(self, tag, attrs):
        if tag == "strong":
            self.in_strong = True
            self.h3_buf = []
        if tag in ("h3", "h2"):
            self.in_h3 = True
            self.h3_buf = []

    def handle_endtag(self, tag):
        if tag == "strong" and self.in_strong:
            text = "".join(self.h3_buf).strip()
            if "LIVING AS CHRISTIANS" in text.upper():
                self.in_lac = True
            elif "CONCLUDING" in text.upper() or "CONGREGATION BIBLE STUDY" in text.upper():
                # Don't terminate on CBS — CBS is part of LAC for our purposes
                # but we DO terminate on Concluding
                if "CONCLUDING" in text.upper():
                    self.in_lac = False
            self.in_strong = False
        if tag in ("h3", "h2"):
            text = "".join(self.h3_buf).strip()
            if self.in_lac:
                m = re.match(r'^(\d+)\.\s+(.+)$', text)
                if m:
                    self.parts.append((int(m.group(1)), m.group(2)))
            if "LIVING AS CHRISTIANS" in text.upper():
                self.in_lac = True
            self.in_h3 = False

    def handle_data(self, data):
        if self.in_strong or self.in_h3:
            self.h3_buf.append(data)


def _parse_lac_parts(mwb_html: str) -> list[LACPart]:
    """Parse the LAC section. Items typically include a part number plus
    'Discussion' or 'Talk' or 'Local Needs' (which is a CO talk-style item).
    """
    p = _LACSectionParser()
    p.feed(mwb_html)
    out = []
    for num, title in p.parts:
        # Look for the part's metadata text in the surrounding HTML to determine
        # if it's a Discussion. The page has lines like "(15 min. Discussion.)"
        # or "(15 min.)" or "(10 min. Talk.)" near the item.
        part_chunk_pat = re.compile(
            rf'>{num}\.\s+{re.escape(title)}\s*<.*?(?:</p>|<h\d|<div\s+class="bodyTxt")',
            re.DOTALL,
        )
        chunk_m = part_chunk_pat.search(mwb_html)
        chunk_text = chunk_m.group(0) if chunk_m else ""
        is_disc = bool(re.search(r'\bDiscussion\b', chunk_text, re.IGNORECASE))
        out.append(LACPart(number=num, title=title, is_discussion=is_disc))
    return out


# ----------------------------------------------------------------------
# Top-level discovery
# ----------------------------------------------------------------------

def discover(study_date: str | None = None,
             iso_year: int | None = None,
             iso_week: int | None = None) -> WeekDiscovery:
    """Discover next-week materials. Provide either study_date OR (iso_year, iso_week)."""
    if study_date:
        d = dt.date.fromisoformat(study_date)
        iso = d.isocalendar()
        iso_year = iso.year
        iso_week = iso.week
    elif iso_year is None or iso_week is None:
        raise ValueError("must provide either study_date or (iso_year, iso_week)")
    else:
        # Approximate the Sunday of the ISO week so we have a study_date
        d = dt.date.fromisocalendar(iso_year, iso_week, 7)
        study_date = d.isoformat()

    meetings_url = f"https://wol.jw.org/en/wol/meetings/r1/lp-e/{iso_year}/{iso_week}"
    out = WeekDiscovery(
        study_date=study_date,
        iso_year=iso_year,
        iso_week=iso_week,
        week_label="",
        meetings_url=meetings_url,
    )

    try:
        meetings_html = _fetch(meetings_url)
    except Exception as e:
        out.warnings.append(f"meetings page fetch failed: {e}")
        return out

    # Title gives us the week label, e.g. "May 11-17"
    tm = re.search(r'<title>([^<]+?)\s*&mdash;\s*Watchtower', meetings_html)
    if tm:
        out.week_label = tm.group(1).strip()

    # All DocIds linked from the meetings page
    docids = sorted(set(int(m.group(1)) for m in re.finditer(
        r'/en/wol/d/r1/lp-e/(\d+)', meetings_html
    )))
    if not docids:
        out.warnings.append("no DocIds found on meetings page")
        return out

    # Disambiguate: WT articles are 7-digit (YYYYNNN); mwb week pages are 9-digit (2020YYNNN)
    wt_candidates = [d for d in docids if d < 10_000_000]
    mwb_candidates = [d for d in docids if d >= 10_000_000]

    if wt_candidates:
        out.wt_document_id = wt_candidates[0]
        out.wt_url = f"https://wol.jw.org/en/wol/d/r1/lp-e/{out.wt_document_id}"
        try:
            wt_html = _fetch(out.wt_url)
            tm = re.search(r'<h1[^>]*>(.*?)</h1>', wt_html, re.DOTALL)
            if tm:
                out.wt_title = re.sub(r'\s+', ' ',
                                      re.sub(r'<[^>]+>', '', tm.group(1))).strip()
            tm = re.search(r'class="themeScrp"[^>]*>(.*?)</p>', wt_html, re.DOTALL)
            if tm:
                out.wt_theme_scripture = re.sub(
                    r'\s+', ' ', re.sub(r'<[^>]+>', ' ', tm.group(1))
                ).strip()
            out.wt_issue = _parse_issue_from_wt_html(wt_html)
        except Exception as e:
            out.warnings.append(f"WT article fetch failed: {e}")

    if mwb_candidates:
        out.mwb_document_id = mwb_candidates[0]
        out.mwb_url = f"https://wol.jw.org/en/wol/d/r1/lp-e/{out.mwb_document_id}"
        try:
            mwb_html = _fetch(out.mwb_url)
            out.mwb_issue = _parse_mwb_issue_from_html(mwb_html, iso_year)
            book_name, book_num, c_start, c_end = _parse_bible_reading(mwb_html)
            out.bible_reading_book_name = book_name
            out.bible_reading_book = book_num
            out.bible_reading_chapter_start = c_start
            out.bible_reading_chapter_end = c_end
            out.lac_parts = _parse_lac_parts(mwb_html)
            # Find CBS lesson DocIds by parsing the workbook's "Congregation
            # Bible Study" section. The workbook embeds a popover URL like
            #   /en/wol/pc/r1/lp-e/<mwb_doc>/11/0
            # which renders the lessons inline. Fetching that popover gives
            # us the actual lesson DocIds (e.g., lfb lessons 84+85 = 1102016094
            # + 1102016095 for May 17).
            cbs_doc_ids, cbs_label, cbs_pub = _parse_cbs_lessons(
                mwb_html, out.mwb_document_id
            )
            out.cbs_document_ids = cbs_doc_ids
            out.cbs_lesson_label = cbs_label
            out.cbs_publication = cbs_pub
        except Exception as e:
            out.warnings.append(f"mwb workbook fetch failed: {e}")

    return out


def _parse_cbs_lessons(mwb_html: str, mwb_doc_id: int) -> tuple[list[int], str | None, str | None]:
    """Find the CBS lesson DocIds + label + publication symbol from the
    workbook's 'Congregation Bible Study' section.

    The workbook embeds a popover URL like:
        <a href="/en/wol/pc/r1/lp-e/<mwb_doc>/11/0"><em>lfb</em> lessons 84-85</a>

    Fetching that popover renders the actual lesson DocIds. We extract them
    by searching for /lp-e/<docid> patterns in the popover HTML.

    Returns (doc_ids, label, publication_symbol). Empty list / None on failure.
    """
    # Find the CBS link in the workbook — look for "Congregation Bible Study"
    # followed by an anchor to a /pc/ popover URL.
    cbs_idx = mwb_html.find("Congregation Bible Study")
    if cbs_idx < 0:
        return ([], None, None)
    chunk = mwb_html[cbs_idx:cbs_idx + 2000]
    # Pull the popover href + the visible label (e.g., "lfb lessons 84-85")
    m = re.search(
        r'<a\s+href="(/en/wol/pc/[^"]+)"[^>]*>(.*?)</a>',
        chunk, re.DOTALL,
    )
    if not m:
        return ([], None, None)
    popover_url = f"https://wol.jw.org{m.group(1)}"
    label_html = m.group(2)
    label_text = re.sub(r"<[^>]+>", " ", label_html)
    label_text = re.sub(r"\s+", " ", label_text).strip()
    # Publication symbol — pulled from <em>lfb</em> inside the anchor
    pub_m = re.search(r"<em[^>]*>([a-zA-Z]+)</em>", label_html)
    publication = pub_m.group(1) if pub_m else None
    # Fetch the popover; the rendered lessons embed their own DocIds
    try:
        pop_html = _fetch(popover_url)
    except Exception:
        return ([], label_text, publication)
    # Lesson DocIds are 10-digit, lfb DocIds are in the 11020xxxxx range.
    # The popover also contains nav links ("prev/next lesson"), "see more"
    # links, and similar-publication references — all of which match the
    # same pattern but are NOT the lesson(s) being studied this week.
    # Two-part filter:
    #   1. Parse the label ("lessons 84-85" → 2, "lesson 86" → 1) so we
    #      know how many to keep.
    #   2. Rank DocIds by frequency in the popover; actual content DocIds
    #      appear 4-9× (body content + thumbnail + cross-refs), nav links
    #      appear 1×. Take the top-N by frequency.
    from collections import Counter
    expected = _lesson_count_from_label(label_text)
    counts = Counter(int(d) for d in re.findall(r"/lp-e/(11\d{8})", pop_html))
    doc_ids = sorted(d for d, _ in counts.most_common(expected))
    return (doc_ids, label_text, publication)


def _lesson_count_from_label(label: str | None) -> int:
    """Parse 'lessons 84-85' (range) or 'lesson 86' (single) or
    'lessons 84, 86' (comma list) → integer count. Defaults to 1."""
    if not label:
        return 1
    # Range: "lessons 84-85" → 2
    m = re.search(r"lessons?\s+(\d+)\s*[-–]\s*(\d+)", label, re.IGNORECASE)
    if m:
        try:
            count = int(m.group(2)) - int(m.group(1)) + 1
            return max(1, count)
        except ValueError:
            return 1
    # Comma list: "lessons 84, 86, 88" → 3
    m = re.search(r"lessons?\s+(\d+(?:\s*,\s*\d+){1,})", label, re.IGNORECASE)
    if m:
        return len([x for x in m.group(1).split(",") if x.strip()])
    # Single: "lesson 86" → 1
    m = re.search(r"lesson\s+\d+", label, re.IGNORECASE)
    if m:
        return 1
    return 1


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--study-date", help="ISO date in the study week (e.g., 2026-05-17)")
    g.add_argument("--iso-week", help="ISO week (use with --iso-year), e.g., 20",
                   type=int)
    p.add_argument("--iso-year", type=int)
    p.add_argument("--json", action="store_true", help="emit JSON instead of human report")
    args = p.parse_args()

    result = discover(
        study_date=args.study_date,
        iso_year=args.iso_year,
        iso_week=args.iso_week,
    )

    if args.json:
        print(json.dumps(asdict(result), indent=2, default=str))
        return 0

    print(f"Week {result.week_label} ({result.iso_year}-W{result.iso_week:02d})")
    print(f"  meetings:  {result.meetings_url}")
    if result.wt_document_id:
        print(f"  WT:        DocId={result.wt_document_id}  {result.wt_title!r}")
        print(f"             theme: {result.wt_theme_scripture!r}")
        print(f"             url:   {result.wt_url}")
        print(f"             issue: {result.wt_issue}")
    else:
        print("  WT:        NOT DISCOVERED")
    if result.mwb_document_id:
        print(f"  mwb:       DocId={result.mwb_document_id}  issue={result.mwb_issue}")
        print(f"             url:   {result.mwb_url}")
        if result.bible_reading_book_name:
            chaps = (f"{result.bible_reading_chapter_start}-{result.bible_reading_chapter_end}"
                     if result.bible_reading_chapter_end != result.bible_reading_chapter_start
                     else str(result.bible_reading_chapter_start))
            print(f"  Bible:     {result.bible_reading_book_name} {chaps} "
                  f"(book #{result.bible_reading_book})")
        for lac in result.lac_parts:
            tag = "DISCUSSION" if lac.is_discussion else "(talk/local-needs)"
            print(f"  LAC #{lac.number}: {lac.title}  [{tag}]")
    if result.warnings:
        print()
        for w in result.warnings:
            print(f"  ⚠ {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
