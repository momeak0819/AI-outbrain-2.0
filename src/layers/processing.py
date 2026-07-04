"""Five-layer adapter for the source-neutral Processing core."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from asr import create_asr_engine
from pipeline import PipelineOptions, PipelineResult, export_transcript
from text_normalizer import to_simplified

from .acquisition import AcquiredContent
from .artifact_cleanup import cleanup_consumed_media
from .models import ProcessingResult
from .processing_core import ProcessingRequest, process_media


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    attributes = getattr(value, "__dict__", None)
    if isinstance(attributes, dict):
        return {
            str(key): _json_safe(item)
            for key, item in attributes.items()
            if not str(key).startswith("_")
        }
    return str(value)


def _safe_segments(segments) -> list[dict]:
    safe: list[dict] = []
    for segment in segments or []:
        converted = _json_safe(segment)
        safe.append(converted if isinstance(converted, dict) else {"value": converted})
    return safe


def _export_paths(paths: list[str]) -> tuple[str, str]:
    markdown_path = ""
    txt_path = ""
    for item in paths:
        suffix = Path(item).suffix.lower()
        if suffix == ".md":
            markdown_path = item
        elif suffix == ".txt":
            txt_path = item
    return markdown_path, txt_path


def _media_kind(acquired: AcquiredContent) -> str:
    matching = [
        record
        for record in acquired.result.artifact_records
        if record.path == acquired.media_path
    ]
    if len(matching) == 1:
        return matching[0].kind
    return acquired.result.media_type


def process_acquired(
    acquired: AcquiredContent,
    options: PipelineOptions,
    log: Callable[[str], None] | None = None,
) -> tuple[PipelineResult, ProcessingResult]:
    if acquired.result.status != "completed":
        result = PipelineResult(
            success=False,
            metadata=acquired.metadata,
            error=acquired.result.error,
        )
        return result, ProcessingResult(
            status="skipped",
            error_code="acquisition_failed",
            error=acquired.result.error,
            recoverable=acquired.result.recoverable,
            processing_mode="asr",
            metadata=_json_safe(acquired.metadata),
        )

    engine_name = options.engine.strip().lower().replace("-", "_")
    request = ProcessingRequest(
        media_path=acquired.media_path,
        media_kind=_media_kind(acquired),
        engine_name=engine_name,
        engine_config=options.config,
        export_format=options.export_format,
        output_dir=options.output_dir,
        to_simplified=options.to_simplified,
        metadata=acquired.metadata,
    )
    warnings: list[str] = []
    try:
        core = process_media(
            request,
            log=log,
            engine_factory=create_asr_engine,
            exporter=export_transcript,
            normalizer=to_simplified,
        )
        pipeline_result = PipelineResult(
            success=core.success,
            transcript=core.normalized_text,
            metadata=acquired.metadata,
            exported_paths=core.exported_paths or None,
            audio_path=acquired.media_path,
            engine=core.engine,
            error=core.error,
        )
        markdown_path, txt_path = _export_paths(core.exported_paths)
        processing_result = ProcessingResult(
            status="completed" if core.success else "failed",
            engine=core.engine,
            transcript=core.normalized_text,
            transcript_chars=len(core.normalized_text),
            normalized=core.normalized,
            artifacts=core.exported_paths,
            error_code=core.error_code,
            error=core.error,
            recoverable=core.recoverable,
            processing_mode="asr",
            raw_transcript=core.raw_transcript,
            normalized_text=core.normalized_text,
            segments=_safe_segments(core.segments),
            markdown_path=markdown_path,
            txt_path=txt_path,
            metadata=_json_safe(acquired.metadata),
            warnings=warnings,
        )
        return pipeline_result, processing_result
    finally:
        def cleanup_log(message: str) -> None:
            if message.startswith("warning:"):
                warnings.append(message)
            if log:
                log(message)

        cleanup_consumed_media(
            acquired,
            keep_audio=options.keep_audio,
            audio_output_dir=options.audio_output_dir,
            output_dir=options.output_dir,
            log=cleanup_log,
        )
