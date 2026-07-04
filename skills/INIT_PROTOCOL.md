# Douyin Init Protocol

All project-local skills must run this protocol before calling `transcribe`, `batch`, or `check-env`.

The generic `ingest` command uses the same initialization gate.

Real terminal users should start from the local Web Console:

```bash
python -X utf8 main.py
```

AI agents and automated workflows may keep using already-initialized `agent_cli.py` subcommands directly. First-run initialization is Web Console only. The Web Console calls the same initialization and five-layer handlers; it must not bypass this protocol. Agents must not recreate the first-run wizard as chat questions for real users.

## State Check

From the project root, check whether `config.ini` exists.

- Let `agent_cli.py` create and switch to the project `.venv`; never install local ASR dependencies into the system Python.
- If `config.ini` exists, continue with the requested command.
- If `config.ini` does not exist, do not call `transcribe`, `batch`, or `check-env` yet. Start the Web Console initialization page first with `python -X utf8 agent_cli.py init` or `python -X utf8 main.py`.
- Do not ask onboarding questions in chat. Do not offer any second CLI/chat initialization method; first-run setup is Web Console only.

## Web Console Initialization Order

The Web Console must present the first-run fields in this order. This section documents the page order; it is not permission for an agent to ask these questions in chat.

1. ASR engine:
   - `mimo`
   - `faster_whisper`

2. If the user chooses `mimo`, ask for the MiMo API Key.
   - Do not repeat the key back to the user.
   - Do not print it in the final reply.

3. If the user chooses `faster_whisper`, ask for the local model:
   - `base`
   - `small`
   - `medium`
   - Before writing config, tell the user: first local setup installs `faster-whisper` and `opencc-python-reimplemented`, then downloads the selected model through domestic mirrors. It may take a while on first run.

4. Ask for the transcript output directory.
   - Default: `Obsidian\AI外脑知识库\00_Inbox\抖音链接`

5. Ask for the export format:
   - `md`
   - `txt`
   - `both`
   - Default: `md`

6. Ask whether to keep extracted audio:
   - yes -> `--keep-audio`
   - no -> `--no-keep-audio`
   - Default: no

7. Ask whether to configure Obsidian MCP now.
   - If yes, pass `--configure-mcp`, then continue with `mcp-setup` and real MCP verification.
   - If no, pass `--skip-mcp`; content mode is forced to `original`.

8. When MCP will be configured, ask what content to return in IM or an agent terminal:
   - `original`: transcript only
   - `card`: knowledge-card review draft only
   - `both`: transcript and knowledge-card review draft
   - Default: `both`

9. Use interaction channel `auto` unless the user explicitly requests `im` or `terminal`.

## Write Config

The Web Console submits these values through the internal initialization handler. Agents must not present or run any user-facing second setup path.

When the user chooses local faster-whisper in the Web Console, initialization may prepare the local ASR environment:

- installs `faster-whisper`
- installs `opencc-python-reimplemented` for Simplified Chinese conversion
- downloads the selected faster-whisper model through `https://hf-mirror.com`

The Web Console also records whether the user chooses to keep extracted audio.

When the user skips MCP in the Web Console, the Web/API handler records the matching original-only routing.

## MCP Setup Gate

After Web Console initialization with MCP enabled:

1. Run `agent_cli.py mcp-setup --client "<current agent>" --pretty`.
2. Guide the user through the returned template without storing credentials in the project.
3. Use real MCP tools to list the vault, read `_知识卡片模板.md`, create a test note in `_待审核`, and delete it.
4. Only after those calls succeed, run `agent_cli.py mcp-verify` with all four verification flags.
5. Do not claim `mcp_ready` or `curation_ready` until verification succeeds.

## Continue Original Task

Only after the Web Console initialization returns `success: true`, continue with the original requested transcription, batch, archive, or environment check command.

If initialization fails, report the JSON error and stop. Do not run transcription with defaults.

## Safety

- Never expose API keys in replies.
- Do not create `config.ini` by hand; use the local Web Console.
- The internal Web/API setup handler is not a user-facing initialization route.
- `agent_cli.py init` is the required Web Console entry and may be started by the agent when `config.ini` is missing.
- Do not run a chat-based initialization wizard for real users; use the local Web Console instead.
