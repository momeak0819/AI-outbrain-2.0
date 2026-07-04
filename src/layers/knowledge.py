"""Knowledge-layer routing from normalized processing output to review decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import KnowledgeContext, KnowledgeResult, ProcessingResult


@dataclass
class KnowledgeDecision:
    """Structured Knowledge result plus workflow routing; never user-facing text."""

    result: KnowledgeResult
    normalized_text: str = ""
    next_action: str = ""
    next_skill: str = ""
    workflow_complete: bool = False
    requires_mcp: bool = False
    requires_review: bool = False
    requires_user_approval: bool = False
    fallback: str = ""
    review_path: str = ""
    draft_path: str = ""
    recommended_next_step: str = ""
    source_retention: str = "keep"
    extra: dict[str, Any] = field(default_factory=dict)

    def legacy_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "content_mode": self.result.content_mode,
            "review_id": self.result.review_id,
            "workflow_status": self.result.status,
            "next_action": self.next_action,
            "next_skill": self.next_skill,
            "workflow_complete": self.workflow_complete,
            "requires_mcp": self.requires_mcp,
            "requires_review": self.requires_review,
            "requires_user_approval": self.requires_user_approval,
            "source_retention": self.source_retention,
        }
        optional_result_fields = {
            "review_status": self.result.review_status,
            "suggested_category": self.result.suggested_category,
            "target_path": self.result.target_path,
            "final_card_path": self.result.final_card_path,
            "final_index_path": self.result.final_index_path,
        }
        fields.update({key: value for key, value in optional_result_fields.items() if value})
        if self.result.error_code:
            fields.update(
                {
                    "stage": "knowledge",
                    "error_code": self.result.error_code,
                    "error": self.result.error,
                    "curation_error": self.result.error,
                    "recoverable": self.result.recoverable,
                }
            )
        if self.fallback:
            fields["fallback"] = self.fallback
        if self.review_path:
            fields["review_path"] = self.review_path
        if self.draft_path:
            fields["draft_path"] = self.draft_path
        fields.update(self.extra)
        return fields


def _normalized_text(processing_result: ProcessingResult) -> str:
    return processing_result.normalized_text or processing_result.transcript


def _route_report(context: KnowledgeContext) -> dict[str, Any]:
    if context.route_report is not None:
        return context.route_report
    if context.route_report_provider is None:
        return {}
    return dict(context.route_report_provider() or {})


def _readiness(context: KnowledgeContext, report: dict[str, Any]) -> dict[str, Any]:
    if context.readiness is not None:
        return context.readiness
    if context.readiness_provider is not None:
        return dict(context.readiness_provider() or {})
    readiness = report.get("readiness")
    if isinstance(readiness, dict):
        return readiness
    ready = bool(report.get("mcp_ready"))
    return {
        "ready": ready,
        "error_code": "" if ready else "mcp_unavailable",
        "error": "",
        "recoverable": not ready,
    }


def _vault_validation(report: dict[str, Any]) -> dict[str, Any]:
    validation = report.get("vault_validation")
    if isinstance(validation, dict):
        return validation
    missing = list(report.get("missing_required_paths") or [])
    vault_exists = bool(report.get("vault_exists", True))
    valid = vault_exists and not missing
    return {
        "valid": valid,
        "missing_required_paths": missing,
        "error_code": "" if valid else "vault_structure_invalid",
        "error": "",
        "recoverable": not valid,
    }


def create_knowledge_result(
    processing_result: ProcessingResult,
    context: KnowledgeContext,
    source_payload: dict[str, Any] | None = None,
) -> KnowledgeDecision:
    """Create the sole Knowledge routing decision without formatting a reply."""
    content_mode = context.content_mode
    text = _normalized_text(processing_result)

    if processing_result.status != "completed":
        return KnowledgeDecision(
            result=KnowledgeResult(status="skipped", content_mode=content_mode),
            normalized_text=text,
            workflow_complete=True,
        )

    if content_mode == "original":
        return KnowledgeDecision(
            result=KnowledgeResult(status="transcript_ready", content_mode="original"),
            normalized_text=text,
            next_action="reply_with_original",
            workflow_complete=True,
        )

    report = _route_report(context)
    readiness = _readiness(context, report)
    vault_validation = _vault_validation(report)
    vault_invalid = not bool(vault_validation.get("valid", True))
    mcp_ready = bool(readiness.get("ready"))

    if vault_invalid or not mcp_ready:
        if vault_invalid:
            error_code = str(vault_validation.get("error_code") or "vault_structure_invalid")
            error = str(
                vault_validation.get("error")
                or "Obsidian 知识库结构不完整，知识卡片草稿尚未创建。"
            )
            recoverable = bool(vault_validation.get("recoverable", True))
        else:
            error_code = str(readiness.get("error_code") or "mcp_unavailable")
            error = str(
                readiness.get("error")
                or "当前 AI Agent 尚未完成 Obsidian MCP 真实验证，知识卡片草稿尚未创建。"
            )
            recoverable = bool(readiness.get("recoverable", True))
        return KnowledgeDecision(
            result=KnowledgeResult(
                status=error_code,
                content_mode=content_mode,
                error_code=error_code,
                error=error,
                recoverable=recoverable,
            ),
            normalized_text=text,
            next_action="configure_mcp_then_retry_curation",
            next_skill="obsidian-mcp-env-check",
            workflow_complete=False,
            requires_mcp=True,
            requires_review=True,
            requires_user_approval=True,
            fallback="original",
            recommended_next_step=str(report.get("recommended_next_step") or ""),
            extra={"readiness": readiness, "vault_validation": vault_validation},
        )

    if context.review_creator is None:
        raise ValueError("review_creator is required when Knowledge curation is ready")
    review_payload = dict(processing_result.metadata)
    review_payload.update(source_payload or {})
    if not review_payload.get("md_path"):
        review_payload["md_path"] = processing_result.markdown_path
    if not review_payload.get("txt_path"):
        review_payload["txt_path"] = processing_result.txt_path
    review = context.review_creator(
        review_payload,
        content_mode,
        context.interaction_channel,
    )
    return KnowledgeDecision(
        result=KnowledgeResult(
            status="pending_draft",
            content_mode=content_mode,
            review_id=str(review.get("review_id") or ""),
            review_status=str(review.get("status") or ""),
            suggested_category=str(review.get("suggested_category") or ""),
            target_path=str(review.get("target_path") or ""),
        ),
        normalized_text=text,
        next_action="curate_via_obsidian_mcp",
        next_skill="douyin-curate-via-obsidian-mcp",
        workflow_complete=False,
        requires_mcp=True,
        requires_review=True,
        requires_user_approval=True,
        review_path=str(review.get("review_path") or ""),
        draft_path=str(review.get("draft_path") or ""),
        extra={"readiness": readiness, "vault_validation": vault_validation},
    )
