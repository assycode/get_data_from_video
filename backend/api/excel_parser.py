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
    """解析 Excel 字节流，提取达人列表。"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        df = pd.read_excel(BytesIO(file_bytes), header=None)
    except Exception as exc:
        return {"error": f"Excel 解析失败: {exc}"}

    logger.info(f"[Excel] 原始数据 shape: {df.shape}")
    logger.info(f"[Excel] 前5行预览:\n{df.head()}")

    # 去掉完全空白的行
    df = df.dropna(how="all").reset_index(drop=True)

    if df.empty:
        return {"error": "Excel 文件为空或没有有效数据"}

    # 策略：寻找表头行
    header_row_idx = _find_header_row(df)
    if header_row_idx is None:
        logger.info("[Excel] 未找到表头行，假设第一行是数据")
        header_row_idx = 0
        df.columns = [f"col_{i}" for i in range(len(df.columns))]
    else:
        logger.info(f"[Excel] 找到表头行: idx={header_row_idx}, 表头={list(df.iloc[header_row_idx])}")
        df.columns = df.iloc[header_row_idx]
        df = df.iloc[header_row_idx + 1:].reset_index(drop=True)

    logger.info(f"[Excel] 解析后列名: {list(df.columns)}")
    logger.info(f"[Excel] 前3行数据:\n{df.head(3)}")

    # 识别关键列
    nickname_col = _find_column(df.columns, ["昵称", "账号昵称", "name", "up主", "达人"])
    url_col = _find_column(df.columns, ["链接", "主页", "space", "url", "b站主页链接", "个人主页"])
    mid_col = _find_column(df.columns, ["mid", "upper_mid", "uid", "id"])

    logger.info(f"[Excel] 匹配到的列: nickname_col={nickname_col}, url_col={url_col}, mid_col={mid_col}")

    creators = []
    skipped = 0

    for idx, row in df.iterrows():
        nickname = None
        if nickname_col is not None:
            nickname = row[nickname_col] if pd.notna(row[nickname_col]) else None

        upper_mid = None
        space_url = None

        # 优先从 mid 列获取
        if mid_col is not None and pd.notna(row[mid_col]):
            try:
                upper_mid = int(float(row[mid_col]))
                logger.info(f"[Excel] 行{idx}: 从 mid 列获取 upper_mid={upper_mid}")
            except (ValueError, TypeError) as exc:
                logger.warning(f"[Excel] 行{idx}: mid 列转换失败: {row[mid_col]} ({exc})")

        # 其次从 url 列提取
        if upper_mid is None and url_col is not None and pd.notna(row[url_col]):
            space_url = str(row[url_col]).strip()
            upper_mid = extract_mid_from_space_url(space_url)
            if upper_mid:
                logger.info(f"[Excel] 行{idx}: 从 URL 提取 upper_mid={upper_mid}")

        if upper_mid is None:
            logger.warning(f"[Excel] 行{idx}: 无法提取 upper_mid, nickname={nickname}, url={space_url}, row={dict(row)}")
            skipped += 1
            continue

        creators.append({
            "nickname": str(nickname) if nickname else f"UP主_{upper_mid}",
            "upper_mid": upper_mid,
            "space_url": space_url,
        })

    logger.info(f"[Excel] 解析完成: total={len(creators)}, skipped={skipped}")
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
