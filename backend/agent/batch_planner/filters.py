"""
过滤与记录组装模块。

负责视频列表去重、按全局条件筛选、以及根据 export_fields 组装最终导出记录。
与平台无关的通用数据处理逻辑集中在此。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from agent.executor import _extract_timestamp
from models.schemas import GlobalFilter

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# 字段名映射：接口返回的驼峰/下划线 → 统一的 export_fields 格式
# ------------------------------------------------------------------------------

# 接口返回字段名 → export_fields 标准字段名
FIELD_NAME_MAPPING: dict[str, str] = {
    # 小红书驼峰 → 下划线
    "noteId": "note_id",
    "userId": "user_id",
    "likeNum": "likeNum",  # 保持一致
    "readNum": "readNum",
    "collectNum": "collectNum",
    "shareNum": "shareNum",
    "cmtNum": "cmtNum",
    "followCnt": "followCnt",
    "isVideo": "isVideo",
    "imgUrl": "imgUrl",
    "thirdReadUserNum": "thirdReadUserNum",
    "isAdvertise": "isAdvertise",
    "brandName": "brandName",
    "contentTags": "contentTags",
    
    # 快手驼峰兼容
    "photoId": "photo_id",
    "caption": "caption",
    
    # 抖音兼容
    "awemeId": "aweme_id",
}

# export_fields 标准字段名 → 接口可能的返回字段名列表（按优先级排序）
REVERSE_FIELD_MAPPING: dict[str, list[str]] = {
    "note_id": ["note_id", "noteId"],
    "user_id": ["user_id", "userId"],
    "photo_id": ["photo_id", "photoId"],
}


# ------------------------------------------------------------------------------
# 去重
# ------------------------------------------------------------------------------


def _dedup_video_list(video_list: list[dict]) -> list[dict]:
    """按 bvid / aweme_id / note_id 去重（支持多平台）。"""
    seen: set[str] = set()
    deduped: list[dict] = []
    for v in video_list:
        if not isinstance(v, dict):
            continue
        # 支持 B站(bvid)、抖音(aweme_id)、小红书(note_id/noteId)、快手(photo_id/photoId)
        key = v.get("bvid") or v.get("aweme_id") or v.get("note_id") or v.get("noteId") or v.get("photo_id") or v.get("photoId")
        if key and key not in seen:
            seen.add(key)
            deduped.append(v)
    return deduped


# ------------------------------------------------------------------------------
# 全局过滤
# ------------------------------------------------------------------------------


def _apply_global_filter(video_list: list[dict], global_filter: GlobalFilter, param_pool: dict[str, Any] | None = None) -> list[dict]:
    """按全局过滤条件筛选视频列表。
    
    修改：支持花火UP主画像数据直通（当没有视频列表但有花火数据时）
    """
    # ===== 新增：花火画像数据直通 =====
    if param_pool and not video_list:
        has_huahuo_data = "mapping_id" in param_pool or "upper_mid" in param_pool
        if has_huahuo_data:
            logger.info(f"检测到花火UP主画像数据，跳过滤波，直接导出")
            return [{}]  # 返回占位列表，触发一次导出
    # ===== 新增结束 =====
    
    topic = global_filter.topic.lstrip("#").strip() if global_filter.topic else ""
    start_date = global_filter.start_date
    end_date = global_filter.end_date

    start_ts = None
    end_ts = None
    if start_date:
        try:
            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
        except ValueError:
            pass
    if end_date:
        try:
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp()) + 86399
        except ValueError:
            pass

    filtered: list[dict] = []
    for v in video_list:
        if not isinstance(v, dict):
            continue

        # 时间过滤
        ts = _extract_timestamp(v)
        if start_ts and ts > 0 and ts < start_ts:
            continue
        if end_ts and ts > 0 and ts > end_ts:
            continue

        # 话题过滤
        if topic:
            title = str(v.get("title", ""))
            desc = str(v.get("desc", "")) if v.get("desc") else str(v.get("description", ""))
            dynamic = str(v.get("dynamic", ""))
            # 快手 caption（标题/描述）
            caption = str(v.get("caption", ""))
            tags = v.get("tags", [])
            tags_text = " ".join(str(t.get("tag_name", t)) if isinstance(t, dict) else str(t) for t in tags)
            participle = v.get("participle", [])
            participle_text = " ".join(str(p) for p in participle if isinstance(p, str))
            # 抖音 text_extra（话题标签）
            text_extra = v.get("text_extra", [])
            text_extra_text = " ".join(
                str(t.get("hashtag_name", t)) if isinstance(t, dict) else str(t)
                for t in text_extra
            )
            # 小红书 contentTags（话题标签）
            content_tags = v.get("contentTags", [])
            content_tags_text = " ".join(
                f"{t.get('taxonomy1Tag', '')} {' '.join(t.get('taxonomy2Tags', []))}" if isinstance(t, dict) else str(t)
                for t in content_tags
            )
            combined = f"{title} {desc} {dynamic} {caption} {tags_text} {participle_text} {text_extra_text} {content_tags_text}"
            if topic.lower() not in combined.lower():
                continue

        filtered.append(v)

    return filtered


# ------------------------------------------------------------------------------
# 导出记录组装
# ------------------------------------------------------------------------------


def _build_export_record(
    item: dict,
    param_pool: dict[str, Any],
    export_fields: list[str],
    nickname: str,
) -> dict[str, Any] | None:
    """根据 export_fields 从 item 和 param_pool 中组装最终导出记录。
    
    调试信息：记录 export_fields 和实际获取的字段值。

    字段来源优先级：
    1. item 中直接匹配的字段
    2. get_video_list 返回的 vlist 字段别名映射（play→view, comment→reply, created→pubdate, length→duration）
    3. param_pool 中的字段
    4. stat / statistics 对象中的统计字段
    5. get_video_detail 返回的 View / author / text_extra 对象中的字段
    6. 花火UP主画像数据（新增）
    """
    record: dict[str, Any] = {}
    
    # 调试日志
    logger.info(f"[_build_export_record] export_fields={export_fields}")
    logger.info(f"[_build_export_record] item.keys={list(item.keys())}, param_pool.keys={list(param_pool.keys())}")
    
    # ===== 新增：花火UP主画像数据检测 =====
    has_huahuo_id = "upper_mid" in param_pool or "mapping_id" in param_pool
    has_video_id = "bvid" in item or "aweme_id" in item or "note_id" in item or "photo_id" in item
    
    if has_huahuo_id and not has_video_id:
        # 这是花火UP主画像数据，直接从 param_pool 构建记录
        logger.info(f"[_build_export_record] 检测到花火UP主画像数据，从 param_pool 构建记录")
        record["platform"] = "huahuo"
        
        for field in export_fields:
            if field == "platform":
                continue
            
            # 支持嵌套字段（如 upper_prices.custom_price）
            if "." in field:
                parts = field.split(".")
                value = param_pool
                for part in parts:
                    if isinstance(value, dict):
                        value = value.get(part)
                    else:
                        value = None
                        break
                record[field] = value
            else:
                # 尝试所有可能的字段名（支持驼峰/下划线映射）
                possible_names = REVERSE_FIELD_MAPPING.get(field, [field])
                value = None
                for name in possible_names:
                    if name in item and item[name] is not None:
                        value = item[name]
                        break
                    if name in param_pool and param_pool[name] is not None:
                        value = param_pool[name]
                        break
                record[field] = value
        
        # 兜底：确保 creator_nickname 和 creator_mid 存在
        if "creator_nickname" not in record:
            record["creator_nickname"] = param_pool.get("nickname") or nickname
        if "creator_mid" not in record:
            record["creator_mid"] = param_pool.get("upper_mid") or param_pool.get("mapping_id")
        
        # ===== 新增：扁平化 upper_prices 对象 =====
        # upper_prices 可能是对象或数组，提取其中的 custom_price 和 star_price
        upper_prices = param_pool.get("upper_prices")
        if isinstance(upper_prices, dict):
            # 是对象，直接提取
            if "custom_price" not in record or record["custom_price"] is None:
                record["custom_price"] = upper_prices.get("custom_price")
            if "star_price" not in record or record["star_price"] is None:
                record["star_price"] = upper_prices.get("star_price")
        elif isinstance(upper_prices, list) and upper_prices:
            # 是数组，取第一个元素
            first = upper_prices[0]
            if isinstance(first, dict):
                if "custom_price" not in record or record["custom_price"] is None:
                    record["custom_price"] = first.get("custom_price")
                if "star_price" not in record or record["star_price"] is None:
                    record["star_price"] = first.get("star_price")
        
        # 格式化报价信息字段，方便直接显示
        if record.get("custom_price") or record.get("star_price"):
            custom = record.get("custom_price", "-")
            star = record.get("star_price", "-")
            record["upper_prices"] = f"{custom} / {star}"
        # ===== 新增结束 =====
        
        return record if record else None
    # ===== 新增结束 =====

    # get_video_list 返回的 vlist 字段名与标准字段名的映射
    _LIST_FIELD_ALIASES: dict[str, str] = {
        "play": "view",
        "comment": "reply",
        "created": "pubdate",
        "length": "duration",
        "description": "desc",
    }

    def _parse_duration(val: Any) -> int | None:
        """解析 get_video_list 返回的 length 字段（如 '3:45'）为秒数。"""
        if isinstance(val, int):
            return val
        if isinstance(val, str):
            parts = val.split(":")
            try:
                if len(parts) == 2:
                    return int(parts[0]) * 60 + int(parts[1])
                if len(parts) == 3:
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            except (ValueError, TypeError):
                pass
        return None

    def _get_field(field: str) -> Any:
        # 0. 尝试所有可能的字段名映射（接口返回可能是驼峰或下划线）
        possible_names = REVERSE_FIELD_MAPPING.get(field, [field])
        for name in possible_names:
            if name in item and item[name] is not None:
                return item[name]

        # 1. item 中直接匹配（兜底）
        if field in item and item[field] is not None:
            return item[field]

        # 2. get_video_list 字段别名映射（vlist 中的 play/comment/created/length/description）
        for src_key, dst_key in _LIST_FIELD_ALIASES.items():
            if dst_key == field and src_key in item and item[src_key] is not None:
                if field == "duration":
                    parsed = _parse_duration(item[src_key])
                    if parsed is not None:
                        return parsed
                elif field == "view" or field == "reply":
                    # play/comment 是整数，直接返回
                    val = item[src_key]
                    if isinstance(val, int) and val >= 0:
                        return val
                else:
                    return item[src_key]

        # 3. param_pool 中直接匹配
        if field in param_pool and param_pool[field] is not None:
            return param_pool[field]

        # 4. 特殊字段映射
        if field == "description":
            return item.get("desc") or param_pool.get("desc")
        if field == "note_id":
            # 小红书 noteId 驼峰命名兼容
            return item.get("note_id") or item.get("noteId") or param_pool.get("note_id")
        if field == "creator_nickname":
            return (
                nickname
                or item.get("creator_nickname")
                or item.get("author_nickname")
                or param_pool.get("owner_name")
                or param_pool.get("author_nickname")
                or param_pool.get("nickname")
            )
        if field == "creator_mid":
            return (
                item.get("creator_mid")
                or item.get("author_uid")
                or param_pool.get("upper_mid")
                or param_pool.get("owner_mid")
                or param_pool.get("author_uid")
                or param_pool.get("user_id")  # 小红书 user_id 作为 creator_mid
            )
        if field == "url":
            # B站
            bvid = item.get("bvid") or param_pool.get("bvid")
            if bvid:
                return f"https://www.bilibili.com/video/{bvid}"
            # 抖音
            share_url = item.get("share_url") or param_pool.get("share_url")
            if share_url:
                return share_url
            aweme_id = item.get("aweme_id") or param_pool.get("aweme_id")
            if aweme_id:
                return f"https://www.douyin.com/video/{aweme_id}"

        # 5. stat 对象中的统计字段（B站）
        if field in ("view", "danmaku", "reply", "favorite", "coin", "share", "like"):
            stat = item.get("stat")
            if isinstance(stat, dict) and field in stat:
                return stat[field]
            stat = param_pool.get("stat")
            if isinstance(stat, dict) and field in stat:
                return stat[field]

        # 5b. 抖音 statistics 对象中的统计字段
        if field in ("play_count", "digg_count", "comment_count", "share_count"):
            stat = item.get("statistics")
            if isinstance(stat, dict) and field in stat:
                logger.debug(f"[_get_field] 从 item.statistics 获取 {field}={stat[field]}")
                return stat[field]
            stat = param_pool.get("statistics")
            if isinstance(stat, dict) and field in stat:
                logger.debug(f"[_get_field] 从 param_pool.statistics 获取 {field}={stat[field]}")
                return stat[field]
            logger.debug(f"[_get_field] 未找到 {field}, item.keys={list(item.keys())}, param_pool.keys={list(param_pool.keys())}")

        # 6. get_video_detail 返回的 View 对象中的字段（B站）
        view = item.get("view") or param_pool.get("view")
        if isinstance(view, dict):
            if field in view and view[field] is not None:
                return view[field]
            if field in ("view", "danmaku", "reply", "favorite", "coin", "share", "like"):
                vstat = view.get("stat")
                if isinstance(vstat, dict) and field in vstat:
                    return vstat[field]

        # 6b. 抖音 author 对象中的字段
        author = item.get("author") or param_pool.get("author")
        if isinstance(author, dict):
            if field == "author_uid" and "uid" in author:
                return author["uid"]
            if field == "author_nickname" and "nickname" in author:
                return author["nickname"]
            if field == "author_unique_id" and "unique_id" in author:
                return author["unique_id"]

        # 6c. 抖音 text_extra（话题标签）
        if field in ("text_extra", "hashtags"):
            text_extra = item.get("text_extra") or param_pool.get("text_extra")
            if isinstance(text_extra, list):
                return text_extra

        # 6d. 小红书 contentTags（话题标签）
        if field == "contentTags":
            content_tags = item.get("contentTags") or param_pool.get("contentTags")
            if isinstance(content_tags, list):
                return content_tags

        # 6e. 小红书统计字段
        if field in ("like_num", "fav_num", "cmt_num", "read_num", "share_num", "follow_cnt"):
            val = item.get(field) or param_pool.get(field)
            if val is not None:
                return val

        # 7. get_video_detail 返回的 Card 对象中的字段（B站）
        card = item.get("card") or param_pool.get("card")
        if isinstance(card, dict) and field in card:
            return card[field]

        return None

    for field in export_fields:
        val = _get_field(field)
        if val is not None:
            record[field] = val

    # 兜底：确保 url / creator_nickname / creator_mid 始终存在
    if "url" not in record:
        bvid = item.get("bvid") or param_pool.get("bvid")
        if bvid:
            record["url"] = f"https://www.bilibili.com/video/{bvid}"
        else:
            share_url = item.get("share_url") or param_pool.get("share_url")
            if share_url:
                record["url"] = share_url
            else:
                aweme_id = item.get("aweme_id") or param_pool.get("aweme_id")
                if aweme_id:
                    record["url"] = f"https://www.douyin.com/video/{aweme_id}"
                else:
                    # 小红书笔记链接
                    note_id = item.get("note_id") or param_pool.get("note_id")
                    if note_id:
                        record["url"] = f"https://www.xiaohongshu.com/explore/{note_id}"
    if "creator_nickname" not in record:
        record["creator_nickname"] = (
            nickname
            or item.get("creator_nickname")
            or item.get("author_nickname")
            or param_pool.get("owner_name")
            or param_pool.get("author_nickname")
            or param_pool.get("nickname", "未知")
        )
    if "creator_mid" not in record:
        record["creator_mid"] = (
            item.get("creator_mid")
            or item.get("author_uid")
            or param_pool.get("upper_mid")
            or param_pool.get("owner_mid")
            or param_pool.get("author_uid")
        )

    return record if record else None
