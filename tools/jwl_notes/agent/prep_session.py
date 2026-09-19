"""Model-independent, resumable comment preparation for Work/chat sessions.

No SDK calls, environment loading, network access, or automatic quality verdicts.
Use prepare -> plan -> draft -> review -> [repair -> review] -> export.
State is authoritative; request packets are reproducible views. Export is comments
only: underlines require the separate existing preparation workflow.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .gates import run_article_gates, run_per_comment_gates, _COMMENT_TYPES
import inspect

HERE = Path(__file__).resolve().parent
REVIEW_CHECKS = (
    "accuracy", "paragraph_fit", "no_future_leakage", "voice_and_depth",
    "cold_read", "different_domain", "moved", "encouraged", "memorable",
    "verse_acts_on_listener", "close_state_renamed",
)
POLICY = """Read the whole article and approved voice references before planning.
Plan each question-bearing paragraph's purpose, distinct angle, and points reserved
for later paragraphs. An early paragraph must not consume a later payoff (for
example paragraph 10 must not spend paragraph 14's point). Draft from that plan.
Preserve all existing prompt quality standards and deterministic gates. Accepted
comments are frozen. Review every requested paragraph independently against the
source, plan, all drafts, accepted comments, and approved voice references. Return
specific evidence in reason, including a concrete defect for every failure. Never
claim a check passes merely because its metadata is present. One targeted repair
per failed paragraph is allowed; unresolved failures block export. Do not weaken
quality gates to reduce iteration. A review is an external judgment, not a proof
of semantic quality supplied by this engine."""


class SessionError(ValueError):
    """An explicit, user-actionable checkpoint validation failure."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def policy_documents():
    return {str(p.relative_to(HERE)): p.read_text(encoding="utf-8")
            for p in sorted((HERE / "prompts").rglob("*.md"))}


def draft_documents():
    return {name: text for name, text in policy_documents().items()
            if name == "prompts/comment_agent.md" or name.startswith("prompts/types/")}


def policy_fingerprint():
    return digest({"policy": POLICY, "checks": REVIEW_CHECKS,
                   "prompts": policy_documents(),
                   "voice_recipe": (HERE.parent / "voice" / "drafting-recipe.md").read_text(encoding="utf-8"),
                   "gates": (HERE / "gates.py").read_text(encoding="utf-8"),
                   "engine": Path(__file__).read_text(encoding="utf-8"),
                   "assembly": (HERE / "build_week.py").read_text(encoding="utf-8")})


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SessionError(f"Cannot read JSON {path}: {exc}") from exc


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def locked(run_dir):
    # Prevent overlapping commands from losing immutable locks/repair counts.
    import fcntl
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / ".session.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield run_dir


def require(condition, message):
    if not condition:
        raise SessionError(message)


def positive_id(value, label):
    require(type(value) is int and value > 0, f"{label} must be a positive integer (not a boolean)")
    return value


def nonempty(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label} must be nonempty text")


def indexed(rows, label):
    require(isinstance(rows, list) and bool(rows), f"{label} must be a nonempty list")
    result = {}
    for row in rows:
        require(isinstance(row, dict), f"{label} entries must be objects")
        number = positive_id(row.get("paragraph_number"), f"{label}.paragraph_number")
        key = str(number)
        require(key not in result, f"Duplicate paragraph {number} in {label}")
        result[key] = row
    return result


def validate_source(source):
    require(isinstance(source, dict), "Article must be an object")
    meta = source.get("article_meta")
    require(isinstance(meta, dict), "article_meta must be an object")
    for name in ("article_title", "article_source", "study_date", "key_symbol", "url"):
        nonempty(meta.get(name), f"article_meta.{name}")
    require(meta["key_symbol"] == "w", "Checkpoint preparation currently supports single-document Watchtower articles only; use existing CBS/Gems workflows")
    for name in ("issue", "document_id"):
        positive_id(meta.get(name), f"article_meta.{name}")
    try:
        date.fromisoformat(meta["study_date"])
    except ValueError as exc:
        raise SessionError("study_date must be an ISO date") from exc
    paras = indexed(source.get("paragraphs"), "paragraphs")
    body_pids = set()
    for p in paras.values():
        require(p.get("source_lesson_doc_id") is None, "Multiple-source lessons require the existing CBS workflow")
        pid = positive_id(p.get("body_pid"), "body_pid")
        require(pid not in body_pids, f"Duplicate body_pid {pid}")
        body_pids.add(pid)
        nonempty(p.get("body_text"), "body_text")
        require("question_pid" in p and "question_text" in p, "Each paragraph needs question_pid and question_text (null when absent)")
        if p["question_pid"] is not None:
            positive_id(p["question_pid"], "question_pid")
            nonempty(p["question_text"], "question_text")
        else:
            require(p["question_text"] in (None, ""), "Question text requires a question_pid")
        require(isinstance(p.get("cited_scriptures"), list), "cited_scriptures must be a list")
        for citation in p["cited_scriptures"]:
            nonempty(citation, "cited_scriptures entry")
    question_count = sum(p["question_pid"] is not None for p in paras.values())
    require(question_count > 0, "Article has no question-bearing paragraphs")
    from .gates import gate11_comment_type_variety
    hard_cap = inspect.signature(gate11_comment_type_variety).parameters["hard_cap"].default
    capacity = len(_COMMENT_TYPES) * hard_cap
    require(question_count <= capacity, f"Gate 11 makes complete coverage impossible: {question_count} question-bearing paragraphs exceed {capacity} comments across the allowed types. Resolve the quality policy explicitly before preparing this article")


def coverage(state):
    return {str(p["paragraph_number"]) for p in state["source"]["paragraphs"] if p["question_pid"] is not None}


def load_state(run_dir):
    state = read_json(Path(run_dir) / "state.json")
    require(state.get("policy_sha256") == policy_fingerprint(), "Prompt policy/gates changed; use a new run directory")
    require(state.get("fingerprint") == digest({"source": state["source"], "references": state["references"], "policy": state["policy_sha256"]}), "Source/reference fingerprint mismatch; use a new run directory")
    for key, lock in state["accepted"].items():
        require(lock["draft_sha256"] == digest(state["drafts"].get(key)), f"Accepted paragraph {key} was changed; restore the locked checkpoint")
        require(lock["comment"] == state["drafts"][key], f"Accepted paragraph {key} differs from its locked comment")
    return state


def review_request(state):
    pending = sorted((int(k) for k in state["drafts"] if k not in state["accepted"] and k not in state["failures"] and k not in state["blocked"]))
    packet = {"fingerprint": state["fingerprint"], "policy": POLICY,
              "source": state["source"], "references": state["references"],
              "plan": state["plan"], "drafts": state["drafts"],
              "accepted": state["accepted"], "failures": state["failures"],
              "repair_attempts": state["repair_attempts"], "blocked": state["blocked"],
              "paragraph_numbers": pending, "required_checks": list(REVIEW_CHECKS),
              "article_gate_failures": article_failures(state),
              "review_policy_documents": {name: text for name, text in policy_documents().items() if name == "prompts/critic_gate6.md"},
              "response_shape": {"input_sha256": "copy request hash exactly", "verdicts": [{"paragraph_number": "integer", "passed": "boolean", "reason": "specific evidence / defect", "checks": {k: "boolean" for k in REVIEW_CHECKS}}]}}
    packet["input_sha256"] = digest(packet)
    return packet


def packets(run_dir, state):
    atomic_json(run_dir / "source.json", state["source"])
    common = {"fingerprint": state["fingerprint"], "policy": POLICY,
              "source": state["source"], "references": state["references"],
              "plan": state["plan"], "accepted": state["accepted"]}
    atomic_json(run_dir / "draft-request.json", {**common, "prompt_documents": draft_documents(),
                "paragraph_numbers": sorted(int(k) for k in coverage(state) - state["drafts"].keys())})
    atomic_json(run_dir / "review-request.json", review_request(state))
    atomic_json(run_dir / "repair-request.json", {**common, "failures": {
        k: {"old_draft": state["drafts"][k], "reason": v["reason"], "checks": v.get("checks", {}),
            "attempts_used": state["repair_attempts"].get(k, 0), "blocked": k in state["blocked"]}
        for k, v in state["failures"].items()}, "blocked": state["blocked"]})


def save(run_dir, state):
    atomic_json(run_dir / "state.json", state)
    packets(run_dir, state)


def prepare(source, run_dir, references=None):
    validate_source(source)
    references = [] if references is None else references
    require(isinstance(references, list), "References must be a list of approved comment strings")
    for ref in references:
        nonempty(ref, "Approved reference")
    policy = policy_fingerprint()
    fingerprint = digest({"source": source, "references": references, "policy": policy})
    with locked(run_dir) as run:
        if (run / "state.json").exists():
            state = load_state(run)
            require(state["fingerprint"] == fingerprint, "Source/reference/policy changed; refusing to overwrite this run. Use a new run directory")
            packets(run, state)
        else:
            require(not any(p.name != ".session.lock" for p in run.iterdir()), "Run directory is not empty; refusing to overwrite it")
            state = {"schema_version": 1, "fingerprint": fingerprint, "policy_sha256": policy,
                     "source": source, "references": references, "plan": None, "drafts": {},
                     "accepted": {}, "failures": {}, "repair_attempts": {}, "blocked": {}}
            save(run, state)
    return state


def submit_plan(run_dir, plan):
    with locked(run_dir) as run:
        state = load_state(run)
        rows = indexed(plan, "plan")
        require(set(rows) == coverage(state), "Plan must cover exactly every question-bearing paragraph")
        all_ids = {p["paragraph_number"] for p in state["source"]["paragraphs"]}
        for row in rows.values():
            for field in ("purpose", "angle"):
                nonempty(row.get(field), f"plan.{field}")
            require(isinstance(row.get("reserved_for_later"), list), "reserved_for_later must be a list")
            for ref in row["reserved_for_later"]:
                require(isinstance(ref, dict), "Each future reference must be an object")
                number = positive_id(ref.get("paragraph_number"), "future paragraph_number")
                require(number in all_ids and number > row["paragraph_number"], "Reserved point must reference a known future paragraph")
                nonempty(ref.get("point"), "reserved point")
        ordered = sorted(plan, key=lambda p: p["paragraph_number"])
        require(not state["drafts"] or state["plan"] == ordered, "Plan is immutable once drafts have been submitted")
        state["plan"] = ordered
        save(run, state)


def validate_comment(comment, state):
    key = str(comment["paragraph_number"])
    require(key in coverage(state), f"Unknown/non-question paragraph {key}")
    source = next(p for p in state["source"]["paragraphs"] if str(p["paragraph_number"]) == key)
    for name in ("body_pid", "question_pid", "question_text", "body_text", "cited_scriptures"):
        if name in comment:
            require(type(comment[name]) is type(source[name]) and comment[name] == source[name], f"Paragraph {key}: {name} disagrees with source")
    nonempty(comment.get("content"), "comment.content")
    require(comment.get("comment_type") in {"A", "B", "C", "D", "F", "H"}, f"Paragraph {key}: valid explicit comment_type required")
    try:
        results = run_per_comment_gates(comment)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise SessionError(f"Paragraph {key}: malformed gate metadata: {exc}") from exc
    failures = [str(r) for r in results if not r.passed]
    require(not failures, f"Paragraph {key} failed gates: " + "; ".join(failures))


def submit_drafts(run_dir, comments):
    with locked(run_dir) as run:
        state = load_state(run)
        require(state["plan"] is not None, "Submit the complete article plan before drafting")
        rows = indexed(comments, "drafts")
        for key, comment in rows.items():
            require(key not in state["accepted"], f"Paragraph {key} is accepted and locked")
            require(state["repair_attempts"].get(key, 0) == 0, f"Paragraph {key} already used its repair; submit its review, not another draft")
            require(key not in state["failures"] and key not in state["blocked"], f"Paragraph {key} failed review; use its bounded repair")
            validate_comment(comment, state)
        state["drafts"].update(rows)
        save(run, state)


def article_failures(state):
    if set(state["drafts"]) != coverage(state):
        return ["Article gates await complete draft coverage"]
    try:
        return [str(r) for r in run_article_gates(list(state["drafts"].values())) if not r.passed]
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise SessionError(f"Malformed article gate metadata: {exc}") from exc


def submit_review(run_dir, review):
    with locked(run_dir) as run:
        state = load_state(run)
        require(set(state["drafts"]) == coverage(state), "Review requires complete draft coverage before any comments can be locked")
        request = review_request(state)
        require(isinstance(review, dict) and review.get("input_sha256") == request["input_sha256"], "Stale or missing review input_sha256; read the current review-request.json")
        rows = indexed(review.get("verdicts"), "verdicts")
        require(set(rows) == {str(n) for n in request["paragraph_numbers"]}, "Review must cover exactly every pending draft")
        for key, verdict in rows.items():
            require(type(verdict.get("passed")) is bool, f"Paragraph {key}: passed must be a literal boolean")
            nonempty(verdict.get("reason"), f"Paragraph {key} review reason")
            if not verdict["passed"]:
                require(len(verdict["reason"].split()) >= 4, f"Paragraph {key}: failure reason must identify a concrete defect (at least four words)")
            checks = verdict.get("checks")
            require(isinstance(checks, dict) and set(checks) == set(REVIEW_CHECKS) and all(type(v) is bool for v in checks.values()), f"Paragraph {key}: all required checks must be literal booleans")
            require(not verdict["passed"] or all(checks.values()), f"Paragraph {key}: overall pass cannot override a false check")
        gate_failures = article_failures(state)
        require(not gate_failures or any(not v["passed"] for v in rows.values()), "Article gates failed; identify the specific paragraphs to repair with failed review verdicts: " + "; ".join(gate_failures))
        for key, verdict in rows.items():
            if verdict["passed"] and gate_failures:
                continue  # No locks until the article itself satisfies its gates.
            if verdict["passed"]:
                state["accepted"][key] = {"comment": state["drafts"][key], "draft_sha256": digest(state["drafts"][key]), "input_sha256": request["input_sha256"], "verdict": verdict}
            else:
                state["failures"][key] = verdict
                if state["repair_attempts"].get(key, 0) >= 1:
                    state["blocked"][key] = "One repair used; review still fails: " + verdict["reason"]
        save(run, state)


def submit_repair(run_dir, comments):
    with locked(run_dir) as run:
        state = load_state(run)
        rows = indexed(comments, "repairs")
        for key in rows:
            require(key in state["failures"] and key not in state["accepted"], f"Paragraph {key} is not a failed, unlocked draft")
            require(state["repair_attempts"].get(key, 0) == 0 and key not in state["blocked"], f"Paragraph {key} blocked: its one repair has already been used")
        # Persist attempt consumption BEFORE inspecting output, including invalid
        # output. A crash at this point conservatively blocks, never grants retry.
        for key in rows:
            state["repair_attempts"][key] = 1
            state["blocked"][key] = "Repair attempt consumed; validation not completed"
        save(run, state)
        errors = []
        for key, comment in rows.items():
            try:
                validate_comment(comment, state)
            except SessionError as exc:
                state["blocked"][key] = str(exc)
                errors.append(str(exc))
                continue
            state["drafts"][key] = comment
            del state["failures"][key]
            del state["blocked"][key]
        save(run, state)
        require(not errors, "Repair blocked; original failed draft preserved: " + "; ".join(errors))


def export(run_dir, output):
    with locked(run_dir) as run:
        state = load_state(run)
        require(not state["blocked"] and not state["failures"], "Export blocked by unresolved paragraph failures")
        require(set(state["drafts"]) == coverage(state) == set(state["accepted"]), "Export requires complete source coverage and hash-matching review passes")
        for comment in state["drafts"].values():
            validate_comment(comment, state)
        try:
            failures = [str(r) for r in run_article_gates(list(state["drafts"].values())) if not r.passed]
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise SessionError(f"Malformed article gate metadata: {exc}") from exc
        require(not failures, "Article gates failed: " + "; ".join(failures))
        from .build_week import ParagraphData, assemble_comments_json
        paragraphs = [ParagraphData(**{k: p[k] for k in ("paragraph_number", "body_pid", "question_pid", "question_text", "body_text", "cited_scriptures")}) for p in state["source"]["paragraphs"]]
        comments = {p.body_pid: state["drafts"][str(p.paragraph_number)] for p in paragraphs if str(p.paragraph_number) in state["drafts"]}
        payload = assemble_comments_json(state["source"]["article_meta"], paragraphs, comments, {})
        payload["_meta"]["preparation_standard"] = "Model-independent Work/chat preparation; existing comment and article gates passed; hash-bound external quality review passed. Comment-only export; no underlines."
        payload["_meta"]["prep_session_fingerprint"] = state["fingerprint"]
        output = Path(output)
        require(output.resolve().parent != run.resolve(), "Export outside the checkpoint directory to preserve state and request files")
        atomic_json(output, payload)
        return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "plan", "draft", "review", "repair", "export"):
        item = sub.add_parser(command)
        item.add_argument("--run-dir", required=True, type=Path)
        if command == "prepare":
            item.add_argument("--article-json", required=True, type=Path)
            item.add_argument("--reference-json", type=Path)
        elif command == "export":
            item.add_argument("--output", required=True, type=Path)
        else:
            item.add_argument("--input", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            prepare(read_json(args.article_json), args.run_dir, read_json(args.reference_json) if args.reference_json else None)
        elif args.command == "export":
            export(args.run_dir, args.output)
        else:
            {"plan": submit_plan, "draft": submit_drafts, "review": submit_review, "repair": submit_repair}[args.command](args.run_dir, read_json(args.input))
        print(f"{args.command}: checkpoint saved" if args.command != "export" else f"export: {args.output}")
        return 0
    except (SessionError, OSError) as exc:
        print(f"{args.command}: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
