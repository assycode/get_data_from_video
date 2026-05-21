// =============================================================================
// 常量定义 - 列配置等
// =============================================================================

import type { ColumnConfig } from '../types'

/** B站列配置 */
export const BILIBILI_COLUMN_MAP: Record<string, ColumnConfig> = {
  creator_nickname: { label: 'UP主', width: 120 },
  title: { label: '标题', minWidth: 200 },
  pubdate: { label: '发布时间', width: 160 },
  description: { label: '描述', minWidth: 200 },
  dynamic: { label: '动态', minWidth: 150 },
  duration: { label: '时长(秒)', width: 100 },
  bvid: { label: 'BV号', width: 140 },
  aid: { label: 'AID', width: 120 },
  view: { label: '播放量', width: 100, align: 'right' },
  danmaku: { label: '弹幕', width: 90, align: 'right' },
  reply: { label: '评论', width: 90, align: 'right' },
  favorite: { label: '收藏', width: 90, align: 'right' },
  coin: { label: '投币', width: 90, align: 'right' },
  share: { label: '分享', width: 90, align: 'right' },
  like: { label: '点赞', width: 90, align: 'right' },
  tags: { label: '标签', minWidth: 150 },
  participle: { label: '话题', minWidth: 150 },
  url: { label: '链接', width: 80 },
  creator_mid: { label: 'UP主MID', width: 120 },
  follower: { label: '粉丝数', width: 100, align: 'right' },
  following: { label: '关注数', width: 100, align: 'right' },
  sign: { label: '签名', minWidth: 200 },
  level: { label: '等级', width: 80 },
}

/** 抖音列配置 */
export const DOUYIN_COLUMN_MAP: Record<string, ColumnConfig> = {
  creator_nickname: { label: '达人昵称', width: 120 },
  desc: { label: '标题/描述', minWidth: 200 },
  create_time: { label: '发布时间', width: 160 },
  duration: { label: '时长', width: 100 },
  aweme_id: { label: '视频ID', width: 160 },
  play_count: { label: '播放量', width: 100, align: 'right' },
  digg_count: { label: '点赞', width: 90, align: 'right' },
  comment_count: { label: '评论', width: 90, align: 'right' },
  share_count: { label: '分享', width: 90, align: 'right' },
  author_nickname: { label: '作者昵称', width: 120 },
  author_unique_id: { label: '抖音号', width: 120 },
  url: { label: '链接', width: 80 },
  text_extra: { label: '话题标签', minWidth: 150 },
}

/** 小红书列配置 */
export const XIAOHONGSHU_COLUMN_MAP: Record<string, ColumnConfig> = {
  creator_nickname: { label: '达人昵称', width: 120 },
  nickname: { label: '达人昵称', width: 120 },
  title: { label: '标题', minWidth: 200 },
  content: { label: '内容', minWidth: 200 },
  date: { label: '发布时间', width: 120 },
  isVideo: { label: '是否视频', width: 90 },
  note_id: { label: '笔记ID', width: 160 },
  noteId: { label: '笔记ID', width: 160 },
  readNum: { label: '阅读量', width: 100, align: 'right' },
  likeNum: { label: '点赞', width: 90, align: 'right' },
  collectNum: { label: '收藏', width: 90, align: 'right' },
  shareNum: { label: '分享', width: 90, align: 'right' },
  cmtNum: { label: '评论', width: 90, align: 'right' },
  imgUrl: { label: '封面图', width: 100 },
  contentTags: { label: '话题标签', minWidth: 150 },
  url: { label: '链接', width: 80 },
  user_id: { label: '用户ID', width: 160 },
  creator_mid: { label: '用户ID', width: 160 },
}

/** 快手列配置 */
export const KUAISHOU_COLUMN_MAP: Record<string, ColumnConfig> = {
  creator_nickname: { label: '达人昵称', width: 120 },
  nickname: { label: '达人昵称', width: 120 },
  caption: { label: '标题', minWidth: 200 },
  title: { label: '标题', minWidth: 200 },
  time: { label: '发布时间', width: 160 },
  timestamp: { label: '时间戳', width: 120 },
  photo_id: { label: '视频ID', width: 160 },
  photoId: { label: '视频ID', width: 160 },
  view_count: { label: '播放量', width: 100, align: 'right' },
  like_count: { label: '点赞', width: 90, align: 'right' },
  comment_count: { label: '评论', width: 90, align: 'right' },
  share_count: { label: '分享', width: 90, align: 'right' },
  forward_count: { label: '转发', width: 90, align: 'right' },
  unlike_count: { label: '不喜欢', width: 90, align: 'right' },
  duration: { label: '时长(毫秒)', width: 100 },
  cover_urls: { label: '封面图', width: 100 },
  imgUrl: { label: '封面图', width: 100 },
  url: { label: '链接', width: 80 },
  uid: { label: '用户ID', width: 160 },
  user_id: { label: '用户ID', width: 160 },
  creator_mid: { label: '用户ID', width: 160 },
  kwaiId: { label: '快手号', width: 120 },
  user_name: { label: '用户名', width: 120 },
  headurl: { label: '头像', width: 100 },
  fan: { label: '粉丝数', width: 100, align: 'right' },
  photo: { label: '作品数', width: 100, align: 'right' },
  follow: { label: '关注数', width: 100, align: 'right' },
}

/** 花火列配置 */
export const HUAHUO_COLUMN_MAP: Record<string, ColumnConfig> = {
  // 基础信息
  upper_mid: { label: 'UP主MID', width: 120 },
  mapping_id: { label: '花火账号ID', width: 140 },
  mcn_id: { label: 'MCN ID', width: 120 },
  nickname: { label: '达人昵称', width: 120 },
  fans_num: { label: '粉丝数', width: 100, align: 'right' },
  fans_like_num: { label: '粉丝点赞数', width: 100, align: 'right' },
  
  // 分区
  partition_name: { label: '一级分区', width: 120 },
  second_partition_name: { label: '二级分区', width: 120 },
  partition_full_path: { label: '分区路径', minWidth: 200 },
  has_partition: { label: '有分区', width: 80 },
  
  // 播放数据
  average_play_cnt: { label: '平均播放量', width: 110, align: 'right' },
  average_interactive_rate: { label: '平均互动率', width: 110, align: 'right' },
  
  // 报价
  upper_prices: { label: '报价信息', minWidth: 150 },
  custom_price: { label: '自定义报价', width: 110, align: 'right' },
  star_price: { label: '星任务报价', width: 110, align: 'right' },
  
  // MCN
  mcn_company_name: { label: 'MCN公司名称', minWidth: 150 },
  is_mcn: { label: '是否MCN', width: 90 },
  
  // 趋势数据
  upper_draft_trend_info_vos: { label: '作品趋势数据', minWidth: 200 },
  min_cnt: { label: '最小值', width: 90, align: 'right' },
  max_cnt: { label: '最大值', width: 90, align: 'right' },
  median: { label: '中位数', width: 90, align: 'right' },
  
  // 成长数据
  fans_inc7: { label: '7日粉丝增量', width: 110, align: 'right' },
  fans_inc30: { label: '30日粉丝增量', width: 110, align: 'right' },
  fans_inc90: { label: '90日粉丝增量', width: 110, align: 'right' },
  fans_inc180: { label: '180日粉丝增量', width: 110, align: 'right' },
  fans_inc365: { label: '365日粉丝增量', width: 110, align: 'right' },
  play_inc30: { label: '30日播放增量', width: 110, align: 'right' },
  play_inc_median: { label: '播放中位数', width: 110, align: 'right' },
  data_statistics_by_day_vos: { label: '每日统计数据', minWidth: 200 },
  
  // 亮点数据
  avid_cnt: { label: '投稿数', width: 90, align: 'right' },
  hot_cnt: { label: '热门数', width: 90, align: 'right' },
  explode_cnt: { label: '爆款数', width: 90, align: 'right' },
  hot_rate: { label: '热门率', width: 90, align: 'right' },
  explode_rate: { label: '爆款率', width: 90, align: 'right' },
  high_interact_rate: { label: '高互动率', width: 100, align: 'right' },
  
  // 合作数据
  cooperation_num: { label: '合作数', width: 90, align: 'right' },
  cooperation_upper_num: { label: '合作UP数', width: 100, align: 'right' },
  
  // 其他
  gender: { label: '性别', width: 80 },
  platform: { label: '平台', width: 80 },
  creator_nickname: { label: '达人昵称', width: 120 },
  creator_mid: { label: '达人MID', width: 120 },
  
  // B站通用字段兼容
  mid: { label: 'MID', width: 120 },
  name: { label: '名称', width: 120 },
  sex: { label: '性别', width: 80 },
  face: { label: '头像', width: 100 },
  sign: { label: '签名', minWidth: 200 },
  follower: { label: '粉丝数', width: 100, align: 'right' },
  following: { label: '关注数', width: 100, align: 'right' },
}

/** 合并列配置（通用） */
export const COLUMN_MAP: Record<string, ColumnConfig> = {
  ...BILIBILI_COLUMN_MAP,
  ...DOUYIN_COLUMN_MAP,
  ...XIAOHONGSHU_COLUMN_MAP,
  ...KUAISHOU_COLUMN_MAP,
  ...HUAHUO_COLUMN_MAP,
}
