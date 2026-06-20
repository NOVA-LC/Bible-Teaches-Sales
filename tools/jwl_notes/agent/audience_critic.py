"""audience_critic.py — Gemini 3.5-flash as a brother-in-the-third-row audience critic.

Cross-family critic for Tyler-voice comments. Used by the lesson agent (or
by hand) to validate that a draft comment doesn't just reword the paragraph,
sounds spoken not platform-preacher, and actually uplifts the audience.

Two reasons this lives outside `workers.py`:

  1. It calls a NON-Anthropic model (Gemini), via REST (not gRPC — the sandbox
     proxy breaks Google's grpc trust chain; the official google-generativeai
     SDK fails to authenticate. REST works because it uses the same HTTP path
     that research.py already proved out).
  2. The audience critic is a quality gate, NOT a drafter. Routing it
     separately keeps `workers.py` Anthropic-only and avoids muddying the
     SDKWorker interface.

Loads its system prompt from `prompts/audience_critic.md` (the doctrine,
versioned alongside the type prompts).

Public surface:

  client = AudienceCritic()                       # reads GOOGLE_API_KEY from .env
  verdict = client.critique(article_meta, paragraph_text, question_text, comment_text)
  flawless = AudienceCritic.is_flawless(verdict)

Returns a dict matching the schema in prompts/audience_critic.md, plus a
`_model` field naming which Gemini model actually answered (primary vs
fallback) and `_usage` with the total token count.

Backoff strategy: 5 attempts on `gemini-3.5-flash` with 15-second sleeps on
429, then one final attempt on `gemini-2.5-flash` as fallback. Free-tier
quotas are tight; this absorbs typical rate-limit blips.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Re-use the .env loader and prompt loader from workers.py — no duplication.
# Try relative import first (when loaded as `agent.audience_critic`), fall
# back to absolute (when imported directly from outside the package).
try:
    from .workers import load_dotenv, _load_prompt  # type: ignore  # noqa: E402
except ImportError:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from workers import load_dotenv, _load_prompt  # type: ignore  # noqa: E402


PRIMARY_MODEL = "gemini-3.5-flash"
# Fallback chain in order — each is tried with the same backoff. 3.5-flash
# is the smartest; 2.5-flash is the workhorse; 2.5-flash-lite is the safety
# net when the free-tier daily quota on the better models is exhausted.
FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-2.5-flash-lite")
FALLBACK_MODEL = FALLBACK_MODELS[0]  # back-compat alias
_REST_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)

# Field tags that must ALL be true for a verdict to count as "flawless".
# (Bool fields only — string fields like what_landed are handled separately.)
_REQUIRED_TRUE_FIELDS = (
    "is_unique_thought",
    "enjoyed",
    "uplifted_or_encouraged",
    "makes_sense_first_hearing",
    "verse_acts_on_listener",
    "voice_authentic_spoken",
    "speaker_not_centered",
    "accessible_to_new_brother",
    "sincere_not_performative",
    "overall_pass",
)
# These may be null when the comment has no illustration or cross-ref;
# null counts as "doesn't apply, not a failure."
_REQUIRED_TRUE_OR_NULL_FIELDS = (
    "illustration_serves_verse",
    "illustration_relatable",
    "cross_refs_meaningful",
)
# This is the inverse — must be FALSE for a pass.
_REQUIRED_FALSE_FIELDS = ("is_rewording",)


class AudienceCriticError(RuntimeError):
    """Raised when the critic can't get a verdict after fallback exhausts."""


class AudienceCritic:
    """Brother-in-the-third-row critic, backed by Gemini via REST."""

    def __init__(
        self,
        primary_model: str = PRIMARY_MODEL,
        fallback_models: tuple[str, ...] = FALLBACK_MODELS,
        max_retries: int = 3,
        retry_sleep_s: int = 15,
        timeout_s: int = 90,
    ):
        load_dotenv()
        self._key = os.environ.get("GOOGLE_API_KEY")
        if not self._key:
            raise RuntimeError(
                "GOOGLE_API_KEY not set. Drop it into "
                "tools/jwl_notes/agent/.env as: GOOGLE_API_KEY=AIza..."
            )
        self.primary_model = primary_model
        self.fallback_models = tuple(fallback_models)
        self.max_retries = max_retries
        self.retry_sleep_s = retry_sleep_s
        self.timeout_s = timeout_s
        self._system_prompt = _load_prompt("audience_critic.md")

    # -- public --------------------------------------------------------

    def critique(
        self,
        article_title: str,
        paragraph_number: int,
        paragraph_body: str,
        question_text: str,
        comment_text: str,
    ) -> dict[str, Any]:
        """Run the critic. Returns the verdict dict (see prompts/audience_critic.md).

        Adds `_model` and `_usage` keys. Raises AudienceCriticError if both
        primary and fallback fail after backoff.
        """
        user_msg = self._format_user_message(
            article_title, paragraph_number, paragraph_body, question_text, comment_text
        )

        last_err: Exception | None = None
        # Walk primary → each fallback in sequence. On 429 (quota), the next
        # model in the chain probably has its own quota bucket; try it before
        # burning more time on retries. On 503 (transient), retry the same
        # model after a brief sleep.
        for model in (self.primary_model, *self.fallback_models):
            for attempt in range(self.max_retries):
                try:
                    verdict = self._call(model, user_msg)
                    verdict["_model"] = model
                    return verdict
                except urllib.error.HTTPError as e:
                    last_err = e
                    if e.code == 429:
                        # Quota — skip to next model in the chain.
                        break
                    if e.code in (500, 502, 503, 504):
                        # Transient — wait and retry this same model.
                        time.sleep(self.retry_sleep_s)
                        continue
                    # Other HTTP error — bail to next model.
                    break
                except Exception as e:
                    last_err = e
                    break
        raise AudienceCriticError(
            f"Critic failed across {[self.primary_model, *self.fallback_models]}: "
            f"last error: {last_err!r}"
        )

    @staticmethod
    def is_flawless(verdict: dict[str, Any]) -> bool:
        """A verdict is FLAWLESS iff overall_pass and no critic notes.

        i.e. overall_pass=true AND what_didnt empty AND redraft_guidance empty
        AND every required-true field is true AND is_rewording is false.
        """
        if not verdict.get("overall_pass"):
            return False
        if (verdict.get("what_didnt") or "").strip():
            return False
        if (verdict.get("redraft_guidance") or "").strip():
            return False
        for field in _REQUIRED_TRUE_FIELDS:
            if verdict.get(field) is not True:
                return False
        for field in _REQUIRED_FALSE_FIELDS:
            if verdict.get(field) is not False:
                return False
        for field in _REQUIRED_TRUE_OR_NULL_FIELDS:
            v = verdict.get(field)
            if v is False:
                return False
        return True

    @staticmethod
    def failing_fields(verdict: dict[str, Any]) -> list[str]:
        """Return the names of bool fields that block a flawless verdict."""
        fails: list[str] = []
        for field in _REQUIRED_TRUE_FIELDS:
            if verdict.get(field) is not True:
                fails.append(field)
        for field in _REQUIRED_FALSE_FIELDS:
            if verdict.get(field) is not False:
                fails.append(field)
        for field in _REQUIRED_TRUE_OR_NULL_FIELDS:
            if verdict.get(field) is False:
                fails.append(field)
        return fails

    # -- internals -----------------------------------------------------

    def _format_user_message(
        self,
        article_title: str,
        paragraph_number: int,
        paragraph_body: str,
        question_text: str,
        comment_text: str,
    ) -> str:
        return (
            f'ARTICLE: "{article_title}"\n\n'
            f"PARAGRAPH {paragraph_number} (the reader just read this aloud):\n"
            f"{paragraph_body}\n\n"
            f"PRINTED QUESTION (the conductor just asked this):\n"
            f"{question_text}\n\n"
            f"COMMENT TYLER JUST GAVE:\n"
            f"{comment_text}\n\n"
            f"React. Return only the JSON."
        )

    def _call(self, model: str, user_msg: str) -> dict[str, Any]:
        url = _REST_URL.format(model=model, key=self._key)
        body = json.dumps({
            "systemInstruction": {"parts": [{"text": self._system_prompt}]},
            "contents": [{"parts": [{"text": user_msg}]}],
            "generationConfig": {
                "temperature": 0.3,
                "responseMimeType": "application/json",
            },
        }).encode()
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
            payload = json.loads(r.read())
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        # Strip any markdown fence Gemini may have wrapped the JSON in.
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
        verdict = json.loads(text)
        verdict["_usage"] = (
            payload.get("usageMetadata", {}).get("totalTokenCount", 0)
        )
        return verdict


# ----------------------------------------------------------------------
# CLI — quick smoke test on a single paragraph
# ----------------------------------------------------------------------

def _cli() -> int:
    """python -m agent.audience_critic --doc-id 2026366 --paragraph 17 \\
       --comments comments/2026-06-21-w.json
    """
    import argparse
    import sys

    p = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    p.add_argument("--doc-id", type=int, required=True,
                   help="WOL DocumentId, e.g. 2026366")
    p.add_argument("--paragraph", type=int, required=True,
                   help="Visible paragraph number to critique")
    p.add_argument("--comments", required=True,
                   help="Path to the comments JSON containing the draft")
    p.add_argument("--key-symbol", default="w")
    p.add_argument("--article-title", default="(article)")
    args = p.parse_args()

    # Local imports so the module loads without optional deps
    import sys as _sys
    _here = Path(__file__).resolve().parent
    _sys.path.insert(0, str(_here.parent))
    _sys.path.insert(0, str(_here))
    from jwl_notes import fetch_wol_article  # type: ignore  # noqa: E402
    from build_week import scrape_article  # type: ignore  # noqa: E402

    html = fetch_wol_article(args.doc_id, args.key_symbol)
    paras = {p_.paragraph_number: p_ for p_ in scrape_article(html)}
    para = paras[args.paragraph]

    comments_doc = json.load(open(args.comments))
    comment = next(
        (n["content"] for n in comments_doc["notes"]
         if n.get("paragraph") == args.paragraph and n.get("content")),
        None,
    )
    if not comment:
        print(f"No comment found for paragraph {args.paragraph} in {args.comments}",
              file=sys.stderr)
        return 2

    critic = AudienceCritic()
    verdict = critic.critique(
        article_title=args.article_title,
        paragraph_number=args.paragraph,
        paragraph_body=para.body_text,
        question_text=para.question_text or "",
        comment_text=comment,
    )
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    return 0 if AudienceCritic.is_flawless(verdict) else 1


if __name__ == "__main__":
    import sys
    sys.exit(_cli())
