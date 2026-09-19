"""Offline tests use real deterministic gates and never call a model."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from agent import prep_session as s


def source():
    return {"article_meta": {"article_title": "Patience", "article_source": "w", "study_date": "2026-09-20", "key_symbol": "w", "issue": 20260900, "document_id": 123, "url": "https://example.org/article"}, "paragraphs": [{"paragraph_number": n, "body_pid": n * 2, "question_pid": n * 2 - 1, "question_text": "How can we help?", "body_text": "Listen patiently and offer practical help.", "cited_scriptures": ["James 1:19"]} for n in (10, 14)]}


def comment(n):
    # Structural fixture, not a quality exemplar.
    return {"paragraph_number": n, "comment_type": "F", "content": "Worry weighs on you. " + "Listen patiently and offer practical help to someone today. " * 15 + "Now you have courage.", "audience_state_at_open": "worry", "audience_state_at_close": "courage", "transformation_mechanism": "equip", "herd_distinctive_moves": ["H1"]}


def plan():
    return [{"paragraph_number": n, "purpose": "Teach patience", "angle": "Listen first", "reserved_for_later": [{"paragraph_number": 14, "point": "Practical help"}] if n == 10 else []} for n in (10, 14)]


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / "run"
        s.prepare(source(), self.run, ["Approved reference"])

    def read(self, name):
        return json.loads((self.run / name).read_text())

    def start(self):
        s.submit_plan(self.run, plan()); s.submit_drafts(self.run, [comment(10), comment(14)])

    def review(self, failed=()):
        req = self.read("review-request.json")
        return {"input_sha256": req["input_sha256"], "verdicts": [{"paragraph_number": n, "passed": n not in failed, "reason": "Paragraph 14 payoff appears too early." if n in failed else "Fits its assigned point and preserves the later payoff.", "checks": {k: n not in failed for k in s.REVIEW_CHECKS}} for n in req["paragraph_numbers"]]}

    def test_consumed_repair_cannot_be_overwritten_by_draft_command(self):
        self.start(); s.submit_review(self.run, self.review(failed=(10,)))
        s.submit_repair(self.run, [comment(10)])
        with self.assertRaises(s.SessionError):
            s.submit_drafts(self.run, [comment(10)])

    def test_happy_export(self):
        self.start(); s.submit_review(self.run, self.review())
        out = Path(self.tmp.name) / "out.json"; s.export(self.run, out)
        data = json.loads(out.read_text())
        self.assertEqual([x["data_pid"] for x in data["notes"]], [19, 27])
        self.assertEqual(data["notes"][0]["content"], comment(10)["content"])

    def test_resume_and_changed_inputs_policy(self):
        before = (self.run / "state.json").read_bytes()
        s.prepare(source(), self.run, ["Approved reference"])
        self.assertEqual(before, (self.run / "state.json").read_bytes())
        changed = source(); changed["paragraphs"][0]["body_text"] += " Changed"
        with self.assertRaises(s.SessionError): s.prepare(changed, self.run, ["Approved reference"])
        with self.assertRaises(s.SessionError): s.prepare(source(), self.run, ["Changed reference"])
        with patch.object(s, "policy_fingerprint", return_value="changed"):
            with self.assertRaises(s.SessionError): s.prepare(source(), self.run, ["Approved reference"])
            with self.assertRaises(s.SessionError): s.submit_plan(self.run, plan())

    def test_plan_coverage_future_refs_and_bool_ids(self):
        for bad in (plan()[:1], plan() + plan()[:1]):
            with self.assertRaises(s.SessionError): s.submit_plan(self.run, bad)
        for ref in (10, 9, 99, True):
            bad = plan(); bad[0]["reserved_for_later"][0]["paragraph_number"] = ref
            with self.assertRaises(s.SessionError): s.submit_plan(self.run, bad)
        bad = source(); bad["paragraphs"][0]["paragraph_number"] = True
        with self.assertRaises(s.SessionError): s.prepare(bad, self.run)

    def test_partial_resume_stale_review_immutable_plan(self):
        with self.assertRaises(s.SessionError): s.submit_drafts(self.run, [comment(10)])
        s.submit_plan(self.run, plan()); s.submit_drafts(self.run, [comment(10)])
        stale = self.review(); s.prepare(source(), self.run, ["Approved reference"])
        s.submit_drafts(self.run, [comment(14)])
        self.assertEqual(len(self.read("state.json")["drafts"]), 2)
        with self.assertRaises(s.SessionError): s.submit_review(self.run, stale)
        changed = plan(); changed[0]["angle"] = "Different"
        with self.assertRaises(s.SessionError): s.submit_plan(self.run, changed)

    def test_malformed_review(self):
        self.start()
        bad = self.review(); bad["verdicts"].pop()
        with self.assertRaises(s.SessionError): s.submit_review(self.run, bad)
        bad = self.review(); bad["verdicts"][0]["checks"]["no_future_leakage"] = False
        with self.assertRaises(s.SessionError): s.submit_review(self.run, bad)
        bad = self.review(); bad["verdicts"][0]["passed"] = "true"
        with self.assertRaises(s.SessionError): s.submit_review(self.run, bad)

    def test_targeted_repair_preserves_accepted_and_locks_it(self):
        self.start(); s.submit_review(self.run, self.review(failed=(10,)))
        accepted = copy.deepcopy(self.read("state.json")["accepted"]["14"])
        for fn in (s.submit_drafts, s.submit_repair):
            with self.assertRaises(s.SessionError): fn(self.run, [comment(14)])
        fixed = comment(10); fixed["content"] = fixed["content"].replace("today", "tomorrow")
        s.submit_repair(self.run, [fixed])
        self.assertEqual(accepted, self.read("state.json")["accepted"]["14"])
        self.assertEqual(self.read("review-request.json")["paragraph_numbers"], [10])
        s.submit_review(self.run, self.review()); s.export(self.run, Path(self.tmp.name) / "out.json")

    def test_attempt_persists_after_gate_failure(self):
        self.start(); s.submit_review(self.run, self.review(failed=(10,)))
        bad = comment(10); bad["content"] = "too short"
        with self.assertRaises(s.SessionError): s.submit_repair(self.run, [bad])
        s.prepare(source(), self.run, ["Approved reference"])
        self.assertEqual(self.read("state.json")["drafts"]["10"], comment(10))
        self.assertEqual(self.read("state.json")["repair_attempts"]["10"], 1)
        with self.assertRaises(s.SessionError): s.submit_repair(self.run, [comment(10)])
        with self.assertRaises(s.SessionError): s.export(self.run, Path(self.tmp.name) / "out.json")

    def test_second_review_failure_blocks(self):
        self.start(); s.submit_review(self.run, self.review(failed=(10,)))
        s.submit_repair(self.run, [comment(10)]); s.submit_review(self.run, self.review(failed=(10,)))
        self.assertIn("10", self.read("state.json")["blocked"])
        with self.assertRaises(s.SessionError): s.submit_repair(self.run, [comment(10)])

    def test_invalid_drafts_and_incomplete_export(self):
        s.submit_plan(self.run, plan()); bad = comment(10); bad["content"] = "too short"
        for drafts in ([bad], [comment(99)], [comment(10), comment(10)]):
            with self.assertRaises(s.SessionError): s.submit_drafts(self.run, drafts)
        s.submit_drafts(self.run, [comment(10)])
        with self.assertRaisesRegex(s.SessionError, "complete draft coverage"): s.submit_review(self.run, self.review())
        with self.assertRaises(s.SessionError): s.export(self.run, Path(self.tmp.name) / "out.json")

    def test_failed_review_needs_specific_reason(self):
        self.start()
        for reason in ("", "bad", "needs work", "failed"):
            bad = self.review(failed=(10,)); bad["verdicts"][0]["reason"] = reason
            with self.assertRaises(s.SessionError): s.submit_review(self.run, bad)

    def test_cli_happy_path_without_credentials(self):
        import subprocess
        import sys
        run = Path(self.tmp.name) / "cli-run"
        def command(name, payload=None):
            args = [sys.executable, "-m", "agent.prep_session", name, "--run-dir", str(run)]
            if payload is not None:
                path = Path(self.tmp.name) / (name + ".json")
                path.write_text(json.dumps(payload))
                args += ["--article-json" if name == "prepare" else "--input", str(path)]
            if name == "export": args += ["--output", str(Path(self.tmp.name) / "cli-export.json")]
            result = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        command("prepare", source()); command("plan", plan())
        command("draft", [comment(10), comment(14)])
        req = json.loads((run / "review-request.json").read_text())
        review = {"input_sha256": req["input_sha256"], "verdicts": [{"paragraph_number": n, "passed": True, "reason": "Source, plan, and listener transformation agree.", "checks": {k: True for k in s.REVIEW_CHECKS}} for n in req["paragraph_numbers"]]}
        command("review", review); command("export")

    def test_metadata_mismatch_and_boolean_pid_rejected(self):
        s.submit_plan(self.run, plan())
        for field, value in (("body_pid", 99), ("question_pid", True), ("question_text", "Changed")):
            bad = comment(10); bad[field] = value
            with self.assertRaises(s.SessionError): s.submit_drafts(self.run, [bad])
        for section, field in (("article_meta", "document_id"), ("article_meta", "issue"), ("paragraphs", "body_pid"), ("paragraphs", "question_pid")):
            bad = source(); target = bad[section][0] if section == "paragraphs" else bad[section]
            target[field] = True
            with self.assertRaises(s.SessionError): s.prepare(bad, self.run)

    def test_impossible_type_coverage_fails_before_drafting(self):
        article = source()
        template = article["paragraphs"][0]
        article["paragraphs"] = [dict(template, paragraph_number=n, body_pid=n * 2, question_pid=n * 2 - 1) for n in range(1, 20)]
        with self.assertRaisesRegex(s.SessionError, "Gate 11"):
            s.prepare(article, Path(self.tmp.name) / "too-many")

    def test_packets_exclude_unrelated_prompts(self):
        documents = self.read("draft-request.json")["prompt_documents"]
        self.assertIn("prompts/comment_agent.md", documents)
        self.assertNotIn("prompts/paragraph_comment.md", documents)
        self.assertFalse(any("underline" in name or "lesson_agent" in name for name in documents))

    def test_article_failure_has_bounded_targeted_repair_before_locking(self):
        s.submit_plan(self.run, plan())
        drafts = [comment(10), comment(14)]
        for c in drafts: c["herd_distinctive_moves"] = []
        s.submit_drafts(self.run, drafts)
        self.assertIn("Gate 5", self.read("review-request.json")["article_gate_failures"][0])
        verdict = self.review(failed=(10,))
        verdict["verdicts"][0]["reason"] = "Paragraph needs its earned distinctive move to satisfy Gate 5."
        s.submit_review(self.run, verdict)
        self.assertEqual(self.read("state.json")["accepted"], {})
        s.submit_repair(self.run, [comment(10)])
        self.assertEqual(self.read("state.json")["repair_attempts"]["10"], 1)
        self.assertEqual(self.read("review-request.json")["article_gate_failures"], [])
        self.assertEqual(self.read("review-request.json")["paragraph_numbers"], [10, 14])
        s.submit_review(self.run, self.review())
        s.export(self.run, Path(self.tmp.name) / "repaired-article.json")

    def test_article_gates_fail_closed(self):
        s.submit_plan(self.run, plan()); drafts = [comment(10), comment(14)]
        for c in drafts: c["herd_distinctive_moves"] = []
        s.submit_drafts(self.run, drafts)
        with self.assertRaisesRegex(s.SessionError, "Gate 5"): s.submit_review(self.run, self.review())
        self.assertEqual(self.read("state.json")["accepted"], {})
        with self.assertRaises(s.SessionError): s.export(self.run, Path(self.tmp.name) / "out.json")


if __name__ == "__main__":
    unittest.main()
