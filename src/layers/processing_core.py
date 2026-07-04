"""Source-neutral Processing core for media transcription and export."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from asr import create_asr_engine
from text_normalizer import to_simplified
from transcript_exporter import export_transcript


LogCallback = Callable[[str], None] | None
EngineFactory = Callable[[str, dict[str, dict[str, Any]] | None], Any]
Exporter = Callable[[dict[str, Any], str, str, str, str], list[str]]
Normalizer = Callable[[str], str]


@dataclass(frozen=True)
class ProcessingRequest:
    media_path: str
    media_kind: str
    engine_name: str
    engine_config: dict[str, dict[str, Any]] | None
    export_format: str
    output_dir: str
    to_simplified: bool
    metadata: dict[str, Any]


@dataclass
class ProcessingCoreResult:
    success: bool
    raw_transcript: str = ""
    normalized_text: str = ""
    engine: str = ""
    segments: list[Any] = field(default_factory=list)
    exported_paths: list[str] = field(default_factory=list)
    error_code: str = ""
    error: str = ""
    recoverable: bool = False
    normalized: bool = False


def process_media(
    request: ProcessingRequest,
    log: LogCallback = None,
    engine_factory: EngineFactory | None = None,
    exporter: Exporter | None = None,
    normalizer: Normalizer | None = None,
) -> ProcessingCoreResult:
    """Run the single ASR -> normalize -> export Processing sequence."""
    engine_factory = engine_factory or create_asr_engine
    exporter = exporter or export_transcript
    normalizer = normalizer or to_simplified
    engine = engine_factory(request.engine_name, request.engine_config)

    readiness = engine.check_ready()
    if not readiness.ready:
        return ProcessingCoreResult(
            success=False,
            engine=request.engine_name,
            error_code="asr_unavailable",
            error=readiness.message,
            recoverable=True,
        )

    capabilities = engine.capabilities()
    extension = Path(request.media_path).suffix.lower()
    if (
        (extension and extension not in capabilities.supported_extensions)
        or request.media_kind not in capabilities.supported_media_types
    ):
        message = (
            f"ASR 引擎 {request.engine_name} 不支持该媒体格式："
            f"{extension or '<无扩展名>'} ({request.media_kind or 'unknown'})"
        )
        return ProcessingCoreResult(
            success=False,
            engine=request.engine_name,
            error_code="media_format_unsupported",
            error=message,
            recoverable=True,
        )

    if log:
        log("正在转写，首次运行可能需要下载模型，请耐心等待……")
    transcribed = engine.transcribe(request.media_path)
    segments = list(transcribed.segments or [])
    if not transcribed.success:
        partial_text = transcribed.text or ""
        return ProcessingCoreResult(
            success=False,
            raw_transcript=partial_text,
            normalized_text=partial_text,
            engine=request.engine_name,
            segments=segments,
            error_code="asr_failed",
            error=transcribed.error or "ASR 转写失败",
            recoverable=True,
        )

    raw_transcript = transcribed.text
    normalized_text = (
        normalizer(raw_transcript)
        if request.to_simplified
        else raw_transcript
    )
    normalized = request.to_simplified and normalized_text != raw_transcript
    try:
        paths = exporter(
            request.metadata,
            normalized_text,
            transcribed.engine,
            request.export_format,
            request.output_dir,
        )
    except Exception as exc:
        return ProcessingCoreResult(
            success=False,
            raw_transcript=raw_transcript,
            normalized_text=normalized_text,
            engine=transcribed.engine,
            segments=segments,
            error_code="export_failed",
            error=f"导出文件失败：{exc}",
            recoverable=True,
            normalized=normalized,
        )

    return ProcessingCoreResult(
        success=True,
        raw_transcript=raw_transcript,
        normalized_text=normalized_text,
        engine=transcribed.engine,
        segments=segments,
        exported_paths=paths,
        normalized=normalized,
    )
