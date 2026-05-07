"""
Excel 解析模块

负责读取用户上传的 Excel 文件，提取达人列表信息。
支持两种输入列格式：
1. 包含 "b站主页链接" 列 → 自动从链接提取 upper_mid。
2. 直接包含 "upper_mid" 或 "mid" 列 → 直接使用。

返回标准化的达人列表，供批量任务使用。
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any

import pandas as pd
from utils.common_utils import extract_mid_from_space_url




def parse_excel(file_bytes: bytes) -> dict[str, Any]:
    """解析 Excel 字节流，提取达人列表。

    Args:
        file_bytes: 上传的 Excel 文件二进制内容。

    Returns:
        dict，格式：
        {
            "total": 94,
            "creators": [
                {"nickname": "伊伊星", "upper_mid": 472954189, "space_url": "https://space.bilibili.com/472954189"},
                ...
            ],
            "skipped": 2  # 无法解析mid的行数
        }
    """
    try:
        df = pd.read_excel(BytesIO(file_bytes), header=None)
    except Exception as exc:
        return {"error": f"Excel 解析失败: {exc}"}

    # 去掉完全空白的行
    df = df.dropna(how="all").reset_index(drop=True)

    if df.empty:
        return {"error": "Excel 文件为空或没有有效数据"}

    # 策略：寻找表头行（包含"昵称"、"链接"、"mid"等关键词的行）
    header_row_idx = _find_header_row(df)
    if header_row_idx is None:
        # 找不到表头，尝试假设第一行就是数据
        header_row_idx = 0
        df.columns = [f"col_{i}" for i in range(len(df.columns))]
    else:
        df.columns = df.iloc[header_row_idx]
        df = df.iloc[header_row_idx + 1:].reset_index(drop=True)

    # 识别关键列
    nickname_col = _find_column(df.columns, ["昵称", "账号昵称", "name", "up主", "达人"])
    url_col = _find_column(df.columns, ["链接", "主页", "space", "url", "b站主页链接", "个人主页"])
    mid_col = _find_column(df.columns, ["mid", "upper_mid", "uid", "id"])

    creators = []
    skipped = 0

    for _, row in df.iterrows():
        nickname = None
        if nickname_col is not None:
            nickname = row[nickname_col] if pd.notna(row[nickname_col]) else None

        upper_mid = None
        space_url = None

        # 优先从 mid 列获取
        if mid_col is not None and pd.notna(row[mid_col]):
            try:
                upper_mid = int(float(row[mid_col]))
            except (ValueError, TypeError):
                pass

        # 其次从 url 列提取
        if upper_mid is None and url_col is not None and pd.notna(row[url_col]):
            space_url = str(row[url_col]).strip()
            upper_mid = extract_mid_from_space_url(space_url)

        if upper_mid is None:
            skipped += 1
            continue

        creators.append(
            {
                "nickname": str(nickname) if nickname else f"UP主_{upper_mid}",
                "upper_mid": upper_mid,
                "space_url": space_url,
            }
        )

    return {
        "total": len(creators),
        "creators": creators,
        "skipped": skipped,
    }


def _find_header_row(df: pd.DataFrame) -> int | None:
    """在 DataFrame 中寻找包含表头关键词的行索引。"""
    keywords = ["昵称", "账号", "mid", "链接", "主页", "url", "space", "name", "b站", "up主", "达人"]
    for idx, row in df.iterrows():
        if idx > 30:  # 最多扫描前 30 行
            break
        row_text = " ".join(str(cell) for cell in row if pd.notna(cell)).lower()
        matches = sum(1 for kw in keywords if kw.lower() in row_text)
        if matches >= 2:  # 至少匹配 2 个关键词才认为是表头
            return idx
    return None


def _find_column(columns: pd.Index, keywords: list[str]) -> str | None:
    """根据关键词列表在列名中寻找匹配的列。"""
    cols = list(columns)
    for keyword in keywords:
        for col in cols:
            col_str = str(col).lower().strip()
            if keyword.lower() in col_str:
                return col
    return None
