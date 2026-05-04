# How to draft a Tyler comment — the mesh

> ## ⚠️ GLOBAL RULES — Watchtower / midweek article processing
>
> When processing a *full* article (Watchtower study, midweek workbook
> week, Congregation Bible Study chapter), the AI MUST apply both
> mandates below, on every generation, without being told.
>
> These are not preferences. They are project-defining requirements.
> Operator's verbatim instruction: failure to apply them is "fucking
> useless to the absolute maximum degree."
>
> ### Mandate 1 — The "Less is More" Underline Doctrine
>
> Apply to **every paragraph that has a corresponding study question.
> Do not skip paragraphs.** Sparse coverage is failure.
>
> Each underline phrase must:
> - Be a **surgical extraction of 2 to 6 words** — strict cap of 8
>   for inseparable units of meaning. **Never** a full sentence.
>   **Never** demographic filler (e.g. "of both Jews"). **Never** an
>   article-title repeat (don't underline "art of teaching" if the
>   article *is* "Improve Your Art of Teaching"). **Never** a generic
>   exhortation ("would do well to cultivate", "let us all", etc.).
> - Do **exactly one** of these jobs:
>   - Directly **answer** the printed study question, **or**
>   - **Explain** the cited scripture (the phrase that bridges the
>     verse to the article's argument)
>
> Color per the semantic system (verified against operator's userData.db):
> | Color | When |
> |---|---|
> | **yellow** | Core answer to the printed question. **Cap: 1–2 per paragraph.** |
> | **green**  | Scripture-explainer phrase, or a rule/loophole/freedom-revealing reading |
> | **pink**   | Stop-in-tracks point — strong counsel or warning |
> | **blue**   | Sobering, chilling, or weighty thought |
> | **purple** | Encouraging, pastoral, comforting |
>
> ### Mandate 2 — The Commentary Mandate
>
> For every Watchtower article: autonomously generate **6–8 strategic
> four-slot voice notes** — without waiting for the operator to feed
> content. Each note: 60–130 words; opener / label-parity / rotation /
> landing; in operator's calibrated voice; one per chosen paragraph.
>
> ### Mandate 3 — The JSON anchor split
>
> Every visible paragraph receives **two JSON entries** (one for the
> note, one for the underlines), because JW Library renders them at
> different anchors:
>
> | Entry | `data_pid` | What renders |
> |---|---|---|
> | Note (`content`) | the **question's** data-pid | Inline comment box AND Notes tab |
> | Underlines | the **body paragraph's** data-pid | Highlighted text in the article |
>
> When a question is shared by two paragraphs (e.g., "11–12. (a)…
> (b)…"), the note anchors to the shared question's data-pid; each
> body paragraph gets its own underlines entry on its own body pid.
>
> ### What "useless filler" looks like (do not do)
>
> - ❌ "of both Jews" (demographic context)
> - ❌ "art of teaching" (when that's the article title)
> - ❌ "All Christians would do well to cultivate" (generic exhortation)
> - ❌ Any phrase longer than 8 words
> - ❌ A whole sentence with surrounding context
> - ❌ Skipping a question-bearing paragraph because it "didn't have a strong hook"
>
> ### What "load-bearing" looks like (the standard)
>
> - ✅ "should be teachers" — directly answers Q1
> - ✅ "spoke in such a manner" — explains Acts 14:1 in the article's argument
> - ✅ "knew what was in man" — the John 2:25 phrase the article hangs on
> - ✅ "with all patience" — the 2 Tim 4:2 word the article emphasizes

---


The work above gives you nine principles, twelve named mechanics, three
voice traditions, and a fingerprint match to Sam Herd. That's input
material. **It is not a drafting checklist.** Trying to use all of it
in one comment will violate Restraint (Principle 5) and break the
voice.

This file is the operational mesh — how the inputs combine into a
single 30-second comment without bloat.

---

## The hard constraint: pick, don't mesh

> The principles are *always on*. The mechanics are *one per slot*.
> Most of your toolbox is in reserve at any given moment.

The nine principles are background gravity — concrete carries abstract,
restraint, audience parity, etc. They run automatically in everything
you draft. You don't *choose* them per comment; you choose to operate
inside them.

The twelve mechanics are foreground craft — Voss labeling, Bourdain
preposition-pivot, Tippett formative-origin opener, Mr. Rogers
possession-without-condition, etc. **These are tools. Tools don't get
used all at once.** Each comment uses 2–4 of them, deliberately.

---

## The four-slot architecture

Every Tyler comment has four working slots. Most have three filled and
one empty. Filling all four is rare and only works for the heaviest
paragraphs.

```
[OPENER]   →   [LABEL/PARITY]   →   [ROTATION]   →   [LANDING]
   ↓                ↓                   ↓               ↓
hook            permission           the shift       aphoristic
                (optional)                            inversion
```

Each slot pulls from a small mechanic menu. **Pick one** per slot. The
other mechanics in that slot are in reserve for next time.

### Slot 1 — OPENER (the hook)

| Mechanic | When to reach for it |
|---|---|
| **Brown — positioning declaration** *("I've been chewing on this paragraph all week…")* | When you want immediate parity and warmth |
| **Tippett — formative-origin question** *("What I keep coming back to is what came *before* this paragraph…")* | When the article is mid-argument and the rotation is upstream |
| **Bourdain — climactic-moment opener** *("Look at the verb in this verse…")* | When the paragraph has one specific sentence doing all the work |
| **Hormozi — sound-bite claim** *("Verse 67 was so powerful because…")* | When the paragraph supports a single bold compressed claim |
| **Brené Brown — "you know how" relational** *("You know how when you miss somebody, you only remember the good?")* | When you need the room to nod before you advance |
| **Reinmueller did-you-notice debrief** *("Did you catch what's actually in verse N? Most of us didn't the first time.")* | When the rotation depends on a detail the article cited but didn't unpack |
| **Two-question pre-empt** *("Are we ready? And do we even know what for?")* | When the topic could land flat as a single question — second question re-frames the first |
| **Cook conditional invitation** *("If that's something you've ever yearned for, then sit with this paragraph for a minute.")* | When the paragraph touches a quiet ache the audience carries silently |
| **Lösch historical-frame compression** *("In 1914 the world fell apart. In 1939 it fell apart again. In 2026 here we sit.")* | When the paragraph is about endurance, scope, or the long arc |

**Rule:** never open with the article's topic sentence. Always open one
notch sideways or downstream.

### Slot 2 — LABEL / PARITY (optional, often implied)

| Mechanic | When to reach for it |
|---|---|
| **Voss — labeling the feeling** *("It can feel like..." / "Some of us — myself included — have wondered...")* | When the emotional weight is part of the comment |
| **Perel — name the unnamed dimension** *("There's something the article doesn't quite say out loud, but it's in the wording...")* | When the article *implies* a feeling it doesn't name |
| **Bourdain — self-implication** *("I've done this. I'd be lying if I said I hadn't.")* | Before any critique or insight that could land as judgmental |
| **Mr. Rogers — possession-without-condition** *("It's hard. We don't have to pretend it isn't.")* | When the audience is carrying weight the article doesn't acknowledge |
| **Noumair voiced-objection / voiced-answer** *("Some of us are sitting here thinking, 'but what if they don't come back?' That's the right question.")* | When the audience has a silent objection the article never addresses — speak it in their voice first |
| **Permission-by-uncertainty** *("Some of us aren't sure how to feel about this paragraph yet — and that's okay; the verses themselves take a beat to land.")* | When the paragraph hands the room a shift they may not be ready for |

**Rule:** if the comment is light/observational, leave this slot empty.
If it's heavy/emotional, fill it before you advance.

### Slot 3 — ROTATION (the shift the comment delivers)

| Mechanic | When to reach for it |
|---|---|
| **Morrison — frame refusal** *("Most of us read this as X. Watch what it actually says.")* | When the dominant reading is the wrong reading |
| **Peterson — archetypal compression** *("Peter is the part of us that...")* | When a Bible figure has a universal psychological pattern |
| **Clear — two-noun pivot** *("This isn't preparation. This is panic dressed up as preparation.")* | When the paragraph hinges on a confusion between two near-concepts |
| **Miner — reframed question** *("So the question isn't 'do I see the value' — it's 'am I still searching?'")* | When you want the listener to arrive at the answer themselves |
| **Holiday — obstacle-becomes-path** *("What looks like the test is actually the training.")* | When the paragraph treats a hardship as the obstacle |
| **Hormozi — compression-expansion** *(claim → 3 short parallel beats → bridge → rule)* | When the paragraph is best carried by rhythm, not argument |
| **Schafer concession-pivot (yes-and-yet)** *("Yes, removal is painful. Yes, the empty seat is real. AND — the verses say…")* | When the audience already half-disagrees with where you're going; grant the objection first, then pivot |

**Rule:** ONE rotation per comment. Two rotations dilute. If you have
two, pick the better one and save the other for next week.

### Compressed-image-as-spine (structural meta-mechanic, runs across slots)

This isn't slot-bound. It's a *governance rule* for the whole comment:
**ONE concrete image runs the entire comment as the load-bearing spine.**
The opener sets the image. The label-parity references it. The
rotation pivots on it. The landing closes it. Confirmed by the
AM-talk corpus — Lett's parakeet, Morris's diabetes, Herd's red car —
ONE image carries the whole talk. Same rule for the comment.

If your draft has two images, one is decoration. Cut it.

### Slot 4 — LANDING (the close)

| Mechanic | When to reach for it |
|---|---|
| **Sam Herd — parallel-clause inversion** *("Not dying for each other; living for each other.")* | Default. Use this when in doubt. |
| **Mr. Rogers — possession-without-condition** *("And that part of you doesn't need anyone's permission to be there.")* | When the comment is pastoral / encouragement-shaped |
| **Bourdain — preposition-pivot** *("It isn't faith *with* the truth; it's faith *in* it.")* | When the inversion sits on a single small word |
| **Naval — pursuit-order reframe** *("We notice the storm in that order. The preparation came first.")* | When the comment reorders what the audience already knows |
| **Holiday — Marcus-style aphorism** *("What stands in the way becomes the way.")* | When the comment closes on universal language |
| **Herd temporal-axis inversion** (then/today) *("That was true for Peter then. It's true for us today.")* | When the comment hinges on time — past pattern, present application |
| **Cook conditional invitation** (alternate landing) *("If that's what we yearn for, the verses are waiting.")* | When the landing should leave the room with an open door, not a verdict |

**Rule:** the last sentence is parallel and the last sentence is short.
**No third sentence after.** No CTA, no tag, no "let's keep that in
mind, brothers." Morrison's discipline of silence is the rule.

---

## The decision sequence (use this when stuck)

When drafting a new comment, run these five questions in order:

1. **What's the ONE rotation this comment will deliver?** *(Slot 3.)*
   If you can't say this in one sentence, don't draft yet.
2. **What's the ONE concrete image carrying it?** *(Principle 1.)*
   No image, no comment.
3. **Does this paragraph carry emotional weight that needs labeling?**
   *(Slot 2.)* If yes, write the label first; if no, leave it empty.
4. **What's the right hook for THIS rotation?** *(Slot 1.)* Match the
   hook to the rotation — don't reuse last week's hook out of habit.
5. **What's the landing line?** *(Slot 4.)* Write it before you write
   the bridge between rotation and landing. The landing pulls the
   bridge into the right place.

---

## Default if you have ten minutes and can't decide

Use the **Sam Herd shape**:
- Open with a small-window relational hook (*"You know how…"* / *"It
  makes me think of…"*).
- Render ONE concrete domestic scene fully (one image, sensory detail,
  named relationship).
- Pivot to the verse with a quiet phrase (*"That's kind of what
  happened to…"* / *"That was Jesus."*).
- Land on a parallel-clause inversion.

The default works for any paragraph. The mechanics in slots 1–4 are
*upgrades* on the default, not replacements.

---

## Worked example — ¶14 (your delivered version), tagged

This is the comment you actually gave at the May 3 study. Each beat
tagged with which mechanic is operating.

> "What strikes me is verse 67 — Jesus actually gave them permission
> to leave."
> 🏷  **Slot 1 (Opener):** Bourdain climactic-moment — opens at the
> heat (verse 67), not the topic sentence.

> "That makes me think about my parents' house. I don't live there
> anymore. My brother does. We come and go as we please — both of us."
> 🏷  **Slot 2 (Label/Parity):** Hart pain-as-character meets
> Bourdain self-implication — your real family rendered concretely,
> with you inside the picture.

> "But when my brother walks out, he's got to buy his own food. He
> can't just open the fridge and grab spaghetti. So he stays, even
> when I go — because he knows what he has at home."
> 🏷  **Slot 3 (Rotation):** Clear two-noun pivot disguised as a
> story (*coming-and-going* vs. *staying-because-you-know*) + Hormozi
> compression-expansion (claim → three short parallel beats → bridge).

> "That's Peter right here. He could have walked out; Jesus gave him
> the door. But Peter knew what he had. That's why paragraph 14 says
> he focused on the sayings of truth — he was naming what he'd lose."
> 🏷  **Sam Herd default shape:** quiet pivot to scripture
> (*"That's Peter right here"*) + scripture-paraphrase lock
> (*"focused on the sayings of truth"*) + interpretive bridge.

> "When we know what we have, we stay."
> 🏷  **Slot 4 (Landing):** Sam Herd parallel-clause aphorism. Short.
> Parallel. No sentence after.

**Five mechanics deployed. Seven left in reserve.** That's the mesh.

---

## What this means going forward

When AI drafts a comment for you, the prompt should say:
- Operate inside the nine principles (always on).
- Pick exactly **one mechanic per slot**, no more.
- If unsure, default to the Sam Herd shape.
- Use the variety rule: don't repeat the slot-1 mechanic from last
  week. Across a year of comments, every mechanic should have rotated
  in at least once. Variety is part of the voice — listeners trust a
  voice with range that still sounds like one person.

That last rule is what protects the voice from collapsing into
formula. Restraint per comment + variety across comments = a voice
that compounds.

---

## Files in this voice system (orientation)

| File | Purpose |
|---|---|
| `calibration.md` | Analytical reference. Why this voice is shaped the way it is, who else operates in it, what each technique does. Read once; reread when calibrating. |
| `secular-voice.md` | The same shape stripped of religion, for sales / coaching / LinkedIn. Includes a paste-ready AI prompt. |
| `drafting-recipe.md` *(this file)* | The operational mesh. The four-slot architecture, decision sequence, and default. Reach for this when drafting. |

When drafting, only `drafting-recipe.md` needs to be open. The other two
are reference depth that lives behind it.
