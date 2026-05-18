#!/usr/bin/env python3
"""test_tokenize.py — dry-run alignment tests for jwl_notes tokenization.

Each test pins an empirical ground truth (a paragraph data-pid + an expected
token at a specific index, OR a phrase + expected start/end position), so
breakage of the tokenizer is caught before injection.

Ground truth was captured from JW Library on Tyler's iPhone — the rendered
position of underlines after import. If a future change to the tokenizer
breaks any of these, the underlines will land in the wrong place again.

Run:  python3 test_tokenize.py
Exit 0 = all green. Non-zero = at least one alignment regressed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from jwl_notes import (  # noqa: E402
    extract_paragraph_tokens,
    extract_verse_tokens,
    fetch_wol_article,
    fetch_wol_bible_chapter,
    find_token_range,
)


def _phrase_pos(html: str, pid: int, phrase: str) -> tuple[int, int]:
    return find_token_range(extract_paragraph_tokens(html, pid), phrase)


def _verse_phrase_pos(html: str, book: int, chap: int, verse: int,
                      phrase: str) -> tuple[int, int]:
    return find_token_range(
        extract_verse_tokens(html, book, chap, verse), phrase
    )


# ---------- Article: 2026320 "Improve Your Art of Teaching" ----------
W_HTML = fetch_wol_article(2026320, "w")

ARTICLE_TOKEN_AT_INDEX = [
    # Empirical ground truth — verified against JW Library's actual rendering.
    # ¶1 (data-pid=7): position 32 = "This", position 94 = "Paul".
    (7, 32, "This"),
    (7, 94, "Paul"),
]

ARTICLE_PHRASE_TESTS = [
    # (data-pid, phrase, expected_start, expected_end)
    (7, "should be teachers", 38, 40),
    (7, "spoke in such a manner", 113, 117),
    (8, "limited secular education", 13, 15),
    (10, "knew what was in man", 6, 10),
    (12, "kindness and respect", 53, 55),
    (12, "mild-tempered and lowly in heart", 60, 64),
    (13, "gracious, seasoned with salt", 144, 148),
    (15, "freely quoted from the inspired Scriptures", 99, 104),
    (16, "about 3,000 people were added", 80, 86),
    (19, "with all patience", 19, 21),
    (22, "lighting technician in a theater", 37, 41),
    (23, "joining a club", 44, 46),
    (25, "through his eyes", 90, 92),
]

# All phrases that exist in 2026-05-10-w.json — we don't pin exact
# positions but DO require that they resolve without error. Yellows must
# fully answer the printed question; multiple yellows per paragraph are
# expected when the paragraph offers multiple distinct answers.
ARTICLE_PHRASE_RESOLVES = [
    (7, "all Christians should be teachers"),
    (7, "All Christians would do well to cultivate that art"),
    (7, "spoke in such a manner"),
    (8, "have limited secular education or natural ability"),
    (8, "do not seem to get the positive results that others do"),
    (10, "he understood their needs"),
    (10, "he spoke about matters that affected them personally"),
    (10, "knew what was in man"),
    (11, "by trying to understand their concerns"),
    (11, "without the hope that the Bible offers"),
    (12, "Jesus treated people with kindness and respect"),
    (12, "mild-tempered and lowly in heart"),
    (12, "looked down on the common people"),
    (13, "give those who reject our message the benefit of the doubt"),
    (13, "let [our] words always be gracious, seasoned with salt"),
    (13, "do good to those hating you"),
    (15, "Jesus freely quoted from the inspired Scriptures"),
    (15, "centered his teaching on God’s will and Word"),
    (15, "as one having authority"),
    (16, "he touched the hearts of his listeners with his Scriptural explanation of the prophecies"),
    (16, "not a highly educated man"),
    (16, "about 3,000 people were added"),
    (17, "no better tool to reach our listeners’ hearts than the Word of God"),
    (17, "the Bible contains something far superior to human wisdom"),
    (17, "letting Jehovah speak"),
    (18, "look up key texts and help your student reason on them"),
    (18, "give the student time to absorb the meaning"),
    (18, "not a book study or a picture study"),
    (19, "preach the word . . . with all patience"),
    (19, "Some students may need extra time to grasp truths"),
    (20, "drawing out students with questions"),
    (20, "completely unfamiliar with the Bible"),
    (20, "show your Bible students the power of God’s Word"),
    (22, "focus attention on Jehovah, not on ourselves"),
    (22, "lighting technician in a theater"),
    (22, "in the spotlight"),
    (23, "help your student develop the desire to please Jehovah"),
    (23, "what a wonderful Father we have"),
    (23, "joining a club"),
    (25, "ask Jehovah in prayer to help you analyze your art of teaching"),
    (25, "Try to look at the material through his eyes"),
    (25, "close friendship with Jehovah"),
    (26, "Teaching others about Jehovah is one of the greatest joys we can experience"),
    (26, "much needed in the future new world"),
]

# ---------- Workbook (mwb) for 2026-05-10 LAC ----------
MWB_HTML = fetch_wol_article(202026161, "mwb")

MWB_PHRASE_RESOLVES = [
    (30, "follow the course of hospitality"),
    (36, "Jehovah is the best example"),
    (43, "consider how you would like to show hospitality"),
    (43, "write your goals"),
]

# ---------- Bible: Isaiah 58 + 59 ----------
ISA58_HTML = fetch_wol_bible_chapter(23, 58, "nwtsty")
ISA59_HTML = fetch_wol_bible_chapter(23, 59, "nwtsty")

VERSE_PHRASE_RESOLVES = [
    # Isa 58
    (ISA58_HTML, 23, 58, 6, "the fast that I choose"),
    (ISA58_HTML, 23, 58, 6, "remove the fetters of wickedness"),
    (ISA58_HTML, 23, 58, 6, "let the oppressed go free"),
    (ISA58_HTML, 23, 58, 8, "your light will shine through like the dawn"),
    (ISA58_HTML, 23, 58, 8, "the glory of Jehovah will be your rear guard"),
    (ISA58_HTML, 23, 58, 9, "you will cry for help"),
    (ISA58_HTML, 23, 58, 9, "Here I am!"),
    (ISA58_HTML, 23, 58, 11, "Jehovah will always lead you"),
    (ISA58_HTML, 23, 58, 11, "like a well-watered garden"),
    # Isa 59
    (ISA59_HTML, 23, 59, 1, "the hand of Jehovah is not too short"),
    (ISA59_HTML, 23, 59, 1, "his ear too dull to hear"),
    (ISA59_HTML, 23, 59, 2, "your own errors"),
    (ISA59_HTML, 23, 59, 2, "separated you from your God"),
    (ISA59_HTML, 23, 59, 11, "We all keep growling like bears"),
    (ISA59_HTML, 23, 59, 11, "We hope for justice, but there is none"),
    (ISA59_HTML, 23, 59, 17, "righteousness like a coat of mail"),
    (ISA59_HTML, 23, 59, 17, "garments of vengeance"),
]


def main() -> int:
    failures: list[str] = []
    passed = 0

    # 1. Pinned token-at-index assertions for the article (the empirical bug).
    for pid, idx, expected in ARTICLE_TOKEN_AT_INDEX:
        toks = extract_paragraph_tokens(W_HTML, pid)
        actual = toks[idx] if idx < len(toks) else None
        if actual != expected:
            failures.append(
                f"article ¶data-pid={pid} token[{idx}]: expected {expected!r}, "
                f"got {actual!r}"
            )
        else:
            passed += 1

    # 2. Pinned phrase positions for the article.
    for pid, phrase, e_start, e_end in ARTICLE_PHRASE_TESTS:
        try:
            s, e = _phrase_pos(W_HTML, pid, phrase)
            if (s, e) != (e_start, e_end):
                failures.append(
                    f"article ¶data-pid={pid} {phrase!r}: expected ({e_start},{e_end}), "
                    f"got ({s},{e})"
                )
            else:
                passed += 1
        except ValueError as exc:
            failures.append(f"article ¶data-pid={pid} {phrase!r}: {exc}")

    # 3. All article underlines from the comments JSON resolve.
    for pid, phrase in ARTICLE_PHRASE_RESOLVES:
        try:
            _phrase_pos(W_HTML, pid, phrase)
            passed += 1
        except ValueError as exc:
            failures.append(f"article ¶data-pid={pid} {phrase!r}: {exc}")

    # 4. Workbook phrases resolve.
    for pid, phrase in MWB_PHRASE_RESOLVES:
        try:
            _phrase_pos(MWB_HTML, pid, phrase)
            passed += 1
        except ValueError as exc:
            failures.append(f"mwb ¶data-pid={pid} {phrase!r}: {exc}")

    # 5. Bible verse phrases resolve.
    for html, book, chap, verse, phrase in VERSE_PHRASE_RESOLVES:
        try:
            _verse_phrase_pos(html, book, chap, verse, phrase)
            passed += 1
        except ValueError as exc:
            failures.append(f"verse {book}:{chap}:{verse} {phrase!r}: {exc}")

    print(f"PASSED {passed}")
    for f in failures:
        print(f"FAIL  {f}")
    if failures:
        print(f"\n{len(failures)} failure(s)")
        return 1
    print("\nAll alignment tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
