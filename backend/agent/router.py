"""
Agent 路由模块

对外暴露 HTTP 接口。
关键容错设计：
- LLM 选型失败 → 返回 500 错误，不崩溃。
- 单个达人抓取失败 → batch_planner 内部捕获，继续处理剩余。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from agent.batch_planner import (
    generate_plan,
    run_batch_task,
    get_task_status,
    cancel_task,
    _update_task_cache,
)
from agent.tools import build_openai_functions
from api.excel_parser import parse_excel
from models.schemas import BatchTaskRequest, ChatRequest, PlanTaskRequest

import asyncio
import json
import uuid
from datetime import datetime, timezone

router = APIRouter(prefix="/api", tags=["Agent"])


@router.post("/upload-excel")
async def upload_excel(file: UploadFile = File(...)):
    if not file.filename or not (file.filename.endswith(".xlsx") or file.filename.endswith(".xls")):
        raise HTTPException(status_code=422, detail="仅支持 .xlsx 或 .xls")
    content = await file.read()
    result = parse_excel(content)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return {"code": 0, "message": "success", "data": result}


@router.post("/start-task")
async def start_task(
    request: Request,
    question: str = Form(...),
    file: UploadFile = File(...),
    topic: str | None = Form(None),
    start_date: str | None = Form(None),
    plan_json: str | None = Form(None),
):
    """创建批量抓取任务，立即返回 task_id，任务在后台运行。

    前端拿到 task_id 后，通过 /api/task-progress/{task_id} SSE 接收实时进度。
    """
    logger = __import__("logging").getLogger(__name__)
    logger.info(f"[Router] start-task 收到请求: question={question[:30]!r}, "
                f"file={file.filename!r}, topic={topic!r}, start_date={start_date!r}, "
                f"plan_json_len={len(plan_json) if plan_json else 0}")

    if not file.filename or not (file.filename.endswith(".xlsx") or file.filename.endswith(".xls")):
        logger.error(f"[Router] 文件类型错误: {file.filename}")
        raise HTTPException(status_code=422, detail="仅支持 .xlsx 或 .xls")

    content = await file.read()
    logger.info(f"[Router] 文件大小: {len(content)} bytes")

    parse_result = parse_excel(content)
    logger.info(f"[Router] Excel 解析结果: {parse_result}")

    if "error" in parse_result:
        logger.error(f"[Router] Excel 解析失败: {parse_result['error']}")
        raise HTTPException(status_code=422, detail=parse_result["error"])

    creators = parse_result.get("creators", [])
    logger.info(f"[Router] 解析到 {len(creators)} 个达人")
    if not creators:
        logger.error("[Router] Excel 中未解析到有效的达人数据")
        raise HTTPException(status_code=422, detail="Excel 中未解析到有效的达人数据")

    # 解析 plan
    filters = {}
    if topic:
        filters["topic"] = topic
    if start_date:
        filters["start_date"] = start_date

    if plan_json:
        try:
            plan = json.loads(plan_json)
            logger.info("[Router] 使用前端传入的 plan_json，跳过 LLM 选型")
        except json.JSONDecodeError as exc:
            logger.error(f"[Router] plan_json 解析失败: {exc}")
            raise HTTPException(status_code=422, detail=f"plan_json 格式错误: {exc}")
    else:
        tools = build_openai_functions()
        try:
            plan = await generate_plan(question, tools, filters)
        except Exception as exc:
            logger.error(f"[Router] LLM 选型失败: {exc}")
            raise HTTPException(status_code=500, detail=f"LLM 接口选型失败: {exc}")

    # 生成 task_id 并启动后台任务
    task_id = str(uuid.uuid4())
    await _update_task_cache(task_id, total=len(creators), status="initializing", videos=[])

    # 启动后台任务（不阻塞响应）
    asyncio.create_task(run_batch_task(question, creators, plan, task_id=task_id))

    logger.info(f"[Router] 任务 {task_id} 已创建并转入后台运行")
    return {"code": 0, "message": "success", "task_id": task_id}


@router.post("/plan-task")
async def plan_task(request: PlanTaskRequest):
    """同步接口：LLM 接口选型，返回可直接执行的计划。

    前端应先调用此接口拿到 plan，再携带 plan_json 去 /start-task 创建任务。
    """
    _logger = __import__("logging").getLogger(__name__)
    tools = build_openai_functions()
    filters = {}
    if request.topic:
        filters["topic"] = request.topic
    if request.start_date:
        filters["start_date"] = request.start_date

    _logger.info(f"[Router] plan-task 收到请求: question={request.question[:60]!r}, "
                 f"topic={request.topic!r}, start_date={request.start_date!r}")

    try:
        plan = await generate_plan(request.question, tools, filters)
    except Exception as exc:
        _logger.error(f"[Router] LLM 选型失败: {exc}")
        raise HTTPException(status_code=500, detail=f"LLM 接口选型失败: {exc}")

    _logger.info(f"[Router] plan-task 选型结果: tool_calls={[tc['tool'] for tc in plan.get('tool_calls', [])]}, "
                 f"filters={plan.get('filters', {})}, reasoning={plan.get('reasoning', '')[:100]!r}")

    return {"code": 0, "message": "success", "plan": plan}


@router.get("/task-progress/{task_id}")
async def task_progress(task_id: str):
    """SSE 接口：推送指定任务的实时进度。

    只从 task_cache 读取并推送，不影响后台任务运行。
    SSE 断开/重连不会导致任务重复或中断。
    """
    cache = get_task_status(task_id)
    if cache is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    async def stream():
        # 先推当前缓存快照（帮助前端恢复状态）
        # 使用 initial_cache 避免与循环内的 current 变量名冲突（Python 闭包局部变量规则）
        initial_cache = cache
        yield _sse_event("resume", {
            "task_id": task_id,
            "status": initial_cache.get("status", "unknown"),
            "completed": initial_cache.get("completed", 0),
            "total": initial_cache.get("total", 0),
            "matched_so_far": initial_cache.get("matched_so_far", 0),
            "videos": initial_cache.get("videos", []),
        })

        status = initial_cache.get("status", "")
        if status in ("completed", "cancelled", "error"):
            yield _sse_event("final", {
                "total_creators": initial_cache.get("total", 0),
                "matched_videos": initial_cache.get("matched_so_far", 0),
                "videos": initial_cache.get("videos", []),
            })
            yield _sse_event("done", {})
            return

        # 任务仍在运行中：轮询缓存，每 1 秒推一次增量进度
        prev_completed = initial_cache.get("completed", 0)
        while True:
            await asyncio.sleep(1)
            current = get_task_status(task_id)
            if current is None:
                yield _sse_event("error", {"message": "任务已丢失"})
                yield _sse_event("done", {})
                return

            status = current.get("status", "")
            completed = current.get("completed", 0)
            matched = current.get("matched_so_far", 0)

            # 只在 completed 变化时推送 progress（减少无效推送）
            if completed > prev_completed:
                prev_completed = completed
                yield _sse_event("progress", {
                    "completed": completed,
                    "total": current.get("total", 0),
                    "matched_so_far": matched,
                })

            if status in ("completed", "cancelled", "error"):
                yield _sse_event("final", {
                    "total_creators": current.get("total", 0),
                    "matched_videos": matched,
                    "videos": current.get("videos", []),
                })
                yield _sse_event("done", {})
                return

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/cancel-task")
async def cancel_task_endpoint(task_id: str = Form(...)):
    """取消指定任务。前端点击'取消'时调用。"""
    found = cancel_task(task_id)
    if not found:
        raise HTTPException(status_code=404, detail="任务不存在或已结束")
    return {"code": 0, "message": "任务已取消"}


@router.get("/task-status")
async def task_status(task_id: str):
    """查询指定任务的当前状态（用于前端刷新后恢复 / 轮询）。"""
    cache = get_task_status(task_id)
    if cache is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return {"code": 0, "data": cache}


@router.get("/download-result")
async def download_result(file: str):
    """下载后端生成的 Excel 结果文件。"""
    results_dir = Path(__file__).parent.parent / "results"
    filepath = results_dir / file
    # 安全检查：防止目录遍历攻击
    try:
        filepath_resolved = filepath.resolve()
        results_dir_resolved = results_dir.resolve()
        if not str(filepath_resolved).startswith(str(results_dir_resolved)):
            raise HTTPException(status_code=400, detail="非法文件名")
    except (OSError, ValueError):
        raise HTTPException(status_code=400, detail="非法文件名")
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        filepath,
        filename=file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/health")
async def health():
    return {"status": "ok", "service": "ai-agent-backend"}


def _sse_event(event: str, data: dict) -> str:
    payload = {
        "event": event,
        "content": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
