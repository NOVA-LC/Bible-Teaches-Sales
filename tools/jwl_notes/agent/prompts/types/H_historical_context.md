# Comment Type H — Historical / Cultural Context (Insight-style)

> Read `_shared_core.md` first.

## When this type fits

The paragraph references something whose **historical, cultural, or linguistic context** the modern reader doesn't have. The verse takes for granted something the original audience knew that we don't. Surfacing the context changes how the verse reads forever.

Good fits: parables that reference specific customs, idioms whose meaning is cultural ("eye of a needle," "salt of the earth," "narrow gate"), references to historical events or places, sayings whose Hebrew/Greek root changes their force, NWT translation choices the article doesn't unpack.

**Not** for: paragraphs where the modern reader already has the context (Type A, F), pure-action paragraphs (Type C), narrative-progression paragraphs (Type D).

## The shape — three movements

```
[NAME WHAT WE THINK]   →   [WHAT THEY HEARD]   →   [RELANDING]
        ↓                       ↓                      ↓
"when we read X today        the cultural/             the verse now
we picture Y"                historical fact           reads differently
                             they took for granted
```

The audience walks in with one mental picture. You correct it with the historical fact. The verse RELANDS with the audience now hearing it the way the original hearers did.

## Voice signature

This is the only type where Tyler sounds slightly like a teacher of context — but still grounded, still spoken. "When we hear 'X' in 2026, we picture Y. The audience in N hundred AD heard something different. Here's what." Then the verse re-quoted with the correction in place.

Cite the source if you have one (Insight on the Scriptures entry, NWT footnote, historical record). If you can't name the source, you should not invent the context — return error and let the selector pick a different type.

## Forbidden for Type H specifically

- ❌ Inventing historical or linguistic facts. Type H must be grounded in real research — NWT footnote, Insight reference, established cultural history. If the research-brief doesn't give you the context, return `{"error": "no verified historical context available"}` and the orchestrator will pick a different type.
- ❌ "Bible scholars say..." without naming WHICH scholars or sources. Either cite or don't claim.
- ❌ Long lectures on history. Tyler's voice is still spoken. The context fits in 30-40 words; the rest is the verse relanding on the listener.
- ❌ Forcing context onto a verse that doesn't need it. If the verse's meaning is clear to the modern reader, don't manufacture a "hidden depth."

## Worked example — passing Type H

> *When we read "go and wash in the pool of Siloam" in John 9, we picture Jesus inventing a strange method to test the blind man's obedience. That's not how anyone in first-century Israel would have heard it. "Go, wash" was a phrase Naaman the leper got from Elisha eight hundred years earlier, in 2 Kings 5:10. Same Hebrew shape. Same prophet-style command. And Naaman almost walked away — verse 11 — because the instruction felt beneath him. Jesus wasn't inventing. He was QUOTING. The audience that knew their scrolls would have heard the echo immediately: this man heals the way Elisha healed. He's not just a teacher. He's a prophet in Elijah's line. So when Jehovah hands us an instruction that feels too small to matter, the question isn't whether it'll work. The question is whether we recognize whose line the instruction comes from. Go wash in the river. The pattern is older than you think.*

**What works**: corrects what the modern reader pictures ("inventing a strange method"). Surfaces the cultural/historical fact (the Naaman echo, 800 years earlier). Verse RELANDS with new force (Jesus the prophet-in-Elijah's-line). Closes turning to listener.

## Your output — return ONLY this JSON

```json
{
  "comment_type": "H",
  "what_we_think_today": "the modern misreading or default picture",
  "what_they_heard": "the historical / cultural / linguistic fact the original audience knew",
  "source": "Insight on the Scriptures | NWT footnote | 2 Kings 5 cross-reference | historical record (named)",
  "the_relanding": "how the verse reads now that the context is in place",
  "content": "130-200 word comment text",
  "audience_state_at_open": "the modern picture, named in first 30 words",
  "transformation_mechanism": "invert",
  "audience_state_at_close": "the corrected reading, named in last 30 words",
  "memorable_line": "substring of content"
}
```
