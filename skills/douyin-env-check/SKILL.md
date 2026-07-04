---
name: douyin-env-check
description: Check and explain the local douyin-to-text environment. Use when the user asks whether Douyin transcription is ready, why transcription cannot run, whether ffmpeg/faster-whisper/models are installed, or how to diagnose local ASR setup problems.
---

# Douyin Environment Check

Use this project-local skill to inspect whether `douyin-to-text` can run.

## Required Init Gate

Before running environment checks, follow `../INIT_PROTOCOL.md`.

If `config.ini` is missing, do not ask onboarding questions in chat and do not offer a second CLI setup path. Start the local Web Console for initialization (`python main.py` or `python agent_cli.py init`), and only then continue.

## Commands

Run from the project root:

```bash
python -X utf8 agent_cli.py check-env --pretty
```

Check a specific local model:

```bash
python -X utf8 agent_cli.py check-env --model-size small --pretty
```

Model status only:

```bash
python -X utf8 agent_cli.py models --pretty
```

## Interpret JSON

- `ffmpeg.available` must be true for video audio extraction.
- `ffprobe.available` should be true for MiMo oversized-audio chunking.
- `faster_whisper.available` and `models.<model>.ready` are required for local ASR.
- MiMo mode requires ffmpeg and a valid `MIMO_API_KEY`; it does not require local Whisper models.
- If JSON returns `stage: "init"`, follow `../INIT_PROTOCOL.md`: start or direct the user to the Web Console initialization page. Do not retry through chat questions or a second CLI setup path.

If the user wants to reset local preferences, ask before deleting `config.ini`. Prefer backing it up instead of deleting it directly.

Do not expose API keys.
