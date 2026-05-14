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
    "mid", "id", "账号id", "用户id", "up主id", "创作者id", "up号", "编号"
    # 注意：不单独包含 "uid"，避免与平台特定的 uid 列混淆
}
BVID_KEYWORDS = {
    "bvid", "bv号", "bv", "视频号", "视频id", "视频编号", "作品号"
}
AWEME_ID_KEYWORDS = {
    "aweme_id", "awemeid", "视频id", "抖音视频id", "作品id", "抖音id", "aweme", "视频编号", "作品编号"
}
SEC_UID_KEYWORDS = {
    "sec_uid", "secuid", "用户加密id", "抖音用户id", "加密id", "sec_uid"
}
UID_KEYWORDS = {
    "抖音uid", "douyin_uid", "抖音用户id", "抖音数字id", "抖音号"
    # 注意：不单独包含 "uid"，避免与通用的 uid 列混淆
}
XHS_USER_ID_KEYWORDS = {
    "user_id", "用户id", "小红书id", "xhs_user_id", "xhs_id", "小红书用户id", "小红书uid",
    "xhs_uid", "xhs用户id", "red_id", "小红书账号id"
}
XHS_NOTE_ID_KEYWORDS = {
    "note_id", "笔记id", "笔记编号", "小红书笔记id", "xhs_note_id"
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


# ====================== 【核心】多平台链接识别 ======================
def detect_platform(url: str) -> str:
    """根据 URL 域名判断所属平台。"""
    if not url or not isinstance(url, str):
        return "unknown"
    url_lower = url.strip().lower()
    if any(d in url_lower for d in ("bilibili.com", "b23.tv", "bilivideo.com")):
        return "bilibili"
    if any(d in url_lower for d in ("douyin.com", "iesdouyin.com", "v.douyin.com")):
        return "douyin"
    if any(d in url_lower for d in ("xiaohongshu.com", "xhs.link", "xhs.cn")):
        return "xiaohongshu"
    return "unknown"


def classify_url(url: str) -> dict:
    """
    智能识别 URL 所属平台及链接类型，返回结构化信息。
    支持多平台：B站、抖音、小红书等。

    Returns:
        {
            "platform": "bilibili" | "douyin" | "xiaohongshu" | "unknown",
            "type": "space" | "video" | "short" | "unknown",
            "mid": int | None,
            "bvid": str | None,
            "avid": int | None,
            "short_code": str | None,
            "raw_url": str,
        }
    """
    if not url or not isinstance(url, str):
        return {
            "platform": "unknown", "type": "unknown",
            "mid": None, "bvid": None, "avid": None, "short_code": None, "raw_url": url or "",
        }

    raw_url = url.strip()
    platform = detect_platform(raw_url)
    url_lower = raw_url.lower()

    # -------- B站 --------
    if platform == "bilibili":
        # 1. 主页链接 - 支持多种格式
        # 匹配 space.bilibili.com/数字 或 space.bilibili.com/数字/ 或带协议头的完整URL
        space_match = re.search(r"space\.bilibili\.com/(\d+)(?:/|$)", url_lower)
        if space_match:
            return {"platform": "bilibili", "type": "space", "mid": int(space_match.group(1)), "bvid": None, "avid": None, "short_code": None, "raw_url": raw_url}
        # 尝试匹配可能带有额外路径的情况
        space_match_alt = re.search(r"space\.bilibili\.com/(\d+)", url_lower)
        if space_match_alt:
            return {"platform": "bilibili", "type": "space", "mid": int(space_match_alt.group(1)), "bvid": None, "avid": None, "short_code": None, "raw_url": raw_url}
        # 2. 视频链接 (BV号) — 大小写敏感
        video_bv_match = re.search(r"bilibili\.com/video/(BV\w+)", raw_url, re.IGNORECASE)
        if video_bv_match:
            return {"platform": "bilibili", "type": "video", "mid": None, "bvid": video_bv_match.group(1), "avid": None, "short_code": None, "raw_url": raw_url}
        # 3. 视频链接 (av号)
        video_av_match = re.search(r"bilibili\.com/video/av(\d+)", url_lower)
        if video_av_match:
            return {"platform": "bilibili", "type": "video", "mid": None, "bvid": None, "avid": int(video_av_match.group(1)), "short_code": None, "raw_url": raw_url}
        # 4. 短链接
        short_match = re.search(r"b23\.tv/(\w+)", raw_url, re.IGNORECASE)
        if short_match:
            return {"platform": "bilibili", "type": "short", "mid": None, "bvid": None, "avid": None, "short_code": short_match.group(1), "raw_url": raw_url}
        return {"platform": "bilibili", "type": "unknown", "mid": None, "bvid": None, "avid": None, "short_code": None, "raw_url": raw_url}

    # -------- 抖音 --------
    if platform == "douyin":
        # 1. 用户主页
        user_match = re.search(r"douyin\.com/user/(\w+)", url_lower) or re.search(r"iesdouyin\.com/share/user/(\d+)", url_lower)
        if user_match:
            return {"platform": "douyin", "type": "space", "mid": None, "bvid": None, "avid": None, "short_code": None, "raw_url": raw_url, "sec_uid": user_match.group(1)}
        # 2. 视频链接
        video_match = re.search(r"douyin\.com/video/(\d+)", url_lower) or re.search(r"v\.douyin\.com/(\w+)", url_lower)
        if video_match:
            return {"platform": "douyin", "type": "video", "mid": None, "bvid": None, "avid": None, "short_code": video_match.group(1), "raw_url": raw_url}
        return {"platform": "douyin", "type": "unknown", "mid": None, "bvid": None, "avid": None, "short_code": None, "raw_url": raw_url}

    # -------- 小红书 --------
    if platform == "xiaohongshu":
        # 1. 用户主页
        user_match = re.search(r"xiaohongshu\.com/user/profile/(\w+)", url_lower)
        if user_match:
            return {"platform": "xiaohongshu", "type": "space", "mid": None, "bvid": None, "avid": None, "short_code": None, "raw_url": raw_url, "user_id": user_match.group(1)}
        # 2. 笔记/视频链接
        note_match = re.search(r"xiaohongshu\.com/explore/(\w+)", url_lower) or re.search(r"xhs\.link/(\w+)", url_lower)
        if note_match:
            return {"platform": "xiaohongshu", "type": "video", "mid": None, "bvid": None, "avid": None, "short_code": note_match.group(1), "raw_url": raw_url}
        return {"platform": "xiaohongshu", "type": "unknown", "mid": None, "bvid": None, "avid": None, "short_code": None, "raw_url": raw_url}

    # 兜底：unknown
    return {"platform": "unknown", "type": "unknown", "mid": None, "bvid": None, "avid": None, "short_code": None, "raw_url": raw_url}

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

    # ====================== 【核心】智能匹配列 ======================
    nickname_col = smart_find_column(df.columns, NICKNAME_KEYWORDS)
    url_col = smart_find_column(df.columns, URL_KEYWORDS)
    mid_col = smart_find_column(df.columns, MID_KEYWORDS)
    bvid_col = smart_find_column(df.columns, BVID_KEYWORDS)
    aweme_id_col = smart_find_column(df.columns, AWEME_ID_KEYWORDS)
    sec_uid_col = smart_find_column(df.columns, SEC_UID_KEYWORDS)
    uid_col = smart_find_column(df.columns, UID_KEYWORDS)
    xhs_user_id_col = smart_find_column(df.columns, XHS_USER_ID_KEYWORDS)
    xhs_note_id_col = smart_find_column(df.columns, XHS_NOTE_ID_KEYWORDS)

    logger.info(
        f"[智能匹配结果] 昵称={nickname_col} | 链接={url_col} | mid={mid_col} | bvid={bvid_col} | "
        f"aweme_id={aweme_id_col} | sec_uid={sec_uid_col} | uid={uid_col} | "
        f"xhs_user_id={xhs_user_id_col} | xhs_note_id={xhs_note_id_col}"
    )

    creators = []
    skipped = 0

    for idx, row in df.iterrows():
        nickname = str(row[nickname_col]).strip() if (nickname_col and pd.notna(row[nickname_col])) else None
        upper_mid = None
        space_url = None
        link_info = {"type": "unknown"}
        bvid = None
        avid = None
        aweme_id = None
        sec_uid = None
        uid = None
        user_id = None  # 小红书用户ID
        note_id = None  # 小红书笔记ID

        # 1. 优先取 mid（B站）
        if mid_col and pd.notna(row[mid_col]):
            try:
                upper_mid = int(float(row[mid_col]))
                # 不自动设置平台，让 LLM 根据上下文判断
            except Exception:
                pass

        # 2. 从链接提取（多平台）
        platform = "unknown"
        if url_col and pd.notna(row[url_col]):
            space_url = str(row[url_col]).strip()
            logger.info(f"[URL处理] 行{idx}: URL={space_url}")
            link_info = classify_url(space_url)
            logger.info(f"[URL处理] 行{idx}: 识别结果 platform={link_info.get('platform')}, type={link_info.get('type')}, mid={link_info.get('mid')}")
            platform = link_info.get("platform", "unknown")
            if link_info["type"] == "space" and link_info.get("mid"):
                upper_mid = link_info["mid"]
                logger.info(f"[URL处理] 行{idx}: 提取到 mid={upper_mid}")
            bvid = link_info.get("bvid")
            avid = link_info.get("avid")
            sec_uid = link_info.get("sec_uid")
            user_id = link_info.get("user_id")  # 小红书用户ID
            note_id = link_info.get("short_code")  # 小红书笔记ID可能来自短链接

        # 3. 独立的 bvid 列（B站强信号）
        if bvid_col and pd.notna(row[bvid_col]):
            raw_bvid = str(row[bvid_col]).strip()
            if raw_bvid.upper().startswith("BV"):
                bvid = raw_bvid
                platform = "bilibili"
            elif re.match(r"^\w{10,12}$", raw_bvid):
                bvid = f"BV{raw_bvid}"
                platform = "bilibili"

        # 4. 独立的 aweme_id 列（抖音强信号）
        if aweme_id_col and pd.notna(row[aweme_id_col]):
            aweme_id = str(row[aweme_id_col]).strip()
            platform = "douyin"

        # 5. 独立的 sec_uid 列（抖音用户ID）
        if sec_uid_col and pd.notna(row[sec_uid_col]):
            sec_uid = str(row[sec_uid_col]).strip()
            platform = "douyin"

        # 6. 独立的 uid 列（抖音数字UID）- 需要确认是抖音特定的 uid
        if uid_col and pd.notna(row[uid_col]):
            uid = str(row[uid_col]).strip()
            # 只有当平台还未确定时才设为抖音
            if platform == "unknown":
                platform = "douyin"

        # 7. 独立的小红书 user_id 列
        if xhs_user_id_col and pd.notna(row[xhs_user_id_col]):
            user_id = str(row[xhs_user_id_col]).strip()
            platform = "xiaohongshu"

        # 8. 独立的小红书 note_id 列
        if xhs_note_id_col and pd.notna(row[xhs_note_id_col]):
            note_id = str(row[xhs_note_id_col]).strip()
            platform = "xiaohongshu"

        # 9. 处理通用的 uid 列（如"达人UID"）
        # 如果没有匹配到任何特定平台的 ID 列，但有 mid_col 的数据
        if platform == "unknown" and mid_col and pd.notna(row[mid_col]):
            # 将通用的 uid 存储为 user_id，让 LLM 根据上下文判断平台
            try:
                user_id = str(int(float(row[mid_col])))
            except Exception:
                user_id = str(row[mid_col]).strip()

        # 10. 平台兜底：如果还没识别出平台但有链接，尝试用 detect_platform
        if platform == "unknown" and space_url:
            platform = detect_platform(space_url)

        # 判断是否有可识别的身份
        has_identity = (
            upper_mid is not None
            or bvid is not None
            or avid is not None
            or aweme_id is not None
            or sec_uid is not None
            or uid is not None
            or user_id is not None
            or note_id is not None
            or link_info.get("type") in ("video", "short", "space")
            or platform != "unknown"
        )

        if not has_identity:
            skipped += 1
            continue

        # 生成昵称兜底
        display_name = nickname
        if not display_name:
            identifier = (
                upper_mid
                or bvid
                or aweme_id
                or sec_uid
                or uid
                or user_id
                or note_id
                or link_info.get("short_code")
                or link_info.get("user_id")
                or "unknown"
            )
            display_name = f"达人_{identifier}"

        creators.append({
            "nickname": display_name,
            "upper_mid": upper_mid,
            "platform": platform,
            "link_type": link_info.get("type", "unknown") if (link_info.get("type") != "unknown" or space_url) else ("video" if (bvid or aweme_id or note_id) else "unknown"),
            "bvid": bvid,
            "avid": avid,
            "short_code": link_info.get("short_code"),
            "space_url": space_url,
            # 抖音字段
            "aweme_id": aweme_id,
            "sec_uid": sec_uid,
            "uid": uid,
            # 小红书字段
            "user_id": user_id,
            "note_id": note_id,
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
        if aweme_id_col:
            detected.append("AwemeID列")
        if sec_uid_col:
            detected.append("SecUID列")
        if uid_col:
            detected.append("UID列")
        if xhs_user_id_col:
            detected.append("小红书用户ID列")
        if xhs_note_id_col:
            detected.append("小红书笔记ID列")

        if detected:
            hint = f"检测到了 {', '.join(detected)}，但未能从中提取出有效的达人身份信息。"
        else:
            hint = (
                "未能识别到任何相关列（昵称/链接/MID/BV号/AwemeID/SecUID/UID/小红书ID）。"
                "请确保表格中至少包含以下一种信息："
                "UP主ID（mid）、视频BV号（bvid/BV号）、视频AV号（avid）、"
                "B站主页链接（space.bilibili.com）、视频链接（bilibili.com/video）或短链接（b23.tv）、"
                "抖音链接（douyin.com）、抖音视频ID（aweme_id）、抖音用户加密ID（sec_uid）、抖音数字UID（uid）、"
                "小红书链接（xiaohongshu.com/xhs.link）、小红书用户ID（user_id）、小红书笔记ID（note_id）等。"
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