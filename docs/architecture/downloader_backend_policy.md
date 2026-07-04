# 下载后端策略：yt-dlp 作为获取层核心媒体后端

## 结论

AI 外脑 2.0 的下载后端遵循：

```text
成熟专用链路
→ 平台专用 downloader backend
→ yt-dlp 通用媒体 downloader backend
→ unsupported_source_type / unsupported_platform
```

`yt-dlp` 已登记为初始化可感知的获取层核心能力，并已通过隔离 downloader 接入 Acquisition 层。它用于 YouTube、Bilibili、X/Twitter、Vimeo、Twitch、TikTok、Instagram、小红书和 generic_video 等视频类信源的基础获取能力。

## 固定规则

- `douyin` 继续使用现有成熟专用链路，不改走 `yt-dlp`，失败时也不自动 fallback 到 `yt-dlp`。
- `local_audio` 继续使用本地文件校验链路；用户文件保持 `ownership=user_owned`、`cleanup_policy=never`。
- Source 层只识别 `source_type`，不 import、不调用、不探测 `yt-dlp`。
- Acquisition 层通过 `src/layers/downloaders/ytdlp_downloader.py` 封装 `yt-dlp`，并输出标准 `AcquisitionResult` / `AcquisitionArtifact`。
- Processing 层只消费标准 artifact；如果下载结果是视频容器，必须以 `artifact.kind=video` 表达，不能伪装成 ASR-ready audio。
- Knowledge / Delivery 不感知下载后端。

## 当前已接入视频信源

Source 层可识别：

- `youtube`
- `bilibili`
- `generic_video`
- `x_video`
- `vimeo`
- `twitch`
- `tiktok`
- `instagram`
- `xiaohongshu`

这些信源在 Acquisition 层统一进入 `yt_dlp` backend。真实下载是否成功取决于平台公开可访问性、cookies、地区限制和当前 `yt-dlp` 支持情况；失败必须返回结构化错误。

## 错误协议

`yt-dlp` 获取失败使用 Acquisition 层错误：

- `unsupported_platform`
- `ytdlp_unavailable`
- `ytdlp_metadata_failed`
- `ytdlp_download_failed`
- `ytdlp_auth_required`
- `media_prepare_error`

失败结果必须 `recoverable=true`，并且不得泄露 cookies、token、authorization、secret、password 等敏感字段。

## Artifact 所有权

`yt-dlp` 下载产物默认：

- `ownership=acquisition_temp`
- `cleanup_policy=on_processing_complete`

下载文件不得标记为 `user_owned`。用户显式传入的本地文件仍然是 `user_owned`，且永不自动删除。
