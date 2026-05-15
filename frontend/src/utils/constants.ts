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

/** 合并列配置（通用） */
export const COLUMN_MAP: Record<string, ColumnConfig> = {
  ...BILIBILI_COLUMN_MAP,
  ...DOUYIN_COLUMN_MAP,
  ...XIAOHONGSHU_COLUMN_MAP,
  ...KUAISHOU_COLUMN_MAP,
}
