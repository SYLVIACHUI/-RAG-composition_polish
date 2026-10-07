# 语你一起：中小学生汉语作文智能评价与润色系统

## 演示

![main](https://github.com/SYLVIACHUI/-RAG-composition_polish/blob/main/photo/main.png)
![rag](https://github.com/SYLVIACHUI/-RAG-composition_polish/blob/main/photo/polish.gif)

## 启动

需要 Python 3.10+ 和已启动的 Ollama。需要安装 `requirements.txt` 中的 FastAPI、Uvicorn、LangChain Core、jieba 和 rank-bm25 等依赖。 在运行项目的电脑上准备两个模型：

```powershell
ollama pull qwen3:4b
ollama pull qwen3-embedding:0.6b
```

下载项目并运行（以下为 PowerShell 命令）：

```powershell
git clone https://github.com/SYLVIACHUI/-RAG-composition_polish.git
cd ./-RAG-composition_polish
Copy-Item .env.example .env
python -m pip install -r requirements.txt
python app.py
```

打开 <http://127.0.0.1:8000>。点击“填入示例”，选择年级、润色重点，也可填写个性化要求，然后点击“开始检索与润色”。

本地 `.env`、下载的安装包、模型文件、向量数据库和含作文原文的评价数据库不上传 GitHub。仓库包含配置示例与演示范文，首次运行时自动重建向量库。

首次润色时自动建立向量库；也可运行 `python app.py --index`，或在界面的“查看知识库”中重建。默认端口被占用时使用 `python app.py --port 8001`。

## 实际 RAG 流程

1. 自动读取 `data/essays/` 中每篇独立的 JSON 作文，并同步到 SQLite 作文数据库，按自然段分块；长段落每 300 字分块，重叠 40 字。
2. 调用 Ollama `/api/embed`，使用 `qwen3-embedding:0.6b` 生成 1024 维向量，归一化后写入 SQLite。
3. 使用 Qwen3 Embedding 进行向量检索，同时用 jieba 搜索模式分词和 BM25Okapi 进行关键词检索。两路各召回前 10 个片段，用等权 RRF（常数 60）融合排名，取 Top-3。
4. 将真实检索出的片段、学生原文、年级和个性化要求放入 prompt，调用 `qwen3:4b`。
5. 用同一聊天模型独立对照原文复核一次，再输出润色正文、修改说明、借鉴方法和来源片段 ID。复核时不重新输入范文，减少参考情节对事实核对的干扰。界面实时显示处理阶段；模型复核仍不能替代人工检查。
6. 计算字符 BLEU-4 与字数变化，保存润色记录，支持评价者 A/B 分别填写人工评分。

这里的向量库是 **SQLite 保存向量 + Python 全量余弦检索**，适合最小示例；LangChain Core 负责流程编排与检索器接口，目前未使用 Chroma 或 FAISS。

## 评价的含义与边界

- **机器评价**：字符级 BLEU-4，以学生原文为单一参考；去掉空白，保留标点，采用 1～4 gram 等权精确率和长度惩罚，不做平滑。数值是 0～100，用于观察字面改写程度，**不是润色质量、语义匹配准确率或作文分数**。BLEU 基于 [Papineni 等人的原始论文](https://aclanthology.org/P02-1040/)，此处使用中文字符分词。
- **人工评价**：原意保留、表达通顺、年级适配各 1～5 分。两位评价者应独立评价后分别录入；同一记录、同一评价者再次保存会更新其评分。

## 测试

```powershell
python -m unittest discover -s tests -v
```

测试覆盖向量排序、维度不匹配、输入边界、索引缓存与失败保留、输出截断、来源有效性、BLEU 和人工反馈存储。

Ollama 官方接口：[Embedding](https://docs.ollama.com/api/embed)、[Chat](https://docs.ollama.com/api/chat)。

## 持续扩充作文库

每篇作文独立存放在 `data/essays/`，可自行在目录中新建符合格式的 JSON 文件，下次润色会自动识别。详见 [作文库管理说明](data/essays/README.md)。

## 混合检索

`retrieval.py` 使用 [jieba](https://github.com/fxsjy/jieba) 和 [rank-bm25](https://github.com/dorianbrown/rank_bm25)。查询与片段使用相同分词方式，转小写、去除标点和少量常见停用词；BM25 对标题与正文建立内存索引，查询词去重。索引按片段内容缓存，内容变化后自动更新，重启时自动建立，无需重建已有向量库。

RRF 按两路排名计算 `sum(1 / (60 + rank))`，不直接相加不同尺度的原始分数。没有关键词命中时沿用向量排序；所有分词为空时也可正常回退。界面分别显示语义余弦、BM25 和 RRF 分数，分数均不代表润色质量或概率。当前仍然需要 Ollama 生成查询向量，不会在模型离线时自动切换为纯 BM25。

新增功能后，在 VS Code 所选 Python 环境运行 `python -m pip install -r requirements.txt`，再重启 `python app.py`。混合检索的质量提升需要后续标注集验证。

## FastAPI + LangChain 架构

- `app.py`：FastAPI 路由、Pydantic 请求校验、Uvicorn 服务与 NDJSON 流式响应。原有接口路径保持兼容，参数错误仍返回 HTTP 400 与 `error` 字段。
- `pipeline.py`：使用 LangChain Core 的 LCEL `RunnableSequence` 串联 `prepare_index → hybrid_retrieval → generate_draft → review_fidelity → evaluate_and_save`，`HybridEssayRetriever` 实现 `BaseRetriever`，以 `Document` 传递正文与片段元数据。
- `rag.py`：向量索引、提示词、Ollama 流式传输与结果校验；`polish()` 委托 LangChain 流程执行。
- `retrieval.py`：jieba + BM25 与向量排名的 RRF 融合。
- `evaluation.py`：机器指标、运行记录和人工反馈。

安装和启动：

```powershell
python -m pip install -r requirements.txt
python app.py
```

也可运行 `python -m uvicorn app:app --host 127.0.0.1 --port 8000`。开发调试时可加 `--reload`。继续支持 `python app.py --port 8001` 和 `python app.py --index`。旧服务需要先用 Ctrl+C 停止。

- 页面：<http://127.0.0.1:8000/>
- Swagger 接口文档：<http://127.0.0.1:8000/docs>
- OpenAPI 定义：<http://127.0.0.1:8000/openapi.json>

模型工作放在独立线程中，避免阻塞 FastAPI 事件循环。单进程内同一时间仅允许一项润色或索引任务，忙时返回 409；请使用单 worker，多个 worker 的内存锁不能相互协调。浏览器断开后，工作线程在下一次进度回调时停止；等待 Ollama 响应时不能立即取消，锁保留到工作线程实际退出。

使用 LangChain 的核心包 `langchain-core`，无需安装代理或第三方模型集成包。模型仍通过本地 Ollama 适配器调用，保留两轮生成、超时和格式校验。正式入口关闭 LangSmith 远程追踪，作文不会因追踪环境变量而自动上传。

测试覆盖真实 Uvicorn HTTP 流式进度、并发 409、错误后解锁、请求校验、OpenAPI 和 LCEL 阶段顺序。运行 `python -m unittest discover -s tests -v`。

实现参考：[FastAPI 流式响应](https://fastapi.tiangolo.com/advanced/custom-response/)、[LangChain RunnableSequence](https://reference.langchain.com/python/langchain-core/runnables/base/RunnableSequence)。
