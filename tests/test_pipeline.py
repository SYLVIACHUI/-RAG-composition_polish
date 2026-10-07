import unittest
from unittest.mock import patch
from langchain_core.runnables import RunnableSequence
from pipeline import build_polish_chain, HybridEssayRetriever
import rag
import evaluation


class PipelineTests(unittest.TestCase):
    def test_retriever_preserves_text_and_scores(self):
        ref = {'id':'P1', 'text':'范文', 'title':'题目', 'score':0.8, 'bm25_score':2, 'rrf_score':0.03}
        with patch.object(rag, 'retrieve', return_value=[ref]) as search:
            doc = HybridEssayRetriever(top_k=2).invoke('原文')[0]
        search.assert_called_once_with('原文', 2)
        self.assertEqual(doc.page_content, '范文')
        self.assertEqual(doc.metadata['rrf_score'], 0.03)

    def test_lcel_chain_runs_all_stages_in_order(self):
        self.assertIsInstance(build_polish_chain(), RunnableSequence)
        data = {'essay': rag.SAMPLE, 'grade': rag.GRADES[4], 'focus':rag.FOCUSES[0]}
        draft = {'title':'初稿', 'polished_text':rag.SAMPLE, 'suggestions':[], 'reference_usage':[]}
        reviewed = {**draft, 'title':'复核稿'}
        refs = [{'id':'P1','text':'范文','title':'参考','score':0.9}]
        order, events = [], []
        def index(): order.append('index'); return {'chunks':1}
        def search(*args): order.append('retrieve'); return refs
        def generate(*args): order.append('generate'); self.assertEqual(args[3], refs); return draft
        def review(*args): order.append('review'); self.assertIs(args[1], draft); return reviewed.copy()
        with patch.object(rag, 'ensure_index', side_effect=index), \
             patch.object(rag, 'retrieve', side_effect=search), \
             patch.object(rag, 'generate', side_effect=generate), \
             patch.object(rag, 'review_fidelity', side_effect=review), \
             patch.object(evaluation, 'save_run', return_value='test-run') as save:
            result = rag.polish(data, events.append)
        self.assertEqual(order, ['index','retrieve','generate','review'])
        self.assertEqual(result['title'], '复核稿')
        self.assertEqual(result['run_id'], 'test-run')
        self.assertEqual(result['references'], refs)
        self.assertEqual(result['metrics']['character_bleu'], 100)
        self.assertEqual(events[-1]['type'], 'result')
        save.assert_called_once()

    def test_failure_stops_before_saving(self):
        data = {'essay':rag.SAMPLE,'grade':rag.GRADES[4],'focus':rag.FOCUSES[0]}
        with patch.object(rag, 'ensure_index', side_effect=rag.RagError('offline')), \
             patch.object(rag, 'generate') as generate, patch.object(evaluation, 'save_run') as save:
            with self.assertRaises(rag.RagError): rag.polish(data)
        generate.assert_not_called()
        save.assert_not_called()
