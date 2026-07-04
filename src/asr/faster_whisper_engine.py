"""Local faster-whisper ASR engine."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

try:
    from runtime_paths import portable_model_path
except ImportError:  # Package-style imports used by some tests.
    from src.runtime_paths import portable_model_path

from .base import (
    BaseASREngine,
    EngineCapabilities,
    EngineReadiness,
    TranscriptionResult,
)


class FasterWhisperEngine(BaseASREngine):
    """Transcribe local audio with faster-whisper."""

    name = "faster_whisper"

    def __init__(self, config: Optional[dict[str, Any]] = None):
        self.config = config or {}
        self.model_size = self.config.get("model_size") or self.config.get("local_model") or "base"
        self.device = self.config.get("device") or "cpu"
        self.compute_type = self.config.get("compute_type") or "int8"
        self.language = self.config.get("language", "zh")
        self.model_path = self.config.get("model_path") or self._resolve_model_path()
        self.hf_endpoint = (
            self.config.get("hf_endpoint")
            or os.environ.get("HF_ENDPOINT")
            or "https://hf-mirror.com"
        )

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            supported_extensions=frozenset(
                {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"}
            ),
            supported_media_types=frozenset({"audio"}),
            returns_segments=True,
        )

    def check_ready(self) -> EngineReadiness:
        if not isinstance(self.model_size, str) or not self.model_size.strip():
            return EngineReadiness(
                ready=False,
                code="config_invalid",
                message="faster-whisper 模型配置无效",
            )
        if not isinstance(self.device, str) or not self.device.strip():
            return EngineReadiness(
                ready=False,
                code="config_invalid",
                message="faster-whisper 设备配置无效",
            )
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return EngineReadiness(
                ready=False,
                code="dependency_missing",
                message="未安装 faster-whisper，请运行 pip install faster-whisper",
            )
        return EngineReadiness(ready=True)

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        if not audio_path or not Path(audio_path).exists():
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error=f"音频文件不存在: {audio_path or 'N/A'}",
            )

        try:
            from faster_whisper import WhisperModel
        except ImportError:
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error="未安装 faster-whisper，请运行 pip install faster-whisper",
            )

        try:
            self._ensure_hf_endpoint()
            model = WhisperModel(
                self.model_path or self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        except Exception as exc:
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error=self._format_model_load_error(exc),
            )

        try:
            language = self.language.strip() if isinstance(self.language, str) else self.language
            language_arg = language or None
            segments_iter, _info = model.transcribe(audio_path, language=language_arg)

            segments = []
            text_parts = []
            for segment in segments_iter:
                segment_text = getattr(segment, "text", "") or ""
                text_parts.append(segment_text.strip())
                segments.append(
                    {
                        "start": getattr(segment, "start", None),
                        "end": getattr(segment, "end", None),
                        "text": segment_text,
                    }
                )

            transcript = "\n".join(part for part in text_parts if part)
            return TranscriptionResult(
                success=True,
                text=transcript,
                engine=self.name,
                error=None,
                segments=segments,
            )
        except Exception as exc:
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error=f"faster-whisper 转写失败: {exc}",
            )

    def _ensure_hf_endpoint(self) -> None:
        if self.hf_endpoint and not os.environ.get("HF_ENDPOINT"):
            os.environ["HF_ENDPOINT"] = str(self.hf_endpoint)

    def _resolve_model_path(self) -> str:
        local_path = portable_model_path(str(self.model_size))
        if local_path.exists():
            return str(local_path)
        return ""

    def _format_model_load_error(self, exc: Exception) -> str:
        message = str(exc)
        model_location = self.model_path or self.model_size
        hint = (
            "faster-whisper 模型加载失败。通常是首次下载模型超时或本地没有缓存。\n"
            f"当前模型：{model_location}\n"
            f"当前模型下载源：{os.environ.get('HF_ENDPOINT') or self.hf_endpoint or 'Hugging Face 默认源'}\n"
            "建议：确认 portable 包内 runtime/models/base 或 runtime/models/small 存在；medium 未内置时请切换 base/small 或联网下载。"
        )
        if "ConnectTimeout" in message or "Hub" in message or "snapshot" in message:
            return f"{hint}\n原始错误：{message}"
        return f"{hint}\n原始错误：{message}"
