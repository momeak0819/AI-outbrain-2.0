"""Runtime path helpers for source and packaged builds."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def runtime_dir() -> Path:
    return app_root() / "runtime"


def portable_ffmpeg_path() -> Path:
    return runtime_dir() / "ffmpeg" / "bin" / "ffmpeg.exe"


def resolve_ffmpeg_path() -> str:
    portable = portable_ffmpeg_path()
    if portable.exists():
        return str(portable)
    return shutil.which("ffmpeg") or "ffmpeg"


def portable_model_path(model_name: str) -> Path:
    return runtime_dir() / "models" / model_name


def default_outputs_dir() -> Path:
    return app_root() / "outputs"


def default_audio_dir(output_dir: str | Path | None = None) -> Path:
    base = Path(output_dir) if output_dir else default_outputs_dir()
    return base / "audio"
