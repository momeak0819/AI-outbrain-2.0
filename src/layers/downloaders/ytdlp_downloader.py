"""Isolated yt-dlp downloader backend for Acquisition.

This module deliberately keeps yt-dlp behind a tiny interface so tests can
inject fake backends and the rest of the five-layer pipeline never imports or
configures yt-dlp directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import mimetypes
from pathlib import Path
from typing import Any

from runtime_paths import runtime_dir

from ..acquisition_helpers import safe_metadata_copy


@dataclass(frozen=True)
class YtdlpMedia:
    """A downloaded media artifact plus safe metadata returned by a backend."""

    path: str
    metadata: dict[str, Any] = field(default_factory=dict)
    mime: str = ""


class YtdlpBackendError(Exception):
    """Base class for expected yt-dlp backend failures."""


class YtdlpUnavailableError(YtdlpBackendError):
    """yt-dlp is not importable or otherwise unavailable."""


class YtdlpMetadataError(YtdlpBackendError):
    """Metadata extraction failed."""


class YtdlpDownloadError(YtdlpBackendError):
    """Media download failed."""


class YtdlpAuthRequiredError(YtdlpDownloadError):
    """The platform requires login/cookies for this media."""


class YtdlpUnsupportedPlatformError(YtdlpBackendError):
    """The backend cannot handle this platform/source type."""


class YtdlpDownloader:
    """Default yt-dlp backend hidden behind the Acquisition interface."""

    def is_available(self) -> bool:
        try:
            importlib.import_module("yt_dlp")
        except Exception:
            return False
        return True

    def validate_browser_cookies(self, browser: str) -> bool:
        """Best-effort local check that yt-dlp accepts a browser cookie source.

        This deliberately does not read, export, or display cookie values. It
        only builds a YoutubeDL instance with the cookies-from-browser option so
        the Web Console can distinguish "配置已记录" from "yt-dlp/浏览器配置不可用".
        """

        browser_name = str(browser or "").strip().lower()
        if not browser_name:
            return False
        yt_dlp = self._load_yt_dlp()
        options = self._ydl_options(
            download=False,
            source_metadata={"cookies_from_browser": browser_name},
        )
        try:
            with yt_dlp.YoutubeDL(options):
                return True
        except Exception as exc:
            raise YtdlpAuthRequiredError(_safe_error_summary(exc)) from exc

    def extract_metadata(
        self,
        url: str,
        *,
        source_type: str,
        source_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        yt_dlp = self._load_yt_dlp()
        options = self._ydl_options(
            download=False,
            source_metadata=source_metadata,
        )
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:
            self._raise_phase_error(exc, phase="metadata")
        return safe_metadata_copy(info or {})

    def download(
        self,
        url: str,
        *,
        source_type: str,
        metadata: dict[str, Any],
        output_dir: str | Path | None = None,
    ) -> YtdlpMedia:
        yt_dlp = self._load_yt_dlp()
        output_root = self._controlled_output_dir(output_dir)
        options = self._ydl_options(
            download=True,
            source_metadata=metadata,
            output_dir=output_root,
        )
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
        except Exception as exc:
            self._raise_phase_error(exc, phase="download")
        path = self._extract_download_path(info or {}, output_root)
        if not path:
            raise YtdlpDownloadError("yt-dlp did not return a downloaded file path")
        mime = str((info or {}).get("mime_type") or mimetypes.guess_type(path)[0] or "")
        return YtdlpMedia(
            path=path,
            metadata=safe_metadata_copy(info or {}),
            mime=mime,
        )

    def _load_yt_dlp(self):
        try:
            return importlib.import_module("yt_dlp")
        except Exception as exc:
            raise YtdlpUnavailableError("yt-dlp is not available") from exc

    def _ydl_options(
        self,
        *,
        download: bool,
        source_metadata: dict[str, Any],
        output_dir: Path | None = None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "restrictfilenames": True,
        }
        cookiefile = self._cookiefile(source_metadata)
        if cookiefile:
            options["cookiefile"] = cookiefile
        cookies_from_browser = self._cookies_from_browser(source_metadata)
        if cookies_from_browser:
            options["cookiesfrombrowser"] = (cookies_from_browser,)
        if download:
            if output_dir is None:
                output_dir = self._controlled_output_dir(None)
            options["outtmpl"] = str(output_dir / "%(extractor)s-%(id)s.%(ext)s")
            options["paths"] = {"home": str(output_dir)}
            options["format"] = "bv*+ba/best"
        return options

    def _cookiefile(self, metadata: dict[str, Any]) -> str:
        for key in ("cookies_file", "cookiefile"):
            value = metadata.get(key)
            if value:
                return str(value)
        return ""

    def _cookies_from_browser(self, metadata: dict[str, Any]) -> str:
        for key in ("cookies_from_browser", "cookiesfrombrowser", "browser_cookies"):
            value = metadata.get(key)
            if value:
                browser = str(value).strip().lower()
                if browser in {"chrome", "chromium", "edge", "firefox", "safari", "opera", "brave", "vivaldi"}:
                    return browser
        return ""

    def _controlled_output_dir(self, output_dir: str | Path | None) -> Path:
        root = Path(output_dir) if output_dir else runtime_dir() / "media"
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    def _extract_download_path(self, info: dict[str, Any], output_root: Path) -> str:
        candidates: list[Any] = []
        for item in info.get("requested_downloads") or []:
            if isinstance(item, dict):
                candidates.extend([item.get("filepath"), item.get("_filename")])
        candidates.extend([info.get("filepath"), info.get("_filename")])
        for item in info.get("requested_formats") or []:
            if isinstance(item, dict):
                candidates.extend([item.get("filepath"), item.get("_filename")])

        for candidate in candidates:
            if not candidate:
                continue
            path = Path(str(candidate))
            if not path.is_absolute():
                path = output_root / path
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if self._is_within(resolved, output_root):
                return str(resolved)
        return ""

    def _is_within(self, path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True

    def _raise_phase_error(self, exc: Exception, *, phase: str) -> None:
        summary = _safe_error_summary(exc)
        if _looks_like_auth_error(exc):
            raise YtdlpAuthRequiredError(summary) from exc
        if phase == "metadata":
            raise YtdlpMetadataError(summary) from exc
        raise YtdlpDownloadError(summary) from exc


_SENSITIVE_TEXT_MARKERS = (
    "authorization",
    "cookie",
    "credential",
    "header",
    "password",
    "secret",
    "token",
)

_AUTH_TEXT_MARKERS = (
    "login",
    "log in",
    "sign in",
    "cookie",
    "cookies",
    "authentication",
    "auth",
    "private",
)


def _safe_error_summary(exc: Exception) -> str:
    text = str(exc).strip()
    lowered = text.lower()
    if not text or any(marker in lowered for marker in _SENSITIVE_TEXT_MARKERS):
        return exc.__class__.__name__
    return text


def _looks_like_auth_error(exc: Exception) -> bool:
    text = f"{exc.__class__.__name__} {exc}".lower()
    return any(marker in text for marker in _AUTH_TEXT_MARKERS)
