"""Batch helpers for douyin-to-text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from pipeline import PipelineOptions, PipelineResult, run_pipeline


URL_PATTERN = re.compile(r"https?://[^\s<>'\"，。；,;]+")


@dataclass
class BatchItemResult:
    index: int
    url: str
    result: PipelineResult


BatchProgressCallback = Optional[Callable[[BatchItemResult], None]]
BatchLogCallback = Optional[Callable[[str], None]]
ShouldStopCallback = Optional[Callable[[], bool]]


def extract_urls(text: str) -> list[str]:
    """Extract unique http(s) URLs from pasted batch text, preserving order."""
    urls: list[str] = []
    seen: set[str] = set()

    for match in URL_PATTERN.findall(text or ""):
        url = match.rstrip(").]}")
        if url and url not in seen:
            seen.add(url)
            urls.append(url)

    return urls


def run_batch(
    urls: list[str],
    base_options: PipelineOptions,
    progress: BatchProgressCallback = None,
    log: BatchLogCallback = None,
    should_stop: ShouldStopCallback = None,
) -> list[BatchItemResult]:
    """Run URLs sequentially through the shared pipeline."""
    results: list[BatchItemResult] = []

    for index, url in enumerate(urls, start=1):
        if should_stop and should_stop():
            if log:
                log("已停止后续任务。")
            break

        if log:
            log(f"[{index}/{len(urls)}] 开始处理：{url}")

        options = PipelineOptions(
            url=url,
            engine=base_options.engine,
            export_format=base_options.export_format,
            output_dir=base_options.output_dir,
            audio_output_dir=base_options.audio_output_dir,
            audio_file="",
            skip_audio=base_options.skip_audio,
            keep_audio=base_options.keep_audio,
            mock_metadata=base_options.mock_metadata,
            to_simplified=base_options.to_simplified,
            config=base_options.config,
        )
        result = run_pipeline(options, log=log)
        item = BatchItemResult(index=index, url=url, result=result)
        results.append(item)

        if progress:
            progress(item)

        if log:
            status = "成功" if result.success else f"失败：{result.error}"
            log(f"[{index}/{len(urls)}] {status}")

    return results
