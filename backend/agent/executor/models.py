"""
工具参数 Pydantic 模型定义。

每个工具对应一套参数模型，用于运行时参数校验和类型转换。
新增工具时，在此追加对应的 Args 模型即可。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class GetUpInfoArgs(BaseModel):
    """获取 UP 主基本信息参数"""
    upper_mid: int = Field(..., description="UP主ID（mid）")


class GetUpFollowerArgs(BaseModel):
    """获取 UP 主粉丝数据参数"""
    upper_mid: int = Field(..., description="UP主ID（mid）")


class GetVideoListArgs(BaseModel):
    """获取视频列表参数"""
    upper_mid: int = Field(..., description="UP主ID（mid）")
    pn: int = Field(default=1, description="页码，从1开始")


class GetVideoDataArgs(BaseModel):
    """获取单个视频基础数据参数"""
    id: str = Field(..., description="视频ID，bvid或aid均可，如 BV1iq4y1o7BS")


class GetVideoDetailArgs(BaseModel):
    """获取视频完整数据（含标签）参数"""
    id: str = Field(..., description="视频ID，bvid或aid均可")


class ResolveShortUrlArgs(BaseModel):
    """解析B站短链接参数"""
    short_code: str = Field(..., description="短链接代码，如 b23.tv/xxxx 中的 xxxx 部分")


class GetDouyinVideoDetailArgs(BaseModel):
    """批量获取抖音视频详情参数"""
    ids: str = Field(..., description="视频ID，多个用逗号分隔，单次最多20个。如 '7098235952635579679,7148762346909961503'")


class GetDouyinShortUrlArgs(BaseModel):
    """获取抖音用户短链接参数"""
    sec_uid: str = Field(..., description="用户加密ID（sec_uid）")


class GetDouyinAcNonceArgs(BaseModel):
    """获取抖音 ac_nonce 参数"""
    aweme_id: str = Field(..., description="视频ID（aweme_id）")


class GetDouyinFollowerArgs(BaseModel):
    """获取抖音达人粉丝参数"""
    aweme_id: str = Field(..., description="视频ID（aweme_id）")
    ac_nonce: str = Field(..., description="ac_nonce 标识")
    ac_signature: str = Field(default="", description="ac_signature 签名令牌（文档缺失获取方式，需外部传入）")


class GetDouyinRoomIdArgs(BaseModel):
    """获取抖音用户直播房间号参数"""
    uid: str = Field(..., description="抖音用户数字UID")


class GetDouyinUserVideosArgs(BaseModel):
    """获取抖音用户视频列表参数（文档不完整，预留）"""
    sec_uid: str = Field(..., description="用户加密ID（sec_uid）")
    cursor: int = Field(default=0, description="分页游标，默认0")


class GetXhsNotesListArgs(BaseModel):
    """获取小红书笔记列表参数"""
    user_id: str = Field(..., description="小红书用户ID")
    page_number: int = Field(default=1, description="页码，从1开始")
    page_size: int = Field(default=20, description="每页数量")
    note_type: int = Field(default=4, description="笔记类型 1-图文 2-视频 3-合作 4-全部")
    advertise_switch: int = Field(default=1, description="流量类型 1-全部流量 0-自然流量")
    order_type: int = Field(default=1, description="排序类型 1-最新 2-阅读 3-互动")


class GetXhsNoteInfoArgs(BaseModel):
    """获取小红书笔记详情参数"""
    note_id: str = Field(..., description="笔记ID")


# 快手工具参数模型
class GetKsVideoListArgs(BaseModel):
    """获取快手用户视频列表参数"""
    uid: int | str = Field(..., description="快手用户UID")
    pcursor: int | str | None = Field(default=None, description="时间戳毫秒级别，拉取比当前时间小的数据")


class GetKsVideoDetailArgs(BaseModel):
    """获取快手视频详情参数"""
    photo_id: int | str = Field(..., description="快手视频ID")


class GetKsUserInfoArgs(BaseModel):
    """获取快手用户基础数据参数"""
    uid: int | str = Field(..., description="快手用户UID")


class GetKsTopicListArgs(BaseModel):
    """获取快手话题列表参数"""
    tag: str = Field(..., description="话题标签")
    pcursor: int | str | None = Field(default=None, description="分页游标，用于翻页")


class GetKsShareDataArgs(BaseModel):
    """获取快手视频分享数据参数"""
    photo_id: int | str = Field(..., description="快手视频ID")


class GetKsLiveArgs(BaseModel):
    """获取快手直播数据参数"""
    stream_id: str = Field(..., description="直播ID")


# 花火工具参数模型
class GetHuahuoListArgs(BaseModel):
    """获取花火UP主列表参数"""
    key: str | None = Field(default=None, description="搜索关键词")
    page: int = Field(default=1, description="页码，默认1")
    order_bys: int | None = Field(default=None, description="排序字段，0-综合 1-粉丝升序 2-粉丝降序 3-报价降序 4-报价升序")
    content_tag_id: int | None = Field(default=None, description="内容分类ID")
    commercial_tag_id: str | None = Field(default=None, description="商单类型ID，多个逗号分隔")
    fans_ranges: str | None = Field(default=None, description="粉丝数量范围，多个逗号分隔")
    min_fans_num: int | None = Field(default=None, description="粉丝数最小值")
    max_fans_num: int | None = Field(default=None, description="粉丝数最大值")
    task_price_ranges: str | None = Field(default=None, description="任务价格范围，多个逗号分隔")
    min_task_price: int | None = Field(default=None, description="报价最小值")
    max_task_price: int | None = Field(default=None, description="报价最大值")
    cooperation_types: str | None = Field(default=None, description="合作类型，1-植入视频 2-定制视频 3-直发动态 4-转发动态 -1-非标准")
    region_id: int | None = Field(default=None, description="UP主画像--主分区")
    partition_id: int | None = Field(default=None, description="UP主画像--所在地域省份")
    second_partition_id: int | None = Field(default=None, description="UP主画像--所在地域城市")
    gender: str | None = Field(default=None, description="达人性别，0-男 1-女")


class GetHuahuoUpPortraitArgs(BaseModel):
    """获取UP主个人信息（画像）参数"""
    upper_mid: int = Field(..., description="UP主ID（B站UID）")
    mcn_id: int = Field(..., description="MCN机构ID（花火ID）")


class GetHuahuoUpTrendArgs(BaseModel):
    """获取UP主最新作品参数"""
    upper_mid: int = Field(..., description="UP主ID")
    trend_type: int = Field(default=3, description="数据类型，3-播放量 4-点赞 5-评论 6-弹幕")


class GetHuahuoUpGrowthArgs(BaseModel):
    """获取UP主成长表现参数"""
    upper_mid: int = Field(..., description="UP主ID")
    query_type: int = Field(default=1, description="查询类型，1-总量 2-增量")


class GetHuahuoUpAttentionUserArgs(BaseModel):
    """获取UP主粉丝重合参数"""
    upper_mid: int = Field(..., description="UP主ID")
    fans_range: int = Field(default=6, description="粉丝量范围，2-1~5W 3-5~10W 4-10~20W 5-20~30W 6-30~50W 7-50~100W 8-100~200W 9-200W以上")
    page: int = Field(default=1, description="页码")


class GetHuahuoUpRepresentativeArgs(BaseModel):
    """获取UP主个人案例参数"""
    upper_mid: int = Field(..., description="UP主ID")
    type: int = Field(default=1, description="案例类型，1-个人案例 2-商业案例")


class GetHuahuoUpSimilarContentArgs(BaseModel):
    """获取UP主内容重合资参数"""
    upper_mid: int = Field(..., description="UP主ID")


class GetHuahuoUpHighlightsArgs(BaseModel):
    """获取UP主稿件亮点参数"""
    upper_mid: int = Field(..., description="UP主ID")
    type: int = Field(default=1, description="时间范围，1-近30天 2-近90天 3-近180天")


class GetHuahuoSignedUpListArgs(BaseModel):
    """获取签约UP主列表参数"""
    page: int = Field(default=1, description="页码，默认1")
    size: int = Field(default=50, description="每页条数，默认50")


class GetHuahuoTaskInfoArgs(BaseModel):
    """获取任务基础内容参数"""
    task_no: str = Field(..., description="任务编号")


class GetHuahuoOrderInfoArgs(BaseModel):
    """获取订单基础内容参数"""
    order_no: str = Field(..., description="订单编号")


class GetHuahuoFavUpListArgs(BaseModel):
    """获取清单中的UP主数据参数"""
    folder_id: int = Field(..., description="清单ID")
    page: int = Field(default=1, description="页码，默认1")
    size: int = Field(default=50, description="每页条数，默认50")


class AddHuahuoFavArgs(BaseModel):
    """添加UP主到清单参数"""
    folder_id: int = Field(..., description="清单ID")
    mapping_ids: str = Field(..., description="花火ID，多个逗号分隔")


class CancelHuahuoFavArgs(BaseModel):
    """从清单中移除UP主参数"""
    folder_id: int = Field(..., description="清单ID")
    mapping_id: int = Field(..., description="花火ID")
