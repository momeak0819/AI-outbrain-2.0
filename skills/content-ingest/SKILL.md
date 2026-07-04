---
name: content-ingest
description: Ingest one supported source through the five-layer AI外脑 workflow. Use for a Douyin URL/share text or a local audio file when the generic source-neutral entry is preferred.
---

# Generic Content Ingest

Use this skill for the source-neutral five-layer workflow:

```text
source -> acquisition -> processing -> knowledge -> delivery
```

## Implemented Sources

- `douyin`: URL or copied share text
- `local_audio`: existing local audio file

Video Channels, WeChat articles, Bilibili, webpages, images, and PDF are planned adapters only and must not be presented as implemented.

## Commands

Automatic source detection:

```bash
python -X utf8 agent_cli.py ingest --source-type auto --text "<input>" --pretty
```

Douyin:

```bash
python -X utf8 agent_cli.py ingest --source-type douyin --url "<url>" --pretty
```

Local audio:

```bash
python -X utf8 agent_cli.py ingest --source-type local_audio --audio-file "<path>" --pretty
```

## Response Contract

Read the nested `source`, `acquisition`, `processing`, `knowledge`, `delivery`, and `next` objects first. Legacy flat fields remain available for compatibility.

- If a layer has `status=failed`, report that layer and its error.
- If `next.workflow_complete=false`, continue with `next.action` and `next.skill`.
- `card` and `both` still require MCP draft creation and explicit user approval.
- Do not delete the original source transcript after final filing.
