"""Side-effect-free helpers owned by the Acquisition layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .media_policy import local_media_profile


SENSITIVE_METADATA_FRAGMENTS = (
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


def _safe_metadata_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _safe_metadata_value(item)
            for key, item in value.items()
            if not any(
                fragment in key.lower()
                for fragment in SENSITIVE_METADATA_FRAGMENTS
            )
        }
    if isinstance(value, list):
        return [_safe_metadata_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_safe_metadata_value(item) for item in value)
    return value


def safe_metadata_copy(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Copy metadata recursively while dropping credential-like keys."""
    return _safe_metadata_value(metadata or {})


def metadata_from_local_audio(
    audio_file: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build normalized metadata for an already acquired local media file."""
    path = Path(audio_file)
    profile = local_media_profile(path)
    metadata = {
        "title": path.stem or "local_audio",
        "author": "N/A",
        "original_url": str(path),
        "duration": "N/A",
        "cover_url": "N/A",
        "container_type": profile.container_type if profile else "",
        "container_media_type": profile.kind if profile else "file",
        "mime": profile.mime if profile else "",
    }
    return metadata, {
        "source_url": str(path),
        "audio_file": str(path),
        "container_type": metadata["container_type"],
        "container_media_type": metadata["container_media_type"],
        "mime": metadata["mime"],
    }
