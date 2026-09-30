# 作文数据库：每篇一个文件

本目录是作文的统一编辑入口。每个 `.json` 文件只保存一篇作文，系统自动扫描本目录下所有 JSON 文件。文件名可以改，`id` 应保持稳定；新增作文必须使用新 `id`。

## 添加作文（推荐）

把正文保存为 UTF-8 编码的 TXT 文件，段落之间留一空行。在项目根目录运行：

```powershell
python manage_corpus.py add --file "D:\我的作文\春天.txt" --title "春天来了" --genre "写景散文" --grade "小学四年级" --source "自行整理" --techniques "景物描写" "动静结合"
```

这会自动生成新编号和独立 JSON 文件，并同步作文数据库。也可以直接新建一个 JSON 文件，按下面的结构填写。

```json
{
  "id": "essay012",
  "title": "春天来了",
  "genre": "写景散文",
  "grade": "小学四年级",
  "source": "自行整理",
  "techniques": ["景物描写", "动静结合"],
  "paragraphs": [
    "这里填写第一段完整正文。",
    "这里填写第二段完整正文。"
  ]
}
```

不要把这份模板本身作为范文入库。`paragraphs` 至少有一段，`techniques` 可以是空列表。现有 11 篇均标记为 AI 示例。

## 查看与更新

```powershell
python manage_corpus.py list
python manage_corpus.py reindex
```

- `list` 校验所有文件，列出作文并同步数据库；遇到重复 ID、损坏 JSON 或缺少正文会明确报错。
- `reindex` 同步并重建向量索引；也可在网页“查看知识库”中点“重新生成向量索引”。
- 正常润色前会自动检查作文变化，必要时重建索引。新增作文不需要重启服务。
- 修改原文件会更新对应记录，不会产生重复作文。移走某个文件后，下次同步会移除作文数据库中的对应记录，下次索引更新会移除其向量。

## 三种数据各自的用途

| 位置 | 用途 |
| --- | --- |
| `data/essays/*.json` | 作文原文及元数据；新增、修改从这里入手，可提交 Git |
| `data/compositions.sqlite3` | 自动同步的作文数据库，表名 `compositions`；便于按文体、年级查询 |
| `data/vectors.sqlite3` | RAG 使用的片段和向量；由作文文件自动生成 |

`compositions` 表包含 `id`、`title`、`genre`、`grade`、`source`、`techniques`、`content`、`document_json`、`char_count`、`content_hash`、`created_at`、`updated_at`。

不要直接修改自动生成的数据库来编辑作文，否则下一次同步会以 JSON 文件为准。原来的合并文件已移至 `data/archive/`，只作历史备份，不参与检索。新作文文件进入 Git 前仍需检查来源与是否包含个人信息。
