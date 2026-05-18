# Midweek Meeting — Section-by-Section Comment Reference

How the Christian Life and Ministry Meeting (CLM) is structured, who
delivers each part, and where Tyler can / should / shouldn't comment.

Source: official jw.org *Instructions for Our Christian Life and Ministry
Meeting* (extracted May 2026). All quoted phrasing is verbatim from
that page.

Total meeting length: **1 hour 45 minutes**.

---

## Where the audience comments (Tyler's comment slots, in priority order)

### 🟢 1. SPIRITUAL GEMS (10 min) — primary Bible-verse slot

**Format:** *"Question-and-answer part without an introduction or a
conclusion."* Two questions provided in the workbook; both are about
the week's Bible reading.

**Audience interaction:** Comments invited. *"Those called on should
offer comments of 30 seconds or less."* Note the **30-second cap** —
much shorter than the 60–70-second window Tyler has on a Watchtower
study comment.

**What Tyler comments on:** Bible verses from the week's reading.
- Schema: `KeySymbol='nwtsty'`, `BlockType=2`, `BlockIdentifier=verse`
- Location anchored by `BookNumber` + `ChapterNumber`

**Voice calibration:** Same nine principles, but **half the runway.**
~80–110 words. Tighter restraint. ONE image, ONE rotation, lands
fast. The aphoristic landing matters more here than anywhere else
because there's no time to recover from a weak close.

**How the AI generates for Spiritual Gems:**
1. Read the week's Bible reading + the two workbook questions
2. For each question, draft a 30-second comment using the voice system
3. Anchor each comment to the verse it discusses (BlockType=2)
4. Optionally underline a key phrase in the verse (color per semantics)

---

### 🟢 2. CONGREGATION BIBLE STUDY (30 min) — biggest comment-volume slot

**Format:** *"Question-and-answer study of assigned workbook material."*
Conductor reads each paragraph (or has it read), poses the printed
question, calls on commenters.

**Audience interaction:** Yes — paragraph-by-paragraph. Multiple
audience comments per paragraph are normal. Comments are typically
30–60 seconds.

**What Tyler comments on:** Paragraphs of the current Congregation
Bible Study book.
- Currently in use: *"Love People — Make Disciples"* (`KeySymbol='lff'`)
- Schema: `KeySymbol='lff'` (or current book), `BlockType=1`,
  `BlockIdentifier=data-pid`
- Location anchored by `IssueTagNumber` + `DocumentId`
- Same Watchtower-study schema; same data-pid lookup pattern

**Voice calibration:** ~150–250 words. Slightly tighter than
Watchtower because there are more commenters per paragraph and the
conductor moves the pace. Pick 1–2 paragraphs per chapter to
prepare deeply rather than commenting on every paragraph.

**Strategic note:** Congregation Bible Study has the **highest
volume of comment opportunity per meeting** — 30 minutes, multiple
paragraphs, multiple comments per paragraph. It's where Tyler can
build the most consistent reputation as a thoughtful commenter.

---

### 🟡 3. LIVING AS CHRISTIANS — discussion parts only (within 15 min)

**Format:** Either a talk OR a *discussion*. The workbook designates
which.

**Audience interaction:** **Only when designated as discussion.**
*"When a part is designated as a discussion, the speaker may ask
questions throughout the part in addition to the ones provided."*

**What Tyler comments on:** Workbook paragraphs of the LAC item.
- Schema: `KeySymbol='mwb'`, `BlockType=1`, `BlockIdentifier=data-pid`
- Location: this week's mwb DocumentId for the specific LAC part

**Important:** Not every LAC part is a discussion. Check the workbook
for "*Discussion*" tag or built-in audience questions. If it's a
talk, no audience comments — Tyler doesn't prep this section.

**Voice calibration:** ~100–180 words. Discussion parts have shorter
audience windows than the Congregation Bible Study but a touch
longer than Spiritual Gems.

---

### 🟡 4. CONCLUDING COMMENTS (3 min) — optional invitation

**Format:** Chairman reviews the meeting; *"as time permits, he may
do so by inviting the audience to comment on points they found
beneficial."*

**Audience interaction:** Optional, time-permitting. The chairman
decides whether to open the floor.

**What Tyler comments on:** Anything that struck him from the meeting.
**Not anchorable to a specific paragraph** — this is a meta-comment
on the meeting itself.

**Tool support:** Skip. No persistent note infrastructure needed.
Tyler can keep a mental note or jot in the workbook directly.

---

### 🟡 5. APPLY YOURSELF — DISCUSSION parts only (rare)

**Format:** Most Apply Yourself parts are student demonstrations or
talks (no audience). The exception: *"Discussion Parts"* — *"Elder
or a qualified ministerial servant"* may *"ask questions throughout
the part."*

**Audience interaction:** Only for explicit Discussion-type parts.
Rare in current workbooks.

**What Tyler comments on:** When applicable, on workbook paragraphs.
Same schema as LAC discussions.

**Tool support:** Same as LAC discussions. Same `mwb` Location, same
`BlockType=1` schema. Only invoked when the workbook actually marks
a part as Discussion.

---

## Where the audience does NOT comment (do not prep)

| Section | Why no comments |
|---|---|
| Opening Song & Prayer | Congregational participation only |
| Opening Comments | Chairman's brief remarks |
| Treasures Talk (10 min) | Elder/MS-only talk |
| Bible Reading (4 min) | Male student reads scripture; no audience response |
| Apply Yourself: Starting Conversation | Student demonstration |
| Apply Yourself: Following Up | Student demonstration |
| Apply Yourself: Making Disciples | Student demonstration |
| Apply Yourself: Explaining Beliefs | Student talk or demonstration |
| Apply Yourself: Ministry Talk | Student talk |
| Commendation and Counsel | Chairman addressing student only |
| LAC parts marked as TALK (not discussion) | Talk format; no audience invitation |
| Closing Song & Prayer | Congregational participation only |

**Tool implication:** the AI candidate-generator should never produce
notes/underlines on these sections. It only generates content for
the audience-comment-inviting sections above.

---

## Special-circumstance variations

- **Circuit Overseer visit week:** Congregation Bible Study is
  replaced by the CO's 30-min service talk. **No audience comments
  during the CO talk.** Spiritual Gems and other CLM sections still
  run normally.
- **Week of Assembly / Convention:** No CLM meeting at all.
- **Week of Memorial (weekday):** No CLM meeting.

The AI should ask Tyler / the workbook whether the week is a
special-circumstance week before generating.

---

## File-naming convention for midweek comments

One JSON file per Location (per workbook item / Bible chapter). Suggested
naming for a meeting on `2026-05-07`:

| File | Section | Schema |
|---|---|---|
| `2026-05-07-spiritual-gems.json` | Spiritual Gems Q&A | `nwtsty` Bible verses, BlockType=2 |
| `2026-05-07-cbs-chN.json` | Congregation Bible Study chapter N | `lff` (or current book), BlockType=1 |
| `2026-05-07-lac-itemN.json` | LAC discussion part N (if any) | `mwb` workbook item, BlockType=1 |

If a week has no LAC-discussion-type part, that file just doesn't
exist for the week. The tool runs once per file.

---

## Publication-key reference (KeySymbols)

| KeySymbol | Publication | When used |
|---|---|---|
| `nwtsty` | New World Translation Study Bible | Spiritual Gems, Bible reading verse notes |
| `mwb` | Our Christian Life and Ministry — Meeting Workbook | LAC discussions, sometimes other parts |
| `lff` | *Love People — Make Disciples* | Current Congregation Bible Study book |
| `w` | *The Watchtower* (Study) | Sunday Watchtower study (separate from midweek) |

The Congregation Bible Study book rotates roughly every 18–24 months.
When it changes, update this table and the AI's awareness of which
KeySymbol to use for CBS comments.

---

## Implications for AI candidate generation

When Tyler asks for midweek comments:

1. **Identify the date** of the meeting and pull the workbook week from
   `https://www.jw.org/en/library/jw-meeting-workbook/<bimonth-YYYY-mwb>/`
2. **Identify the Bible reading** for the week (named in the workbook)
3. **Generate Spiritual Gems comments** — read the two workbook questions,
   draft 30-second comments anchored to Bible verses
4. **Generate Congregation Bible Study comments** — for the assigned
   chapter of the current CBS book, identify 2–4 paragraphs worth
   commenting on, draft 30–60-second comments
5. **Check for LAC discussion parts** — only if the workbook marks one
   as Discussion, generate a 30–45-second comment
6. **Skip everything else** — no comments for talks, demonstrations,
   Bible reading, opening/closing
7. **Output one JSON file per Location** following the naming convention
   above

---

## Implications for tool support

The current `jwl_notes.py` already handles:
- ✅ `mwb` Locations (same schema as Watchtower — verified May 2026)
- ✅ `lff` and other workbook-style Locations (same schema, just
  different KeySymbol)
- ✅ Paragraph notes (BlockType=1)
- ✅ Underlines on workbook paragraphs (Phase 2A)

Phase 2D adds:
- 🚧 Bible verse Locations (`nwtsty` — looked up by Book + Chapter
  instead of Issue + DocumentId)
- 🚧 Bible verse notes (BlockType=2, BlockIdentifier=verse)
- ⏸ Bible verse underlines (deferred — verse-level token alignment
  needs verification against Tyler's existing verse highlights)

The tool stays one-file-one-Location. If Tyler wants to inject all
of a week's comments in one shot, we can later add a directory-mode
that loops over all `*.json` in a folder. Not needed for v1.
