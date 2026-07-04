"""Shared helpers for cloud ASR engines.

The classes in this module keep provider implementations small and enforce the
same no-network readiness rule for all cloud engines: readiness only checks
local configuration; real HTTP calls happen inside ``transcribe``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .base import BaseASREngine, EngineCapabilities, EngineReadiness, TranscriptionResult
from .provider_registry import SUPPORTED_CLOUD_AUDIO_EXTENSIONS


SENSITIVE_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "header",
    "password",
    "secret",
    "token",
)


class CloudASREngine(BaseASREngine):
    """Base for implemented cloud ASR providers."""

    display_name = "Cloud ASR"
    required_config_keys: tuple[str, ...] = ()
    env_mapping: dict[str, str] = {}
    default_timeout = 120

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            supported_extensions=frozenset(SUPPORTED_CLOUD_AUDIO_EXTENSIONS),
            supported_media_types=frozenset({"audio"}),
            returns_segments=False,
        )

    def check_ready(self) -> EngineReadiness:
        missing = [key for key in self.required_config_keys if not self._config_value(key)]
        if missing:
            return EngineReadiness(
                ready=False,
                code="config_missing",
                message=f"{self.display_name} 未配置必要凭据：{', '.join(missing)}",
            )
        return EngineReadiness(ready=True)

    def _config_value(self, key: str, default: str = "") -> str:
        env_name = self.env_mapping.get(key, "")
        if env_name:
            value = os.getenv(env_name, "")
            if value:
                return value.strip()
        return str(self.config.get(key, default) or "").strip()

    @property
    def timeout(self) -> int:
        raw = self._config_value("timeout", str(self.default_timeout))
        try:
            return max(1, int(float(raw)))
        except ValueError:
            return self.default_timeout

    def _validate_audio_path(self, audio_path: str) -> Path | TranscriptionResult:
        path = Path(audio_path or "")
        if not audio_path or not path.exists():
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error=f"音频文件不存在：{audio_path or 'N/A'}",
            )
        if not path.is_file():
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error=f"输入不是普通文件：{audio_path}",
            )
        if path.suffix.lower() not in SUPPORTED_CLOUD_AUDIO_EXTENSIONS:
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error=f"{self.display_name} 不支持该音频格式：{path.suffix or '无后缀'}",
            )
        return path

    def _readiness_failure(self) -> TranscriptionResult | None:
        readiness = self.check_ready()
        if readiness.ready:
            return None
        return TranscriptionResult(
            success=False,
            text="",
            engine=self.name,
            error=readiness.message,
        )

    @staticmethod
    def _mime_type(path: Path) -> str:
        suffix = path.suffix.lower()
        return {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
            ".flac": "audio/flac",
            ".aac": "audio/aac",
            ".ogg": "audio/ogg",
        }.get(suffix, "application/octet-stream")

    @staticmethod
    def _audio_format(path: Path) -> str:
        suffix = path.suffix.lower().lstrip(".")
        if suffix == "m4a":
            return "mp4"
        return suffix

    @classmethod
    def _safe_error(cls, prefix: str, detail: object = "") -> str:
        text = str(detail or "").replace("\r", " ").replace("\n", " ")
        lowered = text.lower()
        if any(marker in lowered for marker in SENSITIVE_MARKERS):
            text = detail.__class__.__name__ if not isinstance(detail, str) else "sensitive_error_redacted"
        if len(text) > 300:
            text = text[:300] + "..."
        return f"{prefix}: {text}" if text else prefix


# Backward-compatible name used by the first registration stage.
PlannedCloudASREngine = CloudASREngine
