# Comment Type D — Exegetical Chain (verse-by-verse walk)

> Read `_shared_core.md` first.

## When this type fits

The paragraph is rooted in a chunk of scripture — 3-7 consecutive verses — where the *progression* of the verses IS the argument. The reader needs to be walked through the verses one at a time and shown what each verse is doing.

Good fits: paragraphs anchored in narrative blocks (Job 1:9-12, Acts 17:1-4, John 6:1-15), Sermon-on-the-Mount sequences, prophetic chapters, Psalms-as-argument.

**Not** for: paragraphs anchored in a single verse (Type A or F), paragraphs that need a non-scripture illustration (Type A), pure-application paragraphs (Type C).

## The shape — annotated progression

```
[FRAME: name the chunk]   →   [VERSE-BY-VERSE]   →   [LANDING]
        ↓                         ↓                       ↓
"look at the progression     each verse: what it          the cumulative
in Job 1:9-12"               does + what shifts           argument named
                             between verses
```

This is Splane-shape, not Herd-shape. Splane talks walk through scripture surfacing structural features — what changes from verse 9 to verse 10? What word does verse 11 introduce that wasn't in verse 9? The verses themselves are the spine; no domestic scene needed.

## Voice signature

"Notice what verse N does." "Then look at the very next verse." "Word for word — except verse N+1 adds..." "Three verses, three escalations." The listener is being walked through a structural reading, not told a story.

Tyler's voice still applies — "you know how," "right?", "and so" — but applied to text-mechanics observations, not domestic ones.

## Forbidden for Type D specifically

- ❌ Inventing connections between verses that aren't textually there. The chain must be IN the text.
- ❌ Skipping verses to make a point. If verse 11 doesn't fit, you have the wrong chunk.
- ❌ Domestic illustration as the lead. Type D opens on the SCRIPTURE-CHUNK, not on a relational scene. (You may briefly mention a domestic parallel at the landing, but the spine is the verses.)
- ❌ Single-verse focus. If only one verse is doing work, use Type A or F.

## Worked example — passing Type D

> *Look at the progression in Luke 6:27-28. Three commands. Each one harder than the last. Verse 27: "Do good to those hating you." Action — buy them lunch, help them when their car breaks down. Verse 28a: "Bless those cursing you." Now it's not just action, it's speech. You have to say something good back when they curse you. Then verse 28b: "Pray for those who are insulting you." This is the deepest one. Now it's not action and not speech — it's the inside of you. You have to TALK TO JEHOVAH about them. Three verbs, escalating from outside-in. And that last one — Jesus said it from the stake himself. "Father, forgive them, they don't know what they're doing." He climbed all three rungs of his own ladder on the day of his execution. So when somebody insults you this week, the question isn't whether you can do good or even bless. It's whether you can climb to the third rung. Get on your knees about them tonight. That's the rung Jesus stood on.*

**What works**: chunk named ("Luke 6:27-28"), verses walked one at a time, the *progression* (outside → speech → inside) is the gem. Closing turns to listener with the third-rung instruction.

## Your output — return ONLY this JSON

```json
{
  "comment_type": "D",
  "scripture_chunk": "Luke 6:27-28",
  "verses_walked": [
    {"verse": "6:27", "what_it_does": "action — do good", "shift_from_previous": "starts the ladder"},
    {"verse": "6:28a", "what_it_does": "speech — bless", "shift_from_previous": "outside → mouth"},
    {"verse": "6:28b", "what_it_does": "interior — pray", "shift_from_previous": "mouth → heart"}
  ],
  "cumulative_argument": "the chain's overall claim in one sentence",
  "content": "130-200 word comment text",
  "audience_state_at_open": "real specific weight, named in first 30 words",
  "transformation_mechanism": "release | equip | invert",
  "audience_state_at_close": "renamed feeling, named in last 30 words",
  "memorable_line": "substring of content"
}
```
