"""轻量机器指标与人工反馈。BLEU 在此衡量与原文的字面接近度。"""
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
import uuid

DB_PATH = Path(__file__).resolve().parent / 'data' / 'evaluations.sqlite3'


def machine_metrics(original, polished):
    # 字符分词；去空白，保留标点；无平滑、单参考、1~4 gram 等权 BLEU。
    reference = ''.join(original.split())
    candidate = ''.join(polished.split())
    precisions = []
    for n in range(1, 5):
        ref = Counter(reference[i:i+n] for i in range(len(reference) - n + 1))
        cand = Counter(candidate[i:i+n] for i in range(len(candidate) - n + 1))
        total = sum(cand.values())
        clipped = sum(min(count, ref[gram]) for gram, count in cand.items())
        precisions.append(clipped / total if total else 0)
    bp = min(1, math.exp(1 - len(reference) / len(candidate))) if candidate else 0
    bleu = bp * math.exp(sum(math.log(p) for p in precisions) / 4) if all(precisions) else 0
    return {'character_bleu': round(bleu * 100, 2), 'original_chars': len(reference),
            'polished_chars': len(candidate), 'length_ratio': round(len(candidate) / len(reference), 2) if reference else 0,
            'note': '字符级 BLEU-4 以原文为参考，仅反映字面接近度，不代表作文质量或项目匹配准确率。'}


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH, timeout=20)
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created_at TEXT, payload TEXT)')
    db.execute('''CREATE TABLE IF NOT EXISTS feedback (
        run_id TEXT REFERENCES runs(id), reviewer TEXT, faithfulness INTEGER,
        fluency INTEGER, grade_fit INTEGER, note TEXT, created_at TEXT,
        PRIMARY KEY (run_id, reviewer))''')
    try:
        with db:
            yield db
    finally:
        db.close()


def save_run(request, result):
    run_id = uuid.uuid4().hex
    with connect() as db:
        db.execute('INSERT INTO runs VALUES (?, ?, ?)', (run_id, datetime.now(timezone.utc).isoformat(),
                   json.dumps({'input': request, 'result': result, 'prompt_version': 'v3-with-review'}, ensure_ascii=False)))
    return run_id


def save_feedback(data):
    if not isinstance(data, dict):
        raise ValueError('反馈必须是 JSON 对象。')
    run_id, reviewer = data.get('run_id'), data.get('reviewer')
    if not isinstance(run_id, str) or reviewer not in ('A', 'B'):
        raise ValueError('请选择评价者，并先完成一次润色。')
    scores = [data.get(key) for key in ('faithfulness', 'fluency', 'grade_fit')]
    if any(type(value) is not int or not 1 <= value <= 5 for value in scores):
        raise ValueError('每项评分应为 1～5 分。')
    note = data.get('note', '')
    if not isinstance(note, str) or len(note) > 500:
        raise ValueError('评语不能超过 500 字。')
    with connect() as db:
        if not db.execute('SELECT 1 FROM runs WHERE id=?', (run_id,)).fetchone():
            raise ValueError('找不到对应的润色记录。')
        db.execute('INSERT OR REPLACE INTO feedback VALUES (?, ?, ?, ?, ?, ?, ?)',
                   (run_id, reviewer, *scores, note, datetime.now(timezone.utc).isoformat()))
    return {'message': f'评价者 {reviewer} 的反馈已保存，可用于后续优化提示词和知识库。'}
