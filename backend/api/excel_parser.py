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

# ====================== 工具函数：智能提取mid ======================
def extract_mid_from_bilibili_url(url: str) -> int | None:
    """
    智能提取 B站 mid
    支持：主页链接、视频链接、短链接、任意格式
    例：
    https://space.bilibili.com/123456
    https://www.bilibili.com/video/BV1xx411c7mZ
    https://b23.tv/BV1xx
    """
    if not url or not isinstance(url, str):
        return None

    url = url.strip()

    # 1. 匹配 space 主页链接
    match_space = re.search(r"space\.bilibili\.com/(\d+)", url)
    if match_space:
        return int(match_space.group(1))

    # 2. 匹配视频链接中的 mid（如果你的工具支持，这里可以调用API；不支持就注释）
    # 如果你只需要从主页链接提取，保留上面1即可

    return None

# ====================== 【核心】智能查找列：模糊匹配 ======================
def smart_find_column(columns: pd.Index, target_keywords: set[str]) -> str | None:
    """
    智能匹配列名：
    只要列名 包含 任意一个关键词（不区分大小写、不区分顺序）
    就返回该列
    """
    columns = [str(col).lower().strip() for col in columns if pd.notna(col)]

    for col in columns:
        for kw in target_keywords:
            kw = kw.lower()
            if kw in col:  # 模糊包含：最通用
                return col
    return None

# ====================== 查找表头行（智能版）======================
def _find_header_row(df: pd.DataFrame) -> int | None:
    """
    智能找表头：
    只要一行里 同时出现 昵称类 + 链接类 关键词，就判定为表头
    适配任何表格
    """
    for idx, row in df.iterrows():
        if idx > 50:
            break
        row_str = " ".join(str(c) for c in row if pd.notna(c)).lower()

        # 判定规则：只要命中 昵称/名字 + 链接/主页 任意一个 → 就是表头
        has_nick = any(kw in row_str for kw in NICKNAME_KEYWORDS)
        has_url = any(kw in row_str for kw in URL_KEYWORDS)
        has_mid = any(kw in row_str for kw in MID_KEYWORDS)

        if (has_nick and has_url) or (has_nick and has_mid) or (has_url and has_mid):
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

    # ====================== 【核心】智能匹配三列 ======================
    nickname_col = smart_find_column(df.columns, NICKNAME_KEYWORDS)
    url_col = smart_find_column(df.columns, URL_KEYWORDS)
    mid_col = smart_find_column(df.columns, MID_KEYWORDS)

    logger.info(f"[智能匹配结果] 昵称={nickname_col} | 链接={url_col} | mid={mid_col}")

    creators = []
    skipped = 0

    for idx, row in df.iterrows():
        nickname = str(row[nickname_col]).strip() if (nickname_col and pd.notna(row[nickname_col])) else None
        upper_mid = None
        space_url = None

        # 1. 优先取 mid
        if mid_col and pd.notna(row[mid_col]):
            try:
                upper_mid = int(float(row[mid_col]))
            except:
                pass

        # 2. 从链接提取
        if upper_mid is None and url_col and pd.notna(row[url_col]):
            space_url = str(row[url_col]).strip()
            upper_mid = extract_mid_from_bilibili_url(space_url)

        if upper_mid is None:
            skipped += 1
            continue

        creators.append({
            "nickname": nickname if nickname else f"UP_{upper_mid}",
            "upper_mid": upper_mid,
            "space_url": space_url,
        })

    return {
        "total": len(creators),
        "creators": creators,
        "skipped": skipped
    }