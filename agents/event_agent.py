"""
事件日历 Agent：负责抓取近期重大国内外事件。

输入：market_data.json（已有日期和基本信息）
输出字段（写入 market_data.json 的 news_events.events）：
  - EVENTS: 结构化事件列表 [{date, text, tag, css_class}]

事件范围（仅写近期重大国内外事件日历）：
  - 美联储主席/新主席讲话
  - 美国 CPI/PPI/非农
  - 国内 LPR/PMI/社融
  - 重要政策会议
  - AI/半导体/新能源重大发布会
  - 禁止：指数涨跌、北向资金、板块领涨、成交额变化等盘面复盘

双模式：
- 在线：调用 LLM（DeepSeek 联网搜索）获取事件
- 离线：生成 prompt 等待外部执行
"""

import os
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List
from .base import BaseAgent, AgentResult


AGENT_FIELDS = ["EVENTS"]

SYSTEM_PROMPT = """你是 A 股重大事件日历分析师，负责整理近期对 A 股市场有重大影响的事件。

事件范围（仅限以下类别）：
1. 美联储：主席/新主席讲话、利率决议、FOMC 会议纪要
2. 美国宏观：CPI、PPI、非农就业、GDP、零售销售
3. 中国宏观：LPR 调整、PMI 公布、社融/M2 数据、GDP
4. 政策会议：中央经济工作会议、政治局会议、两会、行业政策发布
5. 产业催化：AI/半导体/新能源/机器人等重大产品发布、技术突破、龙头公司财报
6. 国际关系：贸易战、关税、制裁、地缘冲突

严格要求：
- 数据必须准确，不得编造具体日期或数据
- 如果无法确认具体日期，使用"近期关注"代替
- 事件影响方向要明确（利好/利空/中性）
- 事件时间范围：未来7天内即将发生 + 昨天到今天已发生
- 禁止写指数涨跌、北向资金、板块领涨、成交额变化等盘面复盘内容

输出 JSON 格式：
{
  "EVENTS": [
    {"date": "6/25", "text": "美联储利率决议", "tag": "⚠️ 谨慎", "css_class": "today"},
    {"date": "6/27", "text": "美国6月非农就业", "tag": "📈 偏多", "css_class": "future"},
    {"date": "6/28", "text": "国内6月PMI公布", "tag": "🕊️ 利好", "css_class": "future"},
    {"date": "后续关注", "text": "英伟达财报", "tag": "🚀 催化", "css_class": "warning"}
  ]
}

tag 规范：
- 🚀 催化：产业事件、产品发布、技术突破
- 🕊️ 利好：政策利好、数据超预期
- 📈 偏多：对市场整体偏正面
- ⚠️ 谨慎：潜在风险、不确定性高
css_class 规范：
- done：已发生的事件
- today：今天的事件
- future：未来事件
- bullish：利好/偏多
- bearish：利空/偏空
- warning：不确定性/需谨慎
"""


class EventAgent(BaseAgent):
    """事件日历 Agent"""
    name = "event_agent"
    description = "抓取近期重大国内外事件日历"

    def run(self, input_data: dict) -> AgentResult:
        result = AgentResult(success=False, agent_name=self.name, run_id=self.run_id)
        market_data = input_data.get("market_data", {})
        work_dir = input_data.get("work_dir", "/tmp")

        user_prompt = self._build_user_prompt(market_data)

        if self.llm and self.llm.is_online():
            resp = self.llm.chat_json(SYSTEM_PROMPT, user_prompt, temperature=0.3)
            if resp.success and resp.usage:
                parsed = resp.usage.get("parsed_json", {})
                events = parsed.get("EVENTS", [])
                result.success = True
                result.data = {"EVENTS": events}
                result.add_trace("llm_call", "deepseek_api", resp.duration_ms, True)
            else:
                result.add_error(f"LLM 调用失败: {resp.error}")
                result.add_trace("llm_call", "deepseek_api", resp.duration_ms, False)
                # 回退：空事件列表
                result.data = {"EVENTS": []}
                result.success = True
        else:
            # 离线模式：生成 prompt 片段
            result.data = self._offline_fallback(user_prompt, work_dir)
            result.success = True
            result.add_trace("prompt_gen", "offline", 0, True)

        return result

    def _build_user_prompt(self, market_data: dict) -> str:
        """构建用户提示词，注入当前日期"""
        report_date = market_data.get("report_date", datetime.now().strftime("%Y-%m-%d"))
        today = datetime.strptime(report_date, "%Y-%m-%d")
        yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        next_week = (today + timedelta(days=7)).strftime("%Y-%m-%d")

        lines = [
            f"## 当前日期: {report_date}",
            f"## 事件搜索范围: {yesterday} 至 {next_week}",
            "",
            "请搜索并整理以下类别的近期重大事件：",
            "1. 美联储相关：主席讲话、利率决议、FOMC 会议纪要",
            "2. 美国宏观数据：CPI、PPI、非农就业、GDP",
            "3. 中国宏观数据：LPR、PMI、社融/M2",
            "4. 重要政策会议：政治局会议、行业政策",
            "5. 产业催化：AI/半导体/新能源重大发布、龙头财报",
            "6. 国际关系：贸易战、关税、地缘冲突",
            "",
            "注意：",
            "- 如果无法确认具体日期，使用'后续关注'",
            "- 不得编造具体数据",
            "- 只列对市场有重大影响的事件",
            "- 禁止列指数涨跌、板块领涨等盘面信息",
            "",
            "请输出 JSON 格式的 EVENTS 数组。",
        ]
        return "\n".join(lines)

    def _offline_fallback(self, user_prompt: str, work_dir: str) -> dict:
        """离线模式：生成 prompt 片段文件"""
        prompt_path = os.path.join(work_dir, "prompt_event.md")
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(f"# 事件日历分析 Prompt\n\n{SYSTEM_PROMPT}\n\n---\n\n{user_prompt}")
        return {
            "mode": "offline",
            "prompt_path": prompt_path,
            "fields": AGENT_FIELDS,
        }
