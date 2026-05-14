"""comment_agent.py — tool-using replacement for _draft_with_gates.

Drop-in for build_week.py: same return signature as _draft_with_gates.
Activated behind --use-agent-comments flag.

Architecture:
  - Six tools (suggest_type, fetch_research, look_up_insight,
    check_register, score_with_critic, commit_comment).
  - The agent loops in a single context window: reads → optionally
    fetches research / Insight → drafts → optionally pre-flights via
    check_register or score_with_critic → commits.
  - commit_comment runs deterministic per-comment gates only. Critic
    is opt-in via score_with_critic (Flip 1 from review).
  - Hard turn cap (MAX_TURNS=20).
  - Per-paragraph token spend tracked and logged to gate history
    (lesson agent enforces the $20/article kill switch).

Drop-in contract:

    draft_comment_with_agent(
        para,                   # ParagraphData
        article_meta,           # dict
        prior_state,            # dict — see below
        model=DEFAULT_MODEL,
        extra_constraints=None, # dict — see prompt's HONORING section
    ) -> (comment_dict | None, list[GateResult])

prior_state shape:
  {
    "prior_types_used_this_article": [...],
    "prior_mechanics_this_week": [...],
    "prior_named_relationships_this_week": [...],
    "prior_herd_moves_this_week": [...],
    "forbidden_types": [...],   # honored as hard
  }
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from gates import (  # type: ignore  # noqa: E402
    GateResult,
    gate6_critic,
    gate9_jw_register,
    run_per_comment_gates,
)
from workers import SDKWorker, load_dotenv  # type: ignore  # noqa: E402
from research import fetch_deep_brief  # type: ignore  # noqa: E402


PROMPTS_DIR = _HERE / "prompts"
MAX_TURNS = 20
DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

# Sonnet 4.6 approximate pricing (USD per million tokens)
COST_INPUT_PER_MTOK = 3.0
COST_OUTPUT_PER_MTOK = 15.0
COST_CACHE_READ_PER_MTOK = 0.30
COST_CACHE_WRITE_PER_MTOK = 3.75

# Insight on the Scriptures publication key_symbol on WOL.
INSIGHT_KEY_SYMBOL = "it"
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
CACHE_DIR = Path.home() / ".cache" / "jwl_research"

_FATAL_ERROR_MARKERS = (
    "credit balance is too low",
    "invalid x-api-key",
    "authentication_error",
    "permission_error",
    "Your account has been disabled",
)


def _is_fatal(err: Exception) -> bool:
    return any(m in str(err) for m in _FATAL_ERROR_MARKERS)


def _load_system_prompt() -> str:
    return (PROMPTS_DIR / "comment_agent.md").read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# Cost tracking
# ----------------------------------------------------------------------

class CostTracker:
    """Accumulates token usage across the agent loop and the sub-worker
    calls it triggers (suggest_type, critique). Used to log per-paragraph
    spend to the gate history so the lesson agent can enforce a per-
    article kill switch."""

    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.turn_count = 0
        self.sub_calls = {"suggest_type": 0, "critique": 0}

    def add_usage(self, usage):
        """Accumulate from an anthropic Message.usage object."""
        if usage is None:
            return
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0

    def estimated_cost_usd(self) -> float:
        return (
            self.input_tokens / 1_000_000 * COST_INPUT_PER_MTOK
            + self.output_tokens / 1_000_000 * COST_OUTPUT_PER_MTOK
            + self.cache_read_tokens / 1_000_000 * COST_CACHE_READ_PER_MTOK
            + self.cache_write_tokens / 1_000_000 * COST_CACHE_WRITE_PER_MTOK
        )

    def summary(self) -> str:
        return (
            f"~${self.estimated_cost_usd():.3f} "
            f"(in={self.input_tokens}, cache_r={self.cache_read_tokens}, "
            f"cache_w={self.cache_write_tokens}, out={self.output_tokens}, "
            f"turns={self.turn_count}, "
            f"suggest_type={self.sub_calls['suggest_type']}, "
            f"critique={self.sub_calls['critique']})"
        )


# ----------------------------------------------------------------------
# Pre-gate constraint enforcement (H + I from review)
# ----------------------------------------------------------------------

_VALID_COMMENT_TYPES = {"A", "B", "C", "D", "F", "H"}
_VALID_HERD_MOVES = {"H1", "H2", "H3", "H4", "H5"}


def _check_constraints(
    payload: dict,
    prior_state: dict,
    extra_constraints: dict,
) -> list[GateResult]:
    """Enforce forbidden_types (Flip from review item H) and
    extra_constraints (item I) at the Python level inside commit_comment.

    The prompt teaches the agent these are hard, but the prompt is not a
    Python guard. The lesson agent will pass `forbidden_types` frequently
    (article-level Gate 11 squeeze) and `extra_constraints` on Gate 4/5
    redrafts; a single agent slip would tank an article. This catches the
    slip and returns specific failure reasons so the agent revises in-
    context.

    Returns the list of FAILED pre-gates. Empty list means clean — proceed
    to run_per_comment_gates.
    """
    fails: list[GateResult] = []

    ct = (payload.get("comment_type") or "").upper().strip()

    # Forbidden types (item H)
    forbidden = [
        (t or "").upper().strip()
        for t in (prior_state or {}).get("forbidden_types", []) or []
    ]
    if ct and ct in forbidden:
        fails.append(GateResult(
            "Pre-gate (forbidden_types)",
            False,
            f"comment_type {ct!r} is in forbidden_types {forbidden}. "
            "The orchestrator forbade this type for article-level variety "
            "(Gate 11). Pick a different type and redraft.",
        ))
        return fails  # short-circuit: no point checking other constraints

    # extra_constraints (item I)
    ec = extra_constraints or {}

    # force_domestic_scene: Type A or B with domestic_scene.present=true
    if ec.get("force_domestic_scene") is True:
        if ct not in {"A", "B"}:
            fails.append(GateResult(
                "Pre-gate (force_domestic_scene)",
                False,
                f"force_domestic_scene=true requires Type A or B "
                f"(only those types use domestic scenes), got {ct!r}.",
            ))
        else:
            ds = payload.get("domestic_scene") or {}
            if not (isinstance(ds, dict) and ds.get("present") and ds.get("named_relationship")):
                fails.append(GateResult(
                    "Pre-gate (force_domestic_scene)",
                    False,
                    "force_domestic_scene=true requires domestic_scene.present=true "
                    "with a real named_relationship (brother/mom/dad/grandma/"
                    "neighbor/coworker by name/etc.). Got: "
                    f"{ds!r}",
                ))

    # force_herd_move: herd_distinctive_moves must contain the requested move
    forced_move = ec.get("force_herd_move")
    if forced_move:
        forced_move = str(forced_move).upper().strip()
        if forced_move not in _VALID_HERD_MOVES:
            fails.append(GateResult(
                "Pre-gate (force_herd_move)",
                False,
                f"force_herd_move={forced_move!r} is not a valid H1-H5 code.",
            ))
        else:
            moves = payload.get("herd_distinctive_moves") or []
            moves_upper = [str(m).upper().strip() for m in moves if m]
            if forced_move not in moves_upper:
                fails.append(GateResult(
                    "Pre-gate (force_herd_move)",
                    False,
                    f"force_herd_move={forced_move!r} requires that move in "
                    f"herd_distinctive_moves. Got: {moves!r}",
                ))

    # force_invert_mode: transformation_mechanism must be 'invert'
    if ec.get("force_invert_mode") is True:
        mech = (payload.get("transformation_mechanism") or "").lower().strip()
        if mech != "invert":
            fails.append(GateResult(
                "Pre-gate (force_invert_mode)",
                False,
                f"force_invert_mode=true requires "
                f"transformation_mechanism='invert', got {mech!r}.",
            ))

    return fails


# ----------------------------------------------------------------------
# Tool implementations — closures over paragraph + worker + tracker
# ----------------------------------------------------------------------

def _fetch_cached(url: str, timeout: int = 30, retries: int = 1) -> str:
    """HTTP GET with disk cache. WOL's search endpoint hangs reliably on
    Python urllib (curl on the same URL completes in ~10s — likely a TLS
    keep-alive / chunked-transfer interaction). We shell out to curl as
    the primary path; urllib is a last-resort fallback if curl isn't on
    PATH. research.py's chapter fetches don't have this problem and stay
    on urllib (they hit a different URL pattern)."""
    import subprocess
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^A-Za-z0-9]+", "_", url)[:200]
    cache_path = CACHE_DIR / f"{key}.html"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        # Primary: curl
        try:
            proc = subprocess.run(
                ["curl", "-fsSL", "--max-time", str(timeout),
                 "-A", DEFAULT_UA, url],
                capture_output=True, timeout=timeout + 5,
            )
            if proc.returncode == 0 and proc.stdout:
                html = proc.stdout.decode("utf-8", errors="replace")
                cache_path.write_text(html, encoding="utf-8")
                return html
            last_err = RuntimeError(
                f"curl exit {proc.returncode}: {proc.stderr.decode('utf-8', errors='replace')[:200]}"
            )
        except FileNotFoundError:
            # curl not on PATH — fall through to urllib
            last_err = FileNotFoundError("curl not on PATH; falling back to urllib")
            break
        except Exception as e:
            last_err = e
            continue

    # Fallback: urllib (only reached if curl unavailable)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        cache_path.write_text(html, encoding="utf-8")
        return html
    except Exception as e:
        raise (last_err or e)


def _strip_html(html: str) -> str:
    """Lightweight HTML→text. Mirrors research.fetch_footnote_text approach."""
    # Strip script/style blocks first
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common entities
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&#8217;", "'").replace("&#8220;", '"').replace("&#8221;", '"')
                .replace("&#8212;", "—").replace("&#8211;", "–")
                .replace("&lt;", "<").replace("&gt;", ">"))
    return re.sub(r"\s+", " ", text).strip()


def _make_tool_handlers(
    para,
    article_meta: dict,
    prior_state: dict,
    extra_constraints: dict,
    worker: SDKWorker,
    tracker: CostTracker,
):
    """Build the dict of tool-name → handler. Closes over paragraph and
    worker so handlers stay stateless from the outside. Returns
    (handlers_dict, commit_state) where commit_state['payload'] is set
    on accepted commit and commit_state['error'] is set on agent-give-up."""
    commit_state: dict[str, Any] = {
        "payload": None,
        "error": None,
        "last_gates": [],
    }

    def suggest_type(payload: dict | None = None) -> dict:
        """Wraps worker.select_comment_type — returns the selector's
        advice. Agent decides whether to follow it."""
        # Compose the selector payload from this paragraph's data + prior state
        selector_payload = {
            "article_title": article_meta.get("article_title"),
            "study_date": article_meta.get("study_date"),
            "paragraph_number": para.paragraph_number,
            "question_text": para.question_text,
            "body_paragraph_text": para.body_text,
            "cited_scriptures": para.cited_scriptures,
            "research_brief": (payload or {}).get("research_brief", []),
            "prior_types_used_this_article": prior_state.get("prior_types_used_this_article", []),
            "forbidden_types": prior_state.get("forbidden_types", []),
        }
        try:
            tracker.sub_calls["suggest_type"] += 1
            result = worker.select_comment_type(selector_payload)
            tracker.add_usage(getattr(worker, "last_usage", None))
            return result
        except Exception as e:
            return {"error": f"selector failed: {e}"}

    def fetch_research(citation: str, context_window: int = 3,
                       max_xrefs: int = 5) -> dict:
        """Wraps research.fetch_deep_brief for one citation. Returns the
        DeepBrief serialized (verses, contexts, cross-refs, footnotes)."""
        try:
            brief = fetch_deep_brief(
                paragraph_text="",
                explicit_citations=[citation],
                context_window=context_window,
                max_xrefs_per_verse=max_xrefs,
                max_footnotes_per_verse=3,
            )
            if not brief.cited_studies:
                return {"ok": False, "reason": f"could not parse citation: {citation!r}"}
            return {
                "ok": True,
                "studies": [
                    {
                        "citation": vs.citation,
                        "text": vs.text[:500],
                        "context_before": vs.context_before[-3:],
                        "context_after": vs.context_after[:3],
                        "cross_refs": vs.cross_refs[:max_xrefs],
                        "footnotes": vs.footnotes[:3],
                    }
                    for vs in brief.cited_studies
                ],
            }
        except Exception as e:
            return {"ok": False, "reason": f"fetch failed: {e}"}

    def look_up_insight(topic: str) -> dict:
        """Search WOL's Insight on the Scriptures publication for `topic`.
        Returns first matched entry's title, snippet, URL.

        Best-effort: WOL's search HTML structure may shift. If parsing fails
        or no Insight result lands, returns ok=false. The prompt teaches the
        agent that a no-result lookup means "pick a different type, do not
        manufacture context."
        """
        if not topic or not topic.strip():
            return {"ok": False, "reason": "empty topic"}
        q = urllib.parse.quote_plus(topic.strip())
        search_url = (
            f"https://wol.jw.org/en/wol/s/r1/lp-e?q={q}&p={INSIGHT_KEY_SYMBOL}"
        )
        try:
            html = _fetch_cached(search_url)
        except Exception as e:
            return {"ok": False, "reason": f"search fetch failed: {e}"}
        # Find the first Insight result. WOL search results render as
        # <a class="..."> with hrefs like:
        #   /en/wol/d/r1/lp-e/1001070107?q=skin+for+skin&amp;p=par
        # The p=it query restricts the results to Insight, so any matching
        # link in the body is an Insight entry. Take the first.
        m = re.search(
            r'href="(/en/wol/d/r1/lp-e/\d+(?:[?#][^"]*)?)"',
            html,
        )
        if not m:
            return {"ok": False, "reason": f"no Insight entry for {topic!r}"}
        # HTML-unescape: WOL renders &amp; in href, urllib sees the entity
        # literally and the request 400s. Strip query params entirely — the
        # base entry URL alone resolves to the Insight article.
        href = m.group(1).split("?")[0].split("#")[0]
        entry_url = f"https://wol.jw.org{href}"
        try:
            entry_html = _fetch_cached(entry_url)
        except Exception as e:
            return {"ok": False, "reason": f"entry fetch failed: {e}"}
        # Extract the title (first <h1>) and a sizable body snippet.
        title_m = re.search(r"<h1[^>]*>(.*?)</h1>", entry_html, re.DOTALL)
        title = _strip_html(title_m.group(1)) if title_m else ""
        # Find the body container — WOL articles wrap body in <div id="article">
        body_m = re.search(r'<div\s+id="article"[^>]*>(.*?)</div>\s*</article>', entry_html, re.DOTALL)
        body_html = body_m.group(1) if body_m else entry_html
        body_text = _strip_html(body_html)[:3000]
        return {
            "ok": True,
            "title": title,
            "url": entry_url,
            "text": body_text,
        }

    def check_register(text: str) -> dict:
        """Wraps gate9_jw_register. Returns ok + issues with suggestions."""
        if not isinstance(text, str):
            return {"ok": False, "reason": "text must be a string"}
        result = gate9_jw_register({"content": text})
        if result.passed:
            return {"ok": True, "issues": []}
        # gate9's reason string contains the matched terms. Parse out the
        # detected terms + suggestions for the agent.
        # Format: "pastor-register word(s) in narration: [...]. Replace with JW-native: ..."
        m_hits = re.search(r"in narration:\s*\[([^\]]+)\]", result.reason)
        hits = []
        if m_hits:
            for tok in m_hits.group(1).split(","):
                hits.append(tok.strip().strip("'\""))
        return {"ok": False, "issues": hits, "raw": result.reason}

    def score_with_critic(comment_payload: dict,
                          paragraph_data: dict | None = None) -> dict:
        """Spawns a separate Sonnet critic worker (workers.critique).
        Returns the FULL critic verdict so the agent sees overall_pass,
        redraft_guidance, and all the boolean sub-fields verbatim."""
        if not isinstance(comment_payload, dict):
            return {"error": "comment_payload must be a dict"}
        pdata = paragraph_data or {
            "question_text": para.question_text,
            "body_paragraph_text": para.body_text,
        }
        critic_input = {
            "paragraph_number": para.paragraph_number,
            "question_text": pdata.get("question_text"),
            "body_paragraph_text": pdata.get("body_paragraph_text"),
            "comment_content": comment_payload.get("content"),
            "claimed_rotation": comment_payload.get("rotation"),
            "claimed_spine_image": comment_payload.get("spine_image"),
            "claimed_memorable_line": comment_payload.get("memorable_line"),
        }
        try:
            tracker.sub_calls["critique"] += 1
            verdict = worker.critique(critic_input)
            tracker.add_usage(getattr(worker, "last_usage", None))
            return verdict  # pass through verbatim
        except Exception as e:
            return {
                "error": f"critic call failed: {e}",
                "overall_pass": False,
                "redraft_guidance": "(critic unavailable — try again or commit and let gates decide)",
            }

    def commit_comment(**payload) -> dict:
        """Submit final comment OR self-declared error.

        Dual-variant input (Claude passes fields at top level — handler
        accepts arbitrary kwargs and treats them as the payload dict):
          {"error": "..."}   → agent give-up; loop terminates with None
          {...full payload}  → run deterministic per-comment gates (no critic)
        """
        # Variant 1: self-declared error → agent giving up
        if "error" in payload and isinstance(payload["error"], str):
            commit_state["error"] = payload["error"]
            commit_state["last_gates"] = [GateResult(
                "Comment agent self-rejected", False,
                f"agent reported: {payload['error']}",
            )]
            return {
                "accepted": True,  # accepted as a terminator, not as success
                "terminated_by": "agent_error",
                "gate_results": [
                    {"gate": g.gate, "passed": g.passed, "reason": g.reason}
                    for g in commit_state["last_gates"]
                ],
            }

        # Variant 2: full payload → constraint pre-gates → standard gates.
        # Pre-gates (H + I) catch agent-side rule violations before the
        # type-aware gates run, so the agent gets a precise reason and the
        # lesson agent's article-level gates aren't burdened with cleanup.
        pre_fails = _check_constraints(payload, prior_state, extra_constraints)
        if pre_fails:
            commit_state["last_gates"] = pre_fails
            return {
                "accepted": False,
                "gate_results": [
                    {"gate": g.gate, "passed": g.passed, "reason": g.reason}
                    for g in pre_fails
                ],
            }

        gate_results = run_per_comment_gates(payload)
        passed = all(g.passed for g in gate_results)
        commit_state["last_gates"] = gate_results
        if passed:
            # Augment with paragraph metadata (mirrors _draft_with_gates:346-348)
            payload["paragraph_number"] = para.paragraph_number
            payload["body_pid"] = para.body_pid
            payload["question_pid"] = para.question_pid
            commit_state["payload"] = payload
        return {
            "accepted": passed,
            "gate_results": [
                {"gate": g.gate, "passed": g.passed, "reason": g.reason}
                for g in gate_results
            ],
        }

    handlers = {
        "suggest_type": suggest_type,
        "fetch_research": fetch_research,
        "look_up_insight": look_up_insight,
        "check_register": check_register,
        "score_with_critic": score_with_critic,
        "commit_comment": commit_comment,
    }
    return handlers, commit_state


# ----------------------------------------------------------------------
# Tool schemas
# ----------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "name": "suggest_type",
        "description": (
            "Advisory: get the type selector's recommendation for which "
            "comment type (A/B/C/D/F/H) fits this paragraph. Returns "
            "{chosen_type, rationale, alternates_considered}. You may "
            "override the recommendation. Costs one Sonnet call — at most "
            "once per paragraph."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "payload": {
                    "type": "object",
                    "description": "Optional. May include research_brief if you've already fetched it.",
                },
            },
        },
    },
    {
        "name": "fetch_research",
        "description": (
            "Pull NWT verse text + N verses of context + cross-reference "
            "targets + footnotes from WOL for one cited scripture. Disk-"
            "cached. Cheap on cache hit. Call liberally — research depth "
            "is what makes the comment land."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "citation": {
                    "type": "string",
                    "description": "e.g., 'Job 1:6-8' or 'Isa 60:1' or '2 Tim 4:2'",
                },
                "context_window": {
                    "type": "integer",
                    "description": "Verses before and after to include (default 3).",
                },
                "max_xrefs": {
                    "type": "integer",
                    "description": "Max cross-reference verses to follow (default 5).",
                },
            },
            "required": ["citation"],
        },
    },
    {
        "name": "look_up_insight",
        "description": (
            "Search WOL's *Insight on the Scriptures* publication (key_symbol "
            "'it') for a topic / idiom / historical figure / cultural concept. "
            "Returns the first matching Insight entry's title + URL + body "
            "snippet. Required grounding for Type H — if you didn't call "
            "this (or fetch_research) for the historical fact you're "
            "claiming, return an error from Type H rather than guess."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Search query — concept, idiom, place, person, custom.",
                },
            },
            "required": ["topic"],
        },
    },
    {
        "name": "check_register",
        "description": (
            "Pre-flight a draft text against Gate 9 (JW-native register). "
            "Detects pastor / Christendom register words in narration "
            "(direct verse quotes are exempt). Returns {ok, issues, raw}. "
            "Cheap; call on suspect phrasings before commit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Draft text to check.",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "score_with_critic",
        "description": (
            "Spawns a separate Sonnet critic worker and returns the verdict: "
            "moved / encouraged / memorable / cold_read / different_domain / "
            "verse_acts_on_listener / close_state_renamed + redraft_guidance + "
            "overall_pass. The critic does NOT see your reasoning — fresh "
            "context. THIS IS THE EXPENSIVE TOOL — typically 1 call per "
            "paragraph, max 2 on hard paragraphs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "comment_payload": {
                    "type": "object",
                    "description": "The full draft comment (content, rotation, spine_image, memorable_line, etc.).",
                },
                "paragraph_data": {
                    "type": "object",
                    "description": "Optional. Defaults to this paragraph's question + body.",
                },
            },
            "required": ["comment_payload"],
        },
    },
    {
        "name": "commit_comment",
        "description": (
            "Submit the final comment OR self-declared give-up. Pass the "
            "comment fields at the TOP LEVEL of the input — not wrapped in "
            "a 'payload' object. Orchestrator runs deterministic per-comment "
            "gates (1, 1b, 1c, 3, 9, 10) and returns the verdict. Critic "
            "is NOT run by commit. If accepted=true → done, stop. If "
            "accepted=false → read gate_results, revise surgically, recommit. "
            "Two variants: pass full comment fields (comment_type, content, "
            "etc.) OR pass a single 'error' field with a string explanation."
        ),
        "input_schema": {
            "type": "object",
            "description": "Pass comment fields at top level.",
            "properties": {
                "comment_type": {"type": "string", "enum": ["A", "B", "C", "D", "F", "H"]},
                "content": {"type": "string", "description": "130-200 word comment text"},
                "audience_state_at_open": {"type": "string"},
                "audience_state_at_close": {"type": "string"},
                "transformation_mechanism": {"type": "string", "enum": ["release", "equip", "invert"]},
                "memorable_line": {"type": "string"},
                "rotation": {"type": "string", "description": "Type A only"},
                "spine_image": {"type": "string", "description": "Type A only"},
                "tagged_beats": {"type": "array", "description": "Type A only: 3-4 beats with mechanic tags"},
                "domestic_scene": {"type": "object", "description": "Type A/B only: {present, named_relationship, scene_summary}"},
                "herd_distinctive_moves": {"type": "array", "description": "Optional list of H1-H5 codes"},
                "different_domain_check": {"type": "string", "description": "Type A only: short audit"},
                "the_moment": {"type": "string", "description": "Type B only"},
                "the_internal_turn": {"type": "string", "description": "Type B only"},
                "the_verse_confirms": {"type": "string", "description": "Type B only"},
                "situation": {"type": "string", "description": "Type C only"},
                "tool": {"type": "string", "description": "Type C only"},
                "result": {"type": "string", "description": "Type C only"},
                "verse_role": {"type": "string", "description": "Type C only"},
                "scripture_chunk": {"type": "string", "description": "Type D only"},
                "verses_walked": {"type": "array", "description": "Type D only"},
                "cumulative_argument": {"type": "string", "description": "Type D only"},
                "the_weight": {"type": "string", "description": "Type F only"},
                "the_verse_balm": {"type": "string", "description": "Type F only"},
                "the_renamed_state": {"type": "string", "description": "Type F only"},
                "what_we_think_today": {"type": "string", "description": "Type H only"},
                "what_they_heard": {"type": "string", "description": "Type H only"},
                "source": {"type": "string", "description": "Type H only — must reference a look_up_insight or fetch_research result"},
                "the_relanding": {"type": "string", "description": "Type H only"},
                "error": {"type": "string", "description": "If you can't satisfy gates within the turn budget, pass this field with a specific explanation."},
            },
            "additionalProperties": True,
        },
        # Cache the tool array (one breakpoint on the last tool covers all)
        "cache_control": {"type": "ephemeral"},
    },
]


# ----------------------------------------------------------------------
# Main agent loop
# ----------------------------------------------------------------------

def draft_comment_with_agent(
    para,
    article_meta: dict,
    prior_state: dict,
    model: str = DEFAULT_MODEL,
    extra_constraints: dict | None = None,
    cost_tracker: "CostTracker | None" = None,
):
    """Drop-in replacement for build_week._draft_with_gates.

    Returns (comment_payload | None, gate_history). On agent-side give-up
    via commit_comment({"error": ...}), returns (None, history) with a
    GateResult capturing the agent's reason. On turn-budget exhaustion,
    returns (None, history) with the last gate trace.

    When invoked by the lesson agent, pass a shared `cost_tracker` so
    per-paragraph spend rolls up into the article-level kill switch.
    Otherwise a fresh tracker is created and the summary is logged in
    history (build_week's existing path).
    """
    load_dotenv()
    extra_constraints = extra_constraints or {
        "force_domestic_scene": False,
        "force_herd_move": None,
        "force_invert_mode": False,
        "experience_seed": None,
    }
    history: list[GateResult] = []
    tracker = cost_tracker if cost_tracker is not None else CostTracker()

    try:
        from anthropic import Anthropic
    except ImportError:
        history.append(GateResult(
            "Comment agent", False,
            "anthropic SDK not installed (pip install anthropic)",
        ))
        return (None, history)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        history.append(GateResult(
            "Comment agent", False,
            "ANTHROPIC_API_KEY not set in .env",
        ))
        return (None, history)

    try:
        worker = SDKWorker(model=model)
    except RuntimeError as e:
        history.append(GateResult("Comment agent", False, f"worker init: {e}"))
        return (None, history)

    client = Anthropic()
    system_prompt = _load_system_prompt()
    handlers, state = _make_tool_handlers(
        para, article_meta, prior_state, extra_constraints, worker, tracker,
    )

    user_payload = {
        "article_title": article_meta.get("article_title"),
        "article_source": article_meta.get("article_source"),
        "study_date": article_meta.get("study_date"),
        "paragraph_number": para.paragraph_number,
        "body_pid": para.body_pid,
        "question_pid": para.question_pid,
        "question_text": para.question_text,
        "body_paragraph_text": para.body_text,
        "cited_scriptures": para.cited_scriptures,
        "prior_types_used_this_article": prior_state.get("prior_types_used_this_article", []),
        "prior_mechanics_this_week": prior_state.get("prior_mechanics_this_week", []),
        "prior_named_relationships_this_week": prior_state.get("prior_named_relationships_this_week", []),
        "prior_herd_moves_this_week": prior_state.get("prior_herd_moves_this_week", []),
        "forbidden_types": prior_state.get("forbidden_types", []),
        "extra_constraints": extra_constraints,
    }

    messages: list[dict] = [{
        "role": "user",
        "content": json.dumps(user_payload, indent=2, ensure_ascii=False),
    }]

    for turn in range(1, MAX_TURNS + 1):
        tracker.turn_count = turn
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                tools=TOOLS,
                messages=messages,
            )
        except Exception as e:
            history.append(GateResult(
                f"Comment agent turn {turn}", False, f"SDK error: {e}",
            ))
            if _is_fatal(e):
                raise SystemExit(
                    f"\n❌ FATAL: {str(e)[:200]}\n"
                    f"   Fix at https://console.anthropic.com/ then rerun."
                )
            history.append(GateResult("Comment agent", False, f"cost {tracker.summary()}"))
            return (None, history)

        tracker.add_usage(getattr(resp, "usage", None))
        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]

        if not tool_uses:
            text_blocks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
            history.append(GateResult(
                f"Comment agent turn {turn}", False,
                f"agent stopped without committing (stop_reason="
                f"{resp.stop_reason}): {(' '.join(text_blocks))[:200]}",
            ))
            history.append(GateResult("Comment agent", False, f"cost {tracker.summary()}"))
            return (None, history)

        messages.append({"role": "assistant", "content": resp.content})

        tool_results_blocks = []
        terminated = False
        for tu in tool_uses:
            name = tu.name
            args = tu.input or {}
            handler = handlers.get(name)
            if handler is None:
                result = {"error": f"unknown tool: {name}"}
            else:
                try:
                    result = handler(**args)
                except TypeError as e:
                    # Bad input shape — return as a tool result so agent can fix.
                    # Surface the offending kwargs and the schema hint so the
                    # agent can self-correct on the next turn instead of looping.
                    result = {
                        "error": f"bad input to {name}: {e}",
                        "received_keys": sorted(list(args.keys())) if isinstance(args, dict) else None,
                        "hint": (
                            "commit_comment expects comment fields at TOP LEVEL (not nested in 'payload'). "
                            "Other tools: see input_schema for required kwargs."
                        ),
                    }
                except Exception as e:
                    if _is_fatal(e):
                        raise SystemExit(
                            f"\n❌ FATAL: {str(e)[:200]}\n"
                            f"   Fix at https://console.anthropic.com/ then rerun."
                        )
                    result = {"error": f"{name} raised: {e}"}
            tool_results_blocks.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })
            # commit_comment terminates the loop on either accepted=true variant
            if name == "commit_comment" and result.get("accepted"):
                terminated = True

        messages.append({"role": "user", "content": tool_results_blocks})

        if terminated:
            # Append the last gate trace to history so build_week can log it
            for g in state["last_gates"]:
                history.append(g)
            if state["payload"] is not None:
                history.append(GateResult(
                    "Comment agent", True,
                    f"committed in {turn} turn(s); cost {tracker.summary()}",
                ))
                return (state["payload"], history)
            else:
                # Agent self-declared error variant
                history.append(GateResult(
                    "Comment agent", False,
                    f"agent gave up after {turn} turn(s) "
                    f"(reason: {state['error']!r}); cost {tracker.summary()}",
                ))
                return (None, history)

    # Turn budget exhausted
    history.append(GateResult(
        "Comment agent", False,
        f"reached MAX_TURNS={MAX_TURNS} without commit; cost {tracker.summary()}",
    ))
    if state["last_gates"]:
        for g in state["last_gates"]:
            history.append(g)
    return (None, history)


# ----------------------------------------------------------------------
# CLI for quick testing on a single paragraph
# ----------------------------------------------------------------------

def _cli():
    """python -m agent.comment_agent --question "..." --body "..." [--cited Mark 1:22] [--paragraph-number N]"""
    import argparse
    from dataclasses import dataclass

    @dataclass
    class _Para:
        paragraph_number: int
        body_pid: int
        question_pid: int | None
        question_text: str | None
        body_text: str
        cited_scriptures: list[str]

    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--question", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--cited", action="append", default=[])
    p.add_argument("--paragraph-number", type=int, default=1)
    p.add_argument("--body-pid", type=int, default=1)
    p.add_argument("--question-pid", type=int, default=2)
    p.add_argument("--article-title", default="(test)")
    p.add_argument("--study-date", default="2026-05-17")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--forbidden-types", default="", help="Comma-separated")
    p.add_argument("--force-domestic-scene", action="store_true")
    args = p.parse_args()

    para = _Para(
        paragraph_number=args.paragraph_number,
        body_pid=args.body_pid,
        question_pid=args.question_pid,
        question_text=args.question,
        body_text=args.body,
        cited_scriptures=args.cited,
    )
    article_meta = {
        "article_title": args.article_title,
        "article_source": "(test)",
        "study_date": args.study_date,
    }
    prior_state = {
        "prior_types_used_this_article": [],
        "prior_mechanics_this_week": [],
        "prior_named_relationships_this_week": [],
        "prior_herd_moves_this_week": [],
        "forbidden_types": [t.strip() for t in args.forbidden_types.split(",") if t.strip()],
    }
    extra_constraints = {
        "force_domestic_scene": args.force_domestic_scene,
        "force_herd_move": None,
        "force_invert_mode": False,
        "experience_seed": None,
    }
    payload, history = draft_comment_with_agent(
        para, article_meta, prior_state,
        model=args.model, extra_constraints=extra_constraints,
    )
    print("--- Gate history ---")
    for g in history:
        print(f"  {g}")
    print("\n--- Payload ---")
    print(json.dumps(payload, indent=2, ensure_ascii=False) if payload else "None")
    return 0 if payload else 1


if __name__ == "__main__":
    sys.exit(_cli())
