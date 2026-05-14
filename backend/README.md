# AI 批量数据抓取系统 - 后端开发文档

## 系统概述

本系统是一个多平台（B站/抖音/小红书）达人批量数据抓取系统，采用**通用工作流解释器架构**：

1. **LLM 单轮规划**：用户输入需求后，LLM 一次性输出完整工作流 JSON（包含平台分组、工具序列、分页规则、导出字段）
2. **后端通用解释器**：后端完全根据 LLM 返回的 workflow JSON 自动执行，无需硬编码 if/elif 策略分支
3. **参数池机制**：每条达人任务独立维护 param_pool，工具返回自动回填，下一个工具自动获取入参

## 技术栈

- **Web 框架**：FastAPI
- **LLM**：Moonshot AI (Kimi)
- **数据接口**：观星 API（B站/抖音数据接口提供商）
- **Excel 处理**：pandas + openpyxl
- **并发**：asyncio

## 目录结构

```
backend/
├── main.py                 # FastAPI 入口，路由挂载
├── config.py               # 全局配置（环境变量读取）
│
├── agent/                  # Agent 核心逻辑
│   ├── executor/           # 工具执行层
│   │   ├── __init__.py     # 统一入口，导出所有公共 API
│   │   ├── models.py       # Pydantic Args 模型（每个工具的参数定义）
│   │   ├── registry.py     # 工具注册中心（TOOL_META + TOOL_REGISTRY）
│   │   ├── extractors.py   # 数据提取辅助函数
│   │   ├── trim.py         # 结果截断逻辑
│   │   └── core.py         # execute_tool_call 核心调度
│   │
│   ├── batch_planner/      # 批量任务编排层
│   │   ├── __init__.py     # 统一入口
│   │   ├── cache.py        # 任务缓存、取消控制、TTL 清理
│   │   ├── llm.py          # LLM 规划（SYSTEM_PROMPT + generate_plan）
│   │   ├── filters.py      # 过滤与导出记录组装
│   │   ├── workflow.py     # 单达人工作流执行
│   │   └── engine.py       # 批量并发引擎 + SSE
│   │
│   ├── router.py           # HTTP 路由（/api/* 接口）
│   └── tools.py            # OpenAI function 构建
│
├── api/                    # 数据接口层
│   ├── base.py             # 通用 HTTP 请求封装
│   ├── data_apis.py        # 向后兼容的接口导出
│   ├── registry.py         # 平台注册表（自动合并所有平台 API）
│   ├── excel_parser.py     # Excel 解析（智能列名匹配）
│   │
│   ├── bilibili/           # B站平台接口
│   │   ├── __init__.py
│   │   └── apis.py         # B站 API 实现（get_video_list 等）
│   │
│   ├── douyin/             # 抖音平台接口
│   │   ├── __init__.py
│   │   └── apis.py         # 抖音 API 实现（get_douyin_video_detail 等）
│   │
│   └── xiaohongshu/        # 小红书平台接口（占位）
│       ├── __init__.py
│       └── apis.py
│
├── models/
│   └── schemas.py          # Pydantic 数据模型（请求/响应/工作流定义）
│
└── utils/
    └── common_utils.py     # 通用工具函数
```

## 核心架构说明

### 1. 工作流规划流程

```
用户上传 Excel + 输入需求
        ↓
【batch_planner/llm.py】generate_plan()
    - 构建 SYSTEM_PROMPT（包含可用工具描述）
    - 调用 LLM 生成工作流 JSON
    - 校验工具白名单
        ↓
返回 LLMWorkflowPlan（包含 global_filter + export_fields + workflows）
        ↓
【batch_planner/engine.py】run_batch_task()
    - 并发调度多个达人
    - 每个达人调用 process_one_creator()
```

### 2. 单达人工作流执行流程

```
【batch_planner/workflow.py】process_one_creator()
    1. 根据 creator['platform'] 匹配对应 workflow
    2. 初始化 param_pool（从 creator 字段填充）
    3. 按 workflow.tool_sequence 顺序执行工具
       - 参数不足 → 跳过
       - API 失败 → 记录日志，跳过
       - 成功 → 调用 extract_tool_output() 回填 param_pool
    4. 若 page_rule.enable_page=true，自动翻页
    5. 若 each_detail.need_query=true，逐条查详情
    6. 按 global_filter 过滤
    7. 按 export_fields 组装导出记录
```

### 3. 工具执行流程

```
【executor/core.py】execute_tool_call()
    1. 从 TOOL_REGISTRY 查找工具
    2. Pydantic 参数校验
    3. 参数类型转换（LLM 常把 int 传成 string）
    4. 执行实际 API 调用
    5. 结果截断（避免超长返回）
    6. 返回 ToolResult
```

## 如何添加新平台接口（以小红书为例）

### 步骤 1：创建平台接口文件

**新建文件：`api/xiaohongshu/apis.py`**

```python
"""小红书（xiaohongshu）平台数据接口实现"""
from __future__ import annotations

import logging
from api.base import api_request
from config import settings

logger = logging.getLogger(__name__)
BASE_URL = settings.DATA_API_BASE_URL


async def get_xhs_note_detail(note_id: str) -> dict:
    """获取小红书笔记详情"""
    return await api_request(BASE_URL, "/xhs-note-detail", {"note_id": note_id})


async def get_xhs_user_info(user_id: str) -> dict:
    """获取小红书用户信息"""
    return await api_request(BASE_URL, "/xhs-user-info", {"user_id": user_id})


# 接口注册表
API_REGISTRY = {
    "get_xhs_note_detail": get_xhs_note_detail,
    "get_xhs_user_info": get_xhs_user_info,
}
```

**修改文件：`api/xiaohongshu/__init__.py`**

```python
from __future__ import annotations
from .apis import API_REGISTRY
__all__ = ["API_REGISTRY"]
```

### 步骤 2：注册到平台注册表

**修改文件：`api/registry.py`**

```python
from api import bilibili, douyin, xiaohongshu  # 新增
PLATFORMS = [bilibili, douyin, xiaohongshu]    # 加入列表
```

### 步骤 3：在 executor 中注册工具

**修改文件：`agent/executor/models.py`**

新增 Pydantic 参数模型：

```python
class GetXhsNoteDetailArgs(BaseModel):
    """获取小红书笔记详情参数"""
    note_id: str = Field(..., description="小红书笔记ID")
```

**修改文件：`agent/executor/registry.py`**

1. 导入数据接口函数：
```python
from api.data_apis import (
    # ... 原有导入 ...
    get_xhs_note_detail,
)
```

2. 导入参数模型：
```python
from .models import (
    # ... 原有导入 ...
    GetXhsNoteDetailArgs,
)
```

3. 在 `TOOL_META` 中注册工具描述：
```python
TOOL_META = {
    # ... 原有工具 ...
    "get_xhs_note_detail": {
        "description": "获取小红书笔记详情",
        "input_params": ["note_id"],
        "return_fields": ["note_id", "title", "desc", "like_count"],
    },
}
```

4. 在 `TOOL_REGISTRY` 中注册工具：
```python
TOOL_REGISTRY = {
    # ... 原有工具 ...
    "get_xhs_note_detail": {
        "func": get_xhs_note_detail,
        "args_model": GetXhsNoteDetailArgs,
        "description": "获取小红书笔记详情",
    },
}
```

**修改文件：`agent/executor/extractors.py`**

在 `TOOL_OUTPUT_EXTRACTORS` 中添加输出提取器：

```python
TOOL_OUTPUT_EXTRACTORS = {
    # ... 原有提取器 ...
    "get_xhs_note_detail": lambda data: {
        "note_id": _safe_get(data, "data", "note_id"),
        "title": _safe_get(data, "data", "title"),
        # ...
    },
}
```

### 步骤 4：Excel 解析器识别小红书字段（可选）

**修改文件：`api/excel_parser.py`**

1. 新增关键词：
```python
NOTE_ID_KEYWORDS = {"note_id", "笔记id", "笔记编号"}
```

2. 在 `parse_excel()` 中识别列并提取：
```python
if note_id_col and pd.notna(row[note_id_col]):
    note_id = str(row[note_id_col]).strip()
    platform = "xiaohongshu"
```

### 步骤 5：验证

- LLM 会自动感知新工具（`build_tools_prompt()` 动态生成工具描述）
- 无需修改 `batch_planner`，通用解释器自动支持新工具

## 如何修改配置

所有配置集中在 **`config.py`**，支持通过 `.env` 文件覆盖：

### 常用配置项

```bash
# .env 文件示例

# LLM 配置
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.moonshot.cn/v1
LLM_MODEL=kimi-k2.6
LLM_MAX_TOKENS=8192
LLM_TEMPERATURE=1.0

# Plan 生成配置
LLM_PLAN_TIMEOUT=600          # 超时时间（秒）
LLM_PLAN_TEMPERATURE=1.0      # 温度
LLM_PLAN_MAX_ATTEMPTS=2       # 最大重试次数

# 数据 API 配置
DATA_API_BASE_URL=http://api-guanxing.changwankeji.com/api
DATA_API_AUTH_KEY=your_auth_key

# Agent 行为配置
BATCH_CONCURRENCY=3           # 批量任务并发数
MAX_PAGE_PER_UP=10            # 单达人翻页最大页数
MAX_TOOL_RESULT_LENGTH=200000 # 工具结果最大长度
```

### 修改 SYSTEM_PROMPT

**方式 1：通过环境变量（完整替换）**

```bash
LLM_SYSTEM_PROMPT_TEMPLATE="你的自定义 Prompt 模板，使用 {tools_desc} 占位符"
```

**方式 2：修改 `config.py`**

找到 `LLM_SYSTEM_PROMPT_TEMPLATE` 配置项直接修改。

## 关键文件速查

| 需求 | 文件路径 |
|------|---------|
| 添加新平台数据接口 | `api/{platform}/apis.py` |
| 注册新工具 | `agent/executor/models.py` + `registry.py` + `extractors.py` |
| 修改 LLM 超时/温度 | `config.py` → `LLM_PLAN_TIMEOUT` / `LLM_PLAN_TEMPERATURE` |
| 修改 SYSTEM_PROMPT | `config.py` → `LLM_SYSTEM_PROMPT_TEMPLATE` |
| 修改 Excel 列识别规则 | `api/excel_parser.py` |
| 修改导出字段映射 | `agent/batch_planner/filters.py` → `_build_export_record()` |
| 添加新 HTTP 接口 | `agent/router.py` |
| 修改任务并发数 | `config.py` → `BATCH_CONCURRENCY` |

## 开发注意事项

1. **工具命名规范**：使用 `snake_case`，如 `get_douyin_video_detail`
2. **平台隔离**：B站工具只能出现在 `bilibili` workflow 中，不能与抖音工具混用
3. **参数别名**：如果不同工具的参数名不一致（如 `id` vs `bvid`），在 `executor/registry.py` 的 `PARAM_ALIASES` 中配置映射
4. **循环导入**：`executor` 子包内部使用相对导入（`from .xxx import`），外部使用绝对导入（`from agent.executor import`）
5. **日志**：使用 `logger = logging.getLogger(__name__)` 获取 logger，已配置统一格式

## 调试技巧

1. **查看 LLM 生成的 Plan**：
   ```python
   # agent/batch_planner/llm.py 中打印
   logger.info(f"[Plan] 生成的 plan: {plan}")
   ```

2. **查看工具调用参数**：
   ```python
   # executor/core.py 中已存在
   logger.info(f"[ToolExecute] 调用工具: {tool_name} | 参数: {validated_args}")
   ```

3. **查看 param_pool 变化**：
   ```python
   # executor/extractors.py 中
   logger.debug(f"[ParamPool] 回填: {key}={val}")
   ```

## 部署

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python -m uvicorn main:app --reload --port 8000

# 生产环境
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 相关文档

- 前端页面：`frontend/src/App.vue`（主页面）、`DouyinTest.vue`（抖音测试页面）
- 接口文档：启动后访问 `http://localhost:8000/docs`（Swagger）
