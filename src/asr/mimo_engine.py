"""MiMo API ASR engine."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

import requests

from .base import (
    BaseASREngine,
    EngineCapabilities,
    EngineReadiness,
    TranscriptionResult,
)

DEFAULT_MIMO_API_URL = "https://api.xiaomimimo.com/v1/chat/completions"


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def _ffprobe() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def _command_available(command: str) -> bool:
    try:
        result = subprocess.run(
            [command, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _ffprobe_duration(audio_path: str) -> float:
    """Get audio duration in seconds via ffprobe, or -1 on failure."""
    ffprobe = _ffprobe()
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                audio_path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return float(result.stdout.strip())
    except Exception:
        return -1.0


class MiMoEngine(BaseASREngine):
    name = "mimo"
    max_base64_bytes = 10 * 1024 * 1024          # 10 MB hard limit
    target_chunk_base64_bytes = 8 * 1024 * 1024   # split before getting close to the hard limit
    chunk_overlap_seconds = 1.0
    min_chunk_duration = 1.0                      # never go below 1 second per chunk
    max_chunk_retries = 1

    def __init__(self, config: Optional[dict[str, Any]] = None):
        self.config = config or {}
        self.api_key = os.getenv("MIMO_API_KEY") or self.config.get("api_key", "")
        self.api_url = self.config.get("api_url") or DEFAULT_MIMO_API_URL
        self.language = self.config.get("language", "zh")
        self.timeout = int(self.config.get("timeout", 120))

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            supported_extensions=frozenset({".mp3", ".wav"}),
            supported_media_types=frozenset({"audio"}),
            returns_segments=False,
        )

    def check_ready(self) -> EngineReadiness:
        if not self.api_key:
            return EngineReadiness(
                ready=False,
                code="config_missing",
                message="未配置 MIMO_API_KEY",
            )
        return EngineReadiness(ready=True)

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        if not self.api_key:
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error="未配置 MIMO_API_KEY",
            )

        path = Path(audio_path)
        if not audio_path or not path.exists():
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error=f"音频文件不存在: {audio_path or 'N/A'}",
            )

        mime_type = self._mime_type(path)
        if not mime_type:
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error="MiMo ASR 仅支持 wav 或 mp3 音频",
            )

        try:
            audio_base64 = base64.b64encode(path.read_bytes()).decode("utf-8")
        except Exception as exc:
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error=f"读取音频文件失败: {exc}",
            )

        encoded_size = len(audio_base64.encode("utf-8"))
        if encoded_size > self.target_chunk_base64_bytes:
            return self._transcribe_chunked(path, mime_type, encoded_size)

        return self._call_api(mime_type, audio_base64)

    def _transcribe_chunked(
        self,
        path: Path,
        mime_type: str,
        encoded_size: int | None = None,
    ) -> TranscriptionResult:
        """Split oversized audio into chunks, transcribe separately, merge."""
        ffmpeg = _ffmpeg()
        ffprobe = _ffprobe()
        if not _command_available(ffmpeg):
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error="MiMo 分片需要 ffmpeg，但当前未检测到 ffmpeg",
            )
        if not _command_available(ffprobe):
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error="MiMo 分片需要 ffprobe，但当前未检测到 ffprobe",
            )

        duration = _ffprobe_duration(str(path))
        if duration <= 0:
            return TranscriptionResult(
                success=False, text="", engine=self.name,
                error="无法获取音频时长，无法分片",
            )

        total_encoded_bytes = encoded_size or int(path.stat().st_size * 4 / 3)
        # Estimate how many seconds fit in one safe base64 payload.
        bytes_per_second = total_encoded_bytes / duration if duration > 0 else total_encoded_bytes
        chunk_duration = max(
            self.min_chunk_duration,
            (self.target_chunk_base64_bytes / bytes_per_second) if bytes_per_second > 0 else 30.0,
        )
        chunk_count = max(1, int(duration / chunk_duration) + (1 if duration % chunk_duration > 0 else 0))

        if chunk_count == 1:
            # Already a single chunk, should not happen but fall back
            audio_base64 = base64.b64encode(path.read_bytes()).decode("utf-8")
            return self._call_api(mime_type, audio_base64)

        tmp_dir = Path(tempfile.mkdtemp(prefix="mimo_chunks_"))
        texts: list[str] = []
        warnings: list[str] = []
        success_count = 0

        try:
            for i in range(chunk_count):
                base_start = i * chunk_duration
                base_end = min(duration, (i + 1) * chunk_duration)
                start_sec = max(0.0, base_start - (self.chunk_overlap_seconds if i > 0 else 0.0))
                end_sec = min(duration, base_end + (self.chunk_overlap_seconds if i < chunk_count - 1 else 0.0))
                cut_duration = max(self.min_chunk_duration, end_sec - start_sec)
                chunk_path = tmp_dir / f"chunk_{i:04d}{path.suffix}"

                cmd = [
                    ffmpeg, "-y",
                    "-ss", str(start_sec),
                    "-i", str(path),
                    "-t", str(cut_duration),
                    "-c", "copy" if path.suffix.lower() == ".mp3" else "pcm_s16le",
                    str(chunk_path),
                ]
                try:
                    subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True)
                except subprocess.CalledProcessError as exc:
                    warnings.append(f"分片 {i + 1} 切割失败: {exc.stderr[:200]}")
                    continue

                if not chunk_path.exists() or chunk_path.stat().st_size == 0:
                    warnings.append(f"分片 {i + 1} 为空")
                    continue

                try:
                    chunk_b64 = base64.b64encode(chunk_path.read_bytes()).decode("utf-8")
                except Exception as exc:
                    warnings.append(f"分片 {i + 1} 读取失败: {exc}")
                    continue

                result = self._call_api_with_retry(mime_type, chunk_b64)
                if result.success:
                    cleaned_text = self._remove_consecutive_repeated_units(result.text)
                    if cleaned_text != result.text:
                        warnings.append(f"分片 {i + 1} 检测到重复文本，已做保守去重")
                    texts.append(cleaned_text)
                    success_count += 1
                else:
                    warnings.append(f"分片 {i + 1} 转写失败: {result.error}")

            if success_count == 0:
                error_detail = "；".join(warnings)
                return TranscriptionResult(
                    success=False, text="", engine=self.name,
                    error=f"所有 {chunk_count} 个分片均转写失败" + (f": {error_detail}" if error_detail else ""),
                )

            merged = self._merge_chunk_texts(texts)
            error = None
            if success_count != chunk_count:
                error = f"{success_count}/{chunk_count} 分片成功"
            if warnings:
                warning_text = "；".join(warnings)
                error = f"{error}；{warning_text}" if error else warning_text
            return TranscriptionResult(
                success=True, text=merged, engine=self.name,
                error=error,
            )
        finally:
            # Clean up temp chunks
            try:
                for f in tmp_dir.iterdir():
                    f.unlink(missing_ok=True)
                tmp_dir.rmdir()
            except Exception:
                pass

    def _call_api_with_retry(self, mime_type: str, audio_base64: str) -> TranscriptionResult:
        result = self._call_api(mime_type, audio_base64)
        if result.success and not self._looks_repetitive(result.text):
            return result

        last_result = result
        for _ in range(self.max_chunk_retries):
            retry_result = self._call_api(mime_type, audio_base64)
            last_result = retry_result
            if retry_result.success and not self._looks_repetitive(retry_result.text):
                return retry_result
        return last_result

    @staticmethod
    def _merge_chunk_texts(texts: list[str]) -> str:
        merged = ""
        for text in texts:
            cleaned = text.strip()
            if not cleaned:
                continue
            if not merged:
                merged = cleaned
                continue

            trimmed = MiMoEngine._trim_prefix_overlap(merged, cleaned)
            if trimmed:
                merged = f"{merged}\n{trimmed.strip()}"
        return merged

    @staticmethod
    def _trim_prefix_overlap(previous: str, current: str) -> str:
        previous_compact = MiMoEngine._compact_text(previous)
        current_compact = MiMoEngine._compact_text(current)
        max_len = min(len(previous_compact), len(current_compact), 80)

        best = 0
        for length in range(max_len, 9, -1):
            if previous_compact[-length:] == current_compact[:length]:
                best = length
                break

        if best == 0:
            return current

        consumed = 0
        cut_index = 0
        for index, char in enumerate(current):
            if char.isspace():
                continue
            consumed += 1
            if consumed >= best:
                cut_index = index + 1
                break
        return current[cut_index:]

    @staticmethod
    def _remove_consecutive_repeated_units(text: str) -> str:
        units = MiMoEngine._split_text_units(text)
        if len(units) < 2:
            return text.strip()

        deduped: list[str] = []
        previous_compact = ""
        for unit in units:
            compact = MiMoEngine._compact_text(unit)
            if compact and compact == previous_compact and len(compact) >= 6:
                continue
            deduped.append(unit)
            previous_compact = compact
        return "".join(deduped).strip()

    @staticmethod
    def _looks_repetitive(text: str) -> bool:
        units = [MiMoEngine._compact_text(unit) for unit in MiMoEngine._split_text_units(text)]
        units = [unit for unit in units if len(unit) >= 6]
        if len(units) >= 3:
            for index in range(len(units) - 2):
                if units[index] == units[index + 1] == units[index + 2]:
                    return True

        compact = MiMoEngine._compact_text(text)
        if len(compact) < 80:
            return False
        window = max(20, min(80, len(compact) // 3))
        for start in range(0, len(compact) - window * 2 + 1, max(1, window // 2)):
            piece = compact[start:start + window]
            if compact.count(piece) >= 3:
                return True
        return False

    @staticmethod
    def _split_text_units(text: str) -> list[str]:
        units: list[str] = []
        buffer: list[str] = []
        for char in text.strip():
            buffer.append(char)
            if char in "。！？!?；;\n":
                units.append("".join(buffer))
                buffer = []
        if buffer:
            units.append("".join(buffer))
        return units

    @staticmethod
    def _compact_text(text: str) -> str:
        return "".join(str(text).split())

    def _call_api(self, mime_type: str, audio_base64: str) -> TranscriptionResult:
        payload = self._build_payload(mime_type, audio_base64, guided=True)
        result = self._post_payload(payload)
        if result.success:
            cleaned_text = self._remove_consecutive_repeated_units(result.text)
            result.text = cleaned_text
            return result

        # Fall back to the official minimal request shape if extra generation
        # controls are rejected by the service.
        if "HTTP 400" in (result.error or ""):
            fallback = self._post_payload(self._build_payload(mime_type, audio_base64, guided=False))
            if fallback.success:
                fallback.text = self._remove_consecutive_repeated_units(fallback.text)
            return fallback

        return result

    def _build_payload(self, mime_type: str, audio_base64: str, guided: bool) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": f"data:{mime_type};base64,{audio_base64}",
                        },
                    },
                ],
            }
        ]

        payload: dict[str, Any] = {
            "model": "mimo-v2.5-asr",
            "messages": messages,
            "asr_options": {
                "language": self.language or "auto",
            },
        }
        if guided:
            payload["temperature"] = 0
        return payload

    def _post_payload(self, payload: dict[str, Any]) -> TranscriptionResult:
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout:
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error="MiMo ASR 请求超时",
            )
        except requests.RequestException as exc:
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error=f"MiMo ASR 网络请求失败: {exc}",
            )

        if response.status_code != 200:
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error=f"MiMo ASR 请求失败: HTTP {response.status_code} {response.text[:500]}",
            )

        try:
            data = response.json()
        except ValueError:
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error=f"MiMo ASR 响应不是 JSON: {response.text[:500]}",
            )

        text = self._extract_text(data)
        if not text:
            return TranscriptionResult(
                success=False,
                text="",
                engine=self.name,
                error=f"MiMo ASR 响应中没有文字稿: {str(data)[:500]}",
            )

        return TranscriptionResult(
            success=True,
            text=text,
            engine=self.name,
            error=None,
            segments=None,
        )

    @staticmethod
    def _mime_type(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".wav":
            return "audio/wav"
        if suffix == ".mp3":
            return "audio/mpeg"
        return ""

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        choices = data.get("choices", [])
        if not choices:
            return ""

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    value = item.get("text") or item.get("content")
                    if value:
                        parts.append(str(value))
            return "\n".join(parts).strip()

        return ""
