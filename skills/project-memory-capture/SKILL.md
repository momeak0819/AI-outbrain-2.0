---
name: project-memory-capture
description: Capture structured AI coding project memory into the Obsidian project map through the existing review gate.
---

# Project Memory Capture

Use this skill when the user asks to record project memory, summarize a coding phase, write to the project map, create a handoff, or preserve important vibe-coding progress.

## Hard Rules

- Do not save raw chat transcripts or low-value conversation logs.
- Do not include API keys, cookies, tokens, passwords, local secrets, or private credentials.
- Do not write directly into formal Obsidian category folders.
- Always use the review gate: draft -> user review -> approval -> MCP final filing.
- Prefer the local CLI entrypoint so every AI coding agent can use the same workflow.
- If MCP is unavailable, leave the draft in `00_Inbox/_待审核` and report the next action.

## When to Trigger

Trigger after any meaningful development milestone:

- a feature or subsystem is completed;
- an architecture decision is made;
- a difficult bug is fixed;
- a gray/release package is produced;
- technical debt or follow-up work becomes clear;
- the agent is handing off to another window or another AI agent;
- the user says “记录项目记忆”, “写入项目映射库”, “阶段总结”, “收尾”, “整理这个项目”, or similar.

## Memory Structure

Summarize only useful project knowledge:

```markdown
## 本轮目标
## 已完成成果
## 关键决策
## 修改范围
## 测试与验证
## 风险与技术债
## 后续计划
## 可关联知识点
```

## CLI Capture

For structured JSON:

```powershell
python agent_cli.py project-memory-capture --payload-file memory.json --pretty
```

For a Markdown/text summary:

```powershell
python agent_cli.py project-memory-capture --summary-file session.md --project "项目名" --title "阶段标题" --agent "codex" --pretty
```

The CLI creates a reviewable draft and returns `review_id`, `draft_path`, `target_path`, `index_path`, and the next review action.

## Search and Match

Search existing project memories:

```powershell
python agent_cli.py project-memory-search --query "ASR 云服务" --pretty
```

Match a new idea to related projects:

```powershell
python agent_cli.py project-memory-match --idea "yt-dlp Cookie 自动读取" --pretty
```

## Review Completion

After the user approves the draft, use the existing MCP/Obsidian review flow to write the final card and update `08_项目映射库/_项目映射索引.md`, then call `review-finalized`.
