"""LangChain LCEL 作文流程；模型传输层沿用 rag.py 的 Ollama 流式适配器。"""
import time
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableLambda
from langsmith import tracing_context
from pydantic import Field

import rag
import evaluation


class HybridEssayRetriever(BaseRetriever):
    top_k: int = Field(default=3, ge=1)

    def _get_relevant_documents(self, query, *, run_manager):
        return [Document(page_content=c['text'], metadata={k: v for k, v in c.items() if k != 'text'})
                for c in rag.retrieve(query, self.top_k)]


def build_polish_chain(emit=lambda event: None):
    def prepare(data):
        essay, grade, focus = rag.validate_request(data)
        state = {'data': data, 'essay': essay, 'grade': grade, 'focus': focus,
                 'requirement': data.get('requirement', ''), 'started': time.monotonic()}
        emit({'type': 'stage', 'step': 0, 'message': '检查范文和向量索引…'})
        state['index'] = rag.ensure_index()
        return state

    def retrieve(state, config):
        emit({'type': 'stage', 'step': 1, 'message': '正在进行向量与 BM25 混合检索…', 'index': state['index']})
        documents = HybridEssayRetriever().invoke(state['essay'], config=config)
        state['references'] = [{**d.metadata, 'text': d.page_content} for d in documents]
        emit({'type': 'references', 'step': 2, 'message': '已找到参考片段，Qwen3 正在润色…',
              'references': state['references']})
        return state

    def progress(label):
        return lambda seconds: emit({'type': 'stage', 'step': 2,
                                     'message': f'{label}：模型正在输出，本阶段已用时 {seconds} 秒…'})

    def draft(state):
        state['result'] = rag.generate(state['essay'], state['grade'], state['focus'],
                                       state['references'], state['requirement'], progress('作文润色'))
        return state

    def review(state):
        emit({'type': 'stage', 'step': 2, 'message': '初稿已生成，正在对照原文复核人物、动作与结尾…'})
        state['result'] = rag.review_fidelity(state['essay'], state['result'], state['grade'],
                                              state['requirement'], progress('原意复核'))
        return state

    def evaluate(state):
        result = state['result']
        result.update({'references': state['references'], 'index': state['index'],
                       'elapsed_seconds': round(time.monotonic() - state['started'], 1),
                       'chat_model': rag.CHAT_MODEL, 'embedding_model': rag.EMBED_MODEL,
                       'pipeline': 'langchain-lcel-v1'})
        result['metrics'] = evaluation.machine_metrics(state['essay'], result['polished_text'])
        result['run_id'] = evaluation.save_run(state['data'], result)
        emit({'type': 'result', 'step': 3, 'result': result})
        return result

    return (RunnableLambda(prepare, name='prepare_index')
            | RunnableLambda(retrieve, name='hybrid_retrieval')
            | RunnableLambda(draft, name='generate_draft')
            | RunnableLambda(review, name='review_fidelity')
            | RunnableLambda(evaluate, name='evaluate_and_save'))


def run_polish(data, emit=lambda event: None):
    # 作文处理保持本地运行，不因机器上的追踪环境变量上传作文。
    with tracing_context(enabled=False):
        return build_polish_chain(emit).invoke(data)
