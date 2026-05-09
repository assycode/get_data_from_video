"""
Excel 解析模块（智能表头匹配版）
支持 任意列名、任意表格结构 自动识别：昵称、链接、mid
"""
from __future__ import annotations

import re
from io import BytesIO
from typing import Any

import pandas as pd

# ====================== 【核心】智能匹配规则（适配所有列名）======================
# 语义关键词组：只要列名包含任意一个，就判定为对应列
NICKNAME_KEYWORDS = {
    "昵称", "名字", "姓名", "账号", "up主", "达人", "博主", "up", "主播", "名称", "name",
    "nickname", "username", "创作者", "号主", "主理人", "up名字", "up昵称"
}
URL_KEYWORDS = {
    "链接", "主页", "url", "space", "主页链接", "b站", "哔哩哔哩", "返链", "反链",
    "主平台", "视频", "作品", "投稿", "主页地址", "个人主页", "主页url"
}
MID_KEYWORDS = {
    "mid", "uid", "id", "账号id", "用户id", "up主id", "创作者id", "up号", "编号"
}
BVID_KEYWORDS = {
    "bvid", "bv号", "bv", "视频号", "视频id", "视频编号", "作品号"
}

# ====================== 工具函数：智能提取mid ======================
def extract_mid_from_bilibili_url(url: str) -> int | None:
    """
    智能提取 B站 mid（兼容旧版，仅支持主页链接）
    如需完整类型识别，请使用 classify_bilibili_url()
    """
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    match_space = re.search(r"space\.bilibili\.com/(\d+)", url)
    if match_space:
        return int(match_space.group(1))
    return None


# ====================== 【核心】链接类型识别 ======================
def classify_bilibili_url(url: str) -> dict:
    """
    智能识别 B 站链接类型，返回结构化信息

    Returns:
        {
            "type": "space" | "video" | "short" | "unknown",
            "mid": int | None,          # space 类型时有值
            "bvid": str | None,         # video 类型时有值（BV号）
            "avid": int | None,         # video 类型时有值（av号）
            "short_code": str | None,   # short 类型时有值
            "raw_url": str,
        }
    """
    if not url or not isinstance(url, str):
        return {"type": "unknown", "mid": None, "bvid": None, "avid": None, "short_code": None, "raw_url": url or ""}

    raw_url = url.strip()
    url_lower = raw_url.lower()

    # 1. 主页链接
    space_match = re.search(r"space\.bilibili\.com/(\d+)", url_lower)
    if space_match:
        return {
            "type": "space",
            "mid": int(space_match.group(1)),
            "bvid": None,
            "avid": None,
            "short_code": None,
            "raw_url": raw_url,
        }

    # 2. 视频链接 (BV号)
    # ⚠️ BV 号是 base58 编码，大小写敏感！必须从原始 URL 提取，不能转大小写
    video_bv_match = re.search(r"bilibili\.com/video/(BV\w+)", raw_url, re.IGNORECASE)
    if video_bv_match:
        return {
            "type": "video",
            "mid": None,
            "bvid": video_bv_match.group(1),  # 保留原始大小写
            "avid": None,
            "short_code": None,
            "raw_url": raw_url,
        }

    # 3. 视频链接 (av号)
    video_av_match = re.search(r"bilibili\.com/video/av(\d+)", url_lower)
    if video_av_match:
        return {
            "type": "video",
            "mid": None,
            "bvid": None,
            "avid": int(video_av_match.group(1)),
            "short_code": None,
            "raw_url": raw_url,
        }

    # 4. 短链接（从原始 URL 提取，保留大小写）
    short_match = re.search(r"b23\.tv/(\w+)", raw_url, re.IGNORECASE)
    if short_match:
        return {
            "type": "short",
            "mid": None,
            "bvid": None,
            "avid": None,
            "short_code": short_match.group(1),
            "raw_url": raw_url,
        }

    return {"type": "unknown", "mid": None, "bvid": None, "avid": None, "short_code": None, "raw_url": raw_url}

# ====================== 【核心】智能查找列：模糊匹配 ======================
def smart_find_column(columns: pd.Index, target_keywords: set[str]) -> str | None:
    """
    智能匹配列名：
    只要列名 包含 任意一个关键词（不区分大小写、不区分顺序）
    就返回该列的**原始列名**（保留大小写）
    """
    for raw_col in columns:
        if pd.isna(raw_col):
            continue
        col_lower = str(raw_col).lower().strip()
        for kw in target_keywords:
            if kw.lower() in col_lower:
                return str(raw_col)
    return None

# ====================== 查找表头行（智能版）======================
def _find_header_row(df: pd.DataFrame) -> int | None:
    """
    智能找表头：
    只要一行里出现昵称类、链接类或 mid 类任意关键词，就判定为表头。
    适配单列表格（如只有视频URL列）。
    """
    for idx, row in df.iterrows():
        if idx > 50:
            break
        row_str = " ".join(str(c) for c in row if pd.notna(c)).lower()

        has_nick = any(kw in row_str for kw in NICKNAME_KEYWORDS)
        has_url = any(kw in row_str for kw in URL_KEYWORDS)
        has_mid = any(kw in row_str for kw in MID_KEYWORDS)

        # 放宽：只要有任意一类关键词就认为是表头（支持只有URL列的表格）
        if has_nick or has_url or has_mid:
            return idx
    return None

# ====================== 主解析函数 ======================
def parse_excel(file_bytes: bytes) -> dict[str, Any]:
    import logging
    logger = logging.getLogger(__name__)

    try:
        df = pd.read_excel(BytesIO(file_bytes), header=None)
    except Exception as exc:
        return {"error": f"Excel 解析失败: {exc}"}

    # 清洗空行
    df = df.dropna(how="all").reset_index(drop=True)
    if df.empty:
        return {"error": "Excel 无有效数据"}

    # 智能找表头
    header_idx = _find_header_row(df)
    if header_idx is None:
        df.columns = [f"col_{i}" for i in range(len(df.columns))]
    else:
        df.columns = df.iloc[header_idx]
        df = df.iloc[header_idx + 1:].reset_index(drop=True)

    logger.info(f"[智能匹配] 最终列名: {list(df.columns)}")

    # ====================== 【核心】智能匹配四列 ======================
    nickname_col = smart_find_column(df.columns, NICKNAME_KEYWORDS)
    url_col = smart_find_column(df.columns, URL_KEYWORDS)
    mid_col = smart_find_column(df.columns, MID_KEYWORDS)
    bvid_col = smart_find_column(df.columns, BVID_KEYWORDS)

    logger.info(f"[智能匹配结果] 昵称={nickname_col} | 链接={url_col} | mid={mid_col} | bvid={bvid_col}")

    creators = []
    skipped = 0

    for idx, row in df.iterrows():
        nickname = str(row[nickname_col]).strip() if (nickname_col and pd.notna(row[nickname_col])) else None
        upper_mid = None
        space_url = None
        link_info = {"type": "unknown"}
        bvid = None
        avid = None

        # 1. 优先取 mid
        if mid_col and pd.notna(row[mid_col]):
            try:
                upper_mid = int(float(row[mid_col]))
            except:
                pass

        # 2. 从链接提取
        if url_col and pd.notna(row[url_col]):
            space_url = str(row[url_col]).strip()
            link_info = classify_bilibili_url(space_url)
            if link_info["type"] == "space":
                upper_mid = link_info["mid"]
            bvid = link_info.get("bvid")
            avid = link_info.get("avid")

        # 3. 独立的 bvid 列（优先级高于链接中提取的，因为用户可能专门填了 BV号）
        if bvid_col and pd.notna(row[bvid_col]):
            raw_bvid = str(row[bvid_col]).strip()
            # 规范化：确保是 BV 开头
            if raw_bvid.upper().startswith("BV"):
                bvid = raw_bvid
            elif re.match(r"^\w{10,12}$", raw_bvid):
                # 可能是纯 BV 号部分（如 1HF9PB7Et7），补上前缀
                bvid = f"BV{raw_bvid}"

        # 判断是否有可识别的身份（mid / bvid / avid / video / short）
        has_identity = (
            upper_mid is not None
            or bvid is not None
            or avid is not None
            or link_info["type"] == "video"
            or link_info["type"] == "short"
        )

        if not has_identity:
            skipped += 1
            continue

        creators.append({
            "nickname": nickname if nickname else f"UP_{upper_mid or bvid or link_info.get('short_code') or 'unknown'}",
            "upper_mid": upper_mid,
            "link_type": link_info["type"] if (link_info["type"] != "unknown" or space_url) else ("video" if bvid else "unknown"),
            "bvid": bvid,
            "avid": avid,
            "short_code": link_info.get("short_code"),
            "space_url": space_url,
        })

    if not creators:
        # 分析为什么解析失败，给出具体提示
        detected = []
        if nickname_col:
            detected.append("昵称列")
        if url_col:
            detected.append("链接列")
        if mid_col:
            detected.append("MID列")
        if bvid_col:
            detected.append("BV号列")

        if detected:
            hint = f"检测到了 {', '.join(detected)}，但未能从中提取出有效的 bvid、aid 或 mid。"
        else:
            hint = (
                "未能识别到任何相关列（昵称/链接/MID/BV号）。"
                "请确保表格中至少包含以下一种信息："
                "UP主ID（mid）、视频BV号（bvid/BV号）、视频AV号（avid）、"
                "B站主页链接（space.bilibili.com）、视频链接（bilibili.com/video）或短链接（b23.tv）。"
            )

        return {
            "error": (
                f"Excel 中未能识别出任何可作为工具输入的数据。{hint}"
                "请检查表格内容后重新上传。"
            )
        }

    return {
        "total": len(creators),
        "creators": creators,
        "skipped": skipped
    }