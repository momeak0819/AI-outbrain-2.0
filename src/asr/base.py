"""Shared interfaces for ASR engines."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Optional


_READINESS_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


@dataclass(frozen=True)
class EngineCapabilities:
    supported_extensions: frozenset[str]
    supported_media_types: frozenset[str]
    returns_segments: bool


@dataclass(frozen=True)
class EngineReadiness:
    ready: bool
    code: str = ""
    message: str = ""

    def __post_init__(self) -> None:
        if self.ready:
            if self.code or self.message:
                raise ValueError("ready engines must not include code or message")
            return
        if not self.code or not _READINESS_CODE_PATTERN.fullmatch(self.code):
            raise ValueError("unready engines require a snake_case code")
        if not self.message:
            raise ValueError("unready engines require a message")


@dataclass
class TranscriptionResult:
    """Normalized ASR result returned by every engine."""

    success: bool
    text: str
    engine: str
    error: Optional[str] = None
    segments: Optional[list[Any]] = None


class BaseASREngine:
    """Base class for pluggable ASR engines."""

    name = "base"

    def capabilities(self) -> EngineCapabilities:
        raise NotImplementedError

    def check_ready(self) -> EngineReadiness:
        raise NotImplementedError

    def is_available(self) -> bool:
        """Compatibility wrapper for legacy callers."""
        return self.check_ready().ready

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        """Transcribe an audio file."""
        raise NotImplementedError
