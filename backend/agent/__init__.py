"""Agent 核心逻辑包。

本包实现了一个基于 OpenAI Function Calling 的 ReAct 风格 Agent：
- tools.py    ：定义工具 Schema，让 LLM "知道" 它能调用哪些接口
- executor.py ：执行 LLM 选择的工具调用，对接真实数据层
- planner.py  ：与 LLM 交互的主循环，规划 → 调用 → 观察 → 总结
- router.py   ：FastAPI 路由封装，对外暴露 SSE 流式 Chat 接口
"""
