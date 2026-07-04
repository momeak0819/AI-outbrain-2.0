"""Factory for pluggable ASR engines."""

from __future__ import annotations

from typing import Any, Optional

from .base import (
    BaseASREngine,
    EngineCapabilities,
    EngineReadiness,
    TranscriptionResult,
)
from .custom_api_engine import CustomAPIEngine
from .faster_whisper_engine import FasterWhisperEngine
from .aliyun_qwen_asr_engine import AliyunQwenASREngine
from .mimo_engine import MiMoEngine
from .mock_engine import MockASREngine
from .tencent_asr_engine import TencentASREngine
from .volcengine_asr_engine import VolcengineASREngine


class UnknownASREngine(BaseASREngine):
    """Null-object engine used for clear unknown-engine errors."""

    def __init__(self, requested_name: str):
        self.requested_name = requested_name
        self.name = requested_name or "unknown"

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            supported_extensions=frozenset(),
            supported_media_types=frozenset(),
            returns_segments=False,
        )

    def check_ready(self) -> EngineReadiness:
        return EngineReadiness(
            ready=False,
            code="unknown_engine",
            message=f"未知 ASR 引擎：{self.requested_name}",
        )

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        return TranscriptionResult(
            success=False,
            text="",
            engine=self.name,
            error=f"未知 ASR 引擎: {self.requested_name}",
        )


class ASREngineFactory:
    """Create ASR engines by normalized engine name."""

    _engine_map = {
        "mock": MockASREngine,
        "faster_whisper": FasterWhisperEngine,
        "mimo": MiMoEngine,
        "custom_api": CustomAPIEngine,
        "aliyun_qwen_asr": AliyunQwenASREngine,
        "tencent_asr": TencentASREngine,
        "volcengine_asr": VolcengineASREngine,
    }

    @classmethod
    def create(
        cls,
        engine_name: str,
        config: Optional[dict[str, dict[str, Any]]] = None,
    ) -> BaseASREngine:
        normalized_name = (engine_name or "").strip().lower().replace("-", "_")
        engine_class = cls._engine_map.get(normalized_name)

        if not engine_class:
            return UnknownASREngine(engine_name)

        engine_config = (config or {}).get(normalized_name, {})
        return engine_class(engine_config)

    @classmethod
    def registry_names(cls) -> tuple[str, ...]:
        return tuple(cls._engine_map)


def create_asr_engine(
    engine_name: str,
    config: Optional[dict[str, dict[str, Any]]] = None,
) -> BaseASREngine:
    """Convenience wrapper around ASREngineFactory.create."""
    return ASREngineFactory.create(engine_name, config)
