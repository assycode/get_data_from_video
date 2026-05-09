"""
Agent 路由模块

对外暴露 HTTP 接口，通过 SSE 流式返回整个过程。
关键容错设计：
- LLM 选型失败 → 通过 SSE error 事件推送给前端，不崩溃。
- 单个达人抓取失败 → batch_planner 内部捕获，继续处理剩余。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from agent.batch_planner import (
    generate_plan,
    run_batch_task,
    get_task_status,
    cancel_task,
    task_cache,
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
    # api.excel_parser import parse_excel
    result = parse_excel(content)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return {"code": 0, "message": "success", "data": result}


@router.post("/batch-task-from-excel")
async def batch_task_from_excel(
    question: str = Form(...),
    file: UploadFile = File(...),
    topic: str | None = Form(None),
    start_date: str | None = Form(None),
    plan_json: str | None = Form(None),
):
    if not file.filename or not (file.filename.endswith(".xlsx") or file.filename.endswith(".xls")):
        raise HTTPException(status_code=422, detail="仅支持 .xlsx 或 .xls")

    """解析excel中的达人数据
    """
    content = await file.read()
    parse_result = parse_excel(content)
    if "error" in parse_result:
        raise HTTPException(status_code=422, detail=parse_result["error"])

    creators = parse_result.get("creators", [])
    if not creators:
        raise HTTPException(status_code=422, detail="Excel 中未解析到有效的达人数据")

    """过滤器：字典  通过话题和时间进行过滤
    """
    filters = {}
    if topic:
        filters["topic"] = topic
    if start_date:
        filters["start_date"] = start_date

    # 生成任务唯一标识
    task_id = str(uuid.uuid4())

    """建立一个异步流式函数，一边异步运算一边流式输出到前端
    """
    async def stream():
        yield _sse_event("start", {
            "message": "已解析 Excel，开始批量抓取",
            "total_creators": len(creators),
            "skipped": parse_result.get("skipped", 0),
            "task_id": task_id,
        })

        # 如果前端已经传了 plan_json，直接解析使用，跳过 LLM 选型
        if plan_json:
            try:
                plan = json.loads(plan_json)
                logger = __import__("logging").getLogger(__name__)
                logger.info("[Router] 使用前端传入的 plan_json，跳过 batch_task_from_excel的LLM 选型")
                yield _sse_event("thought", {"plan": plan, "message": "使用已选型的执行计划"})
            except json.JSONDecodeError as exc:
                logger = __import__("logging").getLogger(__name__)
                logger.error(f"[Router] plan_json 解析失败: {exc}")
                yield _sse_event("error", {"message": f"plan_json 格式错误: {exc}"})
                yield _sse_event("done", {})
                return
        else:
            # LLM 接口选型（带错误捕获）
            #from agent.tools import build_openai_functions
            tools = build_openai_functions()
            try:
                plan = await generate_plan(question, tools, filters, creators)
            except Exception as exc:
                logger = __import__("logging").getLogger(__name__)
                logger.error(f"[Router] LLM 选型失败: {exc}")
                yield _sse_event("error", {"message": f"LLM 接口选型失败: {exc}"})
                yield _sse_event("done", {})
                return

            yield _sse_event("thought", {"plan": plan, "message": "已生成执行计划"})

        # 执行批量任务（传入 task_id 用于取消控制和状态缓存）
        try:
            async for event in run_batch_task(question, creators, plan, task_id=task_id):
                yield event
        except asyncio.CancelledError:
            # SSE 断开时触发，run_batch_task 内部已处理取消逻辑
            logger.info(f"[Router] SSE 断开，任务 {task_id} 已取消")
            raise

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )

@router.post("/plan-task")
async def plan_task(request: PlanTaskRequest):
    """同步接口：LLM 接口选型，返回可直接执行的计划。

    前端应先调用此接口拿到 plan，再携带 plan_json 去 /batch-task-from-excel
    执行批量抓取。避免 SSE 长连接因 LLM 选型耗时过长而断开重试。
    """
    # 使用tools.build_openai_functions()获取符合openai functioncalling的tool集合
    tools = build_openai_functions()
    filters = {}
    if request.topic:
        filters["topic"] = request.topic
    if request.start_date:
        filters["start_date"] = request.start_date

    try:
        plan = await generate_plan(request.question, tools, filters, request.creators)
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.error(f"[Router] LLM 选型失败: {exc}")
        raise HTTPException(status_code=500, detail=f"LLM 接口选型失败: {exc}")

    return {"code": 0, "message": "success", "plan": plan}


@router.post("/start-task")
async def start_task(
    question: str = Form(...),
    file: UploadFile = File(...),
    topic: str | None = Form(None),
    start_date: str | None = Form(None),
    plan_json: str | None = Form(None),
):
    """创建后台批量任务，返回 task_id。

    与 /batch-task-from-excel 不同：此接口不返回 SSE，只创建任务并立即返回 task_id，
    前端随后通过 GET /api/task-progress/{task_id} 建立 SSE 连接接收进度。
    """
    if not file.filename or not (file.filename.endswith(".xlsx") or file.filename.endswith(".xls")):
        raise HTTPException(status_code=422, detail="仅支持 .xlsx 或 .xls")

    content = await file.read()
    parse_result = parse_excel(content)
    if "error" in parse_result:
        raise HTTPException(status_code=422, detail=parse_result["error"])

    creators = parse_result.get("creators", [])
    if not creators:
        raise HTTPException(status_code=422, detail="Excel 中未解析到有效的达人数据")

    filters = {}
    if topic:
        filters["topic"] = topic
    if start_date:
        filters["start_date"] = start_date

    # 生成任务唯一标识
    task_id = str(uuid.uuid4())
    logger = __import__("logging").getLogger(__name__)

    # 生成 plan（优先用前端传入的 plan_json）
    plan = None
    if plan_json:
        try:
            plan = json.loads(plan_json)
            logger.info(f"[Router][start-task] 使用前端传入的 plan_json，task_id={task_id}")
        except json.JSONDecodeError as exc:
            logger.error(f"[Router][start-task] plan_json 解析失败: {exc}")
            raise HTTPException(status_code=422, detail=f"plan_json 格式错误: {exc}")
    else:
        tools = build_openai_functions()
        try:
            plan = await generate_plan(question, tools, filters, creators)
        except Exception as exc:
            logger.error(f"[Router][start-task] LLM 选型失败: {exc}")
            raise HTTPException(status_code=500, detail=f"LLM 接口选型失败: {exc}")

    # 初始化任务缓存
    from agent.batch_planner import _update_task_cache
    await _update_task_cache(
        task_id,
        status="running",
        total=len(creators),
        completed=0,
        matched_so_far=0,
        videos=[],
    )

    # 启动后台协程消费 run_batch_task 的 generator
    # generator 内部会自动更新 task_cache，我们只需消费它即可
    async def _consume():
        async for _ in run_batch_task(question, creators, plan, task_id=task_id):
            pass  # generator 已自动更新 task_cache，无需额外处理

    asyncio.create_task(_consume())
    logger.info(f"[Router][start-task] 任务 {task_id} 已启动，共 {len(creators)} 个达人")

    return {"code": 0, "message": "任务已创建", "task_id": task_id, "total_creators": len(creators)}


@router.get("/task-progress/{task_id}")
async def task_progress(task_id: str):
    """SSE 接口：订阅指定任务的实时进度。

    前端通过此接口接收 task 的进度推送。任务由 /api/start-task 创建。
    """
    cache = get_task_status(task_id)
    if cache is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    async def stream():
        # 复制外层 cache 避免闭包变量覆盖（Python 局部变量规则）
        current_cache = dict(cache) if cache else {}

        # 先推送当前状态快照
        yield _sse_event("start", {
            "task_id": task_id,
            "status": current_cache.get("status", "unknown"),
            "completed": current_cache.get("completed", 0),
            "total": current_cache.get("total", 0),
            "total_creators": current_cache.get("total", 0),  # 兼容前端
            "matched_so_far": current_cache.get("matched_so_far", 0),
            "videos": current_cache.get("videos", []),
        })

        status = current_cache.get("status", "")
        if status in ("completed", "cancelled", "done"):
            yield _sse_event("final", {
                "total_creators": current_cache.get("total", 0),
                "matched_videos": current_cache.get("matched_so_far", 0),
                "videos": current_cache.get("videos", []),
            })
            yield _sse_event("done", {})
            return

        # 轮询缓存，每 2 秒推一次进度，直到完成或取消
        prev_completed = current_cache.get("completed", 0)
        while True:
            await asyncio.sleep(2)
            current_cache = get_task_status(task_id)
            if current_cache is None:
                yield _sse_event("error", {"message": "任务已丢失"})
                yield _sse_event("done", {})
                return

            status = current_cache.get("status", "")
            completed = current_cache.get("completed", 0)
            matched = current_cache.get("matched_so_far", 0)

            if completed > prev_completed:
                prev_completed = completed
                yield _sse_event("progress", {
                    "completed": completed,
                    "total": current_cache.get("total", 0),
                    "matched_so_far": matched,
                })

            if status in ("completed", "cancelled", "done"):
                yield _sse_event("final", {
                    "total_creators": current_cache.get("total", 0),
                    "matched_videos": matched,
                    "videos": current_cache.get("videos", []),
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
    """查询指定任务的当前状态（用于前端刷新后恢复）。"""
    cache = get_task_status(task_id)
    if cache is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return {"code": 0, "data": cache}


@router.post("/resume-task")
async def resume_task(task_id: str = Form(...)):
    """前端刷新后重新订阅已有任务的 SSE 流。

    如果任务仍在运行中，建立新的 SSE 连接并继续推送后续进度。
    如果任务已完成或已取消，直接返回 final 结果。
    """
    cache = get_task_status(task_id)
    if cache is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    async def stream():
        # 复制外层 cache 避免闭包变量覆盖
        current_cache = dict(cache) if cache else {}

        # 先把当前缓存的快照推给前端恢复状态
        yield _sse_event("resume", {
            "task_id": task_id,
            "status": current_cache.get("status", "unknown"),
            "completed": current_cache.get("completed", 0),
            "total": current_cache.get("total", 0),
            "total_creators": current_cache.get("total", 0),  # 兼容前端
            "matched_so_far": current_cache.get("matched_so_far", 0),
            "videos": current_cache.get("videos", []),
        })

        status = current_cache.get("status", "")
        if status in ("completed", "cancelled", "done"):
            yield _sse_event("final", {
                "total_creators": current_cache.get("total", 0),
                "matched_videos": current_cache.get("matched_so_far", 0),
                "videos": current_cache.get("videos", []),
            })
            yield _sse_event("done", {})
            return

        # 任务仍在运行中：轮询缓存，每 2 秒推一次进度，直到完成或取消
        prev_completed = current_cache.get("completed", 0)
        while True:
            await asyncio.sleep(2)
            current_cache = get_task_status(task_id)
            if current_cache is None:
                yield _sse_event("error", {"message": "任务已丢失"})
                yield _sse_event("done", {})
                return

            status = current_cache.get("status", "")
            completed = current_cache.get("completed", 0)
            matched = current_cache.get("matched_so_far", 0)

            if completed > prev_completed:
                prev_completed = completed
                yield _sse_event("progress", {
                    "completed": completed,
                    "total": current_cache.get("total", 0),
                    "matched_so_far": matched,
                })

            if status in ("completed", "cancelled", "done"):
                yield _sse_event("final", {
                    "total_creators": current_cache.get("total", 0),
                    "matched_videos": matched,
                    "videos": current_cache.get("videos", []),
                })
                yield _sse_event("done", {})
                return

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


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
