# Project Agent Rules

These rules are hard constraints for agent workflows in this project.

## Subwindow Handoff Protocol

- A layer subwindow must report every delegated task back to the architecture-control thread; finishing only inside the layer thread does not count as delivery.
- The report must identify the task, changed files, interface changes, compatibility strategy, test commands and results, risks, Route 1.2 impact, and the exact output expected by the next layer.
- A blocked or failed task must also be reported immediately with the blocking condition and completed checks.
- The architecture-control thread must accept the report before the next layer starts.


## Route 1.2 Purpose

This copy is the Route 1.2 experiment: an AI coding agent controls the Obsidian vault through Obsidian MCP/REST.

- Use any MCP-capable AI coding agent as the WeChat/IM entry and workflow coordinator.
- Use Obsidian MCP/REST to read, search, write, move, and update notes in `Obsidian/AI外脑知识库`.
- Do not call, automate, or bridge into the Claudian chat UI in this route.
- If Obsidian MCP/REST is not configured or unavailable, transcription may continue to Inbox, but curation and final filing must stop.
- Do not silently fall back to direct file writes in formal category folders or index notes.
- Draft curation may be written to `Obsidian/AI外脑知识库/00_Inbox/_待审核/`.
- Final category writes and index updates require explicit WeChat/IM approval first.

## Project Load Protocol

Every AI coding agent loading this project must:

1. Real terminal users should load the project through the local Web Console: `python main.py` or `python agent_cli.py console`. When an AI agent detects a missing `config.ini` in an interactive local session, it should start the Web Console itself instead of asking setup questions in chat. Automated tests may continue to call CLI subcommands directly.
2. Allow the entry point to create and switch to the project `.venv`.
3. Read `initialization_manifest.json`, `skills/INIT_PROTOCOL.md`, and `docs/mcp-setup.md`.
4. Run `python agent_cli.py route12-check --pretty`.
5. Run `python agent_cli.py route12-mcp-templates --pretty`.
6. If `config.ini` does not exist, do not ask first-run questions in chat and do not offer a second chat/CLI initialization path. Run `python -X utf8 agent_cli.py init` or `python -X utf8 main.py` to start the Web Console initialization page.
7. During first initialization, MCP configuration is collected in the Web Console. The internal Web/API setup handler must not be presented to users or agents as an alternate onboarding workflow.
8. If MCP is configured, run `mcp-setup`, guide the user through the matching client template, perform the real MCP checks, then record them with `mcp-verify`.
9. If MCP is skipped, run `mcp-setup --skip`; this forces `im_content_mode=original`.

QoderWork CN is the recommended default agent and should prefer the QoderWork-specific templates. Other agents must use their platform template or a generic template.

The project provides rules and templates but cannot guarantee that every agent auto-registers MCP configuration. Keep real credentials in the agent's secure MCP configuration or local environment variables.

An installed Obsidian REST/MCP plugin is not proof that the current agent is connected. Do not report Route 1.2 as ready until the agent has listed the vault, read `_知识卡片模板.md`, and created then deleted a test note through MCP.

## Portability and Release Rules

- Preserve every project skill, MCP template, CLI command, ASR engine, test, and Vault category.
- Every confirmed workflow, source adapter, ASR engine, skill, or MCP tool must be registered in `initialization_manifest.json`; inventory tests must fail when registration is missing.
- User runtime data stays inside the project for whole-folder portability.
- A broken `.venv` may be rebuilt, but models, config, reviews, outputs, and Vault content must remain untouched.
- Build clean initialization packages with `python tools/build_source_release.py`; the builder must not mutate the working project.
- Claudian may remain in a working Vault, but it is excluded from Route 1.2 source releases and must never be called by this route.

## Channel-Neutral Review Protocol

- Read `[preferences] im_content_mode` before replying: `original`, `card`, or `both`.
- Read `[preferences] interaction_channel`; `auto` means use IM when the request came from IM, otherwise use the current agent/terminal conversation.
- IM and terminal conversations must use the same review gate.
- In `card` or `both` mode, transcription is not the end of the workflow. Follow `next_skill` and create the Obsidian MCP review draft.
- If JSON contains `workflow_complete=false`, keep executing `next_action`/`next_skill`; do not announce completion.
- Never skip `_待审核 -> user review -> review-approve -> final MCP filing`.
- After writing or revising the MCP draft, call `review-draft-ready`.
- After approved MCP filing and index update, call `review-finalized`.
- Natural-language confirmation, revision, or cancellation must map to `review-approve`, `review-revise`, or `review-cancel`.
- Do not delete the original transcript after final filing.

## Five-Layer Response Protocol

- Treat the system as `source -> acquisition -> processing -> knowledge -> delivery`.
- Prefer the nested `source`, `acquisition`, `processing`, `knowledge`, `delivery`, and `next` objects when interpreting command results.
- Preserve legacy flat JSON fields for existing integrations.
- Report the exact failed layer and its error instead of describing every failure as transcription failure.
- Current implemented source adapters include `douyin`, `local_audio`, and video URL sources backed by yt-dlp: `youtube`, `bilibili`, `generic_video`, `x_video`, `vimeo`, `twitch`, `tiktok`, `instagram`, and `xiaohongshu`.
- For generic source-neutral ingestion, use `agent_cli.py ingest`.

## Douyin Transcription Replies

- Markdown and TXT exports are file outputs only.
- `original`: return the transcript in the current interaction channel.
- `card`: return the knowledge-card review draft, classification logic, target path, planned operations, source path, and review commands.
- `both`: return both the transcript and the knowledge-card review draft.
- If MCP is unavailable in `card` or `both`, report the failure and return the original transcript as fallback.
- Do not send the Markdown file as the main reply.
