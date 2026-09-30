"""每篇作文一个 JSON 文件，自动同步到 SQLite 作文数据库。"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parent
ESSAY_DIR = ROOT / 'data' / 'essays'
DB_PATH = ROOT / 'data' / 'compositions.sqlite3'


def validate_document(doc, filename='作文'):
    if not isinstance(doc, dict):
        raise ValueError(f'{filename}：作文必须是 JSON 对象。')
    for field in ('id', 'title', 'genre', 'grade', 'source'):
        if not isinstance(doc.get(field), str) or not doc[field].strip():
            raise ValueError(f'{filename}：缺少有效的 {field}。')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', doc['id']):
        raise ValueError(f'{filename}：id 只能包含英文字母、数字、下划线和连字符。')
    for field in ('paragraphs', 'techniques'):
        if not isinstance(doc.get(field), list) or any(not isinstance(s, str) or not s.strip() for s in doc[field]):
            raise ValueError(f'{filename}：{field} 必须是非空字符串组成的列表。')
    if not doc['paragraphs']:
        raise ValueError(f'{filename}：正文不能为空。')
    return doc


def load_documents(directory=None):
    directory = Path(directory) if directory is not None else ESSAY_DIR
    documents, ids = [], set()
    for file in sorted(directory.glob('*.json')):
        try:
            doc = validate_document(json.loads(file.read_text(encoding='utf-8-sig')), file.name)
        except (ValueError, OSError) as exc:
            raise ValueError(f'作文文件读取失败：{file.name}：{exc}') from exc
        if doc['id'] in ids:
            raise ValueError(f'作文编号重复：{doc["id"]}。请为新增作文使用新编号。')
        ids.add(doc['id'])
        documents.append(doc)
    if not documents:
        raise ValueError('作文库为空，请向 data/essays 添加作文 JSON 文件。')
    return sorted(documents, key=lambda d: (d['id'] != 'original', d['id']))


def sync_database(documents, db_path=None):
    """文件是编辑入口，数据库是自动生成的查询副本；不修改人工评价库。"""
    db_path = Path(db_path) if db_path is not None else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path, timeout=20)) as db, db:
        db.execute('''CREATE TABLE IF NOT EXISTS compositions (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, genre TEXT NOT NULL,
            grade TEXT NOT NULL, source TEXT NOT NULL, techniques TEXT NOT NULL,
            content TEXT NOT NULL, document_json TEXT NOT NULL,
            char_count INTEGER NOT NULL, content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_compositions_genre ON compositions(genre)')
        ids = {d['id'] for d in documents}
        for doc in documents:
            encoded = json.dumps(doc, ensure_ascii=False, sort_keys=True)
            content = '\n\n'.join(doc['paragraphs'])
            digest = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
            db.execute('''INSERT INTO compositions
                (id,title,genre,grade,source,techniques,content,document_json,char_count,content_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, genre=excluded.genre, grade=excluded.grade,
                source=excluded.source, techniques=excluded.techniques, content=excluded.content,
                document_json=excluded.document_json, char_count=excluded.char_count,
                content_hash=excluded.content_hash, updated_at=CURRENT_TIMESTAMP
                WHERE compositions.content_hash != excluded.content_hash''',
                (doc['id'], doc['title'], doc['genre'], doc['grade'], doc['source'],
                 json.dumps(doc['techniques'], ensure_ascii=False), content, encoded,
                 len(''.join(content.split())), digest))
        stale = [(row[0],) for row in db.execute('SELECT id FROM compositions') if row[0] not in ids]
        db.executemany('DELETE FROM compositions WHERE id=?', stale)
    return len(documents)


def read_documents():
    documents = load_documents()
    sync_database(documents)
    return documents
