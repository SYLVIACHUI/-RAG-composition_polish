import unittest
from contextlib import contextmanager
from unittest.mock import patch

import rag
from retrieval import tokenize, rank_bm25, fuse_rankings, lexical_index


class RetrievalTests(unittest.TestCase):
    def test_chinese_and_english_tokenization(self):
        words = tokenize('我在图书馆阅读 Python，！')
        self.assertIn('图书馆', words)
        self.assertIn('python', words)
        self.assertNotIn('我', words)
        self.assertNotIn('，', words)

    def test_keyword_match_and_empty_inputs(self):
        chunks = [{'id': str(i), 'title': '', 'text': text} for i, text in enumerate(
            ['纸飞机折纸', '篮球比赛', '花园浇水', '厨房做饭', '海边散步'])]
        self.assertEqual(rank_bm25('纸飞机', chunks)[0]['id'], '0')
        self.assertEqual(rank_bm25('宇宙飞船', chunks), [])
        self.assertEqual(rank_bm25('的，！', chunks), [])
        self.assertEqual(rank_bm25('飞机', []), [])
        self.assertEqual(rank_bm25('飞机', [{'id': 'x', 'title': '', 'text': '！'}]), [])

    def test_small_corpus_and_content_changes(self):
        lexical_index.cache_clear()
        chunks = [{'id': 'x', 'title': '飞机', 'text': '纸飞机'}]
        self.assertEqual(rank_bm25('飞机', chunks)[0]['id'], 'x')
        chunks[0] = {'id': 'x', 'title': '篮球', 'text': '比赛'}
        self.assertEqual(rank_bm25('飞机', chunks), [])
        self.assertEqual(rank_bm25('篮球', chunks)[0]['id'], 'x')

    def test_cache_survives_semantic_order_changes(self):
        lexical_index.cache_clear()
        chunks = [{'id': 'x', 'title': '飞机', 'text': '折纸'},
                  {'id': 'y', 'title': '篮球', 'text': '比赛'}]
        rank_bm25('飞机', chunks)
        rank_bm25('篮球', list(reversed(chunks)))
        self.assertEqual(lexical_index.cache_info().misses, 1)
        self.assertEqual(lexical_index.cache_info().hits, 1)

    def test_fusion_promotes_keyword_candidate_without_changing_cosine(self):
        semantic = [{'id': str(i), 'score': 1-i/20} for i in range(12)]
        lexical = [{**semantic[11], 'bm25_score': 8}, {**semantic[2], 'bm25_score': 3}]
        result = fuse_rankings(semantic, lexical, top_k=3, candidate_k=2)
        self.assertEqual(result[0]['id'], '2')
        keyword = next(c for c in result if c['id'] == '11')
        self.assertEqual(keyword['score'], semantic[11]['score'])
        self.assertEqual(keyword['retrieval_sources'], ['bm25'])
        self.assertEqual(len({c['id'] for c in result}), len(result))
        self.assertEqual([c['id'] for c in fuse_rankings(semantic, [])], ['0','1','2'])

    def test_retrieve_uses_both_channels_and_keeps_metadata(self):
        rows = [('x', '纸飞机', '折纸机翼', '[0,1]'), ('y', '篮球', '球场比赛', '[1,0]')]
        class DB:
            def execute(self, query): return self
            def fetchall(self): return rows
        @contextmanager
        def connect(): yield DB()
        with patch.object(rag, 'embed', return_value=[[1,0]]), \
             patch.object(rag, 'connect', connect), \
             patch.object(rag, 'read_corpus', return_value={'chunks': [{'id':'x','grade':'小学五年级'}]}):
            result = rag.retrieve('纸飞机')
        match = next(c for c in result if c['id']=='x')
        self.assertIn('bm25', match['retrieval_sources'])
        self.assertEqual(match['grade'], '小学五年级')
        self.assertEqual(match['score'], 0)
