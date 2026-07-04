---
name: douyin-transcribe-batch
description: Batch transcribe multiple Douyin links or copied share texts into txt/md using the project agent CLI. Use when the user asks for batch transcription, provides multiple Douyin links, a text list, or a file containing many Douyin share links.
---

# Douyin Batch Transcription

Use this project-local skill when there are multiple links or the user says "batch", "batch transcription", "multiple links", or "list".

## Hard Rules

- Markdown/TXT outputs are file exports only.
- Follow configured `im_content_mode`: `original`, `card`, or `both`.
- In `card` or `both`, continue every successful item to a review draft before completing the workflow.
- Continue every item whose `workflow_complete` is false; do not stop at successful transcription.
- Use `interaction_channel=auto` for IM or direct agent terminal calls.
- Do not send Markdown files as the main IM reply.

## Required Init Gate

Before batch transcription, follow `../INIT_PROTOCOL.md`.

If `config.ini` is missing, do not ask onboarding questions in chat and do not offer a second CLI setup path. Start the local Web Console for initialization (`python main.py` or `python agent_cli.py init`), and only then continue. Do not run batch transcription with defaults.

## Commands

Pasted text for IM/chat:

```bash
python -X utf8 agent_cli.py batch --text "<full pasted text>" --engine faster_whisper --model-size base --export md --response-mode im --pretty
```

Input file for IM/chat:

```bash
python -X utf8 agent_cli.py batch --input-file "<links.txt>" --engine faster_whisper --model-size base --export md --response-mode im --pretty
```

Use `--knowledge-dir "<dir>"` to archive Markdown files into a knowledge-base directory.

## Behavior

- URLs are extracted automatically from input text.
- Items run sequentially, not concurrently.
- A failed item does not stop the rest.
- The JSON response includes `total`, `succeeded`, `failed`, and `items[]`.
- Each successful `card/both` item requires its own `review-draft-ready`, approval, MCP filing, and `review-finalized`.
- If JSON returns `stage: "init"`, follow `../INIT_PROTOCOL.md`: start or direct the user to the Web Console initialization page. Do not retry through chat questions or a second CLI setup path.

## Reply

Summarize total/succeeded/failed. Format successful items according to `im_content_mode`. For `card` or `both`, include each `review_id` and do not finalize without approval.

Do not expose API keys.
