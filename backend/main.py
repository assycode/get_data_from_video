"""
FastAPI 应用入口

职责：
1. 创建 FastAPI 实例，配置元数据。
2. 注册全局中间件：CORS（前后端跨域）、异常处理。
3. 挂载子路由：Agent Chat、Excel 上传、批量任务等。
4. 提供直接启动入口（python main.py）。

启动方式：
    uvicorn main:app --reload --port 8000

Swagger 文档：http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent.router import router as agent_router
from config import settings


# ------------------------------------------------------------------------------
# 日志配置（必须在导入其他模块之前设置，确保所有 logger 生效）
# ------------------------------------------------------------------------------

def _setup_logging() -> None:
    """配置根日志记录器，让 INFO 及以上级别的日志输出到控制台。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # 降低 httpx 的日志级别，避免打印过多的连接细节
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


_setup_logging()


# ------------------------------------------------------------------------------
# 应用工厂
# ------------------------------------------------------------------------------

def create_app() -> FastAPI:
    """应用工厂函数。"""

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "AI Agent 后端服务。支持两种模式：\n"
            "1. 单轮对话模式（/api/chat）：基于 OpenAI Function Calling 的智能数据查询。\n"
            "2. 批量抓取模式（/api/batch-task-from-excel）：上传 Excel 达人列表，自动批量抓取数据。\n\n"
            "接口文档通过 docs/api_schema.json 动态加载，支持替换。"
        ),
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(agent_router)

    # 422 详细日志处理器
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc: RequestValidationError):
        logger = logging.getLogger("main")
        logger.error(f"[Main] 422 验证失败: {exc.errors()}")
        return JSONResponse(
            status_code=422,
            content={"code": -1, "message": "请求参数验证失败", "detail": exc.errors()},
        )

    # 全局异常兜底
    @app.exception_handler(Exception)
    async def universal_exception_handler(request, exc):
        return JSONResponse(
            status_code=500,
            content={
                "code": -1,
                "message": "服务器内部错误",
                "detail": str(exc) if settings.DEBUG else None,
            },
        )

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
    )
