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

from agent.batch_planner import generate_plan, run_batch_task
from agent.tools import build_openai_functions
from api.excel_parser import parse_excel
from models.schemas import BatchTaskRequest, ChatRequest, PlanTaskRequest

import json
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

    """建立一个异步流式函数，一边异步运算一边流式输出到前端
    """
    async def stream():
        yield _sse_event("start", {
            "message": "已解析 Excel，开始批量抓取",
            "total_creators": len(creators),
            "skipped": parse_result.get("skipped", 0),
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
            tools = build_openai_functions()
            try:
                plan = await generate_plan(question, tools, filters)
            except Exception as exc:
                logger = __import__("logging").getLogger(__name__)
                logger.error(f"[Router] LLM 选型失败: {exc}")
                yield _sse_event("error", {"message": f"LLM 接口选型失败: {exc}"})
                yield _sse_event("done", {})
                return

            yield _sse_event("thought", {"plan": plan, "message": "已生成执行计划"})

        # 执行批量任务
        async for event in run_batch_task(question, creators, plan):
            yield event

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )

"""使用tools.build_openai_functions()获取符合openai functioncalling的tool集合
"""
@router.post("/plan-task")
async def plan_task(request: PlanTaskRequest):
    """同步接口：LLM 接口选型，返回可直接执行的计划。

    前端应先调用此接口拿到 plan，再携带 plan_json 去 /batch-task-from-excel
    执行批量抓取。避免 SSE 长连接因 LLM 选型耗时过长而断开重试。
    """
    tools = build_openai_functions()
    filters = {}
    if request.topic:
        filters["topic"] = request.topic
    if request.start_date:
        filters["start_date"] = request.start_date

    try:
        plan = await generate_plan(request.question, tools, filters)
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.error(f"[Router] LLM 选型失败: {exc}")
        raise HTTPException(status_code=500, detail=f"LLM 接口选型失败: {exc}")

    return {"code": 0, "message": "success", "plan": plan}


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
