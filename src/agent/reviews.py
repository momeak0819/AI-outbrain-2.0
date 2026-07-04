"""Persisted review state machine used by IM and terminal agent workflows."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any


REVIEW_SCHEMA_VERSION = 1


class ReviewConflictError(RuntimeError):
    """Raised when an optimistic revision check detects a concurrent update."""


@dataclass(frozen=True)
class ReviewLoadResult:
    status: str
    record: dict[str, Any] | None = None
    error: str = ""


def knowledge_failure(
    error_code: str,
    error: str,
    *,
    recoverable: bool,
) -> dict[str, Any]:
    return {
        "success": False,
        "stage": "knowledge",
        "error_code": error_code,
        "error": error,
        "recoverable": recoverable,
    }


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def review_record_path(review_dir: Path, review_id: str) -> Path:
    return review_dir / f"{review_id}.json"


def _upgrade_record(record: dict[str, Any]) -> dict[str, Any]:
    upgraded = dict(record)
    upgraded.setdefault("schema_version", REVIEW_SCHEMA_VERSION)
    revision = upgraded.get("revision", 0)
    upgraded["revision"] = revision if isinstance(revision, int) and revision >= 0 else 0
    events = upgraded.get("events", [])
    upgraded["events"] = list(events) if isinstance(events, list) else []
    upgraded.setdefault("revision_instructions", [])
    upgraded.setdefault("finalization_authorized", False)
    return upgraded


def load_review(review_dir: Path, review_id: str) -> ReviewLoadResult:
    path = review_record_path(review_dir, review_id)
    if not path.exists():
        return ReviewLoadResult(status="not_found")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ReviewLoadResult(status="corrupted", error=str(exc))
    if not isinstance(payload, dict):
        return ReviewLoadResult(
            status="corrupted",
            error="review record must be a JSON object",
        )
    return ReviewLoadResult(status="found", record=_upgrade_record(payload))


def load_review_record(review_dir: Path, review_id: str) -> dict[str, Any] | None:
    """Compatibility wrapper; callers needing corruption detail should use load_review."""
    loaded = load_review(review_dir, review_id)
    return loaded.record if loaded.status == "found" else None


def _disk_revision(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    revision = payload.get("revision", 0)
    return revision if isinstance(revision, int) and revision >= 0 else 0


def save_review_record(
    review_dir: Path,
    record: dict[str, Any],
    *,
    expected_revision: int | None = None,
) -> None:
    """Atomically persist a review record with optional optimistic concurrency."""
    review_dir.mkdir(parents=True, exist_ok=True)
    path = review_record_path(review_dir, record["review_id"])
    if expected_revision is not None:
        actual_revision = _disk_revision(path)
        if actual_revision != expected_revision:
            raise ReviewConflictError(
                f"review revision conflict: expected {expected_revision}, "
                f"found {actual_revision}"
            )

    payload = _upgrade_record(record)
    temp_path: Path | None = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=review_dir,
        )
        temp_path = Path(temp_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _load_for_handler(review_dir: Path, review_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    loaded = load_review(review_dir, review_id)
    if loaded.status == "found":
        return loaded.record, None
    if loaded.status == "corrupted":
        return None, knowledge_failure(
            "review_record_corrupted",
            f"审核记录损坏，无法读取：{review_id}",
            recoverable=False,
        )
    return None, knowledge_failure(
        "review_not_found",
        f"未找到审核记录：{review_id}",
        recoverable=False,
    )


def _event(event_type: str, status: str, **details: Any) -> dict[str, Any]:
    item = {"type": event_type, "status": status, "created_at": utc_timestamp()}
    item.update({key: value for key, value in details.items() if value not in (None, "")})
    return item


def _transition(
    review_dir: Path,
    record: dict[str, Any],
    *,
    expected_statuses: set[str],
    target_status: str,
    event_type: str,
    updates: dict[str, Any] | None = None,
    event_details: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if record.get("status") not in expected_statuses:
        return None, knowledge_failure(
            "invalid_review_transition",
            f"当前审核状态不允许此操作（status={record.get('status')}）。",
            recoverable=True,
        )
    previous_revision = int(record.get("revision", 0))
    changed = dict(record)
    now = utc_timestamp()
    changed["schema_version"] = REVIEW_SCHEMA_VERSION
    changed["status"] = target_status
    changed["updated_at"] = now
    changed["revision"] = previous_revision + 1
    if updates:
        changed.update(updates)
    details = dict(event_details or {})
    details.setdefault("revision", changed["revision"])
    changed.setdefault("events", []).append(
        _event(event_type, target_status, **details)
    )
    try:
        save_review_record(
            review_dir,
            changed,
            expected_revision=previous_revision,
        )
    except ReviewConflictError:
        return None, knowledge_failure(
            "review_conflict",
            "审核记录已被其他操作更新，请刷新状态后重试。",
            recoverable=True,
        )
    return changed, None


def _success(
    mode: str,
    record: dict[str, Any],
    *,
    idempotent: bool = False,
    **fields: Any,
) -> dict[str, Any]:
    payload = {"success": True, "mode": mode, "review": record}
    if idempotent:
        payload["idempotent"] = True
    payload.update(fields)
    return payload


def create_review_record(
    review_dir: Path,
    review_draft_dir: Path,
    payload: dict[str, Any],
    content_mode: str,
    interaction_channel: str,
) -> dict[str, Any]:
    review_id = uuid.uuid4().hex[:12]
    source_path = payload.get("md_path") or payload.get("txt_path") or ""
    source_name = Path(source_path).stem if source_path else (payload.get("title") or review_id)
    draft_path = review_draft_dir / f"{source_name}.md"
    now = utc_timestamp()
    record = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "revision": 0,
        "events": [_event("created", "pending_draft", revision=0)],
        "review_id": review_id,
        "review_path": str(review_record_path(review_dir, review_id)),
        "status": "pending_draft",
        "created_at": now,
        "updated_at": now,
        "title": payload.get("title") or "",
        "author": payload.get("author") or "",
        "source_path": source_path,
        "source_retention": "keep",
        "draft_path": str(draft_path),
        "content_mode": content_mode,
        "interaction_channel": interaction_channel,
        "next_skill": "douyin-curate-via-obsidian-mcp",
        "next_action": "create_review_draft_via_obsidian_mcp",
        "revision_instructions": [],
        "finalization_authorized": False,
        "suggested_category": "",
        "target_path": "",
        "index_path": "",
        "final_card_path": "",
        "final_index_path": "",
    }
    save_review_record(review_dir, record)
    return record


def handle_review_show(review_dir: Path, review_id: str) -> dict[str, Any]:
    record, failure = _load_for_handler(review_dir, review_id)
    if failure:
        return failure
    return _success("review-show", record)


def handle_review_list(review_dir: Path) -> dict[str, Any]:
    records = []
    if review_dir.exists():
        for path in sorted(review_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            loaded = load_review(review_dir, path.stem)
            if loaded.status == "corrupted":
                return knowledge_failure(
                    "review_record_corrupted",
                    f"审核记录损坏，无法读取：{path.stem}",
                    recoverable=False,
                )
            if loaded.status == "found":
                records.append(loaded.record)
    return {"success": True, "mode": "review-list", "total": len(records), "reviews": records}


def handle_review_revise(review_dir: Path, review_id: str, instruction: str) -> dict[str, Any]:
    record, failure = _load_for_handler(review_dir, review_id)
    if failure:
        return failure
    if record.get("status") == "revision_requested":
        for item in reversed(record.get("revision_instructions", [])):
            if (
                item.get("instruction") == instruction
                and item.get("revision") == record.get("revision")
            ):
                return _success(
                    "review-revise",
                    record,
                    idempotent=True,
                    next_skill="douyin-curate-via-obsidian-mcp",
                    workflow_status="revision_requested",
                    workflow_complete=False,
                )

    next_revision = int(record.get("revision", 0)) + 1
    instructions = list(record.get("revision_instructions", []))
    instructions.append(
        {
            "instruction": instruction,
            "created_at": utc_timestamp(),
            "revision": next_revision,
        }
    )
    changed, failure = _transition(
        review_dir,
        record,
        expected_statuses={"awaiting_approval", "revision_requested"},
        target_status="revision_requested",
        event_type="revision_requested",
        updates={
            "revision_instructions": instructions,
            "next_action": "revise_review_draft_via_obsidian_mcp",
        },
        event_details={"instruction": instruction},
    )
    if failure:
        return failure
    return _success(
        "review-revise",
        changed,
        next_skill="douyin-curate-via-obsidian-mcp",
        workflow_status="revision_requested",
        workflow_complete=False,
    )


def handle_review_approve(review_dir: Path, review_id: str) -> dict[str, Any]:
    record, failure = _load_for_handler(review_dir, review_id)
    if failure:
        return failure
    if record.get("status") == "approved":
        return _success(
            "review-approve",
            record,
            idempotent=True,
            next_skill="douyin-curate-via-obsidian-mcp",
            authorization_only=True,
            workflow_status="approved",
            workflow_complete=False,
            requires_user_approval=False,
        )
    changed, failure = _transition(
        review_dir,
        record,
        expected_statuses={"awaiting_approval"},
        target_status="approved",
        event_type="approved",
        updates={
            "approved_at": utc_timestamp(),
            "finalization_authorized": True,
            "next_action": "finalize_via_obsidian_mcp",
        },
    )
    if failure:
        return failure
    return _success(
        "review-approve",
        changed,
        next_skill="douyin-curate-via-obsidian-mcp",
        authorization_only=True,
        workflow_status="approved",
        workflow_complete=False,
        requires_user_approval=False,
    )


def handle_review_cancel(review_dir: Path, review_id: str) -> dict[str, Any]:
    record, failure = _load_for_handler(review_dir, review_id)
    if failure:
        return failure
    if record.get("status") == "cancelled":
        return _success(
            "review-cancel",
            record,
            idempotent=True,
            workflow_status="cancelled",
            workflow_complete=True,
        )
    changed, failure = _transition(
        review_dir,
        record,
        expected_statuses={"pending_draft", "awaiting_approval", "revision_requested"},
        target_status="cancelled",
        event_type="cancelled",
        updates={"next_action": "none", "finalization_authorized": False},
    )
    if failure:
        return failure
    return _success(
        "review-cancel",
        changed,
        workflow_status="cancelled",
        workflow_complete=True,
    )


def handle_review_draft_ready(
    review_dir: Path,
    review_id: str,
    suggested_category: str,
    target_path: str,
    index_path: str,
    draft_path: str = "",
) -> dict[str, Any]:
    record, failure = _load_for_handler(review_dir, review_id)
    if failure:
        return failure
    effective_draft_path = draft_path or str(record.get("draft_path") or "")
    requested = {
        "suggested_category": suggested_category,
        "target_path": target_path,
        "index_path": index_path,
        "draft_path": effective_draft_path,
    }
    current = {key: str(record.get(key) or "") for key in requested}
    if record.get("status") == "awaiting_approval":
        if current == requested:
            return _success(
                "review-draft-ready",
                record,
                idempotent=True,
                workflow_status="awaiting_approval",
                workflow_complete=False,
                requires_user_approval=True,
                next_action="present_draft_and_wait_for_approval",
            )
        return knowledge_failure(
            "invalid_review_transition",
            "审核草稿已就绪；如需修改参数，请先请求 revise。",
            recoverable=True,
        )
    changed, failure = _transition(
        review_dir,
        record,
        expected_statuses={"pending_draft", "revision_requested"},
        target_status="awaiting_approval",
        event_type="draft_ready",
        updates={**requested, "next_action": "wait_for_user_review"},
        event_details={
            "suggested_category": suggested_category,
            "target_path": target_path,
            "index_path": index_path,
            "draft_path": effective_draft_path,
        },
    )
    if failure:
        return failure
    return _success(
        "review-draft-ready",
        changed,
        workflow_status="awaiting_approval",
        workflow_complete=False,
        requires_user_approval=True,
        next_action="present_draft_and_wait_for_approval",
    )


def _valid_vault_relative_path(value: str) -> bool:
    if not value or "\x00" in value:
        return False
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or PureWindowsPath(value).is_absolute():
        return False
    return ".." not in Path(normalized).parts


def handle_review_finalized(
    review_dir: Path,
    review_id: str,
    final_card_path: str,
    final_index_path: str,
) -> dict[str, Any]:
    record, failure = _load_for_handler(review_dir, review_id)
    if failure:
        return failure
    if not _valid_vault_relative_path(final_card_path) or not _valid_vault_relative_path(
        final_index_path
    ):
        return knowledge_failure(
            "invalid_finalization_path",
            "正式卡片和索引路径必须是非空的 Vault 相对路径，且不能包含 ..。",
            recoverable=True,
        )
    if record.get("status") == "finalized":
        if (
            record.get("final_card_path") == final_card_path
            and record.get("final_index_path") == final_index_path
        ):
            return _success(
                "review-finalized",
                record,
                idempotent=True,
                workflow_status="finalized",
                workflow_complete=True,
                source_retention="keep",
            )
        return knowledge_failure(
            "invalid_review_transition",
            "审核已使用不同路径完成归档，不能覆盖最终路径。",
            recoverable=True,
        )
    if record.get("status") != "approved" or not record.get("finalization_authorized"):
        return knowledge_failure(
            "finalization_not_authorized",
            "只有审核批准后才允许正式归档。",
            recoverable=True,
        )
    changed, failure = _transition(
        review_dir,
        record,
        expected_statuses={"approved"},
        target_status="finalized",
        event_type="finalized",
        updates={
            "finalized_at": utc_timestamp(),
            "final_card_path": final_card_path,
            "final_index_path": final_index_path,
            "next_action": "none",
        },
        event_details={
            "final_card_path": final_card_path,
            "final_index_path": final_index_path,
        },
    )
    if failure:
        return failure
    return _success(
        "review-finalized",
        changed,
        workflow_status="finalized",
        workflow_complete=True,
        source_retention="keep",
    )
