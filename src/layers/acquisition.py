"""Acquisition layer: turn a source document into media ready for processing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from audio_extractor import AudioExtractor
from pipeline import PipelineOptions, load_metadata, resolve_audio_path
from runtime_paths import resolve_ffmpeg_path

from .acquisition_helpers import metadata_from_local_audio, safe_metadata_copy
from .downloaders.ytdlp_downloader import (
    YtdlpAuthRequiredError,
    YtdlpBackendError,
    YtdlpDownloadError,
    YtdlpDownloader,
    YtdlpMedia,
    YtdlpMetadataError,
    YtdlpUnavailableError,
    YtdlpUnsupportedPlatformError,
)
from .media_policy import (
    LOCAL_MEDIA_SUFFIXES,
    artifact_kind_for_media,
    container_type_for_media,
    local_media_profile,
    mime_for_media,
)
from .models import AcquisitionArtifact, AcquisitionResult, SourceDocument

LOCAL_AUDIO_SUFFIXES = LOCAL_MEDIA_SUFFIXES
YTDLP_VIDEO_SOURCE_TYPES = frozenset(
    {
        "youtube",
        "bilibili",
        "generic_video",
        "x_video",
        "vimeo",
        "twitch",
        "tiktok",
        "instagram",
        "xiaohongshu",
    }
)

_SENSITIVE_TEXT_MARKERS = (
    "authorization",
    "cookie",
    "credential",
    "header",
    "password",
    "secret",
    "token",
)


@dataclass
class AcquiredContent:
    source: SourceDocument
    result: AcquisitionResult
    metadata: dict[str, Any]
    media_path: str = ""
    cleanup_media: bool = False

    @property
    def primary_artifact(self) -> AcquisitionArtifact | None:
        return next(
            (
                artifact
                for artifact in self.result.artifact_records
                if artifact.role == "primary"
            ),
            None,
        )


def acquire_douyin(
    source: SourceDocument,
    options: PipelineOptions,
    log: Callable[[str], None] | None = None,
) -> AcquiredContent:
    safe_source_metadata = safe_metadata_copy(source.metadata)
    try:
        metadata, video_info = load_metadata(
            source.original_url,
            options.mock_metadata,
            log,
        )
    except Exception:
        if log:
            log("抖音解析过程中发生错误")
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="douyin_parse_error",
            error="抖音解析过程中发生错误",
            metadata=safe_source_metadata,
        )
    if metadata is None:
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="douyin_parse_failed",
            error="抖音链接解析失败",
            metadata=safe_source_metadata,
        )
    metadata = safe_metadata_copy(metadata)
    source.title = str(metadata.get("title") or "")
    source.author = str(metadata.get("author") or "")
    source.metadata.update(metadata)
    engine_name = options.engine.strip().lower().replace("-", "_")
    try:
        media_path = resolve_audio_path(
            options,
            engine_name,
            metadata,
            video_info,
            log,
        )
    except Exception:
        if log:
            log("媒体准备过程中发生错误")
        return _acquisition_failure(
            source,
            media_type="audio",
            error_code="media_prepare_error",
            error="媒体准备过程中发生错误",
            metadata=metadata,
        )
    if media_path is None:
        return _acquisition_failure(
            source,
            media_type="audio",
            error_code="audio_prepare_failed",
            error="音频准备失败",
            metadata=metadata,
        )
    if not media_path and not (engine_name == "mock" and options.skip_audio):
        return _acquisition_failure(
            source,
            media_type="audio",
            error_code="audio_prepare_failed",
            error="音频准备失败",
            metadata=metadata,
        )
    if not media_path:
        metadata["mock_media_skipped"] = True
    else:
        metadata.update(
            {
                "acquired_media_kind": "audio",
                "acquired_mime": mime_for_media(media_path),
                "acquired_container_type": container_type_for_media(media_path),
            }
        )
    return AcquiredContent(
        source=source,
        result=AcquisitionResult(
            status="completed",
            media_type="audio",
            media_path=media_path,
            artifacts=[media_path] if media_path else [],
            recoverable=False,
            artifact_records=(
                [
                    AcquisitionArtifact(
                        path=media_path,
                        kind="audio",
                        role="derived",
                        ownership=(
                            "user_owned"
                            if options.audio_file
                            else "acquisition_temp"
                        ),
                        cleanup_policy=(
                            "never"
                            if options.audio_file
                            else "on_processing_complete"
                        ),
                        mime=mime_for_media(media_path),
                    )
                ]
                if media_path
                else []
            ),
        ),
        metadata=metadata,
        media_path=media_path,
        cleanup_media=bool(media_path and not options.audio_file),
    )


def _acquisition_failure(
    source: SourceDocument,
    media_type: str,
    error_code: str,
    error: str,
    metadata: dict[str, Any] | None = None,
) -> AcquiredContent:
    return AcquiredContent(
        source=source,
        result=AcquisitionResult(
            status="failed",
            media_type=media_type,
            media_path="",
            artifacts=[],
            error_code=error_code,
            error=error,
            recoverable=True,
            artifact_records=[],
        ),
        metadata=safe_metadata_copy(
            source.metadata if metadata is None else metadata
        ),
        media_path="",
        cleanup_media=False,
    )


def _safe_backend_error_summary(exc: Exception) -> str:
    text = str(exc).strip()
    lowered = text.lower()
    if not text or any(marker in lowered for marker in _SENSITIVE_TEXT_MARKERS):
        return exc.__class__.__name__
    return text


def _backend_cookie_config(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        key: metadata[key]
        for key in ("cookies_file", "cookiefile")
        if metadata.get(key)
    }


def _controlled_media_dir(options: PipelineOptions) -> Path:
    base = options.audio_output_dir or options.output_dir or "runtime/media"
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _unique_audio_output_path(video_path: str, output_dir: Path) -> Path:
    stem = Path(video_path).stem or "ytdlp_audio"
    candidate = output_dir / f"{stem}.wav"
    if not candidate.exists():
        return candidate
    index = 1
    while True:
        candidate = output_dir / f"{stem}_{index}.wav"
        if not candidate.exists():
            return candidate
        index += 1


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _is_nonempty_regular_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _prepare_ytdlp_audio_artifact(
    video_path: str,
    options: PipelineOptions,
    log: Callable[[str], None] | None = None,
) -> str:
    output_dir = _controlled_media_dir(options)
    output_path = _unique_audio_output_path(video_path, output_dir)
    extractor = AudioExtractor(ffmpeg_path=resolve_ffmpeg_path(), log=log)
    audio_path = extractor.extract_audio_from_file(
        video_path,
        output_path=str(output_path),
    )
    if not audio_path:
        return ""
    resolved_audio = Path(audio_path).resolve()
    if not _is_within(resolved_audio, output_dir):
        return ""
    if not _is_nonempty_regular_file(resolved_audio):
        return ""
    return str(resolved_audio)


def acquire_ytdlp_video(
    source: SourceDocument,
    options: PipelineOptions,
    log: Callable[[str], None] | None = None,
    backend: Any | None = None,
) -> AcquiredContent:
    """Acquire a yt-dlp-backed video source without leaking backend details."""

    if source.source_type not in YTDLP_VIDEO_SOURCE_TYPES:
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="unsupported_platform",
            error=f"yt-dlp 获取层不支持该平台: {source.source_type or 'N/A'}",
        )

    safe_source_metadata = safe_metadata_copy(source.metadata)
    backend_source_metadata = {
        **safe_source_metadata,
        **_backend_cookie_config(source.metadata),
    }
    downloader = backend if backend is not None else YtdlpDownloader()
    try:
        available = downloader.is_available()
    except Exception:
        available = False
    if not available:
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="ytdlp_unavailable",
            error="yt-dlp 不可用，请安装或配置 yt-dlp 后重试",
            metadata=safe_source_metadata,
        )

    try:
        backend_metadata = downloader.extract_metadata(
            source.original_url,
            source_type=source.source_type,
            source_metadata=backend_source_metadata,
        )
    except YtdlpUnavailableError:
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="ytdlp_unavailable",
            error="yt-dlp unavailable; install or configure yt-dlp and retry",
            metadata=safe_source_metadata,
        )
    except YtdlpUnsupportedPlatformError as exc:
        reason = _safe_backend_error_summary(exc)
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="unsupported_platform",
            error=f"yt-dlp 不支持该平台或链接: {reason}",
            metadata=safe_source_metadata,
        )
    except YtdlpAuthRequiredError as exc:
        reason = _safe_backend_error_summary(exc)
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="ytdlp_auth_required",
            error=f"yt-dlp 下载需要登录或 cookies: {reason}",
            metadata=safe_source_metadata,
        )
    except YtdlpMetadataError as exc:
        reason = _safe_backend_error_summary(exc)
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="ytdlp_metadata_failed",
            error=f"yt-dlp 元数据获取失败: {reason}",
            metadata=safe_source_metadata,
        )
    except YtdlpBackendError as exc:
        reason = _safe_backend_error_summary(exc)
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="ytdlp_metadata_failed",
            error=f"yt-dlp 元数据获取失败: {reason}",
            metadata=safe_source_metadata,
        )
    except Exception as exc:
        reason = _safe_backend_error_summary(exc)
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="ytdlp_metadata_failed",
            error=f"yt-dlp 元数据获取失败: {reason}",
            metadata=safe_source_metadata,
        )

    metadata = {
        **safe_source_metadata,
        **safe_metadata_copy(backend_metadata or {}),
        "download_backend": "yt_dlp",
    }
    source.title = str(metadata.get("title") or source.title or "")
    source.author = str(
        metadata.get("uploader")
        or metadata.get("author")
        or source.author
        or ""
    )
    source.metadata.update(metadata)

    try:
        media = downloader.download(
            source.original_url,
            source_type=source.source_type,
            metadata={
                **metadata,
                **_backend_cookie_config(source.metadata),
            },
            output_dir=options.audio_output_dir or options.output_dir,
        )
    except YtdlpUnavailableError:
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="ytdlp_unavailable",
            error="yt-dlp unavailable; install or configure yt-dlp and retry",
            metadata=metadata,
        )
    except YtdlpAuthRequiredError as exc:
        reason = _safe_backend_error_summary(exc)
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="ytdlp_auth_required",
            error=f"yt-dlp 下载需要登录或 cookies: {reason}",
            metadata=metadata,
        )
    except YtdlpUnsupportedPlatformError as exc:
        reason = _safe_backend_error_summary(exc)
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="unsupported_platform",
            error=f"yt-dlp 不支持该平台或链接: {reason}",
            metadata=metadata,
        )
    except YtdlpDownloadError as exc:
        reason = _safe_backend_error_summary(exc)
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="ytdlp_download_failed",
            error=f"yt-dlp 下载失败: {reason}",
            metadata=metadata,
        )
    except YtdlpBackendError as exc:
        reason = _safe_backend_error_summary(exc)
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="ytdlp_download_failed",
            error=f"yt-dlp 下载失败: {reason}",
            metadata=metadata,
        )
    except Exception as exc:
        reason = _safe_backend_error_summary(exc)
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="ytdlp_download_failed",
            error=f"yt-dlp 下载失败: {reason}",
            metadata=metadata,
        )

    if isinstance(media, str):
        media = YtdlpMedia(path=media)
    media_path = str(getattr(media, "path", "") or "")
    if not media_path:
        return _acquisition_failure(
            source,
            media_type="video",
            error_code="ytdlp_download_failed",
            error="yt-dlp 下载失败: 未返回下载产物路径",
            metadata=metadata,
        )

    media_metadata = safe_metadata_copy(getattr(media, "metadata", {}) or {})
    media_mime = str(getattr(media, "mime", "") or "")
    metadata.update(media_metadata)
    audio_path = ""
    try:
        audio_path = _prepare_ytdlp_audio_artifact(media_path, options, log)
    except Exception:
        audio_path = ""
    if not audio_path:
        return _acquisition_failure(
            source,
            media_type="audio",
            error_code="media_prepare_error",
            error="yt-dlp video audio preparation failed",
            metadata=metadata,
        )

    metadata.update(
        {
            "acquired_media_kind": "audio",
            "acquired_mime": mime_for_media(audio_path),
            "acquired_container_type": container_type_for_media(audio_path),
            "source_video_path": media_path,
            "source_video_mime": media_mime or mime_for_media(media_path),
        }
    )
    return AcquiredContent(
        source=source,
        result=AcquisitionResult(
            status="completed",
            media_type="audio",
            media_path=audio_path,
            artifacts=[media_path, audio_path],
            recoverable=False,
            artifact_records=[
                AcquisitionArtifact(
                    path=media_path,
                    kind="video",
                    role="source",
                    ownership="acquisition_temp",
                    cleanup_policy="on_processing_complete",
                    mime=media_mime or mime_for_media(media_path),
                ),
                AcquisitionArtifact(
                    path=audio_path,
                    kind="audio",
                    role="primary",
                    ownership="acquisition_temp",
                    cleanup_policy="on_processing_complete",
                    mime=mime_for_media(audio_path),
                )
            ],
        ),
        metadata=metadata,
        media_path=audio_path,
        cleanup_media=True,
    )


def _local_audio_failure(
    source: SourceDocument,
    error_code: str,
    error: str,
) -> AcquiredContent:
    return _acquisition_failure(
        source,
        media_type="audio",
        error_code=error_code,
        error=error,
    )


def acquire_local_audio(source: SourceDocument, audio_file: Path) -> AcquiredContent:
    path_text = str(audio_file)

    try:
        exists = audio_file.exists()
    except OSError as exc:
        return _local_audio_failure(
            source,
            "source_file_unreadable",
            f"无法访问本地媒体文件 {path_text}: {exc}",
        )
    if not exists:
        return _local_audio_failure(
            source,
            "source_file_not_found",
            f"本地媒体文件不存在: {path_text}",
        )

    try:
        is_file = audio_file.is_file()
    except OSError as exc:
        return _local_audio_failure(
            source,
            "source_file_unreadable",
            f"无法检查本地媒体文件 {path_text}: {exc}",
        )
    if not is_file:
        return _local_audio_failure(
            source,
            "source_not_file",
            f"本地媒体路径不是普通文件: {path_text}",
        )

    suffix = audio_file.suffix.lower()
    if suffix not in LOCAL_AUDIO_SUFFIXES:
        display_suffix = audio_file.suffix or "<无后缀>"
        return _local_audio_failure(
            source,
            "unsupported_audio_format",
            f"不支持的本地媒体格式 {display_suffix}: {path_text}",
        )

    try:
        with audio_file.open("rb") as stream:
            stream.read(1)
    except OSError as exc:
        return _local_audio_failure(
            source,
            "source_file_unreadable",
            f"本地媒体文件不可读 {path_text}: {exc}",
        )

    metadata, _ = metadata_from_local_audio(str(audio_file))
    profile = local_media_profile(audio_file)
    source.title = str(metadata.get("title") or audio_file.stem)
    source.author = str(metadata.get("author") or "")
    source.metadata.update(metadata)
    return AcquiredContent(
        source=source,
        result=AcquisitionResult(
            status="completed",
            media_type="audio",
            media_path=str(audio_file),
            artifacts=[str(audio_file)],
            recoverable=False,
            artifact_records=[
                AcquisitionArtifact(
                    path=str(audio_file),
                    kind=artifact_kind_for_media(audio_file),
                    role="primary",
                    ownership="user_owned",
                    cleanup_policy="never",
                    mime=profile.mime if profile else "",
                )
            ],
        ),
        metadata=metadata,
        media_path=str(audio_file),
        cleanup_media=False,
    )
