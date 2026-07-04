---
name: obsidian-mcp-env-check
description: Check whether Route 1.2 is locally ready for an AI coding agent to control the Obsidian vault through MCP or REST.
---

# Obsidian MCP Environment Check

Use this project-local skill when the user asks whether Route 1.2, Obsidian MCP, agent MCP, or the vault bridge is ready.

## Hard Rules

- MCP required: this route depends on an Obsidian MCP/REST bridge for vault operations.
- No Claudian bridge: do not automate or call the Claudian chat UI in Route 1.2.
- Do not save API keys in project files.
- Do not perform final category writes while checking environment readiness.
- Do not treat an installed Obsidian plugin as proof that the current agent has an MCP connection.

## Command

Run from the project root:

```bash
python -X utf8 agent_cli.py route12-check --pretty
python -X utf8 agent_cli.py route12-mcp-templates --pretty
python -X utf8 agent_cli.py mcp-status --pretty
```

Read `../../docs/mcp-setup.md` before selecting a template. If the current agent is QoderWork CN, prefer the QoderWork-specific templates. Otherwise use the matching platform or generic template.

## Reply

Report:

- vault path
- whether required vault directories exist
- whether `_知识卡片模板.md` exists
- whether `00_Inbox/_待审核/` exists
- whether Claudian is present only as a non-used plugin
- whether an Obsidian MCP/REST bridge plugin appears to be installed
- whether the current agent has completed real MCP verification
- recommended next step

If no MCP/REST bridge is detected, tell the user to install and enable `REST and MCP server` in Obsidian or configure `Local REST API + obsidian-mcp-server`.
