---
name: douyin-curate-via-obsidian-mcp
description: After a Douyin transcript is written to Inbox, use Obsidian MCP to create a review draft and wait for approval in IM or the current agent terminal before final filing.
---

# Douyin Curation Via Obsidian MCP

Use this skill after a Douyin transcript Markdown has been exported to `00_Inbox/抖音链接/` and the user wants Route 1.2 curation.

## Hard Rules

- MCP required: read and write vault notes through Obsidian MCP/REST tools.
- No Claudian bridge: do not automate or call the Claudian chat UI in Route 1.2.
- Review before final write: write only a draft to `00_Inbox/_待审核/` until the user approves in IM or the current agent terminal.
- Keep the original transcript in Inbox.
- Do not store API keys in project files.
- If MCP is unavailable, transcription may remain in Inbox, but curation, final category writes, moves, and index updates must stop.

## Workflow

1. Confirm Route 1.2 readiness with `obsidian-mcp-env-check` and inspect `route12-mcp-templates` if MCP status is unknown.
2. Use Obsidian MCP to read the transcript Markdown.
3. Use Obsidian MCP to read `_知识卡片模板.md` and category index notes.
4. Generate a curation draft with:
   - source transcript path
   - suggested category
   - suggested target path
   - card Markdown
   - index update plan
   - open questions for the user
5. Use Obsidian MCP to write the draft to `00_Inbox/_待审核/`.
6. Call `agent_cli.py review-draft-ready` with the category, target card path, index path, and MCP draft path.
7. Present the summary, draft, and `review_id` in the current interaction channel.
8. Map natural language to:
   - confirm -> `agent_cli.py review-approve --review-id <id>`
   - revise -> `agent_cli.py review-revise --review-id <id> --instruction "<request>"`
   - cancel -> `agent_cli.py review-cancel --review-id <id>`
9. Only after `review-approve` succeeds, use Obsidian MCP to write the final card and update the index.
10. Call `agent_cli.py review-finalized` with both final paths.
11. Keep the original Inbox transcript.

## Review Reply Shape

- knowledge card draft
- classification logic
- key card points
- planned file and index operations
- original source path
- review ID and confirm/revise/cancel actions

## Failure Handling

- If MCP tools are unavailable, stop and report that Route 1.2 cannot proceed.
- If the draft cannot be written through MCP, report the failure and do not write directly to the final category folders.
- If the user changes category, title, or understanding, revise the draft first and ask for approval again.
