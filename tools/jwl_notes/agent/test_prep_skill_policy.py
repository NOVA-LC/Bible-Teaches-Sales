"""Exercise early feasibility and context reuse with local structural fixtures."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from agent import prep_session as s
from agent.test_prep_session import source, plan, comment


def context():
    return {
        "research": [{"id": "r1", "claim": "The text tells readers to listen.",
                      "source_url": "https://example.org/source", "evidence": "Be quick to listen.",
                      "kind": "quotation"}],
        "experiences": [{"id": "e1", "text": "Synthetic fixture supplied by the test author.",
                         "source": "Test author fixture; not a real user experience."}],
    }


class SkillPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / "session"

    def prepare(self, saved_context=None):
        if saved_context is None:
            return s.prepare(source(), self.run)
        return s.prepare(source(), self.run, context=saved_context)

    def read(self, name="state.json"):
        return json.loads((self.run / name).read_text())

    def verdict(self, failed=()):
        req = self.read("review-request.json")
        return {"input_sha256": req["input_sha256"], "verdicts": [
            {"paragraph_number": n, "passed": n not in failed,
             "reason": "The later paragraph payoff was spent here." if n in failed else "Matches the source, plan and approved voice.",
             "checks": {k: n not in failed for k in s.REVIEW_CHECKS}}
            for n in req["paragraph_numbers"]]}

    def test_plan_requires_explicit_type_before_prose(self):
        self.prepare(); rows = plan(); del rows[0]["comment_type"]
        with self.assertRaisesRegex(s.SessionError, "comment_type"):
            s.submit_plan(self.run, rows)
        self.assertIsNone(self.read()["plan"])

    def test_type_cap_and_required_features_fail_during_plan(self):
        article = source(); template = article["paragraphs"][0]
        article["paragraphs"] = [dict(template, paragraph_number=n, body_pid=2*n, question_pid=2*n-1) for n in range(1, 5)]
        s.prepare(article, self.run)
        rows = [dict(plan()[0], paragraph_number=n, reserved_for_later=[]) for n in range(1, 5)]
        with self.assertRaisesRegex(s.SessionError, "Gate 11"):
            s.submit_plan(self.run, rows)
        for n, row in enumerate(rows):
            row["comment_type"] = "F" if n < 2 else "C"
            row["herd_distinctive_moves"] = []
        with self.assertRaisesRegex(s.SessionError, "Gate 5"):
            s.submit_plan(self.run, rows)
        self.assertEqual(self.read()["drafts"], {})

    def test_experience_and_historical_types_require_supplied_evidence(self):
        self.prepare()
        for ct, field, value in (("B", "experience_id", "invented"), ("H", "evidence_ids", ["invented"])):
            rows = plan(); rows[0].update(comment_type=ct, **{field: value})
            with self.assertRaises(s.SessionError):
                s.submit_plan(self.run, rows)

    def test_real_context_is_available_in_each_packet_and_resume_is_exact(self):
        saved = context(); self.prepare(saved)
        rows = plan(); rows[0].update(comment_type="B", experience_id="e1")
        rows[1].update(comment_type="H", evidence_ids=["r1"])
        s.submit_plan(self.run, rows)
        before = (self.run / "state.json").read_bytes()
        self.prepare(saved)
        self.assertEqual(before, (self.run / "state.json").read_bytes())
        for name in ("draft-request.json", "review-request.json", "repair-request.json"):
            self.assertEqual(self.read(name)["context"], saved)
            self.assertIn("workflow_policy", self.read(name))
        docs = self.read("draft-request.json")["prompt_documents"]
        self.assertTrue(any("B_experience" in p for p in docs))
        self.assertFalse(any("A_illustration" in p for p in docs))
        changed = copy.deepcopy(saved); changed["research"][0]["evidence"] = "Different text."
        with self.assertRaises(s.SessionError): self.prepare(changed)

    def test_malformed_context_fails_without_creating_a_checkpoint(self):
        for mutate in (
            lambda c: c["research"].append(copy.deepcopy(c["research"][0])),
            lambda c: c["research"][0].update(source_url="javascript:bad"),
            lambda c: c["research"][0].update(evidence=""),
            lambda c: c["research"][0].update(kind="verified-by-confidence"),
            lambda c: c["experiences"][0].update(source=""),
        ):
            bad = context(); mutate(bad)
            with self.assertRaises(s.SessionError): self.prepare(bad)
            self.assertFalse((self.run / "state.json").exists())

    def test_draft_cannot_disregard_the_type_plan(self):
        self.prepare(); s.submit_plan(self.run, plan())
        changed = comment(10); changed["comment_type"] = "H"
        with self.assertRaisesRegex(s.SessionError, "planned type"):
            s.submit_drafts(self.run, [changed])

    def test_status_tracks_next_action_without_rewriting_and_retains_why(self):
        self.prepare()
        self.assertEqual(s.status(self.run)["next_action"], "plan")
        s.submit_plan(self.run, plan())
        self.assertEqual(s.status(self.run)["next_action"], "draft")
        s.submit_drafts(self.run, [comment(10), comment(14)])
        self.assertEqual(s.status(self.run)["next_action"], "review")
        s.submit_review(self.run, self.verdict(failed=(10,)))
        self.assertEqual(s.status(self.run)["next_action"], "repair")
        reason = self.read()["failures"]["10"]["reason"]
        s.submit_repair(self.run, [comment(10)])
        s.submit_review(self.run, self.verdict())
        before = (self.run / "state.json").read_bytes()
        report = s.status(self.run)
        self.assertEqual(report["next_action"], "export")
        self.assertEqual(report["repair_attempts_used"], 1)
        self.assertEqual(report["checkpoint_counts"]["review"], 2)
        self.assertIn(reason, json.dumps(self.read()["events"]))
        self.assertEqual(before, (self.run / "state.json").read_bytes())

    def test_cli_status_is_read_only_and_reports_blocked_reason(self):
        self.prepare(); s.submit_plan(self.run, plan())
        s.submit_drafts(self.run, [comment(10), comment(14)])
        s.submit_review(self.run, self.verdict(failed=(10,)))
        bad = comment(10); bad["content"] = "Too short"
        with self.assertRaises(s.SessionError): s.submit_repair(self.run, [bad])
        before = (self.run / "state.json").read_bytes()
        result = subprocess.run([sys.executable, "-m", "agent.prep_session", "status", "--run-dir", str(self.run)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["next_action"], "resolve_blocker")
        self.assertIn("10", report["blocked"])
        self.assertEqual(before, (self.run / "state.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
