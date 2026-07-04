"""Volcengine Doubao speech recognition engine.

This implementation follows Volcengine's recording-file style workflow:
submit a publicly reachable audio URL and then query the task result. Local
file upload/object-storage staging is intentionally not hidden here; when no
``audio_url`` is configured, the engine returns a clear, recoverable error.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import requests

from .base import TranscriptionResult
from .cloud_stub import CloudASREngine


DEFAULT_VOLCENGINE_SUBMIT_URL = "https://openspeech.bytedance.com/api/v1/auc/submit"
DEFAULT_VOLCENGINE_QUERY_URL = "https://openspeech.bytedance.com/api/v1/auc/query"


class VolcengineASREngine(CloudASREngine):
    name = "volcengine_asr"
    display_name = "火山引擎豆包语音识别"
    required_config_keys = ("app_id", "access_token")
    env_mapping = {
        "app_id": "VOLCENGINE_ASR_APP_ID",
        "access_token": "VOLCENGINE_ASR_ACCESS_TOKEN",
    }

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        readiness_failure = self._readiness_failure()
        if readiness_failure:
            return readiness_failure

        path_or_error = self._validate_audio_path(audio_path)
        if isinstance(path_or_error, TranscriptionResult):
            return path_or_error

        audio_url = self._config_value("audio_url") or self._config_value("file_url")
        if not audio_url:
            return TranscriptionResult(
                False,
                "",
                self.name,
                "火山引擎录音文件识别需要公网可访问的 audio_url；本阶段不在 ASR 引擎内上传本地文件。",
            )

        task_id = self._config_value("task_id") or str(uuid.uuid4())
        submit_payload = self._build_submit_payload(audio_url, task_id)
        submit = self._post_json(self._config_value("submit_url", DEFAULT_VOLCENGINE_SUBMIT_URL), submit_payload)
        if isinstance(submit, TranscriptionResult):
            return submit
        submit_code = str(submit.get("code", submit.get("status_code", "0")))
        if submit_code not in {"0", "20000000", "success", "Success"}:
            return TranscriptionResult(False, "", self.name, self._safe_error("火山引擎 ASR 提交任务失败", submit))

        attempts = int(self._config_value("poll_attempts", "20"))
        interval = float(self._config_value("poll_interval", "2"))
        query_url = self._config_value("query_url", DEFAULT_VOLCENGINE_QUERY_URL)
        for _ in range(max(1, attempts)):
            query_payload = self._build_query_payload(task_id)
            query = self._post_json(query_url, query_payload)
            if isinstance(query, TranscriptionResult):
                return query
            status = str(query.get("status") or query.get("status_text") or query.get("message") or "").lower()
            code = str(query.get("code", query.get("status_code", ""))).lower()
            text = self._extract_text(query)
            if text:
                return TranscriptionResult(True, text, self.name, segments=self._extract_segments(query))
            if status in {"failed", "failure", "error"} or code not in {"", "0", "20000000", "success"}:
                return TranscriptionResult(False, "", self.name, self._safe_error("火山引擎 ASR 任务失败", query))
            if interval > 0:
                time.sleep(interval)

        return TranscriptionResult(False, "", self.name, "火山引擎 ASR 任务查询超时")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer; {self._config_value('access_token')}",
            "Content-Type": "application/json",
        }

    def _build_submit_payload(self, audio_url: str, task_id: str) -> dict[str, Any]:
        return {
            "app": {
                "appid": self._config_value("app_id"),
                "token": self._config_value("access_token"),
                "cluster": self._config_value("cluster", "volcengine_streaming_common"),
            },
            "user": {"uid": self._config_value("uid", "ai-waibrain-local")},
            "audio": {
                "url": audio_url,
                "format": self._config_value("audio_format", "auto"),
            },
            "request": {
                "reqid": task_id,
                "workflow": self._config_value("workflow", "audio_in,resample,partition,vad,fe,decode"),
                "show_language": True,
                "show_utterances": True,
            },
        }

    def _build_query_payload(self, task_id: str) -> dict[str, Any]:
        return {
            "appid": self._config_value("app_id"),
            "token": self._config_value("access_token"),
            "cluster": self._config_value("cluster", "volcengine_streaming_common"),
            "task_id": task_id,
            "reqid": task_id,
        }

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any] | TranscriptionResult:
        try:
            response = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            return TranscriptionResult(False, "", self.name, self._safe_error("火山引擎 ASR 请求失败", exc))
        if response.status_code >= 400:
            return TranscriptionResult(
                False,
                "",
                self.name,
                self._safe_error(f"火山引擎 ASR 返回 HTTP {response.status_code}", response.text),
            )
        try:
            return response.json()
        except ValueError:
            return TranscriptionResult(False, "", self.name, self._safe_error("火山引擎 ASR 响应不是 JSON", response.text))

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        result = data.get("result") or data.get("data") or data
        if isinstance(result, dict):
            for key in ("text", "result", "transcript"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            utterances = result.get("utterances") or result.get("utterance")
            if isinstance(utterances, list):
                parts = [str(item.get("text", "")).strip() for item in utterances if isinstance(item, dict)]
                return "\n".join(part for part in parts if part).strip()
        for key in ("text", "result", "transcript"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _extract_segments(data: dict[str, Any]) -> list[Any] | None:
        result = data.get("result") or data.get("data") or data
        if isinstance(result, dict):
            for key in ("utterances", "utterance", "segments"):
                value = result.get(key)
                if isinstance(value, list):
                    return value
        return None
