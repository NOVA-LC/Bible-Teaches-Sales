"""Regression tests for local repairs; no SDK or network calls."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from agent import lesson_agent as la

class RedraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.state = la.LessonState('2026-09-20', 'wt', False, la.CostTracker(), Path(self.tmp.name), io.StringIO())
        self.state.article_meta = {'title': 'Comfort', 'source': 'w'}
        self.para = la.ParagraphData(10, 20, 19, 'Why?', 'Trust in Jehovah.', [])
        self.later = la.ParagraphData(14, 28, 27, 'How?', 'A later payoff.', [])
        self.state.paragraphs = [self.para]
        self.state.article_paragraphs = [self.para, self.later]
        self.state.paragraph_by_num = {10: self.para}
        self.original = {'content': 'Keep this good draft.', 'comment_type': 'F'}
        self.state.drafted_comments[20] = self.original.copy()
        la._save_comment(self.state, 20, self.original)
        self.handlers = la._make_tool_handlers(self.state)

    def test_repair_receives_reason_original_and_full_article(self):
        replacement = dict(self.original, content='Repair only the close.')
        with patch.object(la, 'draft_comment_with_agent', return_value=(replacement, [])) as draft:
            self.assertTrue(self.handlers['redraft_comment'](10, reason='Reserve the payoff for paragraph 14')['accepted'])
        kw = draft.call_args.kwargs
        self.assertEqual(kw['revision']['previous_comment'], self.original)
        self.assertIn('paragraph 14', kw['revision']['reason'])
        self.assertEqual([p['paragraph_number'] for p in draft.call_args.args[1]['article_context']], [10, 14])
        self.assertEqual(draft.call_args.args[2]['prior_types_used_this_article'], [])

    def test_failed_repair_retains_draft_but_cannot_ship_or_cache_as_accepted(self):
        with patch.object(la, 'draft_comment_with_agent', return_value=(None, [])):
            self.assertFalse(self.handlers['redraft_comment'](10, reason='Fix continuity')['accepted'])
        self.assertEqual(self.state.drafted_comments[20], self.original)
        self.assertEqual(json.loads((Path(self.tmp.name)/'state/comments/20.json').read_text()), self.original)
        self.assertFalse(self.handlers['commit_lesson']()['ok'])
        self.assertFalse(self.handlers['draft_comment'](10)['accepted'])

    def test_invalid_requests_do_not_spend_attempts(self):
        for n, reason in [(999, 'Fix this'), (10, ''), (10, '(no reason given)')]:
            self.assertFalse(self.handlers['redraft_comment'](n, reason=reason)['ok'])
        self.assertEqual(self.state.redraft_cycles_used, 0)

    def test_attempt_and_failure_persist_before_dispatch_and_clear_after_success(self):
        def draft(*args, **kwargs):
            meta = json.loads((Path(self.tmp.name)/'state/meta.json').read_text())
            self.assertEqual(meta['redraft_cycles_used'], 1)
            self.assertIn(10, meta['failed_comments'])
            return self.original.copy(), []
        with patch.object(la, 'draft_comment_with_agent', side_effect=draft):
            self.handlers['redraft_comment'](10, reason='Fix close')
        meta = json.loads((Path(self.tmp.name)/'state/meta.json').read_text())
        self.assertNotIn(10, meta['failed_comments'])

    def test_failed_checkpoint_never_unquarantines_old_draft(self):
        replacement = dict(self.original, content='Good replacement')
        with patch.object(la, 'draft_comment_with_agent', return_value=(replacement, [])), patch.object(la, '_save_comment', side_effect=OSError('disk full')):
            result = self.handlers['redraft_comment'](10, reason='Fix continuity')
        self.assertFalse(result['accepted'])
        self.assertIn(10, self.state.failed_comments)
        la._save_meta(self.state)  # A later unrelated checkpoint must remain safe.
        meta = json.loads((Path(self.tmp.name)/'state/meta.json').read_text())
        self.assertIn(10, meta['failed_comments'])
        self.assertEqual(self.state.drafted_comments[20], self.original)

    def test_writer_and_critic_receive_article_context(self):
        import os
        from types import SimpleNamespace
        from unittest.mock import Mock
        from agent import comment_agent as ca
        context = [{"paragraph_number": 14, "body_text": "Later payoff"}]
        meta = {"article_context": context}
        revision = {"previous_comment": self.original, "reason": "Reserve later payoff"}
        client = Mock()
        client.messages.create.return_value = SimpleNamespace(content=[], stop_reason='end_turn', usage=None)
        worker = Mock(last_usage=None)
        worker.critique.return_value = {"overall_pass": False}
        with patch.dict('sys.modules', {'anthropic': SimpleNamespace(Anthropic=lambda:client)}), patch.dict(os.environ, {'ANTHROPIC_API_KEY':'offline-test-placeholder'}), patch.object(ca, 'SDKWorker', return_value=worker), patch.object(ca, 'load_dotenv'):
            ca.draft_comment_with_agent(self.para, meta, {}, revision=revision)
        payload = json.loads(client.messages.create.call_args.kwargs['messages'][0]['content'])
        self.assertEqual(payload['revision'], revision)
        self.assertEqual(payload['article_context'], context)
        handlers, _ = ca._make_tool_handlers(self.para, meta, {}, {}, worker, ca.CostTracker())
        handlers['score_with_critic'](self.original)
        self.assertEqual(worker.critique.call_args.args[0]['article_context'], context)

if __name__ == '__main__': unittest.main()
