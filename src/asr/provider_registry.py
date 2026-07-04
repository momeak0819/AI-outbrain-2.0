"""Registry of ASR providers exposed by the project."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ASRProvider:
    engine_id: str
    display_name: str
    provider: str
    deployment_type: str
    status: str
    requires_api_key: bool
    supported_extensions: tuple[str, ...]
    notes: str = ""


SUPPORTED_CLOUD_AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg")


ASR_PROVIDERS: tuple[ASRProvider, ...] = (
    ASRProvider(
        engine_id="mock",
        display_name="Mock ASR",
        provider="project",
        deployment_type="test",
        status="implemented",
        requires_api_key=False,
        supported_extensions=(".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".mp4"),
        notes="测试用模拟引擎，不进行真实转写。",
    ),
    ASRProvider(
        engine_id="faster_whisper",
        display_name="faster-whisper",
        provider="local",
        deployment_type="local",
        status="implemented",
        requires_api_key=False,
        supported_extensions=SUPPORTED_CLOUD_AUDIO_EXTENSIONS,
        notes="本地离线 ASR 兜底。",
    ),
    ASRProvider(
        engine_id="mimo",
        display_name="小米 MiMo ASR",
        provider="xiaomi",
        deployment_type="cloud",
        status="implemented",
        requires_api_key=True,
        supported_extensions=(".mp3", ".wav"),
        notes="当前已实现的云端 ASR。",
    ),
    ASRProvider(
        engine_id="custom_api",
        display_name="Custom API ASR",
        provider="custom",
        deployment_type="cloud",
        status="planned",
        requires_api_key=True,
        supported_extensions=(".mp3", ".wav"),
        notes="自定义 ASR API 占位。",
    ),
    ASRProvider(
        engine_id="aliyun_qwen_asr",
        display_name="阿里云百炼 Qwen-ASR",
        provider="aliyun",
        deployment_type="cloud",
        status="implemented",
        requires_api_key=True,
        supported_extensions=SUPPORTED_CLOUD_AUDIO_EXTENSIONS,
        notes="P0 云 ASR；使用 OpenAI-compatible chat/completions 接口上传本地音频。",
    ),
    ASRProvider(
        engine_id="tencent_asr",
        display_name="腾讯云 ASR",
        provider="tencent_cloud",
        deployment_type="cloud",
        status="implemented",
        requires_api_key=True,
        supported_extensions=SUPPORTED_CLOUD_AUDIO_EXTENSIONS,
        notes="P0 云 ASR；使用录音文件识别任务 CreateRecTask/DescribeTaskStatus。",
    ),
    ASRProvider(
        engine_id="volcengine_asr",
        display_name="火山引擎豆包语音识别",
        provider="volcengine",
        deployment_type="cloud",
        status="implemented",
        requires_api_key=True,
        supported_extensions=SUPPORTED_CLOUD_AUDIO_EXTENSIONS,
        notes="P0 云 ASR；使用音频 URL 提交/查询任务，本地上传需后续媒体准备能力。",
    ),
)


def provider_ids() -> tuple[str, ...]:
    return tuple(provider.engine_id for provider in ASR_PROVIDERS)


def providers_as_dicts() -> list[dict[str, object]]:
    return [
        {
            "engine_id": provider.engine_id,
            "display_name": provider.display_name,
            "provider": provider.provider,
            "deployment_type": provider.deployment_type,
            "status": provider.status,
            "requires_api_key": provider.requires_api_key,
            "supported_extensions": list(provider.supported_extensions),
            "notes": provider.notes,
        }
        for provider in ASR_PROVIDERS
    ]
