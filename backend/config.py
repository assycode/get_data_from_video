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
    LLM_API_KEY: str = _getenv("LLM_API_KEY", "sk-GJnRCMSXKOK36ja6ozfhUC7pT3pw8k7YBFM7j5AnlkNKLtpN")
    LLM_BASE_URL: str = _getenv("LLM_BASE_URL", "https://api.moonshot.cn/v1")
    LLM_MODEL: str = _getenv("LLM_MODEL", "kimi-k2.6")
    LLM_MAX_TOKENS: int = int(_getenv("LLM_MAX_TOKENS", "8192"))
    LLM_TEMPERATURE: float = float(_getenv("LLM_TEMPERATURE", "1"))
    LLM_WITE_TIME: int = _getenv("LLM_WITE_TIME", "2000")

    # --- 数据 API（观星接口）---
    # 接口基础地址，可从接口文档中提取，支持替换
    DATA_API_BASE_URL: str = _getenv("DATA_API_BASE_URL", "http://api-guanxing.changwankeji.com/api")
    # 接口认证密钥（如需要）
    DATA_API_AUTH_KEY: str = _getenv("DATA_API_AUTH_KEY", "")
    # 接口请求超时（秒）
    DATA_API_TIMEOUT: int = int(_getenv("DATA_API_TIMEOUT", "300"))

    # --- Agent 行为 ---
    MAX_TOOL_ITERATIONS: int = int(_getenv("MAX_TOOL_ITERATIONS", "20"))
    MAX_TOOL_RESULT_LENGTH: int = int(_getenv("MAX_TOOL_RESULT_LENGTH", "8000"))
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
