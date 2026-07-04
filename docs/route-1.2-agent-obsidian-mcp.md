# Route 1.2: AI Coding Agent Directly Controls Obsidian MCP

This route tests whether an MCP-capable AI coding agent can control the Obsidian vault directly, without automating the Claudian plugin.

## Goal

WeChat, another IM channel, or a command-line AI agent receives a Douyin link. The agent transcribes it into Inbox, then uses Obsidian MCP/REST to read the transcript, generate a curation draft, write the draft to the review area, wait for approval in the originating channel, and finally write the card and index updates into the formal knowledge library.

This route can be used by QoderWork CN, Claude Code, Codex, Trae, or any other AI coding agent that can call MCP tools.

## Recommended Obsidian Bridge

Preferred option:

- Install the Obsidian community plugin `REST and MCP server`.
- Enable its local server in Obsidian.
- Configure the AI coding agent to connect to the local MCP endpoint using Streamable HTTP or SSE.

Fallback option:

- Install the Obsidian `Local REST API` plugin.
- Run an external MCP server such as `obsidian-mcp-server`.
- Configure the AI coding agent as a STDIO MCP client for that server.

## Agent MCP Setup

In the AI coding agent or MCP client, add an MCP server for the Obsidian bridge:

- Use Streamable HTTP/SSE if the Obsidian plugin exposes a local MCP endpoint.
- Use STDIO if the bridge is an external process such as an npm MCP server.
- Keep API keys in the agent or MCP client's secure configuration. Do not write them into project files.

## End-to-End Workflow

1. WeChat, another IM channel, or a command-line AI agent receives a Douyin link.
2. The agent runs the existing transcription workflow and writes Markdown to `Obsidian/AI外脑知识库/00_Inbox/抖音链接/`.
3. The agent calls Obsidian MCP to read the transcript, `_知识卡片模板.md`, and category indexes.
4. The agent asks the model to generate a curation draft and writes it to `Obsidian/AI外脑知识库/00_Inbox/_待审核/`.
5. The agent calls `review-draft-ready`.
6. The agent replies in the originating channel with summary, suggested category, target path, and draft content.
7. After explicit approval, the agent uses Obsidian MCP to write the final card and update the relevant index.
8. The agent calls `review-finalized`.
9. The agent reports the final paths and index changes in the originating channel.

## Verification Checklist

- `python agent_cli.py route12-check --pretty` reports the vault structure.
- Obsidian is open and the MCP/REST bridge plugin is enabled.
- The AI coding agent can list vault files through MCP.
- The AI coding agent can read `_知识卡片模板.md`.
- The AI coding agent can create and delete a test note in `00_Inbox/_待审核/`.
- `mcp-status` reports that the current agent connection was verified.
- The final write step is only performed after approval in the originating channel.

## Troubleshooting

- If the AI coding agent cannot connect, verify Obsidian is running and the bridge plugin is enabled.
- If file reads work but writes fail, check plugin permissions and vault path mapping.
- If the bridge requires an API key, store it in the agent or MCP client settings, not in this project.
- If MCP tools are unavailable, stop and report the missing bridge instead of writing final category files directly.
- Do not use Claudian automation in this route; Route 1.21 is reserved for testing Claudian bridge behavior.
