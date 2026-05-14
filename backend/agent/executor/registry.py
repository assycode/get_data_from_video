"""
工具注册中心。

负责维护工具元数据（TOOL_META）、工具注册表（TOOL_REGISTRY）、
参数别名映射（PARAM_ALIASES），以及参数池相关的构建函数。

新增工具时，只需在此追加注册即可，core.py 等模块无需改动。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from pydantic import BaseModel

# 数据接口函数
from api.data_apis import (
    get_up_info,
    get_up_follower,
    get_video_list,
    get_video_data,
    get_video_detail,
    resolve_short_url,
    get_douyin_video_detail,
    get_douyin_short_url,
    get_douyin_ac_nonce,
    get_douyin_follower,
    get_douyin_room_id,
    get_douyin_user_videos,
    get_xhs_notes_list,
    get_xhs_note_info,
)

from .models import (
    GetUpInfoArgs,
    GetUpFollowerArgs,
    GetVideoListArgs,
    GetVideoDataArgs,
    GetVideoDetailArgs,
    ResolveShortUrlArgs,
    GetDouyinVideoDetailArgs,
    GetDouyinShortUrlArgs,
    GetDouyinAcNonceArgs,
    GetDouyinFollowerArgs,
    GetDouyinRoomIdArgs,
    GetDouyinUserVideosArgs,
    GetXhsNotesListArgs,
    GetXhsNoteInfoArgs,
)

logger = logging.getLogger(__name__)

type ToolEntry = dict[str, Any]

# ------------------------------------------------------------------------------
# 1. 工具元数据（供 LLM 理解工具能力）
# ------------------------------------------------------------------------------

TOOL_META: dict[str, dict[str, Any]] = {
    "get_up_info": {
        "description": "获取UP主基本信息（昵称、头像、签名等）",
        "input_params": ["upper_mid"],
        "return_fields": ["mid", "name(昵称)", "sex", "face", "sign(签名)", "level"],
    },
    "get_up_follower": {
        "description": "获取UP主粉丝统计数据",
        "input_params": ["upper_mid"],
        "return_fields": ["mid", "follower(粉丝数)", "following(关注数)"],
    },
    "get_video_list": {
        "description": "获取UP主视频列表（分页返回多条视频概要）",
        "input_params": ["upper_mid", "pn(页码,从1开始)"],
        "return_fields": [
            "vlist(视频列表数组, 每条含bvid/aid/title/play/comment/created等)",
            "page(分页信息: pn/ps/count)",
        ],
    },
    "get_video_data": {
        "description": "获取单个视频基础数据（不含标签，适合仅需播放量/点赞/时长等统计量）",
        "input_params": ["id(视频ID,支持bvid或avid)"],
        "return_fields": [
            "bvid", "aid", "title(标题)", "pubdate(发布时间戳)", "duration(时长秒)",
            "desc(描述)", "dynamic(动态文案)", "pic(封面图)",
            "stat(统计对象: view/danmaku/reply/favorite/coin/share/like)",
            "owner(作者信息: mid/name)",
        ],
    },
    "get_video_detail": {
        "description": "获取视频完整数据（含标签Tags和分词participle），是唯一返回话题标签的接口",
        "input_params": ["id(视频ID,支持bvid或 avid)"],
        "return_fields": [
            "View(视频基础信息,同get_video_data)",
            "Tags(标签数组,每项含tag_name)",
            "participle(分词/话题标签字符串数组)",
            "Card(UP主卡片信息)",
        ],
    },
    "resolve_short_url": {
        "description": "解析B站短链接(b23.tv/xxxx)为真实URL，提取bvid/avid/mid",
        "input_params": ["short_code(短链接代码,如b23.tv/xxxx中的xxxx)"],
        "return_fields": [
            "bvid(解析出的BV号)",
            "avid(解析出的AV号)",
            "mid(解析出的UP主MID)",
            "resolved_url(跳转后的真实URL)",
        ],
    },
    # --- 抖音工具 ---
    "get_douyin_video_detail": {
        "description": "批量获取抖音视频详情（单次最多20个），返回播放量/点赞/评论/话题标签等。是抖音最核心的数据接口",
        "input_params": ["ids(视频ID,多个逗号分隔,如'aweme_id1,aweme_id2')"],
        "return_fields": [
            "data(视频详情数组, 每条含aweme_id/desc/create_time/author/statistics/text_extra)",
            "aweme_id(视频ID)", "desc(标题文案)", "create_time(发布时间戳)",
            "statistics(统计: comment_count评论/digg_count点赞/play_count播放/share_count分享)",
            "text_extra(话题标签数组, 每项含hashtag_name)",
            "author(作者信息: uid/nickname/avatar/unique_id)",
        ],
    },
    "get_douyin_short_url": {
        "description": "通过用户sec_uid获取抖音短链接（v.douyin.com/xxxx）",
        "input_params": ["sec_uid(用户加密ID)"],
        "return_fields": ["short_url(短链接)", "target(目标URL)"],
    },
    "get_douyin_ac_nonce": {
        "description": "获取查询达人粉丝所需的ac_nonce标识（get_douyin_follower的前置步骤）",
        "input_params": ["aweme_id(视频ID)"],
        "return_fields": ["ac_nonce(标识字符串)"],
    },
    "get_douyin_follower": {
        "description": "获取视频对应达人的粉丝数（需要ac_nonce和ac_signature）",
        "input_params": ["aweme_id(视频ID)", "ac_nonce(标识)", "ac_signature(签名令牌)"],
        "return_fields": ["followerCount(粉丝数)"],
    },
    "get_douyin_room_id": {
        "description": "获取抖音用户当前直播房间号",
        "input_params": ["uid(抖音数字UID)"],
        "return_fields": ["room_id(房间ID)"],
    },
    "get_douyin_user_videos": {
        "description": "获取抖音用户视频列表（主页作品）—— ⚠️ 接口文档不完整，当前为占位，调用会返回提示",
        "input_params": ["sec_uid(用户加密ID)", "cursor(分页游标,默认0)"],
        "return_fields": ["aweme_list(视频列表)", "has_more(是否有更多)", "cursor(下一页游标)"],
    },
    # --- 小红书工具 ---
    "get_xhs_notes_list": {
        "description": "获取小红书用户笔记列表，返回笔记ID/标题/封面/阅读量/点赞/收藏等",
        "input_params": ["user_id(用户ID)", "page_number(页码,默认1)", "page_size(每页数量,默认20)", "note_type(笔记类型,默认4全部)", "advertise_switch(流量类型,默认1全部)", "order_type(排序类型,默认1最新)"],
        "return_fields": [
            "list(笔记列表数组, 每条含noteId/title/imgUrl/date/isVideo/readNum/likeNum/collectNum)",
            "total(总数)",
        ],
    },
    "get_xhs_note_info": {
        "description": "获取小红书笔记详情，返回完整的互动数据和作者信息",
        "input_params": ["note_id(笔记ID)"],
        "return_fields": [
            "likeNum(点赞数)", "favNum(收藏数)", "cmtNum(评论数)", "readNum(阅读数)",
            "shareNum(分享数)", "followCnt(涨粉数)", "userInfo(作者信息)",
        ],
    },
}

# ------------------------------------------------------------------------------
# 2. 工具注册表：tool_name → {func, args_model, description}
# ------------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, ToolEntry] = {
    "get_up_info": {
        "func": get_up_info,
        "args_model": GetUpInfoArgs,
        "description": "获取UP主基本信息",
    },
    "get_up_follower": {
        "func": get_up_follower,
        "args_model": GetUpFollowerArgs,
        "description": "获取UP主粉丝数据",
    },
    "get_video_list": {
        "func": get_video_list,
        "args_model": GetVideoListArgs,
        "description": "获取UP主视频列表（分页）",
    },
    "get_video_data": {
        "func": get_video_data,
        "args_model": GetVideoDataArgs,
        "description": "获取单个视频基础数据（不含标签）",
    },
    "get_video_detail": {
        "func": get_video_detail,
        "args_model": GetVideoDetailArgs,
        "description": "获取视频完整数据（含标签Tags和分词participle）",
    },
    "resolve_short_url": {
        "func": resolve_short_url,
        "args_model": ResolveShortUrlArgs,
        "description": "解析B站短链接为真实URL",
    },
    # --- 抖音工具 ---
    "get_douyin_video_detail": {
        "func": get_douyin_video_detail,
        "args_model": GetDouyinVideoDetailArgs,
        "description": "批量获取抖音视频详情（单次最多20个）",
    },
    "get_douyin_short_url": {
        "func": get_douyin_short_url,
        "args_model": GetDouyinShortUrlArgs,
        "description": "通过sec_uid获取抖音用户短链接",
    },
    "get_douyin_ac_nonce": {
        "func": get_douyin_ac_nonce,
        "args_model": GetDouyinAcNonceArgs,
        "description": "获取查询达人粉丝所需的ac_nonce标识",
    },
    "get_douyin_follower": {
        "func": get_douyin_follower,
        "args_model": GetDouyinFollowerArgs,
        "description": "获取视频对应达人的粉丝数",
    },
    "get_douyin_room_id": {
        "func": get_douyin_room_id,
        "args_model": GetDouyinRoomIdArgs,
        "description": "获取抖音用户当前直播房间号",
    },
    "get_douyin_user_videos": {
        "func": get_douyin_user_videos,
        "args_model": GetDouyinUserVideosArgs,
        "description": "获取抖音用户视频列表（文档不完整，占位）",
    },
    # --- 小红书工具 ---
    "get_xhs_notes_list": {
        "func": get_xhs_notes_list,
        "args_model": GetXhsNotesListArgs,
        "description": "获取小红书用户笔记列表",
    },
    "get_xhs_note_info": {
        "func": get_xhs_note_info,
        "args_model": GetXhsNoteInfoArgs,
        "description": "获取小红书笔记详情",
    },
}

# ------------------------------------------------------------------------------
# 3. 参数别名映射
# ------------------------------------------------------------------------------

PARAM_ALIASES: dict[str, list[str]] = {
    "id": ["bvid", "avid"],  # short_code 必须通过 resolve_short_url 解析为 bvid 后才能使用
    "upper_mid": ["upper_mid", "owner_mid", "mid"],
    # 抖音参数别名
    "ids": ["aweme_id", "aweme_ids"],  # get_douyin_video_detail 的 ids 可从 aweme_id 推导
    "sec_uid": ["sec_uid"],
    "aweme_id": ["aweme_id"],
    "uid": ["uid", "author_user_id"],  # get_douyin_room_id 可从 author_user_id 推导
    # 小红书参数别名
    "user_id": ["user_id", "xhs_user_id"],
    "note_id": ["note_id", "xhs_note_id"],
}


# ------------------------------------------------------------------------------
# 4. 对外接口
# ------------------------------------------------------------------------------


def get_tool_names() -> list[str]:
    """返回所有已注册工具的名称列表（白名单）。"""
    return list(TOOL_REGISTRY.keys())


def build_tools_prompt() -> str:
    """从 TOOL_META 生成给 LLM 的工具描述文本（含入参+反参）。"""
    lines = ["## 可用工具（工具名必须严格匹配，严禁编造）\n"]
    for tool_name, meta in TOOL_META.items():
        lines.append(f"- {tool_name}：{meta['description']}")
        lines.append(f"  · 入参：{', '.join(meta['input_params'])}")
        lines.append(f"  · 反参：{', '.join(meta['return_fields'])}")
    return "\n".join(lines)


def build_args_from_pool(tool_name: str, param_pool: dict[str, Any]) -> dict[str, Any] | None:
    """根据 param_pool 自动构建指定工具的入参。

    匹配规则：
    1. 从 TOOL_REGISTRY 获取 args_model，遍历其字段名
    2. 每个字段先从 param_pool 中直接查找同名字段
    3. 找不到时，查 PARAM_ALIASES 尝试别名映射
    4. 还找不到且字段有默认值，则用默认值
    5. 必填字段找不到值 → 返回 None（参数不足）
    """
    entry = TOOL_REGISTRY.get(tool_name)
    if entry is None:
        return None

    args_model: type[BaseModel] = entry["args_model"]
    args: dict[str, Any] = {}

    # 遍历 Pydantic 模型字段
    for field_name, field_info in args_model.model_fields.items():
        val = param_pool.get(field_name)

        # 直接匹配失败 → 尝试别名
        if val is None and field_name in PARAM_ALIASES:
            for alias in PARAM_ALIASES[field_name]:
                if alias in param_pool and param_pool[alias] is not None:
                    val = param_pool[alias]
                    break

        # 分页字段特殊处理
        if field_name == "pn" and val is None:
            val = param_pool.get("pn", 1)

        if val is not None:
            args[field_name] = val
        elif field_info.is_required():
            # 必填但 param_pool 里没有
            logger.debug(f"[ParamPool] 工具 {tool_name} 必填字段 {field_name} 缺失")
            return None
        # 非必填缺失 → 交给 Pydantic 默认值

    return args
