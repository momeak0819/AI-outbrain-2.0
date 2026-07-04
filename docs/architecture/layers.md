# 五层架构说明

AI 外脑 2.0 采用五层架构：

```text
Source → Acquisition → Processing → Knowledge → Delivery
```

## Source 信源层

职责：识别内容来自哪里，只做类型判断和输入包装。

当前实现：

- `douyin`
- `local_audio`
- `youtube`
- `bilibili`
- `generic_video`
- `x_video`
- `vimeo`
- `twitch`
- `tiktok`
- `instagram`
- `xiaohongshu`

Source 层不下载、不转写、不调用 MCP、不检查本地文件是否存在。

## Acquisition 获取层

职责：把信源转为标准本地媒体、文本候选或结构化失败。

当前核心能力：

- Douyin 专用链路。
- local_audio 本地文件校验。
- `yt-dlp` 通用媒体下载后端。
- `AcquisitionArtifact` 所有权与清理策略。

## Processing 处理层

职责：把音频/视频/文本候选转为干净文本，并导出 Markdown/TXT。

当前核心能力：

- ASR engine factory。
- faster-whisper、MiMo、P0 云 ASR、mock。
- Processing Core 统一执行 readiness、capability、transcribe、normalize、export。
- 安全清理 Acquisition 临时媒体。

## Knowledge 知识层

职责：把文本转为可审核知识草稿，并通过 Route 1.2 审核门进入 Obsidian。

当前核心能力：

- `create_knowledge_result` 唯一入口。
- Review 状态机。
- MCP readiness / Vault structure validation。
- original/card/both 知识流程裁定。

## Delivery 交付层

职责：把五层结果包装成 canonical envelope，并投影为旧 flat JSON 字段。

当前核心能力：

- `WorkflowEnvelope`
- canonical failure
- legacy projection
- batch aggregation
- Web Console / CLI 统一可消费结果。
