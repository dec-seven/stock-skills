"""
Agent 包：多 Agent 协作生成股市分析报告。

架构原则：
- agents 不互调，由 workflows/ 编排
- 每个 Agent 单一职责，输入/输出明确
- LLM 调用支持在线（DeepSeek API）+ 离线（生成 prompt 等待外部执行）双模式
- Tool 封装现有脚本，不破坏旧路径
"""

from .base import BaseAgent, AgentResult, Tool, ToolResult
from .macro_agent import MacroAgent
from .sector_agent import SectorAgent
from .stock_agent import StockAgent
from .risk_manager_agent import RiskManagerAgent
from .evolution_agent import EvolutionAgent

__all__ = [
    "BaseAgent",
    "AgentResult",
    "Tool",
    "ToolResult",
    "MacroAgent",
    "SectorAgent",
    "StockAgent",
    "RiskManagerAgent",
    "EvolutionAgent",
]
