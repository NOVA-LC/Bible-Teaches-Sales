"""Worker backends for paragraph-comment / underline / critic dispatch.

Two backends:

  - SDKWorker — calls the Anthropic SDK directly. Use this for autonomous
    off-session runs (e.g., cron). Requires ANTHROPIC_API_KEY in the
    environment (loaded from .env via python-dotenv if present).

  - InSessionWorker — placeholder that raises NotImplementedError. When
    running inside Claude Code, the orchestrator is invoked by the
    parent Claude session, which dispatches workers via its Agent tool
    and writes the responses to disk for the orchestrator to pick up.
    See RUNBOOK.md for the in-session manual loop.

Both backends speak the same interface: `.draft_comment(payload)`,
`.draft_underlines(payload)`, `.critique(payload)` — each returns a dict
parsed from the worker's JSON response.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


# ----------------------------------------------------------------------
# .env loading (no python-dotenv dependency to keep this stdlib-only)
# ----------------------------------------------------------------------

def load_dotenv(env_path: Path | None = None) -> None:
    """Tiny .env loader. Reads KEY=VALUE lines, ignores comments / blanks.
    Does NOT overwrite vars already in os.environ."""
    if env_path is None:
        # Look in agent/, then in tools/jwl_notes/, then in repo root.
        here = Path(__file__).resolve().parent
        for candidate in (here / ".env", here.parent / ".env", here.parent.parent.parent / ".env"):
            if candidate.exists():
                env_path = candidate
                break
    if env_path is None or not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        # Set the var if it's missing OR currently empty. An empty shell-set
        # var (e.g., `export ANTHROPIC_API_KEY=` in .zshrc) would otherwise
        # silently block .env from loading the real key.
        if key and not os.environ.get(key):
            os.environ[key] = value


# ----------------------------------------------------------------------
# Common — load prompt templates and parse JSON-only responses
# ----------------------------------------------------------------------

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of `text`. Workers may surround the
    JSON with explanatory prose; we strip ```json fences and locate the
    first {...} block whose braces balance."""
    # Strip ``` fences if present
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        block = fence.group(1)
        return json.loads(block)
    # Otherwise scan for first balanced { ... }
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                return json.loads(text[start:i + 1])
    raise ValueError("no balanced JSON object found in worker response")


# ----------------------------------------------------------------------
# SDK worker
# ----------------------------------------------------------------------

class SDKWorker:
    """Dispatches to Claude via the official Anthropic SDK."""

    def __init__(self, model: str = "claude-sonnet-4-6", max_tokens: int = 2048):
        load_dotenv()
        try:
            import anthropic  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "Anthropic SDK not installed. Run: pip install anthropic"
            ) from e
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Drop your rotated key into "
                f"{PROMPTS_DIR.parent / '.env'} as: ANTHROPIC_API_KEY=sk-ant-..."
            )
        from anthropic import Anthropic
        self._client = Anthropic()
        self._model = model
        self._max_tokens = max_tokens
        # Legacy single-prompt drafter (kept for backward compat)
        self._comment_prompt = _load_prompt("paragraph_comment.md")
        self._underline_prompt = _load_prompt("paragraph_underlines.md")
        self._critic_prompt = _load_prompt("critic_gate6.md")
        # Free-thinking pipeline: shared core + type selector + per-type drafters
        self._shared_core = _load_prompt("_shared_core.md")
        self._select_type_prompt = _load_prompt("select_comment_type.md")
        self._type_prompts = {
            "A": _load_prompt("types/A_illustration_led.md"),
            "B": _load_prompt("types/B_experience_led.md"),
            "C": _load_prompt("types/C_pure_cta.md"),
            "D": _load_prompt("types/D_exegetical_chain.md"),
            "F": _load_prompt("types/F_pastoral_direct.md"),
            "H": _load_prompt("types/H_historical_context.md"),
        }

    def _call(self, system_prompt: str, user_payload: dict) -> dict:
        """Single SDK round-trip. Returns parsed JSON from the response."""
        # Prompt caching: cache the system prompt (large, stable across the run)
        # so repeat dispatches in the same article share a cache hit.
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": json.dumps(user_payload, indent=2, ensure_ascii=False),
            }],
        )
        # Concatenate all text blocks
        text = "".join(
            b.text for b in msg.content if getattr(b, "type", None) == "text"
        )
        return _extract_json(text)

    def draft_comment(self, payload: dict) -> dict:
        return self._call(self._comment_prompt, payload)

    def draft_underlines(self, payload: dict) -> dict:
        return self._call(self._underline_prompt, payload)

    def critique(self, payload: dict) -> dict:
        return self._call(self._critic_prompt, payload)

    # -- Free-thinking pipeline --------------------------------------------

    def select_comment_type(self, payload: dict) -> dict:
        """Phase 1 of the typed pipeline. Picks comment type A/B/C/D/F/H
        given paragraph + research_brief + prior types used this article.
        Returns {'chosen_type': 'A', 'rationale': '...', ...}."""
        return self._call(self._select_type_prompt, payload)

    def draft_typed_comment(self, comment_type: str, payload: dict) -> dict:
        """Phase 2 of the typed pipeline. Drafts a comment in the chosen
        type's specific shape. The shared core + type prompt are both
        loaded as the system prompt (concatenated, so the shared
        non-negotiables apply on top of the type-specific shape)."""
        if comment_type not in self._type_prompts:
            raise ValueError(
                f"Unknown comment type {comment_type!r}; "
                f"valid: {sorted(self._type_prompts)}"
            )
        # Compose the system prompt: shared core first (universal rules),
        # then the type-specific prompt (shape + examples + output schema).
        composed = (
            self._shared_core
            + "\n\n---\n\n"
            + self._type_prompts[comment_type]
        )
        return self._call(composed, payload)


# ----------------------------------------------------------------------
# In-session worker — file-based drop box for the parent Claude session
# ----------------------------------------------------------------------

class InSessionWorker:
    """Filesystem-based dispatch for use inside Claude Code.

    The orchestrator writes a job request to `runs/<run_id>/jobs/<job_id>.json`
    and blocks until a corresponding `runs/<run_id>/results/<job_id>.json`
    appears (or a `runs/<run_id>/errors/<job_id>.txt` does).

    The parent Claude session (this assistant) polls the jobs/ directory,
    spawns Agent tool calls per job, and writes results back. See
    RUNBOOK.md for the manual loop.

    NOTE: This is a placeholder. For tonight's demo, the orchestrator can
    be invoked with --interactive to print job payloads to stdout and
    read results from stdin instead.
    """

    def __init__(self, run_dir: Path):
        self._run_dir = run_dir
        for sub in ("jobs", "results", "errors"):
            (run_dir / sub).mkdir(parents=True, exist_ok=True)

    def draft_comment(self, payload: dict) -> dict:
        raise NotImplementedError(
            "InSessionWorker is a stub. Run the orchestrator under Claude "
            "Code with --interactive, or set ANTHROPIC_API_KEY and use "
            "SDKWorker. See RUNBOOK.md."
        )

    def draft_underlines(self, payload: dict) -> dict:
        raise NotImplementedError(self.draft_comment.__doc__)

    def critique(self, payload: dict) -> dict:
        raise NotImplementedError(self.draft_comment.__doc__)


# ----------------------------------------------------------------------
# Picker
# ----------------------------------------------------------------------

def get_worker(backend: str = "auto", run_dir: Path | None = None) -> Any:
    """Return the worker instance for the requested backend.

    `backend = "auto"` → SDK if ANTHROPIC_API_KEY is set, else InSession.
    """
    if backend == "sdk":
        return SDKWorker()
    if backend == "in_session":
        if run_dir is None:
            raise ValueError("InSessionWorker requires run_dir")
        return InSessionWorker(run_dir)
    if backend == "auto":
        load_dotenv()
        if os.environ.get("ANTHROPIC_API_KEY"):
            return SDKWorker()
        if run_dir is None:
            raise ValueError("auto-fallback to InSessionWorker requires run_dir")
        return InSessionWorker(run_dir)
    raise ValueError(f"unknown backend: {backend}")
