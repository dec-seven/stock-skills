"""
宏观市场 Agent：负责 A 股大盘定调 + 美股隔夜影响 + 全球市场分析。

输入：market_data.json（yesterday.indices / overnight_us / global_markets）
输出字段（写入 llm_analysis.json）：
  - MARKET_TONE: 市场定调（一句话）
  - US_IMPACT_ON_A: 美股对 A 股影响
  - GLOBAL_MARKET_ANALYSIS: 全球市场对 A 股影响分析
  - EMOTION_FEATURE: 情绪特征
  - TODAY_PREDICTION: 今日预测（方向+区间）

双模式：
- 在线（DEEPSEEK_API_KEY 存在）：调 LLM 直接生成
- 离线：生成 prompt 片段，由编排器合并后外部执行
"""

import os
import json
from typing import Dict
from .base import BaseAgent, AgentResult
from shared.ai.market_facts import extract_market_facts, build_facts_summary


# 每个 Agent 负责的 llm_analysis.json 字段
AGENT_FIELDS = ["MARKET_TONE", "US_IMPACT_ON_A", "GLOBAL_MARKET_ANALYSIS", "EMOTION_FEATURE", "TODAY_PREDICTION"]

# 系统提示词：定义 Agent 角色 + 输出规范
SYSTEM_PROMPT = """你是 A 股宏观市场分析师，负责：
1. 综合昨日 A 股指数表现、成交额、涨跌家数，给出今日市场定调
2. 分析美股隔夜走势对 A 股的影响（道指/标普/纳指/VIX/SOX/NVDA/TSLA/油/金）
3. 分析全球市场（日经/恒指/美元指数/离岸人民币）对 A 股的传导
4. 判断市场情绪特征（高涨/温和/寒冷/极寒）
5. 给出今日方向预测 + 上证指数区间

严格要求：
- 数据必须基于“不可改写事实”和 market_data.json，不得编造
- 不可改写事实优先级最高，输出不得与其冲突
- 若主要指数多数下跌，禁止写“全线上涨/普涨/风险偏好提升”
- 若下跌家数多于上涨家数，禁止写“情绪积极/赚钱效应强”
- 方向判断要明确：偏多/震荡/偏空/防守
- 区间要具体到点位（如 3150-3180）
- 情绪特征要描述市场情绪状态（如"市场情绪高涨，投资者信心充足"），不要返回 CSS 类名
- 严谨严格，不自我安慰，高位高估值要折价

输出 JSON 格式：
{
  "MARKET_TONE": "一句话市场定调",
  "US_IMPACT_ON_A": "美股对 A 股影响（2-3句）",
  "GLOBAL_MARKET_ANALYSIS": "全球市场对 A 股影响（1-2句）",
  "EMOTION_FEATURE": "情绪特征描述（如：市场情绪高涨，投资者追涨意愿强）",
  "TODAY_PREDICTION": {
    "direction": "偏多|震荡|偏空|防守",
    "sh_range_low": 3150,
    "sh_range_high": 3180,
    "reasoning": "预测理由"
  }
}
"""


class MacroAgent(BaseAgent):
    """宏观市场 Agent"""
    name = "macro_agent"
    description = "宏观市场分析：A 股定调 + 美股影响 + 全球市场 + 情绪 + 方向预测"

    def run(self, input_data: dict) -> AgentResult:
        """
        Args:
            input_data: {
                "market_data": dict,  # market_data.json 内容
                "work_dir": str,      # 工作目录（tmp）
            }
        """
        result = AgentResult(success=False, agent_name=self.name, run_id=self.run_id)
        market_data = input_data.get("market_data", {})
        work_dir = input_data.get("work_dir", "/tmp")

        # 构建用户提示词（注入关键数据）
        user_prompt = self._build_user_prompt(market_data)

        if self.llm and self.llm.is_online():
            # 在线模式：直接调 LLM
            resp = self.llm.chat_json(SYSTEM_PROMPT, user_prompt, temperature=0.3)
            if resp.success and resp.usage:
                parsed = resp.usage.get("parsed_json", {})
                result.success = True
                result.data = parsed
                result.add_trace("llm_call", "deepseek_api", resp.duration_ms, True)
            else:
                result.add_error(f"LLM 调用失败: {resp.error}")
                result.add_trace("llm_call", "deepseek_api", resp.duration_ms, False)
                # 回退：生成 prompt 片段
                result.data = self._offline_fallback(user_prompt, work_dir)
                result.success = True
        else:
            # 离线模式：生成 prompt 片段，等待外部执行
            result.data = self._offline_fallback(user_prompt, work_dir)
            result.success = True
            result.add_trace("prompt_gen", "offline", 0, True)

        return result

    def _build_user_prompt(self, market_data: dict) -> str:
        """构建用户提示词，注入关键市场数据"""
        yesterday = market_data.get("yesterday", {})
        indices = yesterday.get("indices", [])
        overnight_us = market_data.get("overnight_us", {})
        global_markets = market_data.get("global_markets", {})
        breadth = yesterday.get("market_breadth", {})
        turnover = yesterday.get("turnover", {})
        facts = extract_market_facts(market_data)

        lines = [build_facts_summary(facts), "", "## 市场数据（请基于此分析）", ""]

        # A 股指数
        if indices:
            lines.append("### A 股主要指数")
            for idx in indices:
                name = idx.get("name", "")
                close = idx.get("close", "")
                pct = idx.get("pct", idx.get("pct_change", ""))
                lines.append(f"- {name}: 收盘 {close}, 涨跌幅 {pct}%")
            lines.append("")

        # 涨跌家数
        if breadth:
            lines.append("### 涨跌家数")
            lines.append(f"- 上涨 {breadth.get('up_count', breadth.get('advancing', 'N/A'))} 家，下跌 {breadth.get('down_count', breadth.get('declining', 'N/A'))} 家")
            lines.append(f"- 涨停 {breadth.get('limit_up', 'N/A')} 家，跌停 {breadth.get('limit_down', 'N/A')} 家")
            lines.append("")

        # 成交额
        if turnover:
            lines.append(f"### 成交额: {turnover.get('total', 'N/A')} 亿")
            lines.append("")

        # 美股
        if overnight_us:
            lines.append("### 美股隔夜")
            for key in ["dow", "sp500", "nasdaq", "vix", "sox", "nvda", "tsla", "oil", "gold"]:
                item = overnight_us.get(key, {})
                if item:
                    pct = item.get('pct', item.get('pct_change', 'N/A'))
                    lines.append(f"- {item.get('name', key)}: {item.get('close', 'N/A')}, 涨跌 {pct}%, 原因: {item.get('reason', 'N/A')}")
            lines.append("")

        # 全球市场
        if global_markets:
            lines.append("### 全球市场")
            for key in ["nikkei", "hsi", "dxy", "cnh"]:
                item = global_markets.get(key, {})
                if item:
                    pct = item.get("pct") if item.get("pct") is not None else item.get("pct_change", "")
                    lines.append(f"- {item.get('name', key)}: {item.get('close', 'N/A')}, 涨跌 {pct}%")
            lines.append("")

        lines.append("请输出 JSON（含 MARKET_TONE/US_IMPACT_ON_A/GLOBAL_MARKET_ANALYSIS/EMOTION_FEATURE/TODAY_PREDICTION）。")
        return "\n".join(lines)

    def _offline_fallback(self, user_prompt: str, work_dir: str) -> dict:
        """离线模式：生成 prompt 片段文件，返回路径信息"""
        prompt_path = os.path.join(work_dir, "prompt_macro.md")
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(f"# 宏观市场分析 Prompt\n\n{SYSTEM_PROMPT}\n\n---\n\n{user_prompt}")
        return {
            "mode": "offline",
            "prompt_path": prompt_path,
            "fields": AGENT_FIELDS,
        }
