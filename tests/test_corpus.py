import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import corpus


class CorpusTests(unittest.TestCase):
    def doc(self, id='one', text='测试作文正文。'):
        return dict(id=id, title='标题', genre='写景', grade='小学五年级', source='测试数据', techniques=[], paragraphs=[text])

    def test_new_files_updates_and_removals_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / 'test.sqlite3'
            file = root / 'one.json'
            file.write_text(json.dumps(self.doc()), encoding='utf-8')
            corpus.sync_database(corpus.load_documents(root), db)
            file.write_text(json.dumps(self.doc(text='修改后的正文。')), encoding='utf-8')
            (root / 'two.json').write_text(json.dumps(self.doc('two')), encoding='utf-8')
            corpus.sync_database(corpus.load_documents(root), db)
            conn = sqlite3.connect(db)
            try:
                self.assertEqual(conn.execute('SELECT count(*) FROM compositions').fetchone()[0], 2)
                self.assertEqual(conn.execute("SELECT content FROM compositions WHERE id='one'").fetchone()[0], '修改后的正文。')
            finally:
                conn.close()
            corpus.sync_database([self.doc('two')], db)
            conn = sqlite3.connect(db)
            try:
                self.assertEqual(conn.execute('SELECT id FROM compositions').fetchall(), [('two',)])
            finally:
                conn.close()

    def test_duplicate_ids_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('a.json', 'b.json'):
                (root / name).write_text(json.dumps(self.doc()), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '重复'):
                corpus.load_documents(root)

    def test_invalid_document_rejected(self):
        for changed in ({'paragraphs': []}, {'title': ''}, {'paragraphs': ['']}, {'techniques': '写法'}):
            with self.assertRaises(ValueError):
                corpus.validate_document({**self.doc(), **changed})
