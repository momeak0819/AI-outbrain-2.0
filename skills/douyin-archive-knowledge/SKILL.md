---
name: douyin-archive-knowledge
description: Save Douyin transcripts into a local knowledge-base directory using douyin-to-text. Use when the user asks to archive, save into a knowledge system, write to a knowledge base, organize Markdown files, or preserve Douyin transcript outputs.
---

# Douyin Knowledge Archive

Use this project-local skill when the user wants transcript Markdown saved into a knowledge-base directory.

## Hard Rules

- Markdown output is the archived file artifact.
- Follow configured `im_content_mode`.
- Formal category filing is allowed only after `review-approve`.
- Use the current IM or agent terminal as the review channel.
- Do not send the Markdown file as the main IM reply.

## Required Init Gate

Before archiving transcripts, follow `../INIT_PROTOCOL.md`.

If `config.ini` is missing, do not ask onboarding questions in chat and do not offer a second CLI setup path. Start the local Web Console for initialization (`python main.py` or `python agent_cli.py init`), and only then continue. Do not archive with default settings.

## Commands

Single item for IM/chat:

```bash
python -X utf8 agent_cli.py transcribe --text "<share text>" --knowledge-dir "<knowledge_dir>" --engine faster_whisper --model-size base --export md --response-mode im --pretty
```

Batch for IM/chat:

```bash
python -X utf8 agent_cli.py batch --text "<many links>" --knowledge-dir "<knowledge_dir>" --engine faster_whisper --model-size base --export md --response-mode im --pretty
```

## Directory Rules

- `--knowledge-dir` is the final Markdown output directory.
- If the user does not provide a directory, ask for one before archiving.
- Audio defaults to `<knowledge_dir>/audio` unless `--audio-output-dir` is provided.
- Do not hardcode the user's knowledge-base path inside skill files.
- If JSON returns `stage: "init"`, follow `../INIT_PROTOCOL.md`: start or direct the user to the Web Console initialization page. Do not retry through chat questions or a second CLI setup path.

## Reply

Confirm source and final paths according to the content mode. Preserve the Inbox transcript after final filing. If batch archiving partially fails, list successful files first, then failed links with reasons.

Do not expose API keys.
