# Source Adapter 协议

Source Adapter 只负责识别和包装输入，不负责下载、文件校验、ASR 或知识加工。

## Adapter 职责

- 接收 `SourceInput`。
- 在 auto 模式下判断是否能处理该输入。
- 在显式 `source_type` 模式下执行强制路由包装。
- 返回 `SourceDocument` 或结构化 Source failure。

## 已实现 Source Types

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

## 边界

- 不检查本地路径是否存在。
- 不调用 `yt-dlp`。
- 不调用 FFmpeg。
- 不调用 ASR。
- 不写 Obsidian。

## 视频类 SourceDocument

视频 URL 信源应输出：

- `status=ready`
- `source_type=<platform>`
- `media_type=video`
- `original_url=<url>`
- `metadata.download_backend=yt_dlp`
- `metadata.platform=<platform>`

Douyin 是例外：继续输出 `source_type=douyin` 并进入专用 Acquisition 链路。
