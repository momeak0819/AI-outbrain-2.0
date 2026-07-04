"""Transcript export helpers for douyin-to-text."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class TranscriptExporter:
    """Export Douyin transcripts as UTF-8 txt or Markdown files."""

    illegal_filename_chars = '\\/:*?"<>|'
    default_basename = "douyin_transcript"
    max_basename_length = 80

    def __init__(self, default_output_dir: Optional[str] = None):
        project_root = Path(__file__).resolve().parents[1]
        self.default_output_dir = Path(default_output_dir) if default_output_dir else project_root / "outputs"

    def export_txt(
        self,
        metadata: dict[str, Any],
        transcript: str,
        asr_engine: str,
        output_dir: Optional[str] = None,
    ) -> str:
        """Export transcript as a UTF-8 text file and return the file path."""
        created_at = self._now()
        content = self._build_txt(metadata, transcript, asr_engine, created_at)
        return str(self._write_file(metadata, content, ".txt", output_dir))

    def export_md(
        self,
        metadata: dict[str, Any],
        transcript: str,
        asr_engine: str,
        output_dir: Optional[str] = None,
    ) -> str:
        """Export transcript as a UTF-8 Markdown file and return the file path."""
        created_at = self._now()
        content = self._build_md(metadata, transcript, asr_engine, created_at)
        return str(self._write_file(metadata, content, ".md", output_dir))

    def _build_txt(
        self,
        metadata: dict[str, Any],
        transcript: str,
        asr_engine: str,
        created_at: str,
    ) -> str:
        return "\n".join(
            [
                f"视频标题：{self._field(metadata, 'title')}",
                f"作者：{self._field(metadata, 'author')}",
                f"原始链接：{self._field(metadata, 'original_url')}",
                f"视频时长：{self._field(metadata, 'duration')}",
                f"ASR 引擎：{asr_engine or 'N/A'}",
                f"创建时间：{created_at}",
                "-" * 40,
                transcript or "",
                "",
            ]
        )

    def _build_md(
        self,
        metadata: dict[str, Any],
        transcript: str,
        asr_engine: str,
        created_at: str,
    ) -> str:
        title = self._field(metadata, "title")
        return "\n".join(
            [
                f"# {title}",
                "",
                "## 基本信息",
                f"- 作者：{self._field(metadata, 'author')}",
                f"- 原始链接：{self._field(metadata, 'original_url')}",
                f"- 视频时长：{self._field(metadata, 'duration')}",
                f"- 封面：{self._field(metadata, 'cover_url')}",
                f"- ASR 引擎：{asr_engine or 'N/A'}",
                f"- 创建时间：{created_at}",
                "",
                "## 文字稿",
                "",
                transcript or "",
                "",
            ]
        )

    def _write_file(
        self,
        metadata: dict[str, Any],
        content: str,
        suffix: str,
        output_dir: Optional[str],
    ) -> Path:
        target_dir = Path(output_dir) if output_dir else self.default_output_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        basename = self.sanitize_filename(str(metadata.get("title") or ""))
        filepath = self._unique_path(target_dir / f"{basename}{suffix}")
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def sanitize_filename(self, filename: str) -> str:
        """Sanitize a title for a Windows-safe filename."""
        cleaned = filename.strip()
        for char in self.illegal_filename_chars:
            cleaned = cleaned.replace(char, "_")
        cleaned = " ".join(cleaned.split())
        cleaned = cleaned.strip(" .")

        if not cleaned:
            cleaned = self.default_basename

        return cleaned[: self.max_basename_length].rstrip(" .") or self.default_basename

    @staticmethod
    def _unique_path(path: Path) -> Path:
        if not path.exists():
            return path

        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        index = 1

        while True:
            candidate = parent / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    @staticmethod
    def _field(metadata: dict[str, Any], key: str) -> str:
        value = metadata.get(key)
        if value is None or value == "":
            return "N/A"
        return str(value)

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def export_transcript(
    metadata: dict[str, Any],
    transcript: str,
    asr_engine: str,
    export_format: str,
    output_dir: str,
) -> list[str]:
    """Export transcript files without depending on pipeline orchestration."""
    exporter = TranscriptExporter()
    paths: list[str] = []

    if export_format in ("txt", "both"):
        paths.append(
            exporter.export_txt(metadata, transcript, asr_engine, output_dir)
        )

    if export_format in ("md", "both"):
        paths.append(
            exporter.export_md(metadata, transcript, asr_engine, output_dir)
        )

    return paths
