"""
Risk Manager Agent — 风控 Agent
负责仓位建议、止损位、风险警示
"""
import os
from .base import BaseAgent, AgentResult
from typing import Any, Dict


class RiskManagerAgent(BaseAgent):
    """风控 Agent：仓位/止损/风险警示"""

    name = "risk_manager"

    def __init__(self, llm_client=None, tools=None, run_id=None):
        super().__init__(llm_client=llm_client, tools=tools, run_id=run_id)
    
    def _build_prompt(self, context: Dict[str, Any]) -> str:
        """构建风控分析 prompt"""
        market_data = context.get("market_data", {})
        
        # 提取关键数据
        yesterday = market_data.get("yesterday", {})
        indices = yesterday.get("indices", [])
        
        # A 股指数
        sh = next((i for i in indices if i.get("code") == "000001"), {})
        sz = next((i for i in indices if i.get("code") == "399001"), {})
        cyb = next((i for i in indices if i.get("code") == "399006"), {})
        
        # 涨跌家数
        breadth = yesterday.get("market_breadth", {})
        
        # 成交额
        turnover = yesterday.get("turnover", {}).get("total", "N/A")
        
        # 美股
        us = market_data.get("overnight_us", {})
        nasdaq = us.get("nasdaq", {})
        vix = us.get("vix", {})
        
        # 北向
        north = yesterday.get("north_bound", {}).get("net_inflow", "N/A")
        
        prompt = f"""# 风控分析任务

你是专业风控官，基于市场数据输出仓位、止损、风险警示。

## 市场数据

### A股指数
- 上证: {sh.get('close', 'N/A')} ({sh.get('pct', 'N/A')}%)
- 深证: {sz.get('close', 'N/A')} ({sz.get('pct', 'N/A')}%)
- 创业板: {cyb.get('close', 'N/A')} ({cyb.get('pct', 'N/A')}%)

### 涨跌家数
- 上涨: {breadth.get('up_count', breadth.get('advancing', 'N/A'))} 下跌: {breadth.get('down_count', breadth.get('declining', 'N/A'))}
- 涨停: {breadth.get('limit_up', 'N/A')} 跌停: {breadth.get('limit_down', 'N/A')}

### 成交额
- {turnover} 亿

### 北向资金
- 净流入: {north} 亿

### 美股
- 纳斯达克: {nasdaq.get('close', 'N/A')} ({nasdaq.get('pct', 'N/A')}%)
- VIX: {vix.get('close', 'N/A')} ({vix.get('pct', 'N/A')}%)

## 输出要求（JSON）

```json
{{
  "position": "仓位百分比（如 70%）",
  "stop_loss": {{
    "上证": "止损位（整数）",
    "创业板": "止损位（整数）"
  }},
  "risk_alert": [
    "风险点1（如：成交额骤降30%）",
    "风险点2（如：北向连续3日净流出）"
  ]
}}
```

## 判断规则

### 仓位建议
- **100%**：VIX<15 + 北向净流入>100亿 + 成交额放量 + 涨跌比>2:1
- **80%**：VIX<20 + 北向净流入 + 成交额持平
- **70%**：VIX 20-25 或 北向净流出<50亿 或 成交额缩量
- **50%**：VIX 25-30 或 北向净流出>50亿 或 涨跌比<1:1
- **30%**：VIX>30 或 跌停>50 或 成交额骤降>30%
- **空仓**：VIX>35 或 跌停>100 或 系统性风险

### 止损位
- 上证：关键支撑位（整数关口/均线/前低）
- 创业板：关键支撑位

### 风险警示
- VIX 单日涨幅>20%
- 北向连续 3 日净流出
- 成交额骤降>30%
- 跌停家数>50
- 涨跌比<1:2
- 主要指数跌破关键支撑
- 行业板块整体资金大幅流出

## 注意
- 严格按规则判断，不确定时降低仓位
- 风险警示宁可多不可漏
- 止损位必须是明确的整数或关键点位
"""
        return prompt
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 响应"""
        import json
        
        try:
            # 尝试提取 JSON
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "{" in response:
                # 找第一个 { 和最后一个 }
                start = response.index("{")
                end = response.rindex("}") + 1
                json_str = response[start:end]
            else:
                raise ValueError("响应中未找到 JSON")
            
            result = json.loads(json_str)
            
            # 验证必要字段
            if "position" not in result:
                result["position"] = "70%"
            if "risk_alert" not in result:
                result["risk_alert"] = []
            if "stop_loss" not in result:
                result["stop_loss"] = {
                    "上证": "4050",
                    "创业板": "2400"
                }
            
            return result
            
        except Exception as e:
            # 离线模式或解析失败，返回默认值
            return {
                "position": "70%",
                "stop_loss": {
                    "上证": "4050",
                    "创业板": "2400"
                },
                "risk_alert": [
                    "离线模式，风控分析未执行"
                ]
            }
    
    def run(self, context: Dict[str, Any]) -> AgentResult:
        """执行风控分析"""
        try:
            # 构建 prompt
            prompt = self._build_prompt(context)

            # 调用 LLM（chat 需要 system_prompt + user_prompt）
            response = self.llm.chat(
                system_prompt="你是专业风控官，严格按照规则输出仓位/止损/风险警示。",
                user_prompt=prompt
            )

            # 解析响应
            result = self._parse_response(response.content)

            # 保存 prompt 到文件（离线模式用）
            work_dir = context.get("work_dir", "/tmp")
            prompt_file = os.path.join(work_dir, "prompt_risk_manager.md")
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(prompt)

            return AgentResult(
                success=True,
                agent_name=self.name,
                data={
                    "position": result.get("position", "70%"),
                    "stop_loss": result.get("stop_loss", {}),
                    "risk_alert": result.get("risk_alert", []),
                    "prompt_path": prompt_file,
                    "mode": self.llm.mode
                }
            )

        except Exception as e:
            return AgentResult(
                success=False,
                agent_name=self.name,
                errors=[str(e)],
                data={
                    "position": "70%",
                    "stop_loss": {"上证": "4050", "创业板": "2400"},
                    "risk_alert": [f"风控分析异常: {str(e)}"]
                }
            )
