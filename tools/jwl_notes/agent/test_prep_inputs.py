"""Private-reference and source-adapter tests use synthetic local inputs."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile
from agent import prep_inputs as p

class InputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def backup(self):
        db = self.root/'userData.db'
        with sqlite3.connect(db) as c:
            c.executescript('CREATE TABLE Location(LocationId INTEGER,DocumentId INTEGER,KeySymbol TEXT); CREATE TABLE Note(NoteId INTEGER,LocationId INTEGER,Content TEXT,BlockIdentifier INTEGER);')
            c.executemany('INSERT INTO Location VALUES (?,?,?)', [(1,42,'w'),(2,99,'w'),(3,42,'other')])
            c.executemany('INSERT INTO Note VALUES (?,?,?,?)', [(1,1,'Approved second',20),(2,2,'Unrelated private',10),(3,1,'Approved first',10),(4,3,'Other publication',10)])
        z = self.root/'backup.jwlibrary'
        with zipfile.ZipFile(z,'w') as out: out.write(db,'userData.db')
        return z

    def test_only_explicit_article_references_are_extracted_in_anchor_order(self):
        self.assertEqual(p.extract_references(self.backup(),42,'w'), ['Approved first','Approved second'])

    def test_missing_article_fails_instead_of_using_other_notes(self):
        with self.assertRaises(ValueError): p.extract_references(self.backup(),100,'w')

    def test_cached_inputs_are_identical_or_refuse_overwrite(self):
        out = self.root/'article.json'
        p.save_snapshot(out, {'a':1}); before = out.stat().st_mtime_ns
        p.save_snapshot(out, {'a':1}); self.assertEqual(before,out.stat().st_mtime_ns)
        with self.assertRaises(ValueError): p.save_snapshot(out, {'a':2})
        self.assertEqual(json.loads(out.read_text()),{'a':1})

    def test_source_keeps_full_text_and_question_anchor(self):
        html = '<p id="p37" data-pid="37" class="qu">1. Why listen?</p><p id="p38" data-pid="38" data-rel-pid="[37]" class="sb"><strong>1</strong> Listen patiently.</p>'
        article = p.article_from_html(html, {'document_id':42})
        self.assertEqual(article['paragraphs'][0]['question_pid'],37)
        self.assertIn('Listen patiently.',article['paragraphs'][0]['body_text'])
        with self.assertRaises(ValueError): p.article_from_html('<html>error page</html>',{})

if __name__ == '__main__': unittest.main()
