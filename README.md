# douyin-to-text-agent-cli

## Five-layer architecture

AI外脑 separates product responsibilities into:

```text
信源层 -> 采集层 -> 处理层 -> 知识加工层 -> 返回层
```

Currently implemented sources are Douyin and local audio. Video Channels, WeChat articles, Bilibili, webpages, images, and PDF are planned adapter targets only.

The generic entry point is:

```bash
python agent_cli.py ingest --source-type auto --text "<source input>" --pretty
python agent_cli.py ingest --source-type local_audio --audio-file "<path>" --pretty
```

Results include the nested `source`, `acquisition`, `processing`, `knowledge`, `delivery`, and `next` objects while retaining all legacy flat JSON fields. See `docs/five-layer-architecture.md`.

## Project virtual environment

`agent_cli.py` and `main.py` automatically create and use the project-level `.venv`. Core dependencies are installed there before the original command is restarted. Local ASR dependencies are installed only when `faster_whisper` is selected, so the system Python and an existing system Torch installation are not modified.

Dependency groups:

```bash
pip install -r requirements.txt
pip install -r requirements-asr.txt
```

Set `AI_OUTBRAIN_DISABLE_VENV_BOOTSTRAP=1` only for CI or an already managed environment.

All user runtime data remains inside the project so the whole folder can be copied. `.venv` is reused when valid and rebuilt after a machine or Python-path change; `runtime/models`, configuration, reviews, outputs, and Vault content are preserved.

## Clean source release

Build a clean initialization package without modifying the working project:

```bash
python tools/build_source_release.py
```

The ZIP retains all source code, tests, skills, MCP templates, Vault structure, and Local REST API. It excludes runtime environments, models, caches, secrets, review records, personal Inbox content, and the Claudian plugin from the release package only.

## Route 1.2 MCP startup

This copy supports any MCP-capable AI coding agent. QoderWork CN is the recommended default, while Claude Code, Codex, Trae, VS Code, and other clients can use the templates under `mcp/`.

When an agent loads this project:

```bash
python -X utf8 agent_cli.py route12-check --pretty
python -X utf8 agent_cli.py route12-mcp-templates --pretty
```

Read `docs/mcp-setup.md` before configuring the Obsidian bridge. MCP may be configured in different locations for different agents, so the project provides templates but does not auto-install or auto-register external MCP servers.

Without MCP, transcription may still write to Inbox. Formal classification and index updates must not proceed.

MCP setup is part of first-run initialization. `mcp-setup` guides client configuration, `mcp-verify` records real tool checks, and `mcp-status` reports readiness. Plugin detection alone does not set `mcp_ready=true`. If MCP is skipped, initialization forces `im_content_mode=original`.

## Interactive content routing

Initialization stores two independent preferences:

```ini
[preferences]
im_content_mode = both
interaction_channel = auto
```

`im_content_mode` supports:

- `original`: return the transcript.
- `card`: continue through Obsidian MCP and return a knowledge-card review draft.
- `both`: return the transcript and the review draft.

`interaction_channel = auto` uses the originating IM channel when available. Direct Claude Code, Codex, Trae, or terminal-agent calls continue in the current command/chat window.

Knowledge-card reviews use:

```bash
python agent_cli.py review-list --pretty
python agent_cli.py review-show --review-id "<id>" --pretty
python agent_cli.py review-revise --review-id "<id>" --instruction "<changes>" --pretty
python agent_cli.py review-approve --review-id "<id>" --pretty
python agent_cli.py review-cancel --review-id "<id>" --pretty
```

After an MCP draft is written, call `review-draft-ready`. After approved final card and index writes, call `review-finalized`. IM and command-line AI agents follow this same gate; `interaction_channel` only controls where the review is shown.

Approval authorizes final Obsidian MCP filing. It does not delete the original Inbox transcript.

把抖音链接或分享文案转成文字稿，并导出为 Markdown 或 TXT 的命令行工具。

## 功能

- 支持抖音短链、长链和完整分享文案。
- 支持单条转写和批量转写。
- 支持 `faster_whisper` 本地转写。
- 支持 MiMo ASR API 转写。
- 支持导出 `md`、`txt` 或 `both`。
- 支持指定输出目录或知识库目录。
- 默认将文字稿转换为简体中文。
- `agent_cli.py` 输出 JSON，适合 agent 或脚本调用。

## 安装

安装基础依赖：

```bash
pip install -r requirements.txt
```

如果使用本地 `faster_whisper` 转写，初始化会自动安装本地 ASR 依赖。也可以提前手动安装：

```bash
pip install -U -i https://pypi.tuna.tsinghua.edu.cn/simple faster-whisper opencc-python-reimplemented
```

安装并确认 `ffmpeg` / `ffprobe` 可用：

```bash
ffmpeg -version
ffprobe -version
```

Windows 建议使用 UTF-8 运行：

```bash
python -X utf8 agent_cli.py --help
```

也可以在当前终端设置 `PYTHONUTF8=1`。Windows PowerShell 5.1 的活动代码页、
控制台输出编码和 `$OutputEncoding` 可能不一致，因此终端出现中文乱码不代表源码
已经损坏。请先运行只读检查：

```bash
python -X utf8 tools/check_text_encoding.py
python -X utf8 tools/check_text_encoding.py --json
```

扫描器严格检查公开维护文本的 UTF-8、U+FFFD、NUL 和高置信连续乱码片段。
它不会批量转码或自动改写文件；BOM 只报告为 warning。

## 初始化

首次使用推荐运行交互初始化：

```bash
python -X utf8 agent_cli.py init
```

初始化会配置：

- ASR 引擎：`faster_whisper` 或 `mimo`
- 本地模型：`base`、`small`、`medium`
- MiMo API Key
- 导出目录
- 音频目录
- 是否保留音频
- 默认导出格式

选择本地 `faster_whisper` 时，初始化会自动准备：

- `faster-whisper`
- `opencc-python-reimplemented`，用于简体中文转换
- 所选 faster-whisper 模型

首次本地初始化需要下载依赖和模型，可能耗时较久。Python 依赖使用清华 PyPI 镜像，模型下载默认使用 `https://hf-mirror.com`。

首次初始化强制使用本地 Web Console，不在聊天窗口逐项询问，也不提供第二条 CLI 初始化路径：

```bash
python -X utf8 main.py
```

或：

```bash
python -X utf8 agent_cli.py init
```

Web Console 会引导选择 ASR、输出目录、MCP、内容模式等，并写入 `config.ini`。不要公开或提交包含 API Key 的 `config.ini`。

## Obsidian 初始化知识库

项目内置 `Obsidian/AI外脑知识库/` 作为默认初始化知识库模板。默认转写输出目录为：

```text
Obsidian\AI外脑知识库\00_Inbox\抖音链接
```

发布项目时保留这个目录，它不是运行缓存。`.claudian/sessions/` 只保留空目录占位，本机会话记录不会公开。

## 环境检查

检查本地环境：

```bash
python -X utf8 agent_cli.py check-env --pretty
```

查看本地模型状态：

```bash
python -X utf8 agent_cli.py models --pretty
```

## 单条转写

从分享文案中提取链接并转写：

```bash
python -X utf8 agent_cli.py transcribe --text "<抖音分享文案>" --export md --pretty
```

直接转写链接：

```bash
python -X utf8 agent_cli.py transcribe --url "https://v.douyin.com/xxxx/" --export md --pretty
```

指定引擎：

```bash
python -X utf8 agent_cli.py transcribe --url "https://v.douyin.com/xxxx/" --engine mimo --export md --pretty
```

IM 回复模式会把完整文字稿放进 JSON，便于 agent 直接在聊天里贴正文：

```bash
python -X utf8 agent_cli.py transcribe --text "<抖音分享文案>" --response-mode im --pretty
```

也可以继续使用 `--include-transcript` 只请求 `transcript` 字段。

## 批量转写

从文本中提取多条链接并顺序转写：

```bash
python -X utf8 agent_cli.py batch --text "<多条抖音分享文案>" --export md --pretty
```

从文件读取链接：

```bash
python -X utf8 agent_cli.py batch --input-file links.txt --export md --pretty
```

## 输出目录

指定普通输出目录：

```bash
python -X utf8 agent_cli.py transcribe --text "<抖音分享文案>" --output-dir "Obsidian\AI外脑知识库\00_Inbox\抖音链接" --export both --pretty
```

写入知识库目录：

```bash
python -X utf8 agent_cli.py transcribe --text "<抖音分享文案>" --knowledge-dir "D:\Knowledge\Inbox" --export md --pretty
```

保留提取出的音频：

```bash
python -X utf8 agent_cli.py transcribe --text "<抖音分享文案>" --keep-audio --pretty
```

## JSON 输出

成功示例：

```json
{
  "success": true,
  "mode": "transcribe",
  "title": "示例抖音视频",
  "author": "示例作者",
  "md_path": "Obsidian/AI外脑知识库/00_Inbox/抖音链接/示例抖音视频.md",
  "txt_path": "",
  "exported_paths": ["Obsidian/AI外脑知识库/00_Inbox/抖音链接/示例抖音视频.md"],
  "audio_path": "",
  "engine": "mimo",
  "transcript_chars": 1234,
  "error": "",
  "logs": []
}
```

失败示例：

```json
{
  "success": false,
  "stage": "input",
  "error": "未从输入中找到抖音链接"
}
```

首次使用且没有 `config.ini` 时，非交互调用会返回 `stage=init`。支持本地 skills 的 agent 应按 `skills/INIT_PROTOCOL.md` 在对话里完成初始化，然后重试原命令。

## MiMo 大音频处理

MiMo API 有音频大小限制。工具会在音频接近限制前自动分片转写，并在合并时做相邻去重。分片失败不会写入正文，会体现在返回 JSON 的 `error` 字段中。

## 项目 Skills

项目内置 4 个说明型 skill，供支持本地 skill 的 agent 读取：

- `skills/douyin-env-check/`
- `skills/douyin-transcribe-one/`
- `skills/douyin-transcribe-batch/`
- `skills/douyin-archive-knowledge/`

这些 skill 只说明何时以及如何调用 `agent_cli.py`。

当 `config.ini` 不存在时，skills 会先按 `skills/INIT_PROTOCOL.md` 在对话里完成初始化，再继续转写或检查环境。

## 不要公开的文件

发布或提交前不要包含：

- `config.ini`
- `.env`
- `outputs/`
- `runtime/`
- API Key
- 音频或视频临时文件
- `__pycache__/`
- `.pyc`
