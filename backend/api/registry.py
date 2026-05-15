"""
平台注册表（自动扫描并合并所有平台的 API_REGISTRY）。

新增平台时，只需在 PLATFORMS 列表中导入新包即可，无需修改其他代码。
"""
from __future__ import annotations

from typing import Any

from api import bilibili, douyin, xiaohongshu, kuaishou

# 平台列表：新增平台时在此追加导入
PLATFORMS = [bilibili, douyin, xiaohongshu, kuaishou]

# 动态合并所有平台的 API_REGISTRY
API_REGISTRY: dict[str, Any] = {}
for platform in PLATFORMS:
    registry = getattr(platform, "API_REGISTRY", {})
    API_REGISTRY.update(registry)

# 工具元数据（描述 + 入参 + 反参）
# 注：executor.py 维护了自己的 TOOL_META，此处保留供 registry 独立使用
TOOL_META: dict[str, dict[str, Any]] = {
    # B站工具
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
    # 抖音工具
    "get_douyin_video_detail": {
        "description": "批量获取抖音视频详情（单次最多20个），返回播放量/点赞/评论/话题标签等",
        "input_params": ["ids(视频ID,多个逗号分隔,如'aweme_id1,aweme_id2')"],
        "return_fields": [
            "data(视频详情数组, 每条含aweme_id/desc/create_time/author/statistics/text_extra)",
            "aweme_id(视频ID)", "desc(标题/文案)", "create_time(发布时间戳)",
            "statistics(统计: comment_count/digg_count/play_count/share_count)",
            "text_extra(话题标签数组, 每项含hashtag_name)",
        ],
    },
    "get_douyin_short_url": {
        "description": "通过用户sec_uid获取抖音短链接",
        "input_params": ["sec_uid(用户加密ID)"],
        "return_fields": ["short_url(短链接)", "target(目标URL)"],
    },
    "get_douyin_ac_nonce": {
        "description": "获取查询达人粉丝所需的ac_nonce标识",
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
        "description": "获取抖音用户视频列表（主页作品）—— ⚠️ 接口文档不完整，当前为占位",
        "input_params": ["sec_uid(用户加密ID)", "cursor(分页游标,默认0)"],
        "return_fields": ["aweme_list(视频列表)", "has_more(是否有更多)", "cursor(下一页游标)"],
    },
    # 小红书工具
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
    # 快手工具
    "get_ks_video_list": {
        "description": "获取快手用户视频列表，返回视频ID/标题/封面/播放量/点赞/评论等",
        "input_params": ["uid(快手用户UID)", "pcursor(时间戳毫秒,可选)"],
        "return_fields": [
            "data(视频列表数组, 每条含photo_id/caption/view_count/like_count/comment_count/share_count)",
            "cover_urls(封面图)", "timestamp(发布时间)", "user_id(用户ID)",
        ],
    },
    "get_ks_video_detail": {
        "description": "获取快手单个视频详情，返回完整的视频数据和统计信息",
        "input_params": ["photo_id(快手视频ID)"],
        "return_fields": [
            "caption(标题/简介)", "view_count(播放量)", "like_count(点赞数)",
            "comment_count(评论数)", "share_count(分享数)", "duration(时长)",
        ],
    },
    "get_ks_user_info": {
        "description": "获取快手用户基础数据（昵称/头像/粉丝数/作品数等）",
        "input_params": ["uid(快手用户UID)"],
        "return_fields": [
            "profile(用户资料: user_name/headurl/kwaiId/user_id)",
            "ownerCount(统计数据: fan/photo/follow)",
        ],
    },
}
