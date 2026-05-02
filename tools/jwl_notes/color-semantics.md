# Tyler's Underline Color Semantics

JW Library highlights are color-indexed. Tyler uses color as a
semantic system — each color carries a specific emotional / cognitive
function. When the AI generates underline candidates, it picks the
color based on what the underlined phrase is doing for the reader,
not arbitrarily.

This file is the contract. Both the AI generating candidates AND the
`jwl_notes.py` tool injecting them reference these mappings.

---

## Color → meaning

| Color | What it marks | When to reach for it |
|---|---|---|
| **🟡 Yellow** | Normal / basic / default | The article's primary point. Standard application content. The "answer to the study question" when the answer isn't carrying special emotional weight. **Default if nothing else fits.** |
| **🔴 Red** | *Stop in my tracks* — warnings, caveats, sobering claims | A statement that should make Tyler pause. A warning about a real spiritual danger. A correction of a common misread. *"By the time the wind shows up, our roots are either deep, or they aren't."* |
| **🟣 Purple** | *Encouraged* — uplift, hope, comfort | A statement of Jehovah's love, a reassurance, a verse that lifts. *"With Jehovah, you always gain much more than you lose."* |
| **🔵 Blue** | *Chilling or cold* — weighty, sobering, mortality-adjacent | A statement that names the weight without softening it. The empty seat. The cost of leaving the truth. The gravity of a choice. *"Some no longer walked with him."* |
| **🟢 Green** | *Zealous or rule-loophole* — energizing, or a clever way the principle gives more freedom than expected | A statement that lights a fire to act. OR — a passage that reveals the principle is more generous than the audience assumed (a "you actually can / it's actually allowed" reading). *"Rosemary kept the gathering. She just moved the day."* |

---

## Application rules for the AI

1. **Every numbered paragraph with a study question gets the answer underlined by default.** The color is selected by the *emotional valence* of the answer:
   - Practical "do this" answer → yellow
   - Warning / caveat answer → red
   - Encouraging answer → purple
   - Sobering / weighty answer → blue
   - Zeal-inducing / freedom-revealing answer → green

2. **Additional underlines** beyond the question-answer can be added when a phrase carries one of the four non-yellow functions. Don't double-underline yellow content unless it's particularly load-bearing.

3. **One color per phrase.** If a phrase carries two functions, pick the dominant one. The audience reads color as a single signal.

4. **Color hierarchy** when ambiguous: red > blue > green > purple > yellow. Stop-in-tracks dominates; default-yellow is the floor.

5. **Don't over-color.** A paragraph with five different-color underlines becomes visual noise. Cap at 3 underlines per paragraph; cap at 2 colors per paragraph.

---

## ColorIndex mapping (JW Library SQLite)

The `UserMark.ColorIndex` integer values JW Library uses internally:

| Color | ColorIndex |
|---|---|
| No color (transparent) | 0 |
| Yellow | 1 |
| Green | 2 |
| Blue | 3 |
| Pink (Tyler's "red") | 4 |
| Orange | 5 |
| Purple | 6 |

✅ **Verified against Tyler's userData.db (May 2026).** All six slots
are in active use in Tyler's existing highlights — distribution:
yellow 15,709 / blue 8,921 / pink 8,366 / orange 2,603 / purple 1,376
/ green 990. Tyler's recent highlights on the May 3 article are all
purple (ColorIndex 6).

---

## Style

All underlines use **underline style** (not full highlight box). In
JW Library that's `UserMark.StyleIndex = 0` for "underline" (vs. 1
for "highlight"). Confirmed from Tyler's existing UserMark rows.

---

## Comments JSON schema extension

Each note in `comments/<date>.json` may now carry an optional
`underlines` array:

```json
{
  "paragraph": 2,
  "data_pid": 8,
  "block_type": 1,
  "title": null,
  "content": "...",
  "underlines": [
    {"phrase": "identify potential challenges in the truth and prepare now", "color": "yellow"},
    {"phrase": "those challenges will have less of an impact on us", "color": "purple"}
  ]
}
```

If the entry has only underlines (no commentary worth writing), drop
the `content` field. The tool injects the highlights without a
corresponding `Note` row.

The `phrase` field is matched to the paragraph text via the
HTML-aware token-alignment logic in `jwl_notes.py` (Phase 2A). The
tool resolves it to `StartToken` / `EndToken` offsets and inserts
both `UserMark` and `BlockRange` rows.

---

## Implementation notes for the AI

When generating a comments JSON for a study article:

1. Pull the article and its study questions from WOL.
2. For every numbered paragraph, identify the answer to its question
   and add it as an `underlines` entry. Pick color by valence.
3. Scan each paragraph for additional phrases that carry red / blue /
   green / purple function. Add up to 1–2 more underlines per
   paragraph when warranted.
4. For paragraphs with obscure / "aha" / overlooked depth, draft a
   `content` note using the voice system (`drafting-recipe.md`,
   `calibration.md`). Skip notes on paragraphs with no extra depth.
5. Output the complete JSON. No review gate.
