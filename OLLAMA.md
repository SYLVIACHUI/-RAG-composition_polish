# 本地 Qwen3 模型

已安装 Ollama 0.35.0，两个模型均已下载并通过接口测试。中文聊天回复完整，Embedding 输出为 1024 维。测试记录见 `ollama-verification.json`。

| 用途 | 配置 |
| --- | --- |
| Ollama 程序 | `D:\Ollama\ollama.exe` |
| 模型存储 | `D:\Ollama\models` |
| API 地址 | `http://127.0.0.1:11434` |
| 聊天模型 | `qwen3:4b` |
| Embedding 模型 | `qwen3-embedding:0.6b` |

`.env` 保存供后续项目代码读取的模型名称和地址。Ollama 本身没有分别设置全局聊天和 Embedding 默认模型的选项；调用接口时需要传入对应的 `model` 名称。

## 使用

新开 PowerShell 后，查看模型：

```powershell
ollama list
ollama run qwen3:4b
```

如果当前终端还没有刷新 PATH，可用完整路径：

```powershell
& 'D:\Ollama\ollama.exe' list
```

Embedding 调用示例：

```powershell
$body = @{ model = 'qwen3-embedding:0.6b'; input = 'Example text' } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:11434/api/embed -Method Post -ContentType 'application/json' -Body $body
```

聊天应用建议先使用 4096 上下文长度，再按显存占用调整。当前下载的 `qwen3:4b` 模板包含思考过程，已验证的调用使用 `think: true`；应用展示 `message.content` 作为最终回答，并给生成过程留足 token 数量。

安装包完整下载后，可以运行 `setup-ollama.ps1` 继续安装、下载模型和验证接口。该脚本会检查官方安装包数字签名；模型下载可续传。

官方资料：[Windows 安装](https://docs.ollama.com/windows)、[Qwen3](https://ollama.com/library/qwen3)、[Qwen3 Embedding](https://ollama.com/library/qwen3-embedding)。
