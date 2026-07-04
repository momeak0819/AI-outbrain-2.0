# Obsidian MCP Setup

## Project Contract

This project bundles the Obsidian vault, agent rules, skills, setup documentation, and MCP templates. It does not bundle the Obsidian desktop application.

Every AI coding agent loading this project must:

1. Read this document.
2. Run `python agent_cli.py route12-check --pretty`.
3. Run `python agent_cli.py route12-mcp-templates --pretty`.
4. Configure a matching MCP bridge before curation or final filing.

MCP configuration is part of first-run initialization. Ask whether the user wants to configure it now. Choosing not to configure MCP forces transcript-only (`original`) mode.

Transcription may continue without MCP and may write to `00_Inbox/抖音链接/`. Formal classification, file moves, and index updates must stop until MCP is available and the user has approved the draft.

The review channel is independent from MCP. With `interaction_channel = auto`, an IM-originated task is reviewed in IM; a direct coding-agent invocation is reviewed in that agent's current command/chat window.

Content routing is controlled by `im_content_mode`:

- `original`: transcript only
- `card`: knowledge-card review draft
- `both`: transcript and review draft

For `card` or `both`, the agent must continue after transcription, create the review draft through MCP, and use the persisted `review_id` commands before final filing.

An installed Obsidian plugin is only a prerequisite. `mcp_ready` becomes true only after the current agent has listed the vault, read `_知识卡片模板.md`, created a temporary review note, deleted it through MCP, and recorded those checks with `mcp-verify`.

## Recommended Bridge

Preferred:

- Install Obsidian on the user's machine.
- Open `Obsidian/AI外脑知识库` as the vault.
- Install and enable the Obsidian community plugin `REST and MCP server`.
- Connect the agent with HTTP, SSE, or Streamable HTTP using the endpoint shown by the plugin.

Fallback:

- Install and enable the Obsidian `Local REST API` plugin.
- Run `obsidian-mcp-server` as an external STDIO MCP server.
- Pass the Local REST API URL and key through the agent's secure MCP configuration.

## QoderWork CN Recommended Setup

QoderWork CN is the recommended default agent for this project.

- Prefer `../mcp/qoderwork-cn-http-obsidian.example.json` when Obsidian exposes an MCP endpoint.
- Use `../mcp/qoderwork-cn-stdio-obsidian.example.json` with `Local REST API + obsidian-mcp-server` as the fallback.
- Add the selected server in QoderWork CN's MCP settings.
- Replace placeholders only inside QoderWork CN's secure configuration.
- After connecting, ask the agent to list vault files and read `_知识卡片模板.md`.

## Other Agents

- Claude Code: use `../mcp/claude-code.mcp.example.json` as a project `.mcp.json` reference.
- VS Code/Copilot: use `../mcp/vscode.mcp.example.json` as a `.vscode/mcp.json` reference.
- Trae: follow `../mcp/trae-mcp.example.md`.
- Other clients: use the generic HTTP or STDIO templates.

Each agent controls where MCP configuration is stored. Project rules and templates cannot guarantee automatic registration.

## Security

- Never save real API keys, tokens, secrets, or private endpoints in this repository.
- Keep credentials in the agent's secure MCP settings or local environment variables.
- Do not expose credentials in IM replies or command logs.

## Verification

After setup:

1. Run `python agent_cli.py route12-check --pretty`.
2. Confirm the agent can call the configured Obsidian MCP tools.
3. List the vault root.
4. Read `_知识卡片模板.md`.
5. Create and delete a temporary note under `00_Inbox/_待审核/`.
6. Do not write a formal knowledge card until the user approves the review draft.
