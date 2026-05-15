"""
LLM 工作流规划模块。

负责调用大模型生成按平台分组的工作流规划 JSON，
包括 SYSTEM_PROMPT 构建、达人数据摘要、Plan 生成与校验。
"""
from __future__ import annotations

import asyncio
import json
import logging

from openai import AsyncOpenAI

from config import settings
from models.schemas import LLMWorkflowPlan

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# 全局 LLM 客户端
# ------------------------------------------------------------------------------

_openai_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        logger.info(f"[LLM] 初始化客户端: base_url={settings.LLM_BASE_URL}, model={settings.LLM_MODEL}")
        _openai_client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
    return _openai_client


# ------------------------------------------------------------------------------
# System Prompt（多平台工作流编排）
# ------------------------------------------------------------------------------

# 延迟导入，避免模块加载时的循环导入问题
def _get_tools_desc() -> str:
    logger.debug("[_get_tools_desc] 开始导入 build_tools_prompt")
    try:
        from agent.executor import build_tools_prompt
        logger.debug("[_get_tools_desc] 成功导入 build_tools_prompt")
        result = build_tools_prompt()
        logger.debug(f"[_get_tools_desc] build_tools_prompt 返回长度: {len(result)}")
        return result
    except Exception as e:
        logger.error(f"[_get_tools_desc] 导入或调用失败: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"[_get_tools_desc] 堆栈:\n{traceback.format_exc()}")
        raise


# 使用函数包装，延迟执行，并支持从 config 读取模板
_SYSTEM_PROMPT = None

def _get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is not None:
        logger.debug("[_get_system_prompt] 返回缓存的 SYSTEM_PROMPT")
        return _SYSTEM_PROMPT
    
    logger.debug("[_get_system_prompt] 开始生成 SYSTEM_PROMPT")
    try:
        tools_desc = _get_tools_desc()
        logger.debug(f"[_get_system_prompt] tools_desc 长度: {len(tools_desc)}")
        
        # 使用 config 中的模板，格式化 tools_desc
        logger.debug("[_get_system_prompt] 开始格式化模板")
        _SYSTEM_PROMPT = settings.LLM_SYSTEM_PROMPT_TEMPLATE.format(tools_desc=tools_desc)
        logger.debug(f"[_get_system_prompt] 模板格式化成功，最终长度: {len(_SYSTEM_PROMPT)}")
        return _SYSTEM_PROMPT
    except Exception as e:
        logger.error(f"[_get_system_prompt] 生成失败: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"[_get_system_prompt] 堆栈:\n{traceback.format_exc()}")
        raise


# ------------------------------------------------------------------------------
# 达人数据摘要（给 LLM 的输入）
# ------------------------------------------------------------------------------


def _build_creator_summary(creators: list[dict]) -> str:
    if not creators:
        return "未提供任何达人数据。"
    total = len(creators)

    # 按平台分组统计
    platform_counts: dict[str, int] = {}
    link_types: dict[str, int] = {}
    has_mid = 0
    has_bvid = 0
    has_avid = 0
    has_short = 0
    has_sec_uid = 0
    has_aweme_id = 0
    has_uid = 0
    has_xhs_user_id = 0
    has_xhs_note_id = 0
    for c in creators:
        platform = c.get("platform", "unknown")
        platform_counts[platform] = platform_counts.get(platform, 0) + 1
        lt = c.get("link_type", "unknown")
        link_types[lt] = link_types.get(lt, 0) + 1
        if c.get("upper_mid"):
            has_mid += 1
        if c.get("bvid"):
            has_bvid += 1
        if c.get("avid"):
            has_avid += 1
        if c.get("short_code"):
            has_short += 1
        if c.get("sec_uid"):
            has_sec_uid += 1
        if c.get("aweme_id"):
            has_aweme_id += 1
        if c.get("uid"):
            has_uid += 1
        if c.get("user_id") not in [None, ""]:
            has_xhs_user_id += 1
        if c.get("note_id") not in [None, ""]:
            has_xhs_note_id += 1

    lines = [f"共 {total} 条记录，按平台分布："]
    for plat, count in sorted(platform_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  - {plat}: {count} 条")
    lines.append("")
    lines.append("按 link_type 分布：")
    for lt, count in sorted(link_types.items(), key=lambda x: -x[1]):
        lines.append(f"  - link_type='{lt}': {count} 条")
    if has_mid:
        lines.append(f"  - 含 mid (upper_mid): {has_mid} 条")
    if has_bvid:
        lines.append(f"  - 含 bvid: {has_bvid} 条")
    if has_avid:
        lines.append(f"  - 含 avid: {has_avid} 条")
    if has_short:
        lines.append(f"  - 含 short_code（短链接 b23.tv）: {has_short} 条 ⚠️ bilibili 工作流必须编排 resolve_short_url")
    if has_sec_uid:
        lines.append(f"  - 含 sec_uid（抖音用户加密ID）: {has_sec_uid} 条")
    if has_aweme_id:
        lines.append(f"  - 含 aweme_id（抖音视频ID）: {has_aweme_id} 条")
    if has_uid:
        lines.append(f"  - 含 uid（抖音数字UID）: {has_uid} 条")
    if has_xhs_user_id:
        lines.append(f"  - 含 user_id（小红书用户ID）: {has_xhs_user_id} 条 ⚠️ 小红书工作流必须编排 get_xhs_notes_list")
    if has_xhs_note_id:
        lines.append(f"  - 含 note_id（小红书笔记ID）: {has_xhs_note_id} 条 ⚠️ 可直接调用 get_xhs_note_info")

    # 给 LLM 多个示例，优先覆盖不同 platform + link_type
    samples: list[str] = []
    seen_platforms: set[str] = set()
    # 第一轮：优先取不同 platform 的样本（让 LLM 看到多平台数据）
    for c in creators:
        if len(samples) >= 3:
            break
        plat = c.get("platform", "unknown")
        if plat in seen_platforms:
            continue
        fields = []
        for key in ("nickname", "platform", "link_type", "upper_mid", "bvid", "avid", "short_code", "sec_uid", "aweme_id", "uid", "user_id", "note_id"):
            val = c.get(key)
            if val not in [None, ""]:
                fields.append(f"{key}={val!r}")
        sample_str = f"{{{', '.join(fields)}}}"
        if sample_str:
            samples.append(sample_str)
            seen_platforms.add(plat)
    # 第二轮：补充不同字段特征的样本
    for c in creators:
        if len(samples) >= 3:
            break
        fields = []
        for key in ("nickname", "platform", "link_type", "upper_mid", "bvid", "avid", "short_code", "sec_uid", "aweme_id", "uid", "user_id", "note_id"):
            val = c.get(key)
            if val not in [None, ""]:
                fields.append(f"{key}={val!r}")
        sample_str = f"{{{', '.join(fields)}}}"
        if sample_str and sample_str not in samples:
            samples.append(sample_str)
    lines.append(f"  - 示例记录: {' | '.join(samples)}")
    return "\n".join(lines)


# ------------------------------------------------------------------------------
# Plan 生成
# ------------------------------------------------------------------------------


async def generate_plan(
    question: str,
    tools: list[dict],
    user_filters: dict[str, Any],
    creators: list[dict] | None = None,
) -> dict[str, Any]:
    logger.info(f"[Plan] 开始工作流规划，需求: {question}")

    tools_summary = []
    for t in tools:
        func = t.get("function", {})
        tools_summary.append(f"- {func.get('name', '未知')}: {func.get('description', '无描述')}")
    tools_desc = "\n".join(tools_summary)

    creator_summary = _build_creator_summary(creators or [])

    # 提取实际存在的平台列表
    platforms_in_excel = set()
    for c in creators:
        plat = c.get("platform", "unknown")
        if plat and plat != "unknown":
            platforms_in_excel.add(plat)
    
    # 调试：打印前3个creator的完整数据
    for i, c in enumerate(creators[:3]):
        logger.info(f"[Debug] Creator {i}: platform={c.get('platform')}, user_id={c.get('user_id')!r}, note_id={c.get('note_id')!r}, upper_mid={c.get('upper_mid')}, sec_uid={c.get('sec_uid')}, ks_uid={c.get('ks_uid')!r}, uid={c.get('uid')!r}, aweme_id={c.get('aweme_id')}")
    
    # 根据字段推断平台（如果 platform 字段未设置或不够明确）
    # 使用空字符串检查，避免空字符串被视为 falsy
    has_xhs_fields = any((c.get("user_id") not in [None, ""]) or (c.get("note_id") not in [None, ""]) for c in creators)
    # 抖音：使用 sec_uid 或 aweme_id 判断（uid 可能是快手的，不能作为抖音判断依据）
    has_douyin_fields = any((c.get("sec_uid") not in [None, ""]) or (c.get("aweme_id") not in [None, ""]) for c in creators)
    has_bilibili_fields = any(c.get("upper_mid") or c.get("bvid") for c in creators)
    # 快手：使用 ks_uid 判断（uid 字段可能是通用的，不能单独作为判断依据）
    has_ks_fields = any((c.get("ks_uid") not in [None, ""]) or (c.get("photo_id") not in [None, ""]) for c in creators)
    
    if has_xhs_fields and "xiaohongshu" not in platforms_in_excel:
        platforms_in_excel.add("xiaohongshu")
    if has_douyin_fields and "douyin" not in platforms_in_excel:
        platforms_in_excel.add("douyin")
    if has_bilibili_fields and "bilibili" not in platforms_in_excel:
        platforms_in_excel.add("bilibili")
    if has_ks_fields and "kuaishou" not in platforms_in_excel:
        platforms_in_excel.add("kuaishou")
    
    platforms_str = ", ".join(sorted(platforms_in_excel)) if platforms_in_excel else "未知"
    
    # 根据实际平台生成简化的输出格式示例，避免LLM生成不必要的平台
    workflow_keys = list(platforms_in_excel) if platforms_in_excel else ["bilibili"]
    workflow_examples = []
    for plat in workflow_keys:
        workflow_examples.append(f'    "{plat}": {{"tool_sequence": [...], "page_rule": {{...}}, "each_detail": {{...}}}},')
    workflow_example_str = "\n".join(workflow_examples)
    
    prompt = (
        f"【用户需求】\n{question}\n\n"
        f"【Excel 中已有的数据字段】\n{creator_summary}\n\n"
        f"【Excel 中实际存在的平台】\n"
        f"检测到以下平台的数据: {platforms_str}\n"
        f"字段推断: 小红书={has_xhs_fields}, 抖音={has_douyin_fields}, B站={has_bilibili_fields}, 快手={has_ks_fields}\n\n"
        f"【可用工具列表】\n{tools_desc}\n\n"
        "【强制性规则 - 必须严格遵守】\n"
        "1. **workflows 只能包含以下平台的工作流**: " + ", ".join(platforms_in_excel if platforms_in_excel else ["bilibili"]) + "\n"
        "2. **严禁为未检测到的平台编排工作流** - 不要生成空平台的工作流\n"
        "3. 每个平台的工作流独立编排，工具不能跨平台混用\n"
        "4. 参数不足的步骤会自动跳过，不会报错\n"
        "5. export_fields 可以包含多个平台的字段，缺失的字段后端会自动留空\n\n"
        "【输出格式要求】\n"
        "workflows 只包含实际检测到的平台，格式如下：\n"
        "{\n"
        '  "global_filter": {"topic": "...", "start_date": "...", "end_date": "..."},\n'
        '  "export_fields": [...],\n'
        '  "workflows": {\n'
        f"{workflow_example_str}\n"
        '  },\n'
        '  "reasoning": "..."\n'
        "}\n\n"
        "请严格按上述要求生成工作流规划 JSON："
    )

    client = _get_client()
    max_attempts = settings.LLM_PLAN_MAX_ATTEMPTS
    timeout_seconds = settings.LLM_PLAN_TIMEOUT
    temperature = settings.LLM_PLAN_TEMPERATURE
    last_error = None

    logger.info(f"[Plan] 准备调用 LLM，max_attempts={max_attempts}, timeout={timeout_seconds}s, temperature={temperature}")
    
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f"[Plan] 调用 LLM ({settings.LLM_MODEL})... (attempt {attempt}/{max_attempts})")
            
            # 获取 system prompt（这里可能会触发导入）
            logger.debug("[Plan] 开始获取 system prompt...")
            system_prompt = _get_system_prompt()
            logger.debug(f"[Plan] system prompt 获取成功，长度: {len(system_prompt)}")
            
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=settings.LLM_MAX_TOKENS,
                    temperature=temperature,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            last_error = f"LLM 工作流规划超时（{timeout_seconds}秒）"
            logger.warning(f"[Plan] attempt {attempt} 超时")
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)
        except Exception as exc:
            last_error = f"LLM 工作流规划失败: {exc}"
            logger.error(f"[Plan] attempt {attempt} 失败: {type(exc).__name__}: {exc}")
            import traceback
            logger.error(f"[Plan] 堆栈:\n{traceback.format_exc()}")
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)

        choice = response.choices[0]
        msg = choice.message
        content = msg.content or ""
        
        # 打印 LLM 返回的原始内容用于调试
        logger.info(f"[Plan] LLM 原始返回内容:\n{content[:2000]}...")

        if not content.strip():
            last_error = f"LLM 返回空内容 (finish_reason={choice.finish_reason})"
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)

        try:
            raw_plan = json.loads(content)
        except json.JSONDecodeError as exc:
            last_error = f"LLM 返回格式错误: {exc}"
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)

        if isinstance(raw_plan, str):
            try:
                raw_plan = json.loads(raw_plan)
            except json.JSONDecodeError as exc:
                last_error = f"LLM 返回双重序列化 JSON 解析失败: {exc}"
                if attempt < max_attempts:
                    continue
                raise RuntimeError(last_error)

        if not isinstance(raw_plan, dict):
            last_error = f"LLM 返回格式错误（不是 dict 而是 {type(raw_plan).__name__}）"
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)

        # 用 Pydantic 强校验
        try:
            workflow_plan = LLMWorkflowPlan(**raw_plan)
        except Exception as exc:
            last_error = f"LLM 返回工作流结构校验失败: {exc}"
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)

        # 白名单校验：所有平台 workflow 中的工具必须在注册表中
        logger.debug("[Plan] 开始白名单校验...")
        from agent.executor import get_tool_names
        invalid_tools = set()
        valid_tool_names = set(get_tool_names())
        logger.debug(f"[Plan] 白名单工具数量: {len(valid_tool_names)}")
        for plat, wf in (workflow_plan.workflows or {}).items():
            for step in wf.tool_sequence:
                if step.tool_name not in valid_tool_names:
                    invalid_tools.add(f"{plat}.{step.tool_name}")
            if wf.each_detail.need_query and wf.each_detail.tool_name not in valid_tool_names:
                invalid_tools.add(f"{plat}.{wf.each_detail.tool_name}")

        if invalid_tools:
            last_error = f"LLM 返回了未知工具: {invalid_tools}"
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)

        # 校验 workflows 不能为空
        if not workflow_plan.workflows or len(workflow_plan.workflows) == 0:
            last_error = "LLM 返回的工作流为空，请检查提示词或重试"
            logger.warning(f"[Plan] attempt {attempt} 失败: workflows 为空")
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)

        logger.info(f"[Plan] attempt {attempt} 验证通过")
        break

    if "workflow_plan" not in locals() or workflow_plan is None:
        raise RuntimeError(last_error or "LLM 工作流规划未知错误")

    # 合并用户传入的兜底过滤条件
    gf = workflow_plan.global_filter
    if not gf.topic and user_filters.get("topic"):
        gf.topic = user_filters["topic"]
    if not gf.start_date and user_filters.get("start_date"):
        gf.start_date = user_filters["start_date"]
    if not gf.end_date and user_filters.get("end_date"):
        gf.end_date = user_filters["end_date"]

    # 转回 dict 保持与原有接口兼容
    try:
        plan = workflow_plan.model_dump()
        logger.info(f"[Plan] model_dump() 成功，plan type={type(plan)}")
    except Exception as exc:
        logger.error(f"[Plan] model_dump() 失败: {exc}")
        raise
    
    # 测试 JSON 序列化
    try:
        json_str = json.dumps(plan, ensure_ascii=False)
        logger.info(f"[Plan] JSON 序列化成功，长度={len(json_str)}")
    except Exception as exc:
        logger.error(f"[Plan] JSON 序列化失败: {exc}")
        raise
    
    # 日志：输出每个平台的工作流
    wf_summary = []
    for plat, wf in (plan.get("workflows") or {}).items():
        wf_summary.append(f"{plat}: {[s['tool_name'] for s in wf.get('tool_sequence', [])]}")
    logger.info(
        f"[Plan] 工作流规划成功: workflows={' | '.join(wf_summary)}, "
        f"filters={plan['global_filter']}"
    )
    return plan
