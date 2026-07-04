"""OpenAI Whisper API ASR engine."""

from __future__ import annotations

import os
from typing import Any, Optional

from .base import BaseASREngine, TranscriptionResult


class OpenAIWhisperEngine(BaseASREngine):
    name = "openai_whisper"

    def __init__(self, config: Optional[dict[str, Any]] = None):
        self.config = config or {}
        self.api_key = os.getenv("OPENAI_API_KEY") or self.config.get("api_key", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        if not self.api_key:
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error="未配置 OPENAI_API_KEY",
            )

        return TranscriptionResult(
            success=False,
            text="",
            engine=self.name,
            error="OpenAI Whisper API 转写功能待实现",
        )
