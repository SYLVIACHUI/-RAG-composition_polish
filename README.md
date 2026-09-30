# 语你一起：中小学生汉语作文智能评价与润色系统

## 演示



## 启动

需要 Python 3.10+ 和已启动的 Ollama。**无需安装任何第三方 Python 包。** 在运行项目的电脑上准备两个模型：

```powershell
ollama pull qwen3:4b
ollama pull qwen3-embedding:0.6b
```

下载项目并运行（以下为 PowerShell 命令）：

```powershell
git clone https://github.com/SYLVIACHUI/-RAG-composition_polish.git
cd ./-RAG-composition_polish
Copy-Item .env.example .env
python app.py
```

打开 <http://127.0.0.1:8000>。点击“填入示例”，选择年级、润色重点，也可填写个性化要求，然后点击“开始检索与润色”。

本地 `.env`、下载的安装包、模型文件、向量数据库和含作文原文的评价数据库不上传 GitHub。仓库包含配置示例与演示范文，首次运行时自动重建向量库。

首次润色时自动建立向量库；也可运行 `python app.py --index`，或在界面的“查看知识库”中重建。默认端口被占用时使用 `python app.py --port 8001`。

## 实际 RAG 流程

1. 自动读取 `data/essays/` 中每篇独立的 JSON 作文，并同步到 SQLite 作文数据库，按自然段分块；长段落每 300 字分块，重叠 40 字。
2. 调用 Ollama `/api/embed`，使用 `qwen3-embedding:0.6b` 生成 1024 维向量，归一化后写入 SQLite。
3. 将输入作文转换为向量，计算与库中片段的余弦相似度，取 Top-3。
4. 将真实检索出的片段、学生原文、年级和个性化要求放入 prompt，调用 `qwen3:4b`。
5. 用同一聊天模型独立对照原文复核一次，再输出润色正文、修改说明、借鉴方法和来源片段 ID。复核时不重新输入范文，减少参考情节对事实核对的干扰。界面实时显示处理阶段；模型复核仍不能替代人工检查。
6. 计算字符 BLEU-4 与字数变化，保存润色记录，支持评价者 A/B 分别填写人工评分。

这里的向量库是 **SQLite 保存向量 + Python 全量余弦检索**，适合最小示例；当前不依赖 Chroma、FAISS 或 LangChain。

## 文件

| 文件 | 作用 |
| --- | --- |
| `app.py` | Python HTTP 服务与流式进度接口 |
| `rag.py` | Ollama 调用、切分、向量入库、Top-3 检索和 prompt |
| `evaluation.py` | 字符 BLEU、润色记录和人工反馈持久化 |
| `static/index.html` | 中文浏览器界面，无外部 CDN |
| `data/essays/*.json` | 每篇作文一个文件，包含正文、文体、年级、来源和写法 |
| `data/compositions.sqlite3` | 自动同步的作文数据库 |
| `corpus.py` / `manage_corpus.py` | 作文校验、数据库同步和命令行导入 |
| `data/archive/` | 历史合并文件备份，不参与检索 |
| `data/vectors.sqlite3` | 实际生成的向量数据库 |
| `data/evaluations.sqlite3` | 原文、要求、润色结果、检索片段、prompt 版本、人工评分 |
| `.env` | Ollama 地址和两个模型名称 |

范文内容、Embedding 模型名称或模型摘要发生变化时，系统自动重建索引。构建失败时保留原索引。为照顾 6GB 显存，Embedding 请求后释放模型，聊天上下文设为 8192；同一时刻只处理一个模型任务。

## 评价的含义与边界

- **机器评价**：字符级 BLEU-4，以学生原文为单一参考；去掉空白，保留标点，采用 1～4 gram 等权精确率和长度惩罚，不做平滑。数值是 0～100，用于观察字面改写程度，**不是润色质量、语义匹配准确率或作文分数**。BLEU 基于 [Papineni 等人的原始论文](https://aclanthology.org/P02-1040/)，此处使用中文字符分词。
- **人工评价**：原意保留、表达通顺、年级适配各 1～5 分。两位评价者应独立评价后分别录入；同一记录、同一评价者再次保存会更新其评分。
- 每次润色和人工反馈保存在本机 SQLite，可用于后续 prompt、检索策略和知识库的人工迭代；没有自动训练或自动改写 prompt。
- 目前有 **11 篇 AI 生成范文**（原有 1 篇和新增 10 篇），覆盖多种文体，但仍属于小型演示语料库。库中没有相近主题时也会返回相对最接近的片段，相似度只表示相对接近程度；提示词允许不采纳不相关参考。
- 项目简介中的 **4328 篇数据、Kappa 0.82、匹配度 92%** 没有作为本次演示的测量结果使用。尚未导入完整语料，未开展双人标注统计，也未计算 Kappa 或匹配准确率。
- 本版支持粘贴文字，不含 OCR。模型输出可能出现过度修改，仍需结合原文和人工评分检查。
- 实测已知问题：`qwen3:4b` 在雨伞示例中可能把“拿过去一点”误解为“往我这边靠”，即使加入独立复核也未稳定纠正。因此当前闭环验证只证明检索、生成与评价可运行，不证明语义保真；这类样例应纳入后续人工评估和模型对比。

## 测试

```powershell
python -m unittest discover -s tests -v
```

测试覆盖向量排序、维度不匹配、输入边界、索引缓存与失败保留、输出截断、来源有效性、BLEU 和人工反馈存储。

Ollama 官方接口：[Embedding](https://docs.ollama.com/api/embed)、[Chat](https://docs.ollama.com/api/chat)。

## 持续扩充作文库

每篇作文独立存放在 `data/essays/`，当前共 11 篇。新增 UTF-8 文本示例：

```powershell
python manage_corpus.py add --file "D:\我的作文\春天.txt" --title "春天来了" --genre "写景散文" --grade "小学四年级"
python manage_corpus.py reindex
```

也可直接在目录中新建符合格式的 JSON 文件，下次润色会自动识别。详见 [作文库管理说明](data/essays/README.md)。
