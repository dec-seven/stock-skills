"""
workflows 包：编排多个 Agent 完成完整任务。

架构原则：
- Agent 不互调，由 workflow 编排
- workflow 负责状态管理、断点续跑、并发调度
- 每个 workflow 对应一个完整业务场景

版本：
- morning_brief_langgraph: LangGraph StateGraph 版本（推荐）
- morning_brief: 原生 Python 版本（保留对照）
"""

from .morning_brief import MorningBriefWorkflow
from .morning_brief_langgraph import run_workflow as run_morning_brief_langgraph

__all__ = ["MorningBriefWorkflow", "run_morning_brief_langgraph"]
