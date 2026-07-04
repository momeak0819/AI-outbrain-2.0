"""Custom API ASR engine."""

from __future__ import annotations

import os
from typing import Any, Optional

from .base import (
    BaseASREngine,
    EngineCapabilities,
    EngineReadiness,
    TranscriptionResult,
)


class CustomAPIEngine(BaseASREngine):
    name = "custom_api"

    def __init__(self, config: Optional[dict[str, Any]] = None):
        self.config = config or {}
        self.api_url = self.config.get("api_url", "")
        self.api_key = os.getenv("CUSTOM_ASR_API_KEY") or self.config.get("api_key", "")

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            supported_extensions=frozenset({".mp3", ".wav"}),
            supported_media_types=frozenset({"audio"}),
            returns_segments=False,
        )

    def check_ready(self) -> EngineReadiness:
        if not self.api_url:
            return EngineReadiness(
                ready=False,
                code="config_missing",
                message="未配置自定义 ASR API 地址",
            )
        return EngineReadiness(
            ready=False,
            code="not_implemented",
            message="自定义 ASR API 转写功能尚未实现",
        )

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        if not self.api_url:
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error="未配置自定义 API 地址",
            )

        return TranscriptionResult(
            success=False,
            text="",
            engine=self.name,
            error="自定义 API 转写功能待实现",
        )
