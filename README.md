# AI 外脑 2.0

AI 外脑 2.0 是一个本地运行的个人知识获取与知识管理工作台。它以“五层架构”为核心，把链接、音视频、本地文件和项目记忆整理成可审核、可归档、可继续加工的知识资产。

项目当前不再只是“抖音转文字”，也不只依赖 MiMo。它已经包含本地 Web Console、多信源获取、yt-dlp 视频平台基础获取、多个 ASR 引擎、Obsidian MCP 审核归档、项目记忆沉淀和源码自动更新检查。

## 核心能力

- 本地 Web Console：首次初始化、能力查看、信源配置、ASR 配置、MCP 状态、项目记忆等统一在网页中完成。
- 五层工作流：信源层 → 采集层 → 处理层 → 知识加工层 → 返回层。
- 多信源接入：抖音、本地音频、本地 MP4，以及 YouTube、B 站、TikTok、Instagram、小红书、Twitch、Vimeo、X / Twitter、通用视频链接。
- yt-dlp 获取后端：用于未建立专用链路的视频平台；抖音仍优先使用项目内专用链路。
- 音视频转文字：支持本地和云端 ASR。
- 知识卡片审核：card / both 模式会生成待审核草稿，正式进入知识库必须经过审核门。
- Obsidian 知识库集成：内置 AI 外脑知识库骨架、MCP 模板和分类目录。
- 项目记忆：把 AI coding 阶段成果、决策、风险和下一步沉淀到 `08_项目映射库`。
- 源码自动更新：用户从 GitHub clone 后，启动时可检查远程新版本，并在本地源码未改动时安全快进更新。

## 推荐使用方式

首次运行请在项目根目录执行：

```powershell
python -X utf8 main.py
```

或者：

```powershell
python -X utf8 agent_cli.py init
```

这两个入口都会打开本地 Web Console。首次初始化必须通过 Web Console 完成，不在聊天窗口逐题询问，也不提供第二套对话式初始化流程。

Web Console 默认只监听本机地址：

```text
127.0.0.1
```

## 初始化会配置什么

初始化页面会引导你配置：

- ASR 引擎
- ASR 凭据或本地模型大小
- 文字稿输出目录
- 音频缓存目录
- 导出格式
- 内容返回模式：原文、知识卡片、双输出
- 交互渠道：自动判断、IM、终端
- 是否保留音频
- 是否配置 Obsidian MCP

配置会写入本地 `config.ini`。请不要把包含 API Key、密钥或个人路径的 `config.ini` 提交到公开仓库。

## 支持的信源

当前已登记并接入主管线的信源包括：

| 信源 | 获取方式 | 说明 |
| --- | --- | --- |
| 抖音 | 专用链路 | 当前稳定链路，不改走 yt-dlp |
| 本地音频 | 本地文件 | 支持常见音频格式 |
| 本地 MP4 | 本地文件 | 可作为本地媒体输入 |
| YouTube | yt-dlp | 基础获取能力，部分内容可能需要 Cookie |
| B 站 | yt-dlp | 基础获取能力，部分内容可能需要 Cookie |
| TikTok | yt-dlp | 基础获取能力 |
| Instagram | yt-dlp | 可能需要登录 Cookie |
| 小红书 | yt-dlp | 通常需要登录 Cookie |
| Twitch | yt-dlp | 基础获取能力 |
| Vimeo | yt-dlp | 基础获取能力 |
| X / Twitter | yt-dlp | 可能需要登录 Cookie |
| 通用视频链接 | yt-dlp | 用于无专用适配器的视频网页 |

普通网页正文、公众号正文、PDF、图片 OCR、纯文本直通等方向属于后续扩展，不在当前版本中冒充完整打通。

## 支持的 ASR 引擎

当前 ASR 能力池包括：

| 引擎 | 类型 | 状态 |
| --- | --- | --- |
| faster-whisper | 本地 | 已实现 |
| MiMo ASR | 云端 | 已实现 |
| 阿里云百炼 Qwen-ASR | 云端 | 已接入配置与引擎 |
| 腾讯云 ASR | 云端 | 已接入配置与引擎 |
| 火山引擎豆包语音识别 | 云端 | 已接入配置与引擎 |
| custom_api | 自定义接口 | 预留 |
| mock | 测试引擎 | 用于开发和验证 |

真实云端 ASR 使用前需要在 Web Console 中填写对应服务商凭据。项目不会把密钥写入 README、Skill 或公开模板。

## 常用命令

启动 Web Console：

```powershell
python -X utf8 main.py
```

检查 Route 1.2 / Obsidian MCP 状态：

```powershell
python -X utf8 agent_cli.py route12-check --pretty
```

查看 MCP 模板：

```powershell
python -X utf8 agent_cli.py route12-mcp-templates --pretty
```

通过五层主管线处理一个链接或本地路径：

```powershell
python -X utf8 agent_cli.py ingest "<链接或本地文件路径>" --source-type auto --pretty
```

手动检查源码更新：

```powershell
python -X utf8 agent_cli.py update-check --no-pull --pretty
```

允许安全自动拉取更新：

```powershell
python -X utf8 agent_cli.py update-check --pretty
```

## 自动更新规则

源码版从 GitHub clone 后，每次通过以下入口加载时会检查是否有新版本：

```powershell
python -X utf8 main.py
python -X utf8 agent_cli.py init
python -X utf8 agent_cli.py console
```

更新策略是保守的：

- 只检查当前 Git 仓库的 `origin`。
- 只在当前分支落后远端时处理。
- 只有本地已跟踪源码没有改动时，才执行 `git pull --ff-only`。
- 如果用户本地改过源码，只提示有更新，不会覆盖。
- 不会自动 `git add`、不会自动 `git commit`、不会自动 `git push`。

如需临时关闭启动检查：

```powershell
$env:AI_OUTBRAIN_DISABLE_UPDATE_CHECK = "1"
```

## Obsidian MCP 与审核门

Route 1.2 的目标是让 AI coding agent 通过 Obsidian MCP / REST 控制知识库，而不是直接绕过审核写正式分类目录。

规则：

- 转写结果可以进入 Inbox。
- card / both 模式会生成 `_待审核` 草稿。
- 正式写入分类目录和索引必须经过审核。
- MCP 不可用时，知识卡片归档必须停止；可以把原文作为 fallback 返回。
- 插件已安装不等于 MCP 已连接，必须通过真实读取、写入、删除测试验证。

常用审核命令：

```powershell
python -X utf8 agent_cli.py review-list --pretty
python -X utf8 agent_cli.py review-show --review-id "<review_id>" --pretty
python -X utf8 agent_cli.py review-approve --review-id "<review_id>" --pretty
python -X utf8 agent_cli.py review-revise --review-id "<review_id>" --instruction "<修改意见>" --pretty
python -X utf8 agent_cli.py review-cancel --review-id "<review_id>" --pretty
```

## 项目记忆

项目记忆用于把开发型 AI Agent 的阶段成果沉淀到 Obsidian 的 `08_项目映射库`。

它适合记录：

- 本轮目标
- 已完成成果
- 关键决策
- 修改范围
- 测试与验证
- 风险与技术债
- 后续计划
- 可关联知识点

项目内置 Skill：

```text
skills/project-memory-capture/SKILL.md
```

外部工作 Agent 可以生成结构化 `memory.json` 后调用：

```powershell
python -X utf8 agent_cli.py project-memory-capture --payload-file memory.json --pretty
```

项目记忆同样不直接写正式库，必须经过 `_待审核 → approve → finalized`。

## 项目目录

```text
agent_cli.py                  # 面向 AI Agent 和脚本的 JSON CLI
main.py                       # 用户默认入口，启动本地 Web Console
bootstrap_runtime.py          # 自动创建和复用项目 .venv
src/                          # 核心源码
src/layers/                   # 五层架构实现
src/asr/                      # ASR 引擎
src/web_console/              # 本地 Web Console
skills/                       # 项目内置 Skills
mcp/                          # Obsidian MCP 配置模板
docs/                         # 架构与接入文档
Obsidian/AI外脑知识库/         # 内置知识库骨架
tools/check_text_encoding.py  # UTF-8 文本健康检查
```

## 不要提交的内容

以下内容不应该进入公开 GitHub 仓库：

- `config.ini`
- `.env`
- `.venv/`
- `runtime/`
- `outputs/`
- `.workflow/`
- API Key、Cookie、Token
- 下载媒体和音视频中间文件
- Obsidian 个人运行数据

项目的源码发布构建器会自动排除这些内容。

## 发布源码包

构建干净源码 ZIP：

```powershell
python -X utf8 tools/build_source_release.py
```

发布包会保留：

- Web Console
- 五层架构源码
- ASR 引擎
- yt-dlp 获取层
- Project Memory
- MCP 模板
- Obsidian 知识库骨架
- 必要的只读健康检查工具

发布包会排除：

- 测试目录
- 开发临时目录
- 运行数据
- 本地配置
- 密钥
- 缓存
- 下载媒体

## 推荐工作方式

普通用户：

```powershell
python -X utf8 main.py
```

AI coding agent：

1. 读取 `AGENTS.md`。
2. 读取 `initialization_manifest.json`。
3. 读取 `skills/INIT_PROTOCOL.md`。
4. 执行 Route 1.2 检查。
5. 如缺少 `config.ini`，启动 Web Console，而不是在聊天里做初始化问答。

## 当前边界

- Web Console 是本地控制台，不提供公网服务。
- yt-dlp 平台的真实可用性会受平台限制、地区、登录态和 Cookie 影响。
- 云 ASR 需要用户自行配置服务商凭据。
- 正式知识库归档必须走审核门。
- cc-connect / IM Bridge 实验已取消，不属于当前发布版核心能力。
