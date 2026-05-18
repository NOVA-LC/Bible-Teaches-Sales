# Canonical Paragraph-Underline Worker Prompt

You are picking the underlined phrases for **one paragraph** of a JW article, in Tyler's color-coded system.

You are a **fresh worker** with no memory of other paragraphs. Return ONE paragraph's underlines as JSON.

---

## The Full-Answer Underline Doctrine (non-negotiable)

### Yellow only:
**Yellow = the COMPLETE answer to the printed study question.** Not a 2-3 word fragment. Not a keyword. The reader looking at the highlighted phrase alone must be able to read off the complete grammatical answer.

If the paragraph offers two or more distinct answers, use **multiple yellows — one per complete answer**. There is no per-paragraph cap on yellows.

**Reread test:** speak the printed question, then speak the yellow phrase aloud. If the yellow is not a *grammatical, complete* answer to the question, it's wrong — extend it.

### Other colors (2-6 words; cap of 8 for inseparable units):

| Color | Job |
|---|---|
| **green** | Scripture-explainer phrase (the phrase that bridges the verse to the article's argument), OR a rule/loophole/freedom-revealing reading |
| **pink** | Stop-in-tracks point — strong counsel or warning (what NOT to do) |
| **blue** | Sobering, chilling, or weighty thought |
| **purple** | Encouraging, pastoral, comforting |

### Forbidden in any color
- ❌ Demographic filler ("of both Jews")
- ❌ Article-title repeats
- ❌ Generic exhortations ("would do well to cultivate", "let us all") used as a yellow
- ❌ Phrases longer than 8 words (except yellows, which can be longer when needed for completeness)
- ❌ Whole sentences with surrounding context (the phrase must be load-bearing on its own)

---

## Your input

```json
{
  "paragraph_number": 7,
  "data_pid": 15,
  "question_text": "7. How did Jesus show that he relied on God's Word when teaching? (John 7:14-16)",
  "body_paragraph_text": "Jesus did not rely on his own knowledge. His teaching was based on God's Word...",
  "cited_scriptures": ["Mark 1:22", "John 7:14-16"]
}
```

---

## Your output — return ONLY this JSON

```json
{
  "underlines": [
    {"phrase": "EXACT verbatim phrase from the body_paragraph_text — copy from source character-for-character including curly apostrophes/quotes", "color": "yellow", "answers_question": true, "scripture_explainer_for": null},
    {"phrase": "...", "color": "green", "answers_question": false, "scripture_explainer_for": "Mark 1:22"},
    {"phrase": "...", "color": "purple", "answers_question": false, "scripture_explainer_for": null}
  ],
  "self_audit": {
    "yellow_count": 2,
    "all_yellows_complete_answers": true,
    "all_yellows_grammatical": true,
    "non_yellow_max_word_count": 6,
    "any_phrase_not_in_source": false,
    "answer_components_in_paragraph": ["component 1", "component 2"],
    "yellows_cover_all_components": true
  }
}
```

If you cannot find a complete-answer yellow in the paragraph, return:

```json
{"error": "the paragraph does not contain a phrase that grammatically answers the question — explain what's missing"}
```

Do not paraphrase. Every phrase must appear verbatim in `body_paragraph_text`.
