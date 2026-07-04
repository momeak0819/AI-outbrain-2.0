"""Source layer adapters and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import urlparse
from typing import Iterable

from batch_pipeline import extract_urls

from .media_policy import (
    LOCAL_MEDIA_SUFFIXES,
    artifact_kind_for_media,
)
from .models import InputKind, SourceDocument, SourceInput, SourceMatch, SourceType


_MATCH_UNSET = object()


VIDEO_SOURCE_SPECS = (
    {
        "name": SourceType.YOUTUBE.value,
        "platform": "youtube",
        "domains": ("youtube.com", "youtu.be", "youtube-nocookie.com"),
    },
    {
        "name": SourceType.BILIBILI.value,
        "platform": "bilibili",
        "domains": ("bilibili.com", "b23.tv"),
    },
    {
        "name": SourceType.X_VIDEO.value,
        "platform": "x",
        "domains": ("x.com", "twitter.com"),
    },
    {
        "name": SourceType.VIMEO.value,
        "platform": "vimeo",
        "domains": ("vimeo.com", "player.vimeo.com"),
    },
    {
        "name": SourceType.TWITCH.value,
        "platform": "twitch",
        "domains": ("twitch.tv", "clips.twitch.tv"),
    },
    {
        "name": SourceType.TIKTOK.value,
        "platform": "tiktok",
        "domains": ("tiktok.com", "vm.tiktok.com"),
    },
    {
        "name": SourceType.INSTAGRAM.value,
        "platform": "instagram",
        "domains": ("instagram.com",),
    },
    {
        "name": SourceType.XIAOHONGSHU.value,
        "platform": "xiaohongshu",
        "domains": ("xiaohongshu.com", "xhslink.com"),
    },
)

GENERIC_VIDEO_PATH_MARKERS = (
    "/video",
    "/watch",
    "/short",
    "/reel",
    "/clip",
    "/live",
    "/media",
    "/v/",
)


def _url_candidate(source: SourceInput) -> str:
    source = source.normalized()
    if source.url:
        return source.url.strip()
    for value in (source.raw_input, source.text):
        if value:
            urls = extract_urls(value)
            if urls:
                return urls[0]
    if source.raw_input and source.input_kind in {
        InputKind.URL.value,
        InputKind.UNKNOWN.value,
    }:
        return source.raw_input.strip()
    return ""


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _host_matches(host: str, domains: tuple[str, ...]) -> bool:
    host = host.lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def _looks_like_video_page(url: str) -> bool:
    if not _is_http_url(url):
        return False
    parsed = urlparse(url)
    value = f"{parsed.path.lower()}?{parsed.query.lower()}"
    return any(marker in value for marker in GENERIC_VIDEO_PATH_MARKERS)


class SourceAdapter(ABC):
    name = "base"
    capabilities: tuple[str, ...] = ()

    def can_handle(self, source: SourceInput) -> bool:
        return self.detect(source) is not None

    @abstractmethod
    def detect(self, source: SourceInput) -> SourceMatch | None:
        raise NotImplementedError

    @abstractmethod
    def describe(
        self,
        source: SourceInput,
        match: SourceMatch | None | object = _MATCH_UNSET,
    ) -> SourceDocument:
        raise NotImplementedError


class DouyinSourceAdapter(SourceAdapter):
    name = "douyin"
    capabilities = ("url", "share_text", "video_metadata")

    def detect(self, source: SourceInput) -> SourceMatch | None:
        source = source.normalized()
        candidate = source.url.strip()
        detected_by = "explicit_source_type" if source.source_type == self.name else "url_pattern"

        if not candidate and source.input_kind == InputKind.URL.value:
            candidate = source.raw_input.strip()
        share_text = source.text or (
            source.raw_input
            if source.input_kind == InputKind.TEXT.value
            else ""
        )
        if not candidate and share_text:
            urls = extract_urls(share_text)
            candidate = urls[0] if urls else ""
        if not candidate:
            return None
        if source.source_type != self.name and not (
            "douyin.com" in candidate
            or "iesdouyin.com" in candidate
            or candidate.startswith("mock://")
        ):
            return None
        return SourceMatch(
            source_type=self.name,
            normalized_input=candidate,
            input_kind=InputKind.URL.value,
            media_type="video",
            detected_by=detected_by,
            metadata=dict(source.metadata),
        )

    def describe(
        self,
        source: SourceInput,
        match: SourceMatch | None | object = _MATCH_UNSET,
    ) -> SourceDocument:
        source = source.normalized()
        if match is _MATCH_UNSET:
            match = self.detect(source)
        if match is None:
            return SourceDocument(
                status="failed",
                source_type=self.name,
                media_type="video",
                error_code="source_input_missing",
                error="未从输入中找到抖音链接",
                recoverable=True,
            )
        return SourceDocument(
            status="ready",
            source_type=self.name,
            original_url=match.normalized_input,
            media_type="video",
            metadata={
                **source.metadata,
                **match.metadata,
                "input_text": source.text or (
                    source.raw_input
                    if source.input_kind == InputKind.TEXT.value
                    else ""
                ),
                "adapter": self.name,
                "detected_by": match.detected_by,
                "input_kind": match.input_kind,
                "normalized_input": match.normalized_input,
            },
        )


class LocalAudioSourceAdapter(SourceAdapter):
    name = "local_audio"
    capabilities = ("local_file", "audio")
    suffixes = LOCAL_MEDIA_SUFFIXES

    def detect(self, source: SourceInput) -> SourceMatch | None:
        source = source.normalized()
        input_path = source.audio_file or (
            source.raw_input
            if source.input_kind == InputKind.PATH.value
            else ""
        )
        if not input_path:
            return None
        suffix = Path(input_path).suffix.lower()
        if source.source_type != self.name and suffix not in self.suffixes:
            return None
        container_media_type = artifact_kind_for_media(suffix)
        return SourceMatch(
            source_type=self.name,
            normalized_input=input_path,
            input_kind=InputKind.PATH.value,
            media_type="audio",
            detected_by=(
                "explicit_source_type"
                if source.source_type == self.name
                else "file_extension"
            ),
            metadata={
                **source.metadata,
                "container_media_type": container_media_type,
                **(
                    {"compatibility_route": self.name}
                    if container_media_type == "video"
                    else {}
                ),
            },
        )

    def describe(
        self,
        source: SourceInput,
        match: SourceMatch | None | object = _MATCH_UNSET,
    ) -> SourceDocument:
        source = source.normalized()
        if match is _MATCH_UNSET:
            match = self.detect(source)
        if match is None:
            return SourceDocument(
                status="failed",
                source_type=self.name,
                media_type="audio",
                error_code="source_input_missing",
                error="local_audio 信源必须提供 --audio-file",
                recoverable=True,
            )
        path = Path(match.normalized_input)
        return SourceDocument(
            status="ready",
            source_type=self.name,
            title=path.stem,
            original_url=str(path),
            media_type="audio",
            metadata={
                **source.metadata,
                **match.metadata,
                "audio_file": str(path),
                "adapter": self.name,
                "detected_by": match.detected_by,
                "input_kind": match.input_kind,
                "normalized_input": match.normalized_input,
            },
        )


class VideoUrlSourceAdapter(SourceAdapter):
    capabilities = ("url", "video_metadata", "yt_dlp_backend")

    def __init__(
        self,
        name: str,
        platform: str,
        domains: tuple[str, ...] = (),
        generic: bool = False,
    ) -> None:
        self.name = name
        self.platform = platform
        self.domains = domains
        self.generic = generic

    def detect(self, source: SourceInput) -> SourceMatch | None:
        source = source.normalized()
        candidate = _url_candidate(source)
        if not candidate:
            return None
        explicit = source.source_type == self.name
        if not explicit:
            if not _is_http_url(candidate):
                return None
            parsed = urlparse(candidate)
            if self.generic:
                if not _looks_like_video_page(candidate):
                    return None
            elif not _host_matches(parsed.netloc, self.domains):
                return None
        return SourceMatch(
            source_type=self.name,
            normalized_input=candidate,
            input_kind=InputKind.URL.value,
            media_type="video",
            detected_by=(
                "explicit_source_type"
                if explicit
                else ("generic_video_url" if self.generic else "url_pattern")
            ),
            metadata={
                **source.metadata,
                "platform": self.platform,
                "download_backend": "yt_dlp",
            },
        )

    def describe(
        self,
        source: SourceInput,
        match: SourceMatch | None | object = _MATCH_UNSET,
    ) -> SourceDocument:
        source = source.normalized()
        if match is _MATCH_UNSET:
            match = self.detect(source)
        if match is None:
            return SourceDocument(
                status="failed",
                source_type=self.name,
                media_type="video",
                error_code="source_input_missing",
                error=f"{self.name} 信源必须提供 URL 或 raw_input",
                recoverable=True,
            )
        return SourceDocument(
            status="ready",
            source_type=self.name,
            original_url=match.normalized_input,
            media_type="video",
            metadata={
                **source.metadata,
                **match.metadata,
                "adapter": self.name,
                "platform": self.platform,
                "detected_by": match.detected_by,
                "input_kind": match.input_kind,
                "normalized_input": match.normalized_input,
                "download_backend": "yt_dlp",
            },
        )


def default_source_adapters() -> tuple[SourceAdapter, ...]:
    return (
        DouyinSourceAdapter(),
        LocalAudioSourceAdapter(),
        *(
            VideoUrlSourceAdapter(
                name=spec["name"],
                platform=spec["platform"],
                domains=spec["domains"],
            )
            for spec in VIDEO_SOURCE_SPECS
        ),
        VideoUrlSourceAdapter(
            name=SourceType.GENERIC_VIDEO.value,
            platform="generic_video",
            generic=True,
        ),
    )


class SourceRegistry:
    def __init__(self, adapters: Iterable[SourceAdapter] | None = None):
        self._adapters: dict[str, SourceAdapter] = {}
        for adapter in adapters or default_source_adapters():
            self.register(adapter)

    def register(self, adapter: SourceAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def names(self) -> list[str]:
        return sorted(self._adapters)

    def resolve_match(
        self,
        source: SourceInput,
    ) -> tuple[SourceAdapter | None, SourceMatch | None]:
        source = source.normalized()
        if source.source_type != SourceType.AUTO.value:
            adapter = self._adapters.get(source.source_type)
            return adapter, adapter.detect(source) if adapter else None
        for adapter in self._adapters.values():
            match = adapter.detect(source)
            if match is not None:
                return adapter, match
        return None, None

    def detect(self, source: SourceInput) -> SourceMatch | None:
        return self.resolve_match(source)[1]

    def resolve(self, source: SourceInput) -> SourceAdapter | None:
        return self.resolve_match(source)[0]


DEFAULT_SOURCE_REGISTRY = SourceRegistry()
