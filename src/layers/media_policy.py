"""Side-effect-free local media classification policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LocalMediaProfile:
    suffix: str
    kind: str
    mime: str
    container_type: str


LOCAL_MEDIA_PROFILES = {
    ".mp3": LocalMediaProfile(".mp3", "audio", "audio/mpeg", "mp3"),
    ".wav": LocalMediaProfile(".wav", "audio", "audio/wav", "wav"),
    ".m4a": LocalMediaProfile(".m4a", "audio", "audio/mp4", "m4a"),
    ".flac": LocalMediaProfile(".flac", "audio", "audio/flac", "flac"),
    ".aac": LocalMediaProfile(".aac", "audio", "audio/aac", "aac"),
    ".ogg": LocalMediaProfile(".ogg", "audio", "audio/ogg", "ogg"),
    ".mp4": LocalMediaProfile(".mp4", "video", "video/mp4", "mp4"),
}
LOCAL_MEDIA_SUFFIXES = frozenset(LOCAL_MEDIA_PROFILES)


def normalize_media_suffix(path_or_suffix: str | Path) -> str:
    value = str(path_or_suffix)
    if value.startswith(".") and "/" not in value and "\\" not in value:
        return value.lower()
    return Path(value).suffix.lower()


def local_media_profile(path_or_suffix: str | Path) -> LocalMediaProfile | None:
    return LOCAL_MEDIA_PROFILES.get(normalize_media_suffix(path_or_suffix))


def is_supported_local_media(path_or_suffix: str | Path) -> bool:
    return local_media_profile(path_or_suffix) is not None


def artifact_kind_for_media(path_or_suffix: str | Path) -> str:
    profile = local_media_profile(path_or_suffix)
    return profile.kind if profile else "file"


def mime_for_media(path_or_suffix: str | Path) -> str:
    profile = local_media_profile(path_or_suffix)
    return profile.mime if profile else ""


def container_type_for_media(path_or_suffix: str | Path) -> str:
    profile = local_media_profile(path_or_suffix)
    return profile.container_type if profile else ""
