"""Aliyun Bailian Qwen-ASR engine."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import requests

from .base import TranscriptionResult
from .cloud_stub import CloudASREngine


DEFAULT_ALIYUN_QWEN_ASR_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_ALIYUN_QWEN_ASR_MODEL = "qwen-audio-asr"


class AliyunQwenASREngine(CloudASREngine):
    name = "aliyun_qwen_asr"
    display_name = "阿里云百炼 Qwen-ASR"
    required_config_keys = ("api_key",)
    env_mapping = {"api_key": "ALIYUN_QWEN_ASR_API_KEY"}

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        readiness_failure = self._readiness_failure()
        if readiness_failure:
            return readiness_failure

        path_or_error = self._validate_audio_path(audio_path)
        if isinstance(path_or_error, TranscriptionResult):
            return path_or_error
        path = path_or_error

        try:
            audio_base64 = base64.b64encode(path.read_bytes()).decode("utf-8")
        except OSError as exc:
            return TranscriptionResult(False, "", self.name, self._safe_error("读取音频文件失败", exc))

        endpoint = self._endpoint()
        payload = self._build_payload(path, audio_base64)
        headers = {
            "Authorization": f"Bearer {self._config_value('api_key')}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            return TranscriptionResult(False, "", self.name, self._safe_error("阿里云 Qwen-ASR 请求失败", exc))

        if response.status_code >= 400:
            return TranscriptionResult(
                False,
                "",
                self.name,
                self._safe_error(f"阿里云 Qwen-ASR 返回 HTTP {response.status_code}", response.text),
            )

        try:
            data = response.json()
        except ValueError:
            return TranscriptionResult(False, "", self.name, self._safe_error("阿里云 Qwen-ASR 响应不是 JSON", response.text))

        text = self._extract_text(data)
        if not text:
            return TranscriptionResult(False, "", self.name, self._safe_error("阿里云 Qwen-ASR 响应中没有转写文本", data))
        return TranscriptionResult(True, text, self.name, segments=self._extract_segments(data))

    def _endpoint(self) -> str:
        base_url = self._config_value("base_url", DEFAULT_ALIYUN_QWEN_ASR_BASE_URL).rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"

    def _build_payload(self, path: Path, audio_base64: str) -> dict[str, Any]:
        model = self._config_value("model", DEFAULT_ALIYUN_QWEN_ASR_MODEL)
        return {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": audio_base64,
                                "format": self._audio_format(path),
                            },
                        },
                    ],
                }
            ],
        }

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if choices:
            message = (choices[0] or {}).get("message") or {}
            content = message.get("content", "")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict):
                        value = item.get("text") or item.get("content")
                        if value:
                            parts.append(str(value))
                return "\n".join(parts).strip()
        for key in ("text", "transcript", "result"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _extract_segments(data: dict[str, Any]) -> list[Any] | None:
        for key in ("segments", "sentence_info", "sentences"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        return None
