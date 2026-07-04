"""Delivery layer: canonical envelope, legacy projection, and reply formatting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import (
    AcquisitionResult,
    DeliveryResult,
    KnowledgeResult,
    LayerFailure,
    ProcessingResult,
    SourceDocument,
    WorkflowEnvelope,
)

CANONICAL_LAYERS = ("source", "acquisition", "processing", "knowledge", "delivery")
STAGE_ALIASES = {
    "input": "source",
    "source": "source",
    "acquisition": "acquisition",
    "asr": "processing",
    "processing": "processing",
    "review": "knowledge",
    "knowledge": "knowledge",
    "delivery": "delivery",
}


@dataclass(frozen=True)
class DeliveryContext:
    """Delivery-only context; it does not decide Knowledge routing."""

    content_mode: str = "original"
    response_mode: str = "original"
    reply_mode: str = "desktop"
    interaction_channel: str = "auto"
    workflow_complete: bool = True
    next_action: str = ""
    next_skill: str = ""
    requires_mcp: bool = False
    requires_review: bool = False
    requires_user_approval: bool = False
    source_retention: str = "keep"
    fallback: str = ""
    success: bool | None = None


def build_original_reply_text(payload: dict[str, Any], transcript: str) -> str:
    path = payload.get("md_path") or payload.get("txt_path") or ""
    lines = [
        "转写成功。",
        f"标题：{payload.get('title') or ''}",
        f"作者：{payload.get('author') or ''}",
        f"导出路径：{path}",
        "",
        "文字稿：",
        transcript,
    ]
    return "\n".join(lines).strip()


def format_knowledge_reply(
    payload: dict[str, Any],
    transcript: str,
    decision: Any,
) -> str:
    """Format legacy user-facing text after Knowledge has made its decision."""
    if decision.result.status == "skipped":
        return str(payload.get("reply_text") or "")
    original = build_original_reply_text(payload, transcript)
    if decision.result.status == "transcript_ready":
        return original
    if decision.fallback == "original":
        return "\n\n".join(
            item
            for item in [
                decision.result.error,
                decision.recommended_next_step,
                original,
            ]
            if item
        ).strip()
    status_text = (
        f"Review {decision.result.review_id} created. Continue with Obsidian MCP, "
        f"write the draft to {decision.draft_path}, then present it for approval "
        "in the current interaction channel."
    )
    if decision.result.content_mode == "both":
        return "\n\n".join([original, status_text])
    return status_text


def infer_failure_layer(payload: dict[str, Any]) -> str:
    stage = str(payload.get("stage") or "")
    error = str(payload.get("error") or "")
    if stage in STAGE_ALIASES:
        return STAGE_ALIASES[stage]
    if (
        "链接" in error
        or "文件不存在" in error
        or "鏈接" in error
        or "閾炬帴" in error
        or "鏂囦欢涓嶅瓨鍦" in error
    ):
        return "source"
    if (
        "解析失败" in error
        or "音频准备失败" in error
        or "瑙ｆ瀽澶辫触" in error
        or "闊抽" in error and "澶辫触" in error
    ):
        return "acquisition"
    if (
        "ASR" in error
        or "转写失败" in error
        or "导出文件失败" in error
        or "杞" in error and "澶辫触" in error
        or "瀵煎嚭" in error and "澶辫触" in error
    ):
        return "processing"
    if payload.get("curation_error"):
        return "knowledge"
    return "delivery"


def extract_layer_failure(
    result: SourceDocument
    | AcquisitionResult
    | ProcessingResult
    | KnowledgeResult
    | DeliveryResult,
    stage: str,
) -> LayerFailure | None:
    """Extract a canonical failure without treating skipped as a new failure."""
    if result.status == "skipped":
        return None
    if result.status != "failed" and not result.error_code and not result.error:
        return None
    return LayerFailure(
        stage=stage,
        error_code=result.error_code or f"{stage}_failed",
        error=result.error or f"{stage} failed",
        recoverable=result.recoverable,
    )


def first_layer_failure(envelope: WorkflowEnvelope) -> LayerFailure | None:
    for stage in CANONICAL_LAYERS:
        failure = extract_layer_failure(getattr(envelope, stage), stage)
        if failure is not None:
            return failure
    return None


def failure_to_legacy(failure: LayerFailure) -> dict[str, Any]:
    """Project a canonical failure to the stable flat error fields."""
    return {
        "stage": failure.stage,
        "error_code": failure.error_code,
        "error": failure.error,
        "recoverable": failure.recoverable,
    }


def build_delivery_envelope(
    source: SourceDocument,
    acquisition: AcquisitionResult,
    processing: ProcessingResult,
    knowledge: KnowledgeResult,
    context: DeliveryContext,
    delivery: DeliveryResult | None = None,
) -> WorkflowEnvelope:
    """Build the canonical five-layer envelope from typed layer results."""
    delivery_result = delivery or DeliveryResult(
        status="completed",
        channel=context.interaction_channel,
        reply_mode=context.reply_mode,
        artifacts=list(processing.artifacts),
    )
    provisional = WorkflowEnvelope(
        success=True,
        source=source,
        acquisition=acquisition,
        processing=processing,
        knowledge=knowledge,
        delivery=delivery_result,
        next={
            "action": context.next_action,
            "skill": context.next_skill,
            "requires_mcp": context.requires_mcp,
            "requires_review": context.requires_review,
            "requires_user_approval": context.requires_user_approval,
            "workflow_complete": context.workflow_complete,
            "source_retention": context.source_retention,
            "response_mode": context.response_mode,
        },
    )
    failure = first_layer_failure(provisional)
    success = context.success if context.success is not None else failure is None
    return WorkflowEnvelope(
        success=bool(success),
        source=source,
        acquisition=acquisition,
        processing=processing,
        knowledge=knowledge,
        delivery=delivery_result,
        next=provisional.next,
    )


def build_legacy_projection(envelope: WorkflowEnvelope) -> dict[str, Any]:
    """Project legacy flat JSON fields from the canonical envelope only."""
    source = envelope.source
    acquisition = envelope.acquisition
    processing = envelope.processing
    knowledge = envelope.knowledge
    delivery = envelope.delivery
    exported_paths = list(processing.artifacts or delivery.artifacts or [])
    md_path = processing.markdown_path or next(
        (str(path) for path in exported_paths if str(path).lower().endswith(".md")),
        "",
    )
    txt_path = processing.txt_path or next(
        (str(path) for path in exported_paths if str(path).lower().endswith(".txt")),
        "",
    )
    projection: dict[str, Any] = {
        "success": envelope.success,
        "title": source.title or processing.metadata.get("title", ""),
        "author": source.author or processing.metadata.get("author", ""),
        "input_url": source.original_url,
        "source_type": source.source_type,
        "media_type": source.media_type or acquisition.media_type,
        "audio_path": acquisition.media_path,
        "engine": processing.engine,
        "transcript_chars": processing.transcript_chars
        or len(processing.normalized_text or processing.transcript),
        "md_path": md_path,
        "txt_path": txt_path,
        "exported_paths": exported_paths,
        "content_mode": knowledge.content_mode,
        "workflow_status": knowledge.status,
        "workflow_complete": bool(envelope.next.get("workflow_complete")),
        "next_action": envelope.next.get("action", ""),
        "next_skill": envelope.next.get("skill", ""),
        "requires_mcp": bool(envelope.next.get("requires_mcp")),
        "requires_review": bool(envelope.next.get("requires_review")),
        "requires_user_approval": bool(envelope.next.get("requires_user_approval")),
        "source_retention": envelope.next.get("source_retention", "keep"),
        "interaction_channel": delivery.channel,
        "response_mode": envelope.next.get("response_mode", knowledge.content_mode),
        "reply_mode": delivery.reply_mode,
    }
    transcript = processing.normalized_text or processing.transcript
    if transcript:
        projection["transcript"] = transcript
    if delivery.reply_text:
        projection["reply_text"] = delivery.reply_text
    optional_knowledge_fields = {
        "review_id": knowledge.review_id,
        "review_status": knowledge.review_status,
        "suggested_category": knowledge.suggested_category,
        "target_path": knowledge.target_path,
        "final_card_path": knowledge.final_card_path,
        "final_index_path": knowledge.final_index_path,
        "fallback": knowledge.fallback,
        "review_path": knowledge.review_path,
        "draft_path": knowledge.draft_path,
        "recommended_next_step": knowledge.recommended_next_step,
    }
    projection.update(
        {key: value for key, value in optional_knowledge_fields.items() if value}
    )
    for key in (
        "readiness",
        "vault_validation",
        "mcp_finalization_incomplete",
        "vault_write_not_confirmed",
    ):
        value = getattr(knowledge, key)
        if value is not None:
            projection[key] = value
    failure = first_layer_failure(envelope)
    if failure is not None:
        projection.update(failure_to_legacy(failure))
        if failure.stage == "knowledge":
            projection["curation_error"] = failure.error
    return projection


def build_batch_envelope(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate already-built item projections without recomputing item state."""
    failed = sum(1 for item in items if not item.get("success"))
    workflow_complete = all(item.get("workflow_complete", False) for item in items)
    return {
        "success": failed == 0,
        "mode": "batch",
        "total": len(items),
        "succeeded": len(items) - failed,
        "failed": failed,
        "workflow_status": "complete" if workflow_complete else "in_progress",
        "workflow_complete": workflow_complete,
        "requires_mcp": any(item.get("requires_mcp", False) for item in items),
        "requires_review": any(item.get("requires_review", False) for item in items),
        "requires_user_approval": any(
            item.get("requires_user_approval", False) for item in items
        ),
        "items": items,
    }


def _status_for(success: bool, failure_layer: str, layer: str) -> str:
    if success:
        return "completed"
    failed_index = CANONICAL_LAYERS.index(failure_layer)
    layer_index = CANONICAL_LAYERS.index(layer)
    if layer_index < failed_index:
        return "completed"
    if layer_index == failed_index:
        return "failed"
    return "skipped"


def _knowledge_from_payload(payload: dict[str, Any], status: str) -> KnowledgeResult:
    is_knowledge = infer_failure_layer(payload) == "knowledge"
    return KnowledgeResult(
        status=str(payload.get("workflow_status") or status),
        content_mode=str(payload.get("content_mode") or "original"),
        review_id=str(payload.get("review_id") or ""),
        review_status=str(payload.get("review_status") or ""),
        suggested_category=str(payload.get("suggested_category") or ""),
        target_path=str(payload.get("target_path") or ""),
        final_card_path=str(payload.get("final_card_path") or ""),
        final_index_path=str(payload.get("final_index_path") or ""),
        error_code=str(payload.get("error_code") or "") if is_knowledge else "",
        error=str(payload.get("curation_error") or payload.get("error") or "")
        if is_knowledge
        else "",
        recoverable=bool(payload.get("recoverable", False)) if is_knowledge else False,
        fallback=str(payload.get("fallback") or ""),
        review_path=str(payload.get("review_path") or ""),
        draft_path=str(payload.get("draft_path") or ""),
        recommended_next_step=str(payload.get("recommended_next_step") or ""),
        readiness=payload.get("readiness") if isinstance(payload.get("readiness"), dict) else None,
        vault_validation=payload.get("vault_validation")
        if isinstance(payload.get("vault_validation"), dict)
        else None,
        mcp_finalization_incomplete=payload.get("mcp_finalization_incomplete")
        if isinstance(payload.get("mcp_finalization_incomplete"), dict)
        else None,
        vault_write_not_confirmed=payload.get("vault_write_not_confirmed")
        if isinstance(payload.get("vault_write_not_confirmed"), dict)
        else None,
    )


def attach_layered_response(
    payload: dict[str, Any],
    source_type: str,
    source_input: str = "",
    transcript: str = "",
) -> dict[str, Any]:
    """Compatibility wrapper: build envelope, then derive legacy flat fields."""
    success = bool(payload.get("success"))
    source_override = payload.pop("_layer_source", None)
    acquisition_override = payload.pop("_layer_acquisition", None)
    processing_override = payload.pop("_layer_processing", None)
    failure_layer = infer_failure_layer(payload) if not success else ""

    metadata = {
        "duration": payload.get("duration", ""),
        "cover_url": payload.get("cover_url", ""),
        "input": source_input,
    }
    source = SourceDocument(
        status=_status_for(success, failure_layer, "source") if not success else "completed",
        source_type=source_type,
        title=str(payload.get("title") or ""),
        author=str(payload.get("author") or ""),
        original_url=str(payload.get("input_url") or source_input or ""),
        media_type="audio" if source_type == "local_audio" else "video",
        metadata=metadata,
    )
    if source_override:
        source = SourceDocument(**source_override)
    acquisition = AcquisitionResult(
        status=_status_for(success, failure_layer, "acquisition")
        if not success
        else "completed",
        media_type=source.media_type,
        media_path=str(payload.get("audio_path") or ""),
        artifacts=[item for item in [payload.get("audio_path")] if item],
    )
    if acquisition_override:
        acquisition = AcquisitionResult(**acquisition_override)
    processing_text = transcript or str(payload.get("transcript") or "")
    processing = ProcessingResult(
        status=_status_for(success, failure_layer, "processing")
        if not success
        else "completed",
        engine=str(payload.get("engine") or ""),
        transcript=processing_text,
        transcript_chars=int(payload.get("transcript_chars") or len(processing_text)),
        normalized=success,
        artifacts=list(payload.get("exported_paths") or []),
        normalized_text=processing_text,
        markdown_path=str(payload.get("md_path") or "")
        or next(
            (
                str(item)
                for item in payload.get("exported_paths") or []
                if str(item).lower().endswith(".md")
            ),
            "",
        ),
        txt_path=str(payload.get("txt_path") or "")
        or next(
            (
                str(item)
                for item in payload.get("exported_paths") or []
                if str(item).lower().endswith(".txt")
            ),
            "",
        ),
        metadata=dict(payload.get("metadata") or metadata),
    )
    if processing_override:
        processing = ProcessingResult(**processing_override)
    knowledge = _knowledge_from_payload(
        payload,
        _status_for(success, failure_layer, "knowledge") if not success else "completed",
    )
    delivery = DeliveryResult(
        status="completed" if payload.get("reply_text") or success else _status_for(success, failure_layer, "delivery"),
        channel=str(payload.get("interaction_channel") or "auto"),
        reply_mode=str(payload.get("reply_mode") or "desktop"),
        reply_text=str(payload.get("reply_text") or ""),
        artifacts=list(payload.get("exported_paths") or []),
    )

    if not success:
        target = {
            "source": source,
            "acquisition": acquisition,
            "processing": processing,
            "knowledge": knowledge,
            "delivery": delivery,
        }[failure_layer]
        target.error_code = str(
            payload.get("error_code")
            or target.error_code
            or payload.get("stage")
            or f"{failure_layer}_failed"
        )
        target.error = str(payload.get("error") or target.error or "")
        target.recoverable = bool(
            payload["recoverable"] if "recoverable" in payload else target.recoverable
        )

    context = DeliveryContext(
        content_mode=knowledge.content_mode,
        response_mode=str(payload.get("response_mode") or knowledge.content_mode),
        reply_mode=delivery.reply_mode,
        interaction_channel=delivery.channel,
        workflow_complete=bool(payload.get("workflow_complete")),
        next_action=str(payload.get("next_action") or ""),
        next_skill=str(payload.get("next_skill") or ""),
        requires_mcp=bool(payload.get("requires_mcp")),
        requires_review=bool(payload.get("requires_review")),
        requires_user_approval=bool(payload.get("requires_user_approval")),
        source_retention=str(payload.get("source_retention") or "keep"),
        fallback=knowledge.fallback,
        success=success,
    )
    envelope = build_delivery_envelope(
        source, acquisition, processing, knowledge, context, delivery
    )
    result = {
        **payload,
        **build_legacy_projection(envelope),
        **envelope.to_dict(),
    }
    for legacy_key in ("stage", "error", "error_code", "recoverable"):
        if legacy_key in payload:
            result[legacy_key] = payload[legacy_key]
    return result
