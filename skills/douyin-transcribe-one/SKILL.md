---
name: douyin-transcribe-one
description: Transcribe one Douyin video from a URL or copied share text into txt/md using the project agent CLI. Use when the user sends a single Douyin link, v.douyin.com short link, douyin.com video URL, iesdouyin.com share URL, or pasted Douyin share text and wants a transcript.
---

# Douyin Single Transcription

Use this project-local skill for one Douyin link or one pasted share message.

## Hard Rules

- Markdown/TXT outputs are file exports only.
- Follow configured `im_content_mode`: `original`, `card`, or `both`.
- `card` and `both` must continue to `douyin-curate-via-obsidian-mcp`; do not stop after transcription.
- Use `interaction_channel=auto` so IM requests return to IM and direct agent calls continue in the current command/chat window.
- Do not send the Markdown file as the main IM reply.

## Workflow

1. Run from the project root.
2. Before transcription, follow `../INIT_PROTOCOL.md`.
3. If `config.ini` is missing, do not ask onboarding questions in chat and do not offer a second CLI setup path. Start the local Web Console for initialization (`python main.py` or `python agent_cli.py init`), then continue only after Web initialization succeeds.
4. Prefer `--text` for copied share messages and `--url` for clean URLs.
5. Use `--knowledge-dir` when the user gives a knowledge-base directory.
6. Use configured content and interaction routing. Override with `--im-content-mode` or `--interaction-channel` only when requested.
7. If JSON returns `next_skill`, execute it before treating the workflow as complete.
8. If JSON returns `workflow_complete=false`, continue through the reported state. A successful transcript alone is not completion.

## Commands

Local free mode for IM/chat:

```bash
python -X utf8 agent_cli.py transcribe --text "<full user message>" --engine faster_whisper --model-size base --export md --response-mode im --pretty
```

MiMo mode for IM/chat:

```bash
python -X utf8 agent_cli.py transcribe --text "<full user message>" --engine mimo --export md --response-mode im --pretty
```

Use `MIMO_API_KEY` or `config.ini` for the MiMo key. Do not hardcode keys in skill files or commands that will be logged.

## JSON Handling

Success fields:

- `title`
- `author`
- `md_path`
- `txt_path`
- `audio_path`
- `transcript_chars`
- `reply_mode`
- `reply_text`, when `--response-mode im` is used
- `transcript`, when `--response-mode im` or `--include-transcript` is used

Failure fields:

- `stage`
- `error`
- `logs`

If `stage` is `init`, follow `../INIT_PROTOCOL.md`: start or direct the user to the Web Console initialization page. Do not retry through chat questions or a second CLI setup path.

If the failure looks environmental, run `douyin-env-check`.

For `card` or `both`, write the draft through Obsidian MCP, then call `review-draft-ready`. After user approval and final MCP filing, call `review-finalized`.

## Reply

For desktop users, report title, author, exported path, and transcript length.

Reply in the current interaction channel. For `original`, return the transcript. For `card`, continue until the knowledge-card review draft is available. For `both`, return both. Do not expose API keys.
