"""Safe cleanup for acquisition-owned artifacts consumed by Processing."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Callable

from runtime_paths import default_audio_dir

from .acquisition import AcquiredContent


LogCallback = Callable[[str], None] | None
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def cleanup_consumed_media(
    acquired: AcquiredContent,
    *,
    keep_audio: bool,
    audio_output_dir: str,
    output_dir: str,
    log: LogCallback = None,
) -> bool:
    """Delete one explicitly authorized acquisition temp file.

    Returns True only when the file was deleted. Every ambiguous, conflicting,
    or unsafe case is refused without mutating the filesystem.
    """
    if keep_audio or not acquired.cleanup_media or not acquired.media_path:
        return False

    matching = [
        record
        for record in acquired.result.artifact_records
        if record.path == acquired.media_path
    ]
    if len(matching) != 1:
        return False

    record = matching[0]
    if (
        record.ownership != "acquisition_temp"
        or record.cleanup_policy != "on_processing_complete"
    ):
        return False

    target = Path(acquired.media_path)
    controlled_root = (
        Path(audio_output_dir)
        if audio_output_dir
        else default_audio_dir(output_dir)
    )

    try:
        target_lstat = target.lstat()
        if stat.S_ISLNK(target_lstat.st_mode):
            return False
        if getattr(target_lstat, "st_file_attributes", 0) & _REPARSE_POINT:
            return False
        if not stat.S_ISREG(target_lstat.st_mode):
            return False

        resolved_root = controlled_root.resolve(strict=False)
        resolved_target = target.resolve(strict=True)
        if resolved_target == resolved_root:
            return False
        try:
            resolved_target.relative_to(resolved_root)
        except ValueError:
            return False

        target.unlink()
        return True
    except (FileNotFoundError, PermissionError, OSError) as exc:
        if log:
            log(f"warning: 无法清理 Processing 临时媒体文件：{exc}")
        return False
