# Comment Type C — Pure CTA (action-only, minimal narrative)

> Read `_shared_core.md` first.

## When this type fits

The paragraph is teaching a *practical method* — how to start a Bible study, how to handle objections, how to use a specific scripture in service, how to apply a principle Monday morning. The audience doesn't need an illustration; they need a tool.

Good fits: Apply Yourself to the Field Ministry paragraphs, "Try doing this" paragraphs, paragraphs that themselves give a method.

**Not** for: paragraphs that need pastoral comfort (Type F), historical context (Type H), or doctrinal exposition (Type D).

## The shape — three beats

```
[SITUATION]   →   [TOOL]   →   [RESULT]
     ↓             ↓            ↓
when X         do this         what happens
happens
```

Compressed. Often under 150 words (still ≥130 floor). No domestic scene, no rendered illustration. The whole comment is method + outcome.

## Voice signature

Imperative + conditional. Conditional opener pre-empts permission: *"If you've ever stood at a door and the householder cut you off mid-sentence..."* Then: *"Do this:"* + 1-2 sentence tool. Then: the verse-words that justify it OR the outcome described. Close with the renamed-feeling on the listener as confirmation.

Pure CTA can use a verse as the *tool itself* — not as ornament. Example: "Try this question next study: 'where do you see Jehovah in this verse?' — Heb 4:12, the word is alive — your student will start *finding* him on the page instead of memorizing about him."

## Forbidden for Type C specifically

- ❌ Domestic scenes. Type C has no illustration — that's the whole point.
- ❌ Vague tools ("be more patient", "show more love"). Tools must be specific, doable Monday, and have a checkable result.
- ❌ Multiple tools in one comment. One tool. One result.
- ❌ Verse acting only as proof-text after the tool. The verse must be PART of the tool or the result must be drawn from the verse.

## Worked example — passing Type C

> *If you've ever knocked on a door and the householder gave you the standard "I'm not interested" before you finished your sentence — try this. Don't argue. Don't apologize. Say one sentence: "I'd just hate to leave without leaving you the one verse I came to share — can I read it?" Most people say yes to one verse. Read 2 Peter 3:9 — Jehovah is "patient with you because he does not desire any to be destroyed." Then hand them the tract and walk. The shift that happens: you stopped trying to convince them they need the message. You let the verse decide. Their no isn't your defeat — it's data for next time. Try it Monday. Notice what changes in YOU after that door.*

**What works**: specific tool (one sentence, one verse, walk away). The verse is the tool — 2 Pet 3:9 is what they get. The result is named ("you stopped trying to convince them"). Closing turns to listener: "Try it Monday."

## Your output — return ONLY this JSON

```json
{
  "comment_type": "C",
  "situation": "when X happens",
  "tool": "the specific Monday-morning move",
  "result": "what changes — for the listener or for the situation",
  "verse_role": "the verse is the tool | the verse describes the result | both",
  "content": "130-200 word comment text",
  "audience_state_at_open": "real specific weight, named in first 30 words",
  "transformation_mechanism": "equip",
  "audience_state_at_close": "the equipped state, named in last 30 words",
  "memorable_line": "substring of content"
}
```
