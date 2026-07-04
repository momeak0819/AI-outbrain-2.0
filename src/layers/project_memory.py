"""Project memory capture, search, and matching helpers.

This module keeps project-memory work in the knowledge layer: it creates
reviewable drafts and read-only search/match results, but never writes final
cards into formal Obsidian category folders.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent import reviews as review_service


PROJECT_MEMORY_TYPE = "project_memory"
PROJECT_MEMORY_CATEGORY = "08_项目映射库"
PROJECT_MEMORY_INDEX_PATH = "08_项目映射库/_项目映射索引.md"
PROJECT_MEMORY_TEMPLATE_PATH = "08_项目映射库/_项目记忆模板.md"
PROJECT_MEMORY_SKILL_PATH = "skills/project-memory-capture/SKILL.md"
PROJECT_MEMORY_REQUIRED_FIELDS = ("project", "title", "summary")
PROJECT_MEMORY_LIST_FIELDS = (
    "completed",
    "decisions",
    "changed_areas",
    "files_touched",
    "tests",
    "risks",
    "technical_debt",
    "next_steps",
    "related_topics",
    "linked_projects",
)
SESSION_TYPES = {"development", "bugfix", "release", "architecture", "research", "handoff"}


@dataclass(frozen=True)
class ProjectMemoryContext:
    project_root: Path
    vault_root: Path
    review_dir: Path
    review_draft_dir: Path
    agent: str = "unknown"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_payload_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("project memory payload must be a JSON object")
    return payload


def payload_from_summary_file(
    path: Path,
    *,
    project: str,
    title: str,
    agent: str = "",
    session_type: str = "development",
) -> dict[str, Any]:
    return {
        "type": PROJECT_MEMORY_TYPE,
        "project": project,
        "title": title,
        "summary": path.read_text(encoding="utf-8").strip(),
        "agent": agent,
        "session_type": session_type,
    }


def enrich_project_memory_payload(
    payload: dict[str, Any],
    context: ProjectMemoryContext,
) -> dict[str, Any]:
    enriched = dict(payload)
    enriched["type"] = PROJECT_MEMORY_TYPE
    enriched.setdefault("repo_path", str(context.project_root))
    enriched.setdefault("project_root", str(context.project_root))
    enriched.setdefault("agent", context.agent)
    enriched.setdefault("source_agent", context.agent)
    enriched.setdefault("session_type", "development")
    enriched.setdefault("created_at", utc_timestamp())
    for field in PROJECT_MEMORY_LIST_FIELDS:
        enriched[field] = _as_list(enriched.get(field))
    if "git_branch" not in enriched or "git_commit" not in enriched:
        branch, commit = _git_identity(context.project_root)
        enriched.setdefault("git_branch", branch)
        enriched.setdefault("git_commit", commit)
    return enriched


def validate_project_memory_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    for field in PROJECT_MEMORY_REQUIRED_FIELDS:
        if not str(payload.get(field) or "").strip():
            return _failure(
                "project_memory_payload_invalid",
                f"项目记忆缺少必填字段：{field}",
                recoverable=True,
            )
    session_type = str(payload.get("session_type") or "development")
    if session_type not in SESSION_TYPES:
        return _failure(
            "project_memory_payload_invalid",
            f"session_type 必须是：{', '.join(sorted(SESSION_TYPES))}",
            recoverable=True,
        )
    return None


def create_project_memory_draft(
    payload: dict[str, Any],
    context: ProjectMemoryContext,
) -> dict[str, Any]:
    enriched = enrich_project_memory_payload(payload, context)
    failure = validate_project_memory_payload(enriched)
    if failure:
        return failure

    try:
        context.review_draft_dir.mkdir(parents=True, exist_ok=True)
        draft_path = _unique_path(
            context.review_draft_dir / f"项目记忆-{_date_prefix(enriched)}-{_slug(enriched['title'])}.md"
        )
        draft_path.write_text(render_project_memory_markdown(enriched), encoding="utf-8")
    except Exception as exc:
        return _failure(
            "project_memory_draft_failed",
            f"项目记忆草稿生成失败：{exc}",
            recoverable=True,
        )

    target_path = _target_path(enriched)
    review_payload = {
        **enriched,
        "title": enriched["title"],
        "author": enriched.get("agent", ""),
        "md_path": str(draft_path),
        "target_path": target_path,
        "index_path": PROJECT_MEMORY_INDEX_PATH,
        "suggested_category": PROJECT_MEMORY_CATEGORY,
        "workflow": "project_memory_capture",
    }
    try:
        record = review_service.create_review_record(
            context.review_dir,
            context.review_draft_dir,
            review_payload,
            "card",
            "terminal",
        )
        ready = review_service.handle_review_draft_ready(
            context.review_dir,
            record["review_id"],
            PROJECT_MEMORY_CATEGORY,
            target_path,
            PROJECT_MEMORY_INDEX_PATH,
            str(draft_path),
        )
    except Exception as exc:
        return _failure(
            "project_memory_review_failed",
            f"项目记忆审核记录创建失败：{exc}",
            recoverable=True,
        )
    if not ready.get("success"):
        return {
            **ready,
            "mode": "project-memory-capture",
            "workflow": "project_memory_capture",
        }
    review = ready.get("review") or record
    return {
        "success": True,
        "mode": "project-memory-capture",
        "stage": "knowledge",
        "workflow": "project_memory_capture",
        "workflow_status": ready.get("workflow_status", "awaiting_approval"),
        "workflow_complete": False,
        "requires_review": True,
        "requires_user_approval": True,
        "next_action": "review-approve / review-revise / review-cancel",
        "next_skill": "project-memory-capture",
        "project": enriched["project"],
        "title": enriched["title"],
        "review_id": review.get("review_id"),
        "review_status": review.get("status"),
        "review_path": review.get("review_path"),
        "draft_path": str(draft_path),
        "suggested_category": PROJECT_MEMORY_CATEGORY,
        "target_path": target_path,
        "index_path": PROJECT_MEMORY_INDEX_PATH,
        "memory": _public_payload(enriched),
    }


def render_project_memory_markdown(payload: dict[str, Any]) -> str:
    tags = ["project-memory", "vibe-coding", *_as_list(payload.get("related_topics"))]
    frontmatter = {
        "type": PROJECT_MEMORY_TYPE,
        "project": payload.get("project", ""),
        "repo_path": payload.get("repo_path", ""),
        "agent": payload.get("agent", ""),
        "source_agent": payload.get("source_agent", ""),
        "session_type": payload.get("session_type", "development"),
        "created_at": payload.get("created_at", ""),
        "status": "draft",
        "git_branch": payload.get("git_branch", ""),
        "git_commit": payload.get("git_commit", ""),
        "tags": tags,
    }
    sections = [
        _frontmatter(frontmatter),
        f"# 项目记忆：{payload.get('title', '')}",
        "",
        "## 项目定位",
        str(payload.get("project", "")).strip() or "N/A",
        "",
        "## 本轮目标",
        str(payload.get("summary", "")).strip(),
        "",
        _list_section("## 已完成成果", payload.get("completed")),
        _list_section("## 关键决策", payload.get("decisions")),
        _list_section("## 修改范围", payload.get("changed_areas")),
        _list_section("## 重要文件", payload.get("files_touched")),
        _list_section("## 测试与验证", payload.get("tests")),
        _list_section("## 风险与技术债", [*_as_list(payload.get("risks")), *_as_list(payload.get("technical_debt"))]),
        _list_section("## 后续计划", payload.get("next_steps")),
        _list_section("## 可关联知识点", payload.get("related_topics")),
        _list_section("## 反向匹配提示", payload.get("linked_projects")),
        "",
    ]
    return "\n".join(item for item in sections if item is not None)


def search_project_memory(
    query: str,
    context: ProjectMemoryContext,
    *,
    project: str = "",
    tag: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    try:
        docs = list(_iter_memory_docs(context))
        results = [
            _score_doc(doc, query=query, project=project, tag=tag)
            for doc in docs
        ]
        results = [item for item in results if item["score"] > 0 or not query.strip()]
        results.sort(key=lambda item: item["score"], reverse=True)
        return {
            "success": True,
            "mode": "project-memory-search",
            "stage": "knowledge",
            "query": query,
            "total": len(results[:limit]),
            "results": results[:limit],
        }
    except Exception as exc:
        return _failure("project_memory_search_failed", f"项目记忆搜索失败：{exc}", recoverable=True)


def match_idea_to_projects(
    idea: str,
    context: ProjectMemoryContext,
    *,
    limit: int = 5,
) -> dict[str, Any]:
    if not idea.strip():
        return _failure("project_memory_payload_invalid", "待匹配的新知识或想法不能为空。", recoverable=True)
    search = search_project_memory(idea, context, limit=max(limit * 3, 10))
    if not search.get("success"):
        return search
    candidates = []
    for item in search.get("results", []):
        candidates.append(
            {
                "project": item.get("project", ""),
                "title": item.get("title", ""),
                "path": item.get("path", ""),
                "score": item.get("score", 0),
                "matched_topics": item.get("matched_topics", []),
                "reason": _match_reason(item),
                "suggested_action": "把这个知识点补充到该项目的后续计划或技术债评估中。",
            }
        )
    if not candidates:
        return {
            "success": True,
            "mode": "project-memory-match",
            "stage": "knowledge",
            "idea": idea,
            "candidates": [],
            "error_code": "project_memory_no_match",
            "error": "没有找到明显相关的项目记忆。",
            "recoverable": True,
        }
    return {
        "success": True,
        "mode": "project-memory-match",
        "stage": "knowledge",
        "idea": idea,
        "candidates": candidates[:limit],
    }


def project_memory_status(context: ProjectMemoryContext) -> dict[str, Any]:
    """Return non-mutating readiness for Skill + CLI based project memory capture."""
    skill_path = context.project_root / PROJECT_MEMORY_SKILL_PATH
    template_path = context.vault_root / PROJECT_MEMORY_TEMPLATE_PATH
    formal_dir = context.vault_root / PROJECT_MEMORY_CATEGORY
    index_path = context.vault_root / PROJECT_MEMORY_INDEX_PATH
    checks = {
        "skill_available": skill_path.exists(),
        "cli_capture_available": True,
        "cli_search_available": True,
        "cli_match_available": True,
        "draft_area_exists": context.review_draft_dir.exists(),
        "review_dir_parent_exists": context.review_dir.parent.exists() or context.review_dir.exists(),
        "formal_project_map_exists": formal_dir.exists(),
        "project_memory_template_exists": template_path.exists(),
        "project_memory_index_exists": index_path.exists(),
    }
    ready = all(checks.values())
    missing = [name for name, ok in checks.items() if not ok]
    return {
        "success": True,
        "mode": "project-memory-status",
        "stage": "knowledge",
        "agent": context.agent,
        "automation_mode": "external_agent_scheduler",
        "automation_ready": ready,
        "checks": checks,
        "missing_checks": missing,
        "skill_path": str(skill_path),
        "draft_dir": str(context.review_draft_dir),
        "formal_category": PROJECT_MEMORY_CATEGORY,
        "index_path": PROJECT_MEMORY_INDEX_PATH,
        "capture_command": (
            'python agent_cli.py project-memory-capture '
            '--payload-file memory.json --pretty'
        ),
        "search_command": 'python agent_cli.py project-memory-search --query "关键词" --pretty',
        "match_command": 'python agent_cli.py project-memory-match --idea "新知识点" --pretty',
        "recommended_scheduler": (
            "由工作 AI Agent 自己的自动化/定时任务定期生成 memory.json，"
            "再调用 project-memory-capture；本项目不保存原始聊天流水账。"
        ),
        "workflow_complete": ready,
        "next_action": "configure_external_agent_scheduler" if ready else "restore_project_memory_prerequisites",
    }


def _iter_memory_docs(context: ProjectMemoryContext):
    roots = [
        context.vault_root / PROJECT_MEMORY_CATEGORY,
        context.vault_root / "00_Inbox" / "_待审核",
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            if path.name.startswith("_"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            metadata = _parse_frontmatter(text)
            if metadata.get("type") != PROJECT_MEMORY_TYPE and "项目记忆" not in text[:300]:
                continue
            yield {
                "path": str(path),
                "vault_relative_path": _vault_relative(path, context.vault_root),
                "title": _title(text) or str(metadata.get("title") or path.stem),
                "project": str(metadata.get("project") or ""),
                "tags": _as_list(metadata.get("tags")),
                "text": text,
            }


def _score_doc(doc: dict[str, Any], *, query: str, project: str, tag: str) -> dict[str, Any]:
    if project and project.casefold() not in str(doc.get("project", "")).casefold():
        return {**_result_doc(doc), "score": 0, "matched_topics": []}
    tags = [str(item).casefold() for item in _as_list(doc.get("tags"))]
    if tag and tag.casefold() not in tags:
        return {**_result_doc(doc), "score": 0, "matched_topics": []}
    tokens = _tokens(query)
    haystack = " ".join(
        [
            str(doc.get("title", "")),
            str(doc.get("project", "")),
            " ".join(_as_list(doc.get("tags"))),
            str(doc.get("text", "")),
        ]
    ).casefold()
    matched = [token for token in tokens if token.casefold() in haystack]
    score = len(set(matched))
    if query.strip() and query.casefold() in haystack:
        score += 3
    if project:
        score += 2
    if tag:
        score += 1
    snippet = _snippet(str(doc.get("text", "")), query)
    return {**_result_doc(doc), "score": float(score), "matched_topics": sorted(set(matched)), "snippet": snippet}


def _result_doc(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "project": doc.get("project", ""),
        "title": doc.get("title", ""),
        "path": doc.get("path", ""),
        "vault_relative_path": doc.get("vault_relative_path", ""),
        "tags": _as_list(doc.get("tags")),
    }


def _tokens(value: str) -> list[str]:
    return [
        item
        for item in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_+-]{2,}", value.casefold())
        if item.strip()
    ]


def _snippet(text: str, query: str, width: int = 120) -> str:
    for token in _tokens(query):
        index = text.casefold().find(token.casefold())
        if index >= 0:
            start = max(0, index - width // 2)
            end = min(len(text), index + width // 2)
            return text[start:end].replace("\n", " ").strip()
    return text[:width].replace("\n", " ").strip()


def _parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    metadata: dict[str, Any] = {}
    current_key = ""
    for line in text[4:end].splitlines():
        if line.startswith("  - ") and current_key:
            metadata.setdefault(current_key, []).append(line[4:].strip())
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        current_key = key.strip()
        value = value.strip()
        metadata[current_key] = [] if value == "" and current_key == "tags" else value
    return metadata


def _frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def _list_section(title: str, values: Any) -> str:
    items = _as_list(values)
    if not items:
        return f"{title}\n\n- N/A\n"
    return f"{title}\n\n" + "\n".join(f"- {item}" for item in items) + "\n"


def _as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _title(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value.strip(), flags=re.UNICODE)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-_")
    return cleaned[:60] or "project-memory"


def _date_prefix(payload: dict[str, Any]) -> str:
    created = str(payload.get("created_at") or "")
    return re.sub(r"[^0-9]", "", created[:10]) or datetime.now().strftime("%Y%m%d")


def _target_path(payload: dict[str, Any]) -> str:
    project = _slug(str(payload.get("project") or "unknown-project"))
    title = _slug(str(payload.get("title") or "project-memory"))
    return f"{PROJECT_MEMORY_CATEGORY}/项目卡片/{project}/{_date_prefix(payload)}-{title}.md"


def _unique_path(path: Path) -> Path:
    candidate = path
    index = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        index += 1
    return candidate


def _vault_relative(path: Path, vault_root: Path) -> str:
    try:
        return path.resolve().relative_to(vault_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _git_identity(project_root: Path) -> tuple[str, str]:
    def run(args: list[str]) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            return ""
        return result.stdout.strip() if result.returncode == 0 else ""

    return run(["branch", "--show-current"]), run(["rev-parse", "--short", "HEAD"])


def _public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if "key" not in key.lower()
        and "token" not in key.lower()
        and "secret" not in key.lower()
        and "cookie" not in key.lower()
    }


def _match_reason(item: dict[str, Any]) -> str:
    topics = item.get("matched_topics") or []
    if topics:
        return "命中关键词：" + "、".join(str(topic) for topic in topics[:6])
    return "该项目记忆与输入想法存在文本相似度。"


def _failure(error_code: str, error: str, *, recoverable: bool) -> dict[str, Any]:
    return {
        "success": False,
        "stage": "knowledge",
        "mode": "project-memory",
        "error_code": error_code,
        "error": error,
        "recoverable": recoverable,
    }
