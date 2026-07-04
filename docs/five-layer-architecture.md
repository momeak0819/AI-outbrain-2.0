# AI外脑 1.2 Five-Layer Architecture

## Product Architecture

```mermaid
flowchart TD
    S["信源层<br/>已实现：抖音、本地音频<br/>规划中：视频号、公众号、B站、网页、图片、PDF"]
    A["采集层<br/>链接识别、元数据解析、媒体与音频准备"]
    P["处理层<br/>FFmpeg、ASR、文本规范化、原始材料导出"]
    K["知识加工层<br/>original/card/both、MCP策展、审核、归档、索引"]
    D["返回层<br/>JSON、IM/终端文本、文件、状态、错误、下一步动作"]
    S --> A --> P --> K --> D
```

Only Douyin and local audio are implemented source adapters. Planned sources are extension targets, not current product claims.

## Technical Architecture

```mermaid
flowchart LR
    E["agent_cli.py<br/>transcribe / batch / ingest"]
    R["SourceRegistry"]
    DS["DouyinSourceAdapter"]
    LA["LocalAudioSourceAdapter"]
    A["layers/acquisition.py"]
    P["layers/processing.py"]
    K["content routing + agent/reviews.py + MCP"]
    D["layers/delivery.py"]
    V["Obsidian Vault"]

    E --> R
    R --> DS
    R --> LA
    DS --> A
    LA --> A
    A --> P
    P --> K
    K --> V
    K --> D
```

The orchestration layer connects the five product layers but is not presented as a sixth product layer.

## Layered JSON

Every ingest/transcribe item exposes:

- `source`
- `acquisition`
- `processing`
- `knowledge`
- `delivery`
- `next`

Existing flat fields remain unchanged for older agents and skills.

## Canonical failure contract

Failures shared across the five layers use:

```json
{
  "stage": "processing",
  "error_code": "asr_unavailable",
  "error": "ASR 环境不可用",
  "recoverable": true
}
```

- `stage` is one of `source`, `acquisition`, `processing`, `knowledge`, or
  `delivery`.
- `error_code` is a stable non-empty snake_case machine code.
- `error` is a user-readable UTF-8 message.
- `recoverable` means retry may succeed after the input or environment is
  corrected; it does not authorize automatic retry.

Legacy aliases are projected only at the Delivery compatibility boundary:
`input` maps to `source`, `asr` to `processing`, and `review` to `knowledge`.
Explicit stages take precedence over old message-based inference.
