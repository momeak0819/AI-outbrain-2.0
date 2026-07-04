"""Tencent Cloud ASR engine using recording file recognition tasks."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .base import TranscriptionResult
from .cloud_stub import CloudASREngine


TENCENT_ASR_ENDPOINT = "https://asr.tencentcloudapi.com"
TENCENT_ASR_HOST = "asr.tencentcloudapi.com"
TENCENT_ASR_SERVICE = "asr"
TENCENT_ASR_VERSION = "2019-06-14"


class TencentASREngine(CloudASREngine):
    name = "tencent_asr"
    display_name = "腾讯云 ASR"
    required_config_keys = ("secret_id", "secret_key")
    env_mapping = {
        "secret_id": "TENCENT_ASR_SECRET_ID",
        "secret_key": "TENCENT_ASR_SECRET_KEY",
    }

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        readiness_failure = self._readiness_failure()
        if readiness_failure:
            return readiness_failure

        path_or_error = self._validate_audio_path(audio_path)
        if isinstance(path_or_error, TranscriptionResult):
            return path_or_error
        path = path_or_error

        try:
            audio_bytes = path.read_bytes()
        except OSError as exc:
            return TranscriptionResult(False, "", self.name, self._safe_error("读取音频文件失败", exc))

        create_payload = {
            "EngineModelType": self._config_value("engine_model_type", "16k_zh"),
            "ChannelNum": int(self._config_value("channel_num", "1")),
            "ResTextFormat": int(self._config_value("res_text_format", "0")),
            "SourceType": 1,
            "Data": base64.b64encode(audio_bytes).decode("utf-8"),
            "DataLen": len(audio_bytes),
        }

        create = self._post_action("CreateRecTask", create_payload)
        if isinstance(create, TranscriptionResult):
            return create
        response = create.get("Response") or {}
        if response.get("Error"):
            return TranscriptionResult(False, "", self.name, self._safe_error("腾讯云 ASR 创建任务失败", response["Error"]))
        task_id = ((response.get("Data") or {}).get("TaskId") or response.get("TaskId"))
        if not task_id:
            return TranscriptionResult(False, "", self.name, self._safe_error("腾讯云 ASR 创建任务响应缺少 TaskId", response))

        attempts = int(self._config_value("poll_attempts", "20"))
        interval = float(self._config_value("poll_interval", "2"))
        for _ in range(max(1, attempts)):
            status_payload = {"TaskId": int(task_id)}
            status = self._post_action("DescribeTaskStatus", status_payload)
            if isinstance(status, TranscriptionResult):
                return status
            status_response = status.get("Response") or {}
            if status_response.get("Error"):
                return TranscriptionResult(False, "", self.name, self._safe_error("腾讯云 ASR 查询任务失败", status_response["Error"]))

            data = status_response.get("Data") or status_response
            status_text = str(data.get("StatusStr") or data.get("Status") or "").lower()
            result_text = str(data.get("Result") or data.get("ResultDetail") or "").strip()
            if status_text in {"success", "completed", "complete", "2"} or result_text:
                if result_text:
                    return TranscriptionResult(True, result_text, self.name)
                return TranscriptionResult(False, "", self.name, "腾讯云 ASR 任务完成但没有返回转写文本")
            if status_text in {"failed", "failure", "error", "3"}:
                return TranscriptionResult(False, "", self.name, self._safe_error("腾讯云 ASR 任务失败", data))
            if interval > 0:
                time.sleep(interval)

        return TranscriptionResult(False, "", self.name, "腾讯云 ASR 任务查询超时")

    def _post_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any] | TranscriptionResult:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        timestamp = int(time.time())
        region = self._config_value("region", "ap-guangzhou")
        headers = self._signed_headers(action, body, timestamp, region)
        try:
            response = requests.post(
                TENCENT_ASR_ENDPOINT,
                headers=headers,
                data=body.encode("utf-8"),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            return TranscriptionResult(False, "", self.name, self._safe_error("腾讯云 ASR 请求失败", exc))
        if response.status_code >= 400:
            return TranscriptionResult(
                False,
                "",
                self.name,
                self._safe_error(f"腾讯云 ASR 返回 HTTP {response.status_code}", response.text),
            )
        try:
            return response.json()
        except ValueError:
            return TranscriptionResult(False, "", self.name, self._safe_error("腾讯云 ASR 响应不是 JSON", response.text))

    def _signed_headers(self, action: str, body: str, timestamp: int, region: str) -> dict[str, str]:
        secret_id = self._config_value("secret_id")
        secret_key = self._config_value("secret_key")
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")

        http_request_method = "POST"
        canonical_uri = "/"
        canonical_querystring = ""
        canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{TENCENT_ASR_HOST}\n"
        signed_headers = "content-type;host"
        hashed_request_payload = hashlib.sha256(body.encode("utf-8")).hexdigest()
        canonical_request = "\n".join(
            [
                http_request_method,
                canonical_uri,
                canonical_querystring,
                canonical_headers,
                signed_headers,
                hashed_request_payload,
            ]
        )

        algorithm = "TC3-HMAC-SHA256"
        credential_scope = f"{date}/{TENCENT_ASR_SERVICE}/tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = "\n".join([algorithm, str(timestamp), credential_scope, hashed_canonical_request])

        secret_date = hmac.new(("TC3" + secret_key).encode("utf-8"), date.encode("utf-8"), hashlib.sha256).digest()
        secret_service = hmac.new(secret_date, TENCENT_ASR_SERVICE.encode("utf-8"), hashlib.sha256).digest()
        secret_signing = hmac.new(secret_service, b"tc3_request", hashlib.sha256).digest()
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            f"{algorithm} Credential={secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        return {
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": TENCENT_ASR_HOST,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": TENCENT_ASR_VERSION,
            "X-TC-Region": region,
        }
