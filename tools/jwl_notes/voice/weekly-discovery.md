# Weekly Auto-Discovery

How to take a single week input from Tyler ("next week" / "May 10" /
"week of June 8") and produce all four comments JSON files
(Watchtower, Spiritual Gems, CBS, LAC discussion) without asking him
for any other URL.

This is a process doc for the AI in chat. It encodes the URL patterns,
parsing rules, and inference logic so any session can run the same
playbook.

---

## Inputs

A single date or week descriptor from Tyler. Resolve to a Sunday-
through-Saturday week (the JW week convention). Examples:
- "next week" → calculate from today's date
- "May 10" / "5/10" → the week containing May 10 in the current year
- "week of May 4" → that specific Sun-Sat range

---

## Step 1 — Resolve the bimonthly workbook URL

Workbooks are published bimonthly. Pattern:
```
https://www.jw.org/en/library/jw-meeting-workbook/{months}-{year}-mwb/
```
where `{months}` is `january-february`, `march-april`, `may-june`,
`july-august`, `september-october`, `november-december` (lowercase,
hyphenated).

For May 10, 2026 → `https://www.jw.org/en/library/jw-meeting-workbook/may-june-2026-mwb/`

This page lists the nine weeks the workbook covers; no other detail.

---

## Step 2 — Resolve the specific week page

Per-week URL pattern:
```
{workbook_url}Life-and-Ministry-Meeting-Schedule-for-{Month}-{D}-{D}-{YYYY}/
```

Examples:
- `Life-and-Ministry-Meeting-Schedule-for-May-4-10-2026/`
- `Life-and-Ministry-Meeting-Schedule-for-June-29-July-5-2026/` (cross-month weeks)

The day range is the Sunday-to-Saturday of the meeting week. For dates
spanning a month boundary, both months appear.

---

## Step 3 — Parse the week page

WebFetch the week URL with this extraction prompt:

```
Extract:
1. Bible reading citation (book + chapter range)
2. Each Treasures From God's Word part (number, title, scriptures)
3. Spiritual Gems questions (verbatim) and which verses they target
4. Bible Reading verse range (the 4-min student reading is a SUBSET
   of the full week's reading)
5. Each Apply Yourself part (number, title, type — talk/demonstration)
6. Each Living as Christians part — title, "discussion" or "talk", refs
7. Congregation Bible Study assignment — book name, chapter/lesson, paragraphs
8. Opening + closing songs
```

The page is well-structured — fields appear consistently.

### What you'll get back (May 4-10, 2026 example)

- Bible reading: **Isaiah 58-59**
- Bible Reading (4-min): **Isaiah 59:1-12**
- Spiritual Gems Q1: about **Isaiah 59:11** ("keep growling like bears")
- Spiritual Gems Q2: open ("any spiritual gem")
- LAC Part 7: *"Follow the Course of Hospitality"* (15 min — **Discussion**)
- CBS: ***Lessons from the Bible*** lessons 82-83 ("Jesus Teaches How to Pray")

---

## Step 4 — Resolve the Sunday Watchtower study article

The workbook page does **not** include the Sunday WT study article.
Resolve it separately.

### URL pattern

WT study articles on WOL: `https://wol.jw.org/en/wol/d/r1/lp-e/{document_id}`

DocumentId pattern for the modern Watchtower study issues:
- Format `YYYY{NNN}` where YYYY is the issue year and NNN is a sequential per-issue index
- Examples observed:
  - `2026280` → Watchtower Study Feb 2026, Article 1 ("Are You Prepared for Challenges After Baptism?") — studied April 27 to May 3, 2026
  - `2026281` (likely) → Article 2 of the same issue — studied May 4 to May 10, 2026

### Inference rule

For a given study Sunday:
1. Identify the WT issue currently being studied. Watchtower study issues lag the meeting by ~3 months. April-May 2026 study weeks → Feb 2026 issue. May-June 2026 study weeks → late Feb / March 2026 issue.
2. WOL article DocumentIds for the issue increment by 1 from article 1.
3. Each article studies for one week (Sunday-Saturday), in order.
4. Cross-check by fetching the candidate WOL URL and verifying:
   - The page is dated correctly ("Study Period: {date range}")
   - The article title matches the workbook's "Watchtower Study" line if shown

If the page returns an "article not yet released" type error, back off to the previous DocumentId.

---

## Step 5 — Resolve the CBS book DocumentId

The current CBS book name is in the workbook (Step 3). Map name → KeySymbol:

| Book name (as written) | KeySymbol | Notes |
|---|---|---|
| *Love People — Make Disciples* | `lff` | The 2024-onward outreach focus brochure |
| *Lessons from the Bible* | `lfb` *(verify)* | The 2019 book; may be in CBS rotation |
| *Jesus — The Way, the Truth, the Life* | `jy` | Older CBS book (rotation) |

For each CBS chapter / lesson, the WOL URL pattern is:
`https://wol.jw.org/en/wol/d/r1/lp-e/{document_id}`

The DocumentId for a chapter can be looked up by:
1. Going to the book's WOL landing page
2. Finding the chapter/lesson link
3. Reading the URL

Or — easier — by inferring from the per-meeting DocumentIds Tyler already has in his backup. His `userData.db` query for `lff` Locations gives the DocumentIds for each chapter.

---

## Step 6 — Map LAC discussion items to mwb DocumentId

If the workbook marks an LAC part as "Discussion," that part has its
own DocumentId in the `mwb` publication. Pattern:
- Bimonthly issue `mwb` DocumentId follows `2020{YY}{NNN}` (per Tyler's backup data — May 2026 mwb issue is around 202026160-onward)
- Each part within the issue is its own DocumentId (incrementing)

The cleanest way to find the specific part's DocumentId:
1. Open the week page URL on jw.org
2. Click into the LAC part
3. The URL gives the DocumentId

Or — query Tyler's backup for any existing Locations on the same `mwb` IssueTagNumber to enumerate.

---

## Step 7 — Generate the four JSON files

For each comment slot in the meeting, produce one JSON file:

### A. Sunday Watchtower → `comments/{date}-w.json`

```json
{
  "_meta": {"source": "Watchtower Study, {month} {year}, article {N}", "study_date": "{date}"},
  "key_symbol": "w",
  "issue": YYYYMMOO,
  "document_id": NNNNNNN,
  "default_block_type": 1,
  "notes": [
    {
      "paragraph": N,
      "data_pid": M,
      "block_type": 1,
      "content": "{generated using voice system}",
      "underlines": [{"phrase": "...", "color": "..."}]
    }
  ]
}
```

Generate notes on every paragraph that has obscure depth + underlines
on every numbered paragraph (the answer to its study question, color
per semantics).

### B. Midweek Spiritual Gems → `comments/{date}-spiritual-gems.json`

```json
{
  "_meta": {"source": "Spiritual Gems on Bible reading {Bible reference}"},
  "key_symbol": "nwtsty",
  "book": N,
  "chapter": N,
  "default_block_type": 2,
  "notes": [
    {
      "verse": N,
      "block_type": 2,
      "content": "{30-second draft, ~80-110 words}",
      "underlines": [{"phrase": "...", "color": "..."}]
    }
  ]
}
```

One note per Spiritual Gems question. Q1 anchors to the explicit verse
(e.g., Isa 59:11 for May 4-10). Q2 anchors to whatever verse Tyler is
choosing to highlight.

If the Bible reading spans multiple chapters and you want to comment
on verses from each chapter, **produce one file per chapter** (each
chapter is its own Location).

### C. Congregation Bible Study → `comments/{date}-cbs.json`

```json
{
  "_meta": {"source": "CBS — {book} chapter {N}"},
  "key_symbol": "{KeySymbol of the CBS book}",
  "issue": ...,
  "document_id": ...,
  "default_block_type": 1,
  "notes": [...]
}
```

Pick 2-4 paragraphs to comment on (not every paragraph). 30-60 sec
each. Same Watchtower-style schema.

### D. LAC Discussion (if any) → `comments/{date}-lac.json`

Only produced if a LAC part is marked "Discussion." Same `mwb` schema:

```json
{
  "_meta": {"source": "LAC Discussion: {title}"},
  "key_symbol": "mwb",
  "issue": YYYYMMOO,
  "document_id": NNNNNNN,
  "default_block_type": 1,
  "notes": [...]
}
```

---

## Quick sanity checks before delivering

1. ✅ Every JSON validates (`python -c "import json; json.load(open(F))"`)
2. ✅ Every `data_pid` / `verse` resolves in the source HTML — use the
   tool's `extract_paragraph_tokens` / `extract_verse_tokens` to verify
   no phrase will fail the alignment step
3. ✅ Color choices follow `voice/color-semantics.md`
4. ✅ Each note's word count fits the surface budget:
   - Watchtower paragraph: ~250-280 words
   - CBS paragraph: ~150-250 words
   - LAC discussion: ~100-180 words
   - Spiritual Gems verse: ~80-110 words (30-sec cap)
5. ✅ Voice principles enforced (handoff-prompt.md baseline + four-slot
   architecture from drafting-recipe.md)

---

## What's still manual

- Verifying the WT issue → study-week mapping for unfamiliar weeks
  (the URL DocumentId arithmetic above is reliable for sequential
  weeks but breaks across issue boundaries)
- The CBS book + KeySymbol mapping when a new book enters rotation
- Special-circumstance weeks (Memorial week, CO visit week, assembly
  week) — the workbook indicates these but the AI must check before
  generating

---

## Demonstration

For the next week Tyler asks about, the AI runs Steps 1-7 inline and
delivers all four (or fewer if not all sections apply) JSON files in
the chat, ready for `git add comments/* && commit && push && python
jwl_notes.py …` — one tool invocation per file.
