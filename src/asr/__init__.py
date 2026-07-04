"""Pluggable ASR engines for douyin-to-text."""

from .base import (
    BaseASREngine,
    EngineCapabilities,
    EngineReadiness,
    TranscriptionResult,
)
from .factory import ASREngineFactory, create_asr_engine
from .mock_engine import MockASREngine
from .provider_registry import ASRProvider, ASR_PROVIDERS, provider_ids, providers_as_dicts

__all__ = [
    "ASRProvider",
    "ASR_PROVIDERS",
    "BaseASREngine",
    "EngineCapabilities",
    "EngineReadiness",
    "TranscriptionResult",
    "ASREngineFactory",
    "MockASREngine",
    "create_asr_engine",
    "provider_ids",
    "providers_as_dicts",
]
