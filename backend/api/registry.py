"""
平台注册表（自动扫描并合并所有平台的 API_REGISTRY）。

新增平台时，只需在 PLATFORMS 列表中导入新包即可，无需修改其他代码。
"""
from __future__ import annotations

from typing import Any

from api import bilibili, douyin, xiaohongshu, kuaishou, huahuo

# 平台列表：新增平台时在此追加导入
PLATFORMS = [bilibili, douyin, xiaohongshu, kuaishou, huahuo]

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
    # 花火工具（B站商业合作平台）
    "get_huahuo_list": {
        "description": "获取花火UP主列表（达人库），支持多种筛选条件",
        "input_params": [
            "key(搜索关键词,可选)", "page(页码,默认1)", "order_bys(排序:0综合1粉丝升2粉丝降3报价降4报价升)",
            "content_tag_id(内容分类ID)", "commercial_tag_id(商单类型ID)",
            "fans_ranges(粉丝范围)", "min_fans_num(最小粉丝数)", "max_fans_num(最大粉丝数)",
            "cooperation_types(合作类型:1植入2定制3直发动态4转发动态-1非标准)",
        ],
        "return_fields": [
            "data.data(UP主列表)", "upper_mid(UP主ID)", "nickname(昵称)", "fans_num(粉丝数)",
            "partition_name(主分类)", "price_infos(报价信息)", "tags(标签)",
        ],
    },
    "get_huahuo_up_portrait": {
        "description": "获取UP主个人信息（画像），包含粉丝分布、内容数据、报价等详细信息",
        "input_params": ["upper_mid(UP主ID/B站UID)", "mcn_id(MCN机构ID/花火ID)"],
        "return_fields": [
            "nickname(昵称)", "fans_num(粉丝数)", "upper_prices(报价)",
            "sax_distributions(粉丝性别分布)", "age_distributions(粉丝年龄分布)",
            "top_region_distributions(粉丝地区分布)", "first_categories_profile(粉丝一级分区)",
            "average_play_cnt(平均播放量)", "average_interactive_rate(平均互动率)",
        ],
    },
    "get_huahuo_up_trend": {
        "description": "获取UP主最新作品趋势数据（播放量/点赞/评论/弹幕）",
        "input_params": ["upper_mid(UP主ID)", "trend_type(数据类型:3播放4点赞5评论6弹幕)"],
        "return_fields": [
            "min_cnt(最小值)", "max_cnt(最大值)", "median(平均值)",
            "upper_draft_trend_info_vos(视频数据列表: bv_id/title/pub_date/trend_cnt/play)",
        ],
    },
    "get_huahuo_up_growth": {
        "description": "获取UP主成长表现数据（粉丝增长趋势）",
        "input_params": ["upper_mid(UP主ID)", "query_type(查询类型:1总量2增量)"],
        "return_fields": [
            "fans_inc7/30/90/180/365(7天/30天/90天/180天/365天粉丝增量)",
            "data_statistics_by_day_vos(按天统计数据: date/count)",
        ],
    },
    "get_huahuo_up_attention_user": {
        "description": "获取UP主粉丝重合的达人列表",
        "input_params": [
            "upper_mid(UP主ID)",
            "fans_range(粉丝量范围:2-1~5W 3-5~10W 4-10~20W 5-20~30W 6-30~50W 7-50~100W 8-100~200W 9-200W以上)",
            "page(页码)",
        ],
        "return_fields": [
            "upper_mid(UP主ID)", "mcn_id(花火ID)", "nickname(昵称)", "fans_num(粉丝数)",
            "price_infos(报价信息)", "tags(标签)",
        ],
    },
    "get_huahuo_up_representative": {
        "description": "获取UP主个人案例/商业案例",
        "input_params": ["upper_mid(UP主ID)", "type(案例类型:1个人2商业)"],
        "return_fields": [
            "av_id/bv_id(视频ID)", "title(标题)", "play_cnt(播放量)",
            "like_cnt(点赞数)", "comment_cnt(评论数)", "pub_time(发布时间)",
        ],
    },
    "get_huahuo_up_similar_content": {
        "description": "获取UP主内容重合的达人列表",
        "input_params": ["upper_mid(UP主ID)"],
        "return_fields": [
            "upper_mid(UP主ID)", "mcn_id(花火ID)", "nickname(昵称)",
            "fans_num(粉丝数)", "tags(标签)", "price_infos(报价信息)",
        ],
    },
    "get_huahuo_up_highlights": {
        "description": "获取UP主稿件亮点数据（热门/爆款视频统计）",
        "input_params": ["upper_mid(UP主ID)", "type(时间范围:1近30天2近90天3近180天)"],
        "return_fields": [
            "avid_cnt(投稿数)", "hot_cnt(热门稿件数)", "explode_cnt(爆款视频数)",
            "hot_rate(热门率)", "explode_rate(爆款率)", "high_interact_rate(高互动率)",
        ],
    },
    "get_huahuo_signed_up_list": {
        "description": "获取签约UP主列表",
        "input_params": ["page(页码)", "size(每页条数)"],
        "return_fields": [
            "result(UP主列表)", "up_mid(UP主ID)", "name(昵称)", "face(头像)",
            "total_fans(总粉丝)", "fans(新增粉丝)", "archives(总投稿)", "plays(总播放)",
        ],
    },
    "get_huahuo_task_info": {
        "description": "获取任务基础内容",
        "input_params": ["task_no(任务编号)"],
        "return_fields": [
            "task_id(任务ID)", "task_no(任务编号)", "task_title(任务标题)",
            "brand_name(品牌名)", "total_money(金额)", "execution_start_time(执行开始)",
        ],
    },
    "get_huahuo_order_info": {
        "description": "获取订单基础内容",
        "input_params": ["order_no(订单编号)"],
        "return_fields": [
            "order_id(订单ID)", "order_no(订单编号)", "nickname(UP主昵称)",
            "price(订单金额)", "platform_price(平台价)", "status_desc(状态)",
            "cooperation_type_desc(合作类型)",
        ],
    },
    "get_huahuo_fav_lists": {
        "description": "获取收藏清单列表",
        "input_params": [],
        "return_fields": [
            "folder_id(清单ID)", "folder_name(清单名称)", "file_num(UP主数量)",
        ],
    },
    "get_huahuo_fav_up_list": {
        "description": "获取清单中的UP主数据",
        "input_params": ["folder_id(清单ID)", "page(页码)", "size(每页条数)"],
        "return_fields": [
            "mapping_id(花火ID)", "upper_mid(B站UID)", "nickname(昵称)",
            "fans_num(粉丝数)", "median_play_cnt(播放量中位数)", "price_infos(报价)",
        ],
    },
    "add_huahuo_fav": {
        "description": "添加UP主到清单",
        "input_params": ["folder_id(清单ID)", "mapping_ids(花火ID,多个逗号分隔)"],
        "return_fields": ["data(操作结果)"],
    },
    "cancel_huahuo_fav": {
        "description": "从清单中移除UP主",
        "input_params": ["folder_id(清单ID)", "mapping_id(花火ID)"],
        "return_fields": ["data(操作结果)"],
    },
    "get_huahuo_partitions": {
        "description": "获取UP主分区列表（B站内容分类）",
        "input_params": [],
        "return_fields": [
            "分区树形结构: id/label/children",
        ],
    },
    "get_huahuo_regions": {
        "description": "获取地域列表（中国省份城市）",
        "input_params": [],
        "return_fields": [
            "地域树形结构: id/label/children",
        ],
    },
    "get_huahuo_content_tags": {
        "description": "获取内容标签列表",
        "input_params": [],
        "return_fields": [
            "标签树形结构: id/label/children",
        ],
    },
    "get_huahuo_service_providers": {
        "description": "获取服务商列表",
        "input_params": [],
        "return_fields": [
            "service_provider_name(服务商名称)", "contacts(联系人)", "cooperated_brands(合作品牌)",
        ],
    },
}
