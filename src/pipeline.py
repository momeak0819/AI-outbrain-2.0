"""Shared transcription pipeline for CLI and GUI."""

from __future__ import annotations

import configparser
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from audio_extractor import AudioExtractor
from douyin_parser import DouyinParser
from layers.acquisition_helpers import (
    metadata_from_local_audio as acquisition_metadata_from_local_audio,
)
from layers.media_policy import artifact_kind_for_media
from layers.processing_core import ProcessingRequest, process_media
from runtime_paths import default_audio_dir, resolve_ffmpeg_path
from transcript_exporter import (
    TranscriptExporter,
    export_transcript as export_transcript_files,
)


ENGINE_CHOICES = [
    "mock",
    "faster_whisper",
    "mimo",
    "custom_api",
    "aliyun_qwen_asr",
    "tencent_asr",
    "volcengine_asr",
]
EXPORT_CHOICES = ["txt", "md", "both"]


@dataclass
class PipelineOptions:
    url: str
    engine: str = "mock"
    export_format: str = "both"
    output_dir: str = "outputs"
    audio_output_dir: str = ""
    audio_file: str = ""
    skip_audio: bool = False
    keep_audio: bool = False
    mock_metadata: bool = False
    to_simplified: bool = True
    config: Optional[dict[str, dict[str, Any]]] = None


@dataclass
class PipelineResult:
    success: bool
    transcript: str = ""
    metadata: Optional[dict[str, Any]] = None
    exported_paths: Optional[list[str]] = None
    audio_path: str = ""
    engine: str = ""
    error: str = ""


LogCallback = Optional[Callable[[str], None]]


def run_pipeline(options: PipelineOptions, log: LogCallback = None) -> PipelineResult:
    """Run the legacy Source/Acquisition shell and delegate Processing."""
    config = options.config if options.config is not None else load_config()
    extracted_audio_path = ""

    try:
        if not options.url:
            return fail("错误：请提供抖音链接。", log)

        engine_name = normalize_engine_name(options.engine)
        metadata, video_info = load_metadata(options.url, options.mock_metadata, log)
        if metadata is None:
            return PipelineResult(success=False, error="抖音链接解析失败")

        audio_path = resolve_audio_path(options, engine_name, metadata, video_info, log)
        if audio_path is None:
            return PipelineResult(success=False, metadata=metadata, error="音频准备失败")
        if audio_path and not options.audio_file:
            extracted_audio_path = audio_path

        media_kind = (
            artifact_kind_for_media(options.audio_file)
            if options.audio_file
            else "audio"
        )
        core = process_media(
            ProcessingRequest(
                media_path=audio_path,
                media_kind=media_kind,
                engine_name=engine_name,
                engine_config=config,
                export_format=options.export_format,
                output_dir=options.output_dir,
                to_simplified=options.to_simplified,
                metadata=metadata,
            ),
            log=log,
            exporter=export_transcript,
        )
        if not core.success:
            return fail(
                core.error,
                log,
                metadata,
                audio_path,
                core.engine or engine_name,
            )

        if core.normalized:
            emit(log, "已转换为简体中文")

        emit(log, "转写完成")
        emit(log, "文件已导出")
        for path in core.exported_paths:
            emit(log, path)

        return PipelineResult(
            success=True,
            transcript=core.normalized_text,
            metadata=metadata,
            exported_paths=core.exported_paths,
            audio_path=audio_path,
            engine=core.engine,
        )
    finally:
        if extracted_audio_path and not options.keep_audio:
            cleanup_temp_audio(extracted_audio_path, log)


def load_config(project_root: Optional[Path] = None) -> dict[str, dict[str, Any]]:
    if project_root:
        root = project_root
    elif getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    else:
        root = Path(__file__).resolve().parents[1]
    config_path = root / "config.ini"
    if not config_path.exists():
        return {}

    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8-sig")
    return {section: dict(parser.items(section)) for section in parser.sections()}


def normalize_engine_name(engine_name: str) -> str:
    return (engine_name or "").strip().lower().replace("-", "_")


def load_metadata(
    url: str,
    use_mock_metadata: bool,
    log: LogCallback = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if use_mock_metadata:
        video_info = {
            "title": "示例抖音视频",
            "author_name": "示例作者",
            "source_url": url or "mock://douyin",
            "duration_str": "N/A",
            "cover_url": "N/A",
            "video_url": "",
        }
        metadata = normalize_metadata(video_info)
        emit(log, f"已获取视频信息：{metadata['title']} / {metadata['author']}")
        return metadata, video_info

    emit(log, "正在解析抖音链接...")
    parser = DouyinParser(log=log)
    try:
        video_info = parser.parse(url)
    except Exception as exc:
        emit(log, f"抖音链接解析失败: {exc}")
        return None, {}

    if not video_info:
        emit(log, "抖音链接解析失败。请检查链接是否可访问，或使用 mock 模式测试导出流程。")
        return None, {}

    metadata = normalize_metadata(video_info)
    emit(log, f"已获取视频信息：{metadata['title']} / {metadata['author']}")
    return metadata, video_info


def metadata_from_local_audio(audio_file: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compatibility wrapper for the Acquisition-owned metadata helper."""
    return acquisition_metadata_from_local_audio(audio_file)


def normalize_metadata(video_info: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": first_value(video_info, ["title", "desc"]),
        "author": first_value(video_info, ["author_name", "author", "nickname"]),
        "original_url": first_value(video_info, ["source_url", "original_url", "url"]),
        "duration": first_value(video_info, ["duration_str", "duration"]),
        "cover_url": first_value(video_info, ["cover_url", "cover"]),
    }


def first_value(data: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return "N/A"


def resolve_video_url(video_info: dict[str, Any]) -> str:
    return first_value(video_info, ["video_url", "play_url", "download_url", "url_list"])


def resolve_audio_path(
    options: PipelineOptions,
    engine_name: str,
    metadata: dict[str, Any],
    video_info: dict[str, Any],
    log: LogCallback = None,
) -> str | None:
    if options.audio_file:
        return options.audio_file

    if options.skip_audio:
        if engine_name == "mock":
            emit(log, "已跳过音频提取。")
            return ""

        emit(log, "--skip-audio 仅适合 mock 引擎。真实转写请提供 --audio-file，或去掉 --skip-audio。")
        return None

    return extract_audio(video_info, metadata, options, log)


def extract_audio(
    video_info: dict[str, Any],
    metadata: dict[str, Any],
    options: PipelineOptions,
    log: LogCallback = None,
) -> str | None:
    video_url = resolve_video_url(video_info)
    if video_url == "N/A":
        emit(log, "未获取到视频播放地址，无法提取音频")
        return None

    ffmpeg_path = resolve_ffmpeg_path()
    extractor = AudioExtractor(ffmpeg_path=ffmpeg_path, log=log)

    emit(log, "正在提取音频...")
    audio_output_path = build_audio_output_path(metadata, options)
    audio_path = extractor.extract_audio(
        video_url,
        output_path=str(audio_output_path),
        headers=video_info.get("download_headers", {}),
    )
    if not audio_path:
        emit(log, "音频提取失败")
        return None

    emit(log, f"音频提取成功：{audio_path}")
    return audio_path


def build_audio_output_path(metadata: dict[str, Any], options: PipelineOptions) -> Path:
    audio_dir = Path(options.audio_output_dir) if options.audio_output_dir else default_audio_dir(options.output_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)
    basename = TranscriptExporter().sanitize_filename(str(metadata.get("title") or "douyin_audio"))
    return unique_path(audio_dir / f"{basename}.wav")


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 1
    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def cleanup_temp_audio(audio_path: str, log: LogCallback = None) -> None:
    try:
        if os.path.exists(audio_path):
            os.remove(audio_path)
    except Exception as exc:
        emit(log, f"warning: 删除临时音频失败: {exc}")


def export_transcript(
    metadata: dict[str, Any],
    transcript: str,
    asr_engine: str,
    export_format: str,
    output_dir: str,
) -> list[str]:
    """Compatibility wrapper for callers importing from pipeline."""
    return export_transcript_files(
        metadata,
        transcript,
        asr_engine,
        export_format,
        output_dir,
    )


def fail(
    message: str,
    log: LogCallback = None,
    metadata: Optional[dict[str, Any]] = None,
    audio_path: str = "",
    engine: str = "",
) -> PipelineResult:
    emit(log, message)
    return PipelineResult(success=False, metadata=metadata, audio_path=audio_path, engine=engine, error=message)


def emit(log: LogCallback, message: str) -> None:
    if log:
        log(message)
