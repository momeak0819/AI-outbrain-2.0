"""Text normalization helpers."""

from __future__ import annotations


_FALLBACK_T2S_MAP = str.maketrans(
    {
        "裡": "里",
        "裏": "里",
        "後": "后",
        "這": "这",
        "個": "个",
        "們": "们",
        "來": "来",
        "會": "会",
        "為": "为",
        "與": "与",
        "於": "于",
        "對": "对",
        "時": "时",
        "間": "间",
        "點": "点",
        "說": "说",
        "話": "话",
        "聽": "听",
        "聲": "声",
        "風": "风",
        "樂": "乐",
        "園": "园",
        "農": "农",
        "曆": "历",
        "剛": "刚",
        "別": "别",
        "開": "开",
        "緊": "紧",
        "歡": "欢",
        "過": "过",
        "車": "车",
        "電": "电",
        "雙": "双",
        "還": "还",
        "總": "总",
        "現": "现",
        "場": "场",
        "專": "专",
        "屬": "属",
        "這": "这",
        "樣": "样",
        "書": "书",
        "絕": "绝",
        "從": "从",
        "預": "预",
        "價": "价",
        "值": "值",
        "議": "议",
        "憶": "忆",
        "麼": "么",
        "嗎": "吗",
        "輸": "输",
        "長": "长",
        "聖": "圣",
        "東": "东",
        "學": "学",
        "氣": "气",
        "應": "应",
        "實": "实",
        "體": "体",
        "轉": "转",
        "錄": "录",
        "識": "识",
        "別": "别",
        "簡": "简",
        "繁": "繁",
        "變": "变",
    }
)


def to_simplified(text: str) -> str:
    """Convert Chinese text to Simplified Chinese when possible.

    OpenCC is used when installed. A small built-in character map is kept as a
    dependency-free fallback so the app still improves common Traditional output
    without crashing.
    """
    if not text:
        return text

    try:
        from opencc import OpenCC

        return OpenCC("t2s").convert(text)
    except Exception:
        return text.translate(_FALLBACK_T2S_MAP)
