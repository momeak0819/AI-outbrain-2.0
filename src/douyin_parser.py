"""
抖音视频解析器 - 无需Cookie
直接从移动端分享页面提取视频信息
"""

import re
import json
import time
import requests
from typing import Callable, Optional, Dict


class DouyinParser:
    """抖音视频解析器"""
    
    def __init__(self, log: Optional[Callable[[str], None]] = None):
        self.log = log
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U Build/R16NW) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36',
            'Referer': 'https://www.douyin.com/?is_from_mobile_home=1&recommend=1'
        }
        
        # 视频下载时使用的headers
        self.download_headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U Build/R16NW) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36',
            'Referer': 'https://www.iesdouyin.com/',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        }
    
    def extract_video_id(self, url: str) -> Optional[str]:
        """从抖音分享链接中提取视频ID"""
        # 先从文本中提取URL
        url = self._extract_url_from_text(url)
        
        short_link_pattern = r'https?://v\.douyin\.com/[a-zA-Z0-9_-]+/?'
        long_link_pattern = r'https?://www\.douyin\.com/video/(\d+)'
        ies_link_pattern = r'https?://www\.iesdouyin\.com/share/video/(\d+)'
        
        # 匹配短链接
        short_match = re.search(short_link_pattern, url)
        if short_match:
            short_url = short_match.group(0)
            try:
                response = self._request_get(short_url, headers=self.headers, timeout=10, allow_redirects=True)
                final_url = response.url
                match = re.search(r'/video/(\d+)', final_url)
                if match:
                    return match.group(1)
            except Exception as e:
                self._log(f"解析短链接失败: {e}")
                return None
        
        # 匹配长链接
        for pattern in [long_link_pattern, ies_link_pattern]:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_url_from_text(self, text: str) -> str:
        """从文本中提取URL"""
        # 匹配常见URL模式
        url_pattern = r'https?://[^\s<>"\']+'
        match = re.search(url_pattern, text)
        if match:
            return match.group(0)
        return text
    
    def parse(self, url: str) -> Optional[Dict]:
        """解析抖音链接，返回视频信息"""
        try:
            video_id = self.extract_video_id(url)
            if not video_id:
                self._log("无法从链接中提取视频ID")
                return None
            
            mobile_url = f"https://www.iesdouyin.com/share/video/{video_id}/"
            response = self._request_get(mobile_url, headers=self.headers, timeout=15)
            
            if response.status_code != 200:
                self._log(f"请求失败: HTTP {response.status_code}")
                return None
            
            html = response.text
            pattern = r'window\._ROUTER_DATA\s*=\s*(\{.*?\});?\s*</script>'
            match = re.search(pattern, html, re.DOTALL)
            
            if not match:
                self._log("未找到 _ROUTER_DATA")
                return None
            
            data_str = match.group(1)
            data = json.loads(data_str)
            video_info = self._extract_video_info(data)
            
            if video_info:
                video_info['video_id'] = video_id
                video_info['source_url'] = url
            
            return video_info
            
        except Exception as e:
            self._log(f"解析失败: {e}")
            return None
    
    def _extract_video_info(self, data: Dict) -> Optional[Dict]:
        """从_Router_DATA中提取视频信息"""
        try:
            if 'loaderData' in data:
                loader_data = data['loaderData']
                
                for key in loader_data.keys():
                    if not isinstance(loader_data[key], dict):
                        continue
                    
                    page_data = loader_data[key]
                    
                    if 'videoInfoRes' in page_data:
                        video_info_res = page_data['videoInfoRes']
                        item_list = video_info_res.get('item_list', [])
                        
                        if item_list:
                            return self._parse_video_item(item_list[0])
            
            return None
            
        except Exception as e:
            self._log(f"提取视频信息失败: {e}")
            return None

    def _log(self, message: str) -> None:
        if self.log:
            self.log(message)

    def _request_get(self, url: str, **kwargs) -> requests.Response:
        """GET with a small retry budget for transient Douyin/SSL failures."""
        last_error = None
        for attempt in range(3):
            try:
                return requests.get(url, **kwargs)
            except requests.RequestException as e:
                last_error = e
                if attempt < 2:
                    time.sleep(1 + attempt)

        raise last_error
    
    def _parse_video_item(self, item: Dict) -> Dict:
        """解析单个视频项"""
        desc = item.get('desc', '无标题')
        
        author = item.get('author', {})
        author_name = author.get('nickname', '未知')
        author_id = author.get('short_id', '')
        
        statistics = item.get('statistics', {})
        digg_count = statistics.get('digg_count', 0)
        comment_count = statistics.get('comment_count', 0)
        collect_count = statistics.get('collect_count', 0)
        share_count = statistics.get('share_count', 0)
        play_count = statistics.get('play_count', 0)
        
        video = item.get('video', {})
        play_addr = video.get('play_addr', {})
        
        # 获取视频URL
        video_url = ''
        url_list = play_addr.get('url_list', [])
        
        if url_list:
            video_url = url_list[0]
            # 尝试使用无水印版本
            if 'playwm' in video_url:
                video_url = video_url.replace('playwm', 'play')
        
        # 如果没有获取到视频URL，尝试从bit_rate获取
        if not video_url:
            bit_rate = video.get('bit_rate', [])
            for br in bit_rate:
                br_play_addr = br.get('play_addr', {})
                br_url_list = br_play_addr.get('url_list', [])
                if br_url_list:
                    video_url = br_url_list[0]
                    if 'playwm' in video_url:
                        video_url = video_url.replace('playwm', 'play')
                    break
        
        cover = video.get('cover', {})
        cover_urls = cover.get('url_list', [])
        cover_url = cover_urls[0] if cover_urls else ''
        
        music = item.get('music', {})
        music_title = music.get('title', '')
        music_author = music.get('author', '')
        
        height = video.get('height', 0)
        width = video.get('width', 0)
        duration = video.get('duration', 0)
        
        return {
            'title': desc,
            'author_name': author_name,
            'author_id': author_id,
            'video_url': video_url,
            'cover_url': cover_url,
            'music_title': music_title,
            'music_author': music_author,
            'statistics': {
                '点赞': self._format_count(digg_count),
                '评论': self._format_count(comment_count),
                '收藏': self._format_count(collect_count),
                '转发': self._format_count(share_count),
                '播放': self._format_count(play_count),
            },
            'size': f"{height}x{width}",
            'duration': duration,
            'duration_str': self._format_duration(duration),
            'download_headers': self.download_headers
        }
    
    @staticmethod
    def _format_count(count: int) -> str:
        """格式化数字"""
        if count >= 10000:
            return f"{count/10000:.1f}万"
        return str(count)
    
    @staticmethod
    def _format_duration(duration_ms: int) -> str:
        """格式化时长"""
        seconds = duration_ms // 1000
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        return f"{minutes:02d}:{remaining_seconds:02d}"


def test_parser():
    """测试解析器"""
    parser = DouyinParser()
    
    # 测试包含额外文字的链接
    test_url = "4.66 J@v.sR HIi:/ :0pm 05/27 无尽入局的门重新开啦 # 无尽入局 # 致命游戏 # 阮澜烛凌久时 # 欢迎来到门的世界  https://v.douyin.com/C4v1iGt42ck/ 复制此链接，打开Dou音搜索，直接观看视频！"
    
    print(f"正在解析: {test_url[:50]}...")
    print("=" * 60)
    
    result = parser.parse(test_url)
    
    if result:
        print("✅ 解析成功!")
        print(f"\n标题: {result['title']}")
        print(f"作者: {result['author_name']}")
        print(f"时长: {result['duration_str']}")
        print(f"视频URL: {result['video_url']}")
    else:
        print("❌ 解析失败")


if __name__ == '__main__':
    test_parser()
