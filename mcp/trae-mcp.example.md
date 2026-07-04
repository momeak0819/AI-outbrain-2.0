# Trae MCP Setup Reference

Trae MCP configuration is managed by the Trae client rather than this project.

1. Open Trae MCP settings.
2. Add an Obsidian MCP server.
3. Prefer HTTP/Streamable HTTP when the Obsidian `REST and MCP server` plugin exposes an endpoint.
4. Otherwise add a STDIO server with:

```text
command: npx
args: -y obsidian-mcp-server
env:
  OBSIDIAN_API_URL=${OBSIDIAN_API_URL}
  OBSIDIAN_API_KEY=${OBSIDIAN_API_KEY}
```

Store the actual values in Trae's secure configuration. Do not write them into this project.
