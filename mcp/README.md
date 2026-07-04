# MCP Configuration Templates

These files are examples for connecting an AI coding agent to the Obsidian vault bridge.

## Rules

- QoderWork CN is the recommended default agent for this project.
- Other MCP-capable agents remain supported.
- These files are templates, not active configuration.
- Replace `${...}` placeholders in the agent's secure MCP settings.
- Never commit real API keys, tokens, secrets, or private server URLs.
- Loading a project does not guarantee that an agent will auto-register MCP servers.
- Obsidian must be installed on the user's machine. The desktop application is not bundled in this project.

## Templates

- `qoderwork-cn-http-obsidian.example.json`: recommended QoderWork CN HTTP/Streamable HTTP setup.
- `qoderwork-cn-stdio-obsidian.example.json`: QoderWork CN STDIO fallback.
- `claude-code.mcp.example.json`: Claude Code project-level `.mcp.json` reference.
- `vscode.mcp.example.json`: VS Code/Copilot-style MCP reference.
- `trae-mcp.example.md`: Trae manual setup guidance.
- `generic-http-obsidian-mcp.example.json`: generic HTTP MCP client reference.
- `generic-stdio-obsidian-mcp.example.json`: generic STDIO MCP client reference.

Read `../docs/mcp-setup.md` before configuring a client.
