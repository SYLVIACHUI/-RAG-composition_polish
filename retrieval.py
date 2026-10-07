"""jieba + BM25 召回与等权 RRF 排名融合。"""
from functools import lru_cache
import logging

import jieba
from rank_bm25 import BM25Okapi

jieba.setLogLevel(logging.WARNING)
STOPWORDS = frozenset('的 了 着 和 与 及 是 在 我 我们 你 你们 他 她 它 他们 她们 它们 就 也 都 很 又 把 被 地 得 一个 一些 这个 那个 然后'.split())


def tokenize(text):
    return [word for word in jieba.cut_for_search(text.lower())
            if word not in STOPWORDS and any(char.isalnum() for char in word)]


@lru_cache(maxsize=1)
def lexical_index(documents):
    """以完整片段内容为缓存键，增删改后自动失效；只缓存最新一版。"""
    tokens = [tokenize(text) for text in documents]
    if not any(tokens):
        return None, tokens
    return BM25Okapi(tokens), tokens


def rank_bm25(query, chunks, top_k=10):
    if not chunks or top_k <= 0:
        return []
    words = list(dict.fromkeys(tokenize(query)))
    if not words:
        return []
    # 向量排序随查询变化；固定文档顺序才能跨查询复用词法索引。
    chunks = sorted(chunks, key=lambda c: c['id'])
    index, tokens = lexical_index(tuple(c['title'] + '\n' + c['text'] for c in chunks))
    if index is None:
        return []
    scores = index.get_scores(words)
    query_words = set(words)
    # 不把完全没有关键词交集的片段算作 BM25 命中。
    matches = [{**chunk, 'bm25_score': float(scores[i])} for i, chunk in enumerate(chunks)
               if query_words.intersection(tokens[i])]
    return sorted(matches, key=lambda c: (-c['bm25_score'], c['id']))[:top_k]


def fuse_rankings(semantic, lexical, top_k=3, candidate_k=10):
    """保留 score 的余弦含义，另用 rrf_score 表示融合排序分数。"""
    if top_k <= 0:
        return []
    by_id = {c['id']: {**c, 'bm25_score': 0.0, 'rrf_score': 0.0,
                        'retrieval_sources': []} for c in semantic}
    candidate_k = max(top_k, candidate_k)
    for source, ranking in [('vector', semantic[:candidate_k]), ('bm25', lexical[:candidate_k])]:
        for rank, chunk in enumerate(ranking, 1):
            item = by_id[chunk['id']]
            item['rrf_score'] += 1 / (60 + rank)
            item['retrieval_sources'].append(source)
            if source == 'bm25':
                item['bm25_score'] = chunk['bm25_score']
    candidates = [c for c in by_id.values() if c['retrieval_sources']]
    return sorted(candidates, key=lambda c: (-c['rrf_score'], -c['score'], c['id']))[:top_k]
