"""管理作文库：python manage_corpus.py --help。"""
import argparse
import json
from pathlib import Path
import re
import uuid

import corpus


def main():
    parser = argparse.ArgumentParser(description='语你一起 · 作文库管理')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='校验、同步数据库并列出作文')
    commands.add_parser('reindex', help='同步作文并重建 RAG 向量库')
    add = commands.add_parser('add', help='把 UTF-8 TXT 或 Markdown 正文导入为独立作文')
    add.add_argument('--file', type=Path, required=True)
    add.add_argument('--title', required=True)
    add.add_argument('--genre', required=True)
    add.add_argument('--grade', required=True)
    add.add_argument('--source', default='用户导入，待审定')
    add.add_argument('--techniques', nargs='*', default=[])
    args = parser.parse_args()
    if args.command == 'add':
        content = args.file.read_text(encoding='utf-8-sig').strip()
        lines = content.splitlines()
        if lines and lines[0].strip() == '# ' + args.title:
            content = '\n'.join(lines[1:]).strip()
        doc = {'id': 'essay_' + uuid.uuid4().hex[:12], 'title': args.title,
               'genre': args.genre, 'grade': args.grade, 'source': args.source,
               'techniques': args.techniques,
               'paragraphs': [p.strip() for p in re.split(r'\n\s*\n', content) if p.strip()]}
        corpus.validate_document(doc)
        # 先验证已有库，避免在已有文件损坏时继续加入新数据。
        if any(corpus.ESSAY_DIR.glob('*.json')):
            corpus.load_documents()
        corpus.ESSAY_DIR.mkdir(parents=True, exist_ok=True)
        target = corpus.ESSAY_DIR / (doc['id'] + '.json')
        with target.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(doc, ensure_ascii=False, indent=2) + '\n')
        print(f'已新增：{target}')
    documents = corpus.read_documents()
    for doc in documents:
        print(f"{doc['id']} | {doc['title']} | {doc['genre']} | {doc['grade']}")
    print(f'共 {len(documents)} 篇，已同步到 {corpus.DB_PATH}')
    if args.command == 'reindex':
        import rag
        print(rag.ensure_index(force=True))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
