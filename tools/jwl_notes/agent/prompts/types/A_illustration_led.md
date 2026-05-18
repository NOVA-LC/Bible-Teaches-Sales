# Comment Type A — Illustration-Led (Tyler-Herd default)

> Read `_shared_core.md` first. This prompt adds the SHAPE for Type A on top of the universal non-negotiables.

## When this type fits

The paragraph teaches a principle through a story, an analogy, or an application of a verse to ordinary life. The reader walks in needing to *see* the principle in domestic terms. Good fits: hospitality, parenting, kindness-to-opposers, art-of-teaching, perseverance, family/friendship paragraphs.

**Not** for: heavy doctrinal exegesis (use Type D), pure historical-cultural notes (use Type H), application-with-no-narrative (use Type C), pastoral-direct-encouragement of carried weight (use Type F).

## The shape — four slots

```
[OPENER]   →   [LABEL/PARITY]   →   [ROTATION]   →   [LANDING]
   ↓                ↓                   ↓               ↓
small-window      naming the          the verse        parallel-clause
relational hook   carried weight      acts on the      inversion
                                      listener
```

3-4 of these slots filled (rarely all four). Pick ONE mechanic per slot from the 12-mechanic toolbox. Tag every beat.

### The 12-mechanic toolbox

**Openers (Slot 1):**
- Brown positioning declaration
- Tippett formative-origin question
- Bourdain climactic-moment opener
- Hormozi sound-bite claim
- Brené Brown you-know-how relational
- Reinmueller did-you-notice debrief
- Two-question pre-empt
- Cook conditional invitation
- Lösch historical-frame compression

**Label / Parity (Slot 2, optional):**
- Voss labeling
- Perel name-the-unnamed-dimension
- Bourdain self-implication
- Mr. Rogers possession-without-condition
- Noumair voiced-objection
- Permission-by-uncertainty

**Rotation (Slot 3):**
- Morrison frame refusal
- Peterson archetypal compression
- Clear two-noun pivot
- Miner reframed question
- Holiday obstacle-becomes-path
- Hormozi compression-expansion
- Schafer concession-pivot

**Landing (Slot 4):**
- Sam Herd parallel-clause inversion *(default)*
- Mr. Rogers possession-without-condition
- Bourdain preposition-pivot
- Naval pursuit-order reframe
- Holiday Marcus-style aphorism
- Herd temporal-axis inversion
- Cook conditional invitation

## The different-domain principle (Gate 8)

Your illustration must come from a domain **unrelated** to the verse's surface content. The scripture arrives as the *surprise* that reveals shared abstraction. If the verse is about feeding the hungry, the illustration is NOT bringing food to a homeless person — it's holding the elevator for a stranger whose dad is dying. The connection (kindness offered without awareness of weight) is structural, not surface.

Vary domains across the article: workplace, sports, music, urban infrastructure, transit, childhood, sleep, money, mechanical repair, food service, lawn care.

## Worked example — passing Type A

> *I held the elevator for a guy at my building once. Standard thing. He stepped in and his eyes were red. He looked at me and said, "thank you, man, I'm on my way to my dad's hospital room and I'm really late." Twenty seconds. Doors closed. Never saw him again. Now look at Matthew 25. Jesus is describing the day of judgment, and he separates people based on one thing — did they feed the hungry, take in the stranger, visit the sick. The sheep are confused. They say, "Lord, when did we see YOU hungry? When did we see YOU thirsty?" They don't know they were doing it for him. And Jesus answers: "whatever you did to one of the least of these brothers of mine, you did to me." Notice — the sheep are surprised. The kindness was offered without weight. So when we hold a door, hold an elevator, give somebody our seat on the train — the question isn't whether they deserve it. It's whether we know what we're actually holding open. The kindness we think is small might be sitting at a hospital bed.*

**What works**: elevator (transit domain) ≠ feeding hungry (Mt 25 domain). The verse arrives as surprise. Sheep-are-surprised structure mirrored in listener-also-surprised application. Last 30 words turn directly to listener with the verse-words still warm.

## Your output — return ONLY this JSON

```json
{
  "comment_type": "A",
  "rotation": "one-sentence statement of THE rotation",
  "spine_image": "the ONE concrete image (noun phrase)",
  "content": "130-200 word comment text",
  "tagged_beats": [
    {"text": "first beat", "mechanic": "..."},
    {"text": "second beat", "mechanic": "..."},
    {"text": "third beat (rotation)", "mechanic": "..."},
    {"text": "landing", "mechanic": "..."}
  ],
  "audience_state_at_open": "real specific weight, named in first 30 words",
  "transformation_mechanism": "release | equip | invert",
  "audience_state_at_close": "renamed feeling, named in last 30 words",
  "domestic_scene": {"present": true, "named_relationship": "brother | mom | ...", "scene_summary": "..."},
  "herd_distinctive_moves": ["H1" | "H2" | "H3" | "H4" | "H5"],
  "memorable_line": "substring of content",
  "different_domain_check": "illustration domain: X; verse domain: Y; unrelated: yes/no"
}
```
