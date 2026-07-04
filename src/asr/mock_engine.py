"""Mock ASR engine for end-to-end CLI smoke tests."""

from __future__ import annotations

from typing import Any, Optional

from .base import (
    BaseASREngine,
    EngineCapabilities,
    EngineReadiness,
    TranscriptionResult,
)


class MockASREngine(BaseASREngine):
    """Return a deterministic fake transcript without external dependencies."""

    name = "mock"

    def __init__(self, config: Optional[dict[str, Any]] = None):
        self.config = config or {}

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            supported_extensions=frozenset(
                {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".mp4"}
            ),
            supported_media_types=frozenset({"audio", "video"}),
            returns_segments=False,
        )

    def check_ready(self) -> EngineReadiness:
        return EngineReadiness(ready=True)

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        return TranscriptionResult(
            success=True,
            text="这是模拟转写结果。真实转写请切换到 faster_whisper 或 mimo 引擎。",
            engine=self.name,
            error=None,
            segments=None,
        )
