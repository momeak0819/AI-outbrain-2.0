"""
音频提取模块
使用ffmpeg从视频URL提取音频
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional, Dict


class AudioExtractor:
    """音频提取器"""
    
    def __init__(
        self,
        sample_rate: int = 16000,
        ffmpeg_path: str = "ffmpeg",
        log: Optional[Callable[[str], None]] = None,
    ):
        """
        初始化音频提取器
        
        Args:
            sample_rate: 采样率，默认16000Hz（适合ASR）
            ffmpeg_path: ffmpeg 可执行文件路径
        """
        self.sample_rate = sample_rate
        self.ffmpeg_path = ffmpeg_path or "ffmpeg"
        self.log = log
    
    def check_ffmpeg(self) -> bool:
        """检查ffmpeg是否已安装"""
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if 'ffmpeg version' in result.stdout or 'ffmpeg version' in result.stderr:
                return True
            return False
        except (
            FileNotFoundError,
            PermissionError,
            subprocess.TimeoutExpired,
            OSError,
        ):
            return False
    
    def extract_audio(self, video_url: str, output_path: Optional[str] = None, headers: Optional[Dict] = None) -> Optional[str]:
        """
        从视频URL提取音频
        
        Args:
            video_url: 视频URL
            output_path: 输出音频文件路径，如果为None则使用临时文件
            headers: 请求头字典（用于下载视频时的认证）
        
        Returns:
            音频文件路径，失败返回None
        """
        if output_path is None:
            file_descriptor, output_path = tempfile.mkstemp(
                prefix="audio_",
                suffix=".wav",
            )
            os.close(file_descriptor)
            os.remove(output_path)

        output = Path(output_path)
        output_existed = output.exists()
        if self._is_link_or_reparse(output) or output.is_dir():
            self._log("Audio extraction refused: output path is a link or directory")
            return None

        if not self.check_ffmpeg():
            self._log(
                "未检测到 ffmpeg，请确认 portable 包内 "
                "runtime/ffmpeg/bin/ffmpeg.exe 存在，"
                "或安装 ffmpeg 并加入 PATH"
            )
            self._log("下载地址: https://ffmpeg.org/download.html")
            return None
        
        try:
            cmd = [
                self.ffmpeg_path,
                '-y',
            ]
            
            if headers:
                for key, value in headers.items():
                    cmd.extend(['-headers', f"{key}: {value}"])
            
            cmd.extend([
                '-i', video_url,
                '-vn',           # 禁用视频
                '-acodec', 'pcm_s16le',  # 音频编码器
                '-ar', str(self.sample_rate),  # 采样率
                '-ac', '1',      # 声道数（单声道）
                '-f', 'wav',     # 输出格式
                output_path
            ])
            
            input_type = (
                "remote_url"
                if "://" in video_url
                else "local_file"
            )
            self._log(
                "FFmpeg audio extraction started: "
                f"input_type={input_type}, output={output_path}, "
                f"headers={'yes' if headers else 'no'}"
            )
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            if (
                result.returncode == 0
                and self._is_nonempty_regular_file(output)
            ):
                file_size = output.stat().st_size
                self._log(f"Audio extraction succeeded: {output_path} ({file_size} bytes)")
                return output_path

            self._cleanup_failed_output(output, output_existed)
            self._log("Audio extraction failed")
            return None
                
        except subprocess.TimeoutExpired:
            self._cleanup_failed_output(output, output_existed)
            self._log("Audio extraction timed out (over 5 minutes)")
            return None
        except Exception:
            self._cleanup_failed_output(output, output_existed)
            self._log("Audio extraction error")
            return None

    @staticmethod
    def _is_link_or_reparse(path: Path) -> bool:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction and is_junction())

    @classmethod
    def _is_nonempty_regular_file(cls, path: Path) -> bool:
        try:
            return (
                not cls._is_link_or_reparse(path)
                and path.is_file()
                and path.stat().st_size > 0
            )
        except OSError:
            return False

    @classmethod
    def _cleanup_failed_output(cls, path: Path, existed_before: bool) -> None:
        if existed_before:
            return
        try:
            if (
                not cls._is_link_or_reparse(path)
                and path.is_file()
            ):
                path.unlink()
        except OSError:
            return
    
    def extract_audio_from_file(self, video_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        从本地视频文件提取音频
        
        Args:
            video_path: 视频文件路径
            output_path: 输出音频文件路径
        
        Returns:
            音频文件路径，失败返回None
        """
        if not os.path.exists(video_path):
            self._log(f"Video file not found: {video_path}")
            return None
        
        return self.extract_audio(video_path, output_path)

    def _log(self, message: str) -> None:
        if self.log:
            self.log(message)


def install_ffmpeg_guide():
    """打印ffmpeg安装指南"""
    guide = """
    ================================
    ffmpeg 安装指南
    ================================
    
    Windows:
    1. 访问 https://ffmpeg.org/download.html
    2. 下载 ffmpeg-release-essentials.zip
    3. 解压到任意目录（如 C:\\ffmpeg）
    4. 将 bin 目录添加到系统PATH
    5. 重启命令行工具使配置生效
    
    验证安装: ffmpeg -version
    
    ================================
    """
    print(guide)


if __name__ == '__main__':
    extractor = AudioExtractor()
    
    if extractor.check_ffmpeg():
        print("ffmpeg installed")
    else:
        print("ffmpeg not installed")
        install_ffmpeg_guide()
