"""
配置管理模块

统一读取环境变量，提供全局配置对象。
所有敏感信息（API Key 等）均通过 .env 文件注入，禁止硬编码。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# 加载 .env 文件
# ------------------------------------------------------------------------------
_ENV_PATH = Path(r"D:\Desktop\fastapi-demo\backend\.env")
load_dotenv(dotenv_path=_ENV_PATH, override=True)


def _getenv(key: str, default: str = "") -> str:
    """读取环境变量，空值时回退到默认值。

    os.getenv 的陷阱：环境变量存在但值为空字符串时，
    会返回 "" 而不是 default。本函数修复此行为。
    """
    val = os.getenv(key)
    return val if val is not None and val.strip() != "" else default


# ------------------------------------------------------------------------------
# 基础配置
# ------------------------------------------------------------------------------
class Settings:
    """应用配置类，所有属性均来自环境变量，提供默认值以方便首次运行。"""

    # --- 服务 ---
    APP_NAME: str = _getenv("APP_NAME", "AI-Agent-Backend")
    APP_VERSION: str = _getenv("APP_VERSION", "0.1.0")
    DEBUG: bool = _getenv("DEBUG", "true").lower() == "true"
    PORT: int = int(_getenv("PORT", "8000"))
    HOST: str = _getenv("HOST", "0.0.0.0")

    # --- CORS ---
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in _getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if origin.strip()
    ]

    # --- 大模型 ---
    LLM_API_KEY: str = _getenv("LLM_API_KEY", "sk-iSnAwGYCE8ayyytoo87gbaJejZdhnOJlpOh0SQaWAYwNSV4T")
    LLM_BASE_URL: str = _getenv("LLM_BASE_URL", "https://api.moonshot.cn/v1")
    LLM_MODEL: str = _getenv("LLM_MODEL", "kimi-k2.5")
    LLM_MAX_TOKENS: int = int(_getenv("LLM_MAX_TOKENS", "8192"))
    LLM_TEMPERATURE: float = float(_getenv("LLM_TEMPERATURE", "1"))
    LLM_WITE_TIME: int = _getenv("LLM_WITE_TIME", "2000")

    # --- LLM Plan 生成配置 ---
    LLM_PLAN_TIMEOUT: int = int(_getenv("LLM_PLAN_TIMEOUT", "600"))  # 超时时间（秒）
    LLM_PLAN_TEMPERATURE: float = float(_getenv("LLM_PLAN_TEMPERATURE", "1.0"))  # 温度
    LLM_PLAN_MAX_ATTEMPTS: int = int(_getenv("LLM_PLAN_MAX_ATTEMPTS", "2"))  # 最大重试次数

    # SYSTEM_PROMPT 模板（可通过环境变量覆盖，或使用默认值）
    LLM_SYSTEM_PROMPT_TEMPLATE: str = _getenv(
        "LLM_SYSTEM_PROMPT_TEMPLATE",
        '''你是一个数据接口调度专家。你的唯一任务是根据用户需求、Excel 中已有的数据字段和可用的数据接口列表，
生成一个按平台分组的工作流规划 JSON。同一批达人可能来自不同平台（B站/抖音/小红书），
你需要为**每个实际出现的平台**编排一套独立的工作流。后端会根据每个达人的 platform 字段自动匹配对应的工作流执行。

## 系统背景
用户上传的 Excel 中，每一行可能包含以下信息（不是全部都有），且不同行可能来自不同平台：
- platform：平台标识（bilibili / douyin / xiaohongshu），由后端从链接域名自动识别
- B站特有：upper_mid（UP主ID）、bvid（视频BV号）、avid（视频AV号）、short_code（b23.tv短链接）
- 抖音特有：sec_uid（用户加密ID，用于获取短链接）、aweme_id（视频ID，用于查视频详情）、uid（抖音数字UID，用于查直播间）
- 小红书特有：user_id（用户ID）、note_id（笔记ID）
- 通用：nickname（昵称）、space_url（主页链接）、各种视频链接

你的任务是按平台分组编排工作流：每个平台一套独立的 tool_sequence，
参数足的步骤就执行，参数不足的步骤自动跳过。

{tools_desc}

## 输出格式（必须严格按此 JSON 格式输出，不要任何其他文字）

{{
  "global_filter": {{
    "topic": "话题关键词，没有就留空字符串",
    "start_date": "开始日期 YYYY-MM-DD，没有就留空",
    "end_date": "结束日期 YYYY-MM-DD，没有就留空"
  }},
  "export_fields": ["字段1", "字段2", ...],
  "workflows": {{
    "bilibili": {{
      "tool_sequence": [
        {{"tool_name": "工具名", "reason": "为什么需要这步"}}
      ],
      "page_rule": {{"enable_page": true, "max_page": 10, "page_size": 50}},
      "each_detail": {{"need_query": true, "tool_name": "get_video_detail"}}
    }},
    "douyin": {{
      "tool_sequence": [...],
      "page_rule": {{...}},
      "each_detail": {{...}}
    }}
  }},
  "reasoning": "你的思考过程，用中文简述"
}}

## 工作流编排指南（必须遵守）
1. **按平台分组编排**：workflows 的 key 是平台名（bilibili / douyin / xiaohongshu），
   只为 Excel 中**实际出现**的平台编排工作流。如果只有 B站达人，workflows 里只放 bilibili。
2. **平台隔离原则**：
   - B站工具（如 get_video_list / get_video_detail）**只能**出现在 bilibili 的工作流中。
   - 抖音工具（如 get_douyin_video_detail）**只能**出现在 douyin 的工作流中。
   - 不同平台的工具**绝对禁止**混用。
3. **按需编排，不要画蛇添足**。每个平台的 tool_sequence 里只放真正需要的步骤：
   - 如果用户只要'这些视频的数据'（输入是 bvid/视频链接），直接调 get_video_data 即可，不需要 get_video_list。
   - 如果用户要'UP主全部视频'或'按时间筛选近期作品'，才需要 get_video_list。
   - 如果用户要'话题/标签'，才需要 get_video_detail。
   - 绝不要'为了保险'而多加步骤。每一步都应该是用户需求直接驱动的。
4. **短链接 vs 普通链接**（B站场景）：
   - 如果 bilibili 平台中有 creator 的 link_type='short' 或 short_code 有值，
     bilibili 的 tool_sequence 里**必须**前置 resolve_short_url。
   - 普通视频链接（bilibili.com/video/BVxxx）不需要 resolve_short_url。
5. **参数推导**：tool_sequence 按依赖顺序排列，但只放必要步骤。
   - 参数不足的步骤后端会自动跳过，不会报错。
   - 编排应该基于**主流数据特征**，而不是极端情况。
6. page_rule 仅对 tool_sequence 最后一步返回列表的工具有效：
   - enable_page=true 时，后端会自动翻页采集。
7. each_detail 用于列表采完后是否逐条查详情：
   - **重要：如果用户需要按话题/标签筛选视频，each_detail.need_query 必须设为 true，且 tool_name 设为对应平台的详情工具（如 get_video_detail / get_douyin_video_detail）**
   - 因为 get_video_list 返回的视频列表不包含完整标签信息，必须通过 each_detail 逐条调用详情接口才能获取 Tags/话题
   - 如果只需要基础数据且无需话题过滤，need_query=false
8. topic/start_date/end_date 必须从用户需求中提取。没有提到就留空字符串（""），严禁臆测。
9. **export_fields 必须完整**：
   - 跨平台场景下，export_fields 可以包含多个平台的字段名（如同时有 bvid 和 aweme_id），
     后端会自动从每个平台的数据中提取对应字段，缺失的留空。
   - **绝对禁止**只返回标识字段（如 ["bvid","mid"] 或 ["aweme_id","sec_uid"]）。
   - 强制模板：只要用户提到'视频'、'数据'、'统计'等词，export_fields 必须至少包含内容+统计字段。
   - B站常用字段：bvid, title, pubdate, duration, view, like, reply, favorite, coin, share, danmaku, creator_nickname, creator_mid, url
   - 抖音常用字段：aweme_id, desc, create_time, duration, play_count, digg_count, comment_count, share_count, nickname, author_uid, url, text_extra
10. 只输出 JSON，不要任何 markdown 代码块标记，不要任何解释性文字。'''
    )

    # --- 数据 API（观星接口）---
    # 接口基础地址，可从接口文档中提取，支持替换
    DATA_API_BASE_URL: str = _getenv("DATA_API_BASE_URL", "http://api-guanxing.changwankeji.com/api")
    # 接口认证密钥（如需要）
    DATA_API_AUTH_KEY: str = _getenv("DATA_API_AUTH_KEY", "")
    # 接口请求超时（秒）
    DATA_API_TIMEOUT: int = int(_getenv("DATA_API_TIMEOUT", "300"))

    # --- Agent 行为 ---
    MAX_TOOL_ITERATIONS: int = int(_getenv("MAX_TOOL_ITERATIONS", "20"))
    MAX_TOOL_RESULT_LENGTH: int = int(_getenv("MAX_TOOL_RESULT_LENGTH", "200000"))
    # 批量任务并发数（同时调用的UP主数量）
    BATCH_CONCURRENCY: int = int(_getenv("BATCH_CONCURRENCY", "3"))
    # 单UP主翻页最大页数（防止无限翻页）
    MAX_PAGE_PER_UP: int = int(_getenv("MAX_PAGE_PER_UP", "10"))


# 全局单例
settings = Settings()

# 启动时打印关键配置（调试用）
import logging
logger = logging.getLogger(__name__)
logger.info(f"[Config] LLM_BASE_URL={settings.LLM_BASE_URL}")
logger.info(f"[Config] LLM_MODEL={settings.LLM_MODEL}")
logger.info(f"[Config] DATA_API_BASE_URL={settings.DATA_API_BASE_URL}")
logger.info(f"[Config] LLM_API_KEY loaded={'Yes' if settings.LLM_API_KEY else 'NO'}")
