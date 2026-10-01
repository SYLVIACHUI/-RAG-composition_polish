import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import evaluation
import rag


class CoreTests(unittest.TestCase):
    def test_retrieval_ranks_actual_cosine_scores(self):
        rows = [('P1', 'a', 'first', '[1, 0]'), ('P2', 'b', 'second', '[0, 1]'),
                ('P3', 'c', 'third', '[-1, 0]')]
        ranked = rag.rank_chunks([1, 0], rows, 2)
        self.assertEqual([r['id'] for r in ranked], ['P1', 'P2'])
        self.assertEqual(ranked[0]['score'], 1)

    def test_dimension_mismatch_is_rejected(self):
        with self.assertRaises(rag.RagError):
            rag.rank_chunks([1, 0], [('P1', 'a', 'text', '[1]')])

    def test_invalid_input(self):
        for essay in ('', '短文', '长' * 2001, None):
            with self.assertRaises(ValueError):
                rag.validate_request({'essay': essay, 'grade': rag.GRADES[4], 'focus': rag.FOCUSES[0]})

    def test_bleu_identity_and_no_overlap(self):
        self.assertEqual(evaluation.machine_metrics('今天阳光明媚。', '今天阳光明媚。')['character_bleu'], 100)
        self.assertEqual(evaluation.machine_metrics('甲乙丙丁', '天地玄黄')['character_bleu'], 0)
        self.assertLess(evaluation.machine_metrics('一二三四五六七八', '一二三四')['character_bleu'], 100)

    def test_index_cache_and_failed_rebuild_preserve_old_data(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'vectors.db'
            real_connect = rag.connect
            tags = {'models': [{'name': rag.CHAT_MODEL}, {'name': rag.EMBED_MODEL, 'digest': 'digest-1'}]}
            with patch.object(rag, 'connect', side_effect=lambda: real_connect(path)), \
                 patch.object(rag, 'ollama', return_value=tags), \
                 patch.object(rag, 'embed', return_value=[[1, 0]] * len(rag.read_corpus()['chunks'])) as embed:
                self.assertTrue(rag.ensure_index()['rebuilt'])
                self.assertFalse(rag.ensure_index()['rebuilt'])
                self.assertEqual(embed.call_count, 1)
                embed.side_effect = rag.RagError('network unavailable')
                with self.assertRaises(rag.RagError):
                    rag.ensure_index(force=True)
                with real_connect(path) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM chunks').fetchone()[0], len(rag.read_corpus()['chunks']))

    def test_multidocument_corpus_has_distinct_ids_and_titles(self):
        corpus = rag.read_corpus()
        self.assertEqual(corpus['document_count'], len(corpus['documents']))
        self.assertGreaterEqual(corpus['document_count'], 11)
        self.assertEqual(len({c['id'] for c in corpus['chunks']}), len(corpus['chunks']))
        self.assertEqual({c['title'] for c in corpus['chunks']}, {d['title'] for d in corpus['documents']})
        self.assertGreaterEqual(len({d['genre'] for d in corpus['documents'][1:]}), 10)

    def test_feedback_rejects_missing_run_and_saves_scores(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(evaluation, 'DB_PATH', Path(folder) / 'eval.db'):
            feedback = {'run_id': 'missing', 'reviewer': 'A', 'faithfulness': 4, 'fluency': 4, 'grade_fit': 4}
            with self.assertRaises(ValueError):
                evaluation.save_feedback(feedback)
            feedback['run_id'] = evaluation.save_run({'essay': 'test'}, {'title': 'result'})
            evaluation.save_feedback(feedback)
            feedback['faithfulness'] = 5
            evaluation.save_feedback(feedback)
            with evaluation.connect() as db:
                self.assertEqual(db.execute('SELECT faithfulness FROM feedback').fetchall(), [(5,)])

    def test_truncated_generation_is_not_success(self):
        with patch.object(rag, 'ollama', return_value={'done_reason': 'length'}):
            with self.assertRaises(rag.RagError):
                rag.generate('test', rag.GRADES[4], rag.FOCUSES[0], [])

    def test_unknown_reference_is_rejected(self):
        result = {'title': 'title', 'polished_text': 'essay', 'suggestions': ['suggestion'],
                  'reference_usage': [{'chunk_id': 'P99', 'explanation': 'test'}]}
        with patch.object(rag, 'ollama', return_value={'done_reason': 'stop', 'message': {'content': json.dumps(result)}}):
            with self.assertRaises(rag.RagError):
                rag.generate('test', rag.GRADES[4], rag.FOCUSES[0], [{'id': 'P1'}])

    def test_review_rejects_new_source_ids(self):
        draft = {'title': 'title', 'polished_text': 'text', 'suggestions': ['test'], 'reference_usage': []}
        reviewed = {**draft, 'reference_usage': [{'chunk_id': 'invented', 'explanation': 'test'}]}
        with patch.object(rag, 'ollama', return_value={'done_reason': 'stop', 'message': {'content': json.dumps(reviewed)}}):
            with self.assertRaises(rag.RagError):
                rag.review_fidelity('original', draft, rag.GRADES[4], '')

    def test_review_keeps_complete_structured_response(self):
        draft = {'title': 'title', 'polished_text': 'text', 'suggestions': ['test'], 'reference_usage': []}
        with patch.object(rag, 'ollama', return_value={'done_reason': 'stop', 'message': {'content': json.dumps(draft)}}):
            self.assertEqual(rag.review_fidelity('original', draft, rag.GRADES[4], ''), draft)


if __name__ == '__main__':
    unittest.main()
