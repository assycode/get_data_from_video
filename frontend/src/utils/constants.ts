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

/** 合并列配置（通用） */
export const COLUMN_MAP: Record<string, ColumnConfig> = {
  ...BILIBILI_COLUMN_MAP,
  ...DOUYIN_COLUMN_MAP,
}
