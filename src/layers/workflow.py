"""Workflow orchestration across source, acquisition, processing, knowledge and delivery."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .delivery import attach_layered_response
from .acquisition import (
    YTDLP_VIDEO_SOURCE_TYPES,
    acquire_douyin,
    acquire_local_audio,
    acquire_ytdlp_video,
)
from .models import AcquisitionResult, ProcessingResult, SourceInput
from .processing import process_acquired
from .sources import DEFAULT_SOURCE_REGISTRY, SourceRegistry
from pipeline import ENGINE_CHOICES, PipelineResult


def ingest(
    args: argparse.Namespace,
    run_douyin: Callable[[argparse.Namespace, Any], dict[str, Any]],
    run_local_audio: Callable[[argparse.Namespace, Any], dict[str, Any]],
    run_video: Callable[[argparse.Namespace, Any], dict[str, Any]] | None = None,
    registry: SourceRegistry = DEFAULT_SOURCE_REGISTRY,
) -> dict[str, Any]:
    source_input = SourceInput(
        source_type=getattr(args, "source_type", "auto") or "auto",
        url=getattr(args, "url", "") or "",
        text=getattr(args, "text", "") or "",
        audio_file=getattr(args, "audio_file", "") or "",
        raw_input=getattr(args, "raw_input", "") or "",
        input_kind=getattr(args, "input_kind", "unknown") or "unknown",
        metadata=dict(getattr(args, "source_metadata", {}) or {}),
    ).normalized()
    adapter, match = registry.resolve_match(source_input)
    if adapter is None:
        payload = {
            "success": False,
            "mode": "ingest",
            "stage": "source",
            "error": f"无法识别信源。当前已实现信源: {', '.join(registry.names())}",
            "workflow_status": "failed",
            "workflow_complete": True,
        }
        return attach_layered_response(payload, source_input.source_type, source_input.url or source_input.audio_file)

    document = adapter.describe(source_input, match)
    if document.status == "failed":
        payload = {
            "success": False,
            "mode": "ingest",
            "stage": "source",
            "error": document.error,
            "workflow_status": "failed",
            "workflow_complete": True,
        }
        return attach_layered_response(payload, adapter.name, document.original_url)

    if adapter.name == "douyin":
        payload = run_douyin(args, document)
    elif adapter.name == "local_audio":
        requested_mode = str(getattr(args, "im_content_mode", "") or getattr(args, "mode", "") or "")
        if requested_mode in {"card", "both"}:
            payload = {
                "success": False,
                "mode": "ingest",
                "stage": "input",
                "error_code": "mode_not_supported",
                "error": "local_audio currently supports original mode only.",
                "recoverable": True,
                "content_mode": "original",
                "workflow_status": "failed",
                "workflow_complete": True,
                "requires_mcp": False,
                "requires_review": False,
                "requires_user_approval": False,
            }
            return attach_layered_response(payload, adapter.name, document.original_url)
        payload = run_local_audio(args, document)
    elif adapter.name in YTDLP_VIDEO_SOURCE_TYPES:
        payload = (run_video or run_local_audio)(args, document)
    else:
        payload = {
            "success": False,
            "mode": "ingest",
            "stage": "source",
            "error_code": "unsupported_source_adapter",
            "error": f"Unsupported source adapter: {adapter.name}",
            "recoverable": True,
            "workflow_status": "failed",
            "workflow_complete": True,
        }
        return attach_layered_response(payload, adapter.name, document.original_url)
    payload["mode"] = "ingest"
    payload["source_type"] = adapter.name
    return attach_layered_response(
        payload,
        adapter.name,
        document.original_url,
        str(payload.pop("_processing_transcript", "") or payload.get("transcript") or ""),
    )


def execute_source_pipeline(source_type: str, document, options, log=None):
    """Run acquisition and processing while keeping knowledge/delivery outside."""
    if source_type not in {"douyin", "local_audio", *YTDLP_VIDEO_SOURCE_TYPES}:
        message = f"获取层不支持该来源类型：{source_type or 'N/A'}"
        if log:
            log(message)
        return (
            PipelineResult(success=False, metadata=document.metadata, error=message),
            AcquisitionResult(
                status="failed",
                media_type=document.media_type,
                error_code="unsupported_source_type",
                error=message,
                recoverable=True,
            ),
            ProcessingResult(
                status="skipped",
                error_code="acquisition_failed",
                error=message,
                recoverable=True,
            ),
        )

    engine_name = options.engine.strip().lower().replace("-", "_")
    if engine_name not in ENGINE_CHOICES:
        message = f"未知 ASR 引擎：{options.engine}"
        if log:
            log(message)
        return (
            PipelineResult(success=False, metadata=document.metadata, engine=engine_name, error=message),
            AcquisitionResult(status="skipped", media_type=document.media_type),
            ProcessingResult(
                status="failed",
                engine=engine_name,
                error_code="unknown_asr_engine",
                error=message,
                recoverable=True,
            ),
        )
    if source_type == "douyin":
        acquired = acquire_douyin(document, options, log)
    elif source_type == "local_audio":
        acquired = acquire_local_audio(document, Path(document.original_url))
    elif source_type in YTDLP_VIDEO_SOURCE_TYPES:
        acquired = acquire_ytdlp_video(document, options, log)
    result, processing = process_acquired(acquired, options, log)
    return result, acquired.result, processing
