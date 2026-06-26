#!/usr/bin/env python3
"""LLM 输出事实护栏：校验并重写明显违背 market_data 的宏观结论。"""

from typing import Dict, Any, List
from shared.ai.market_facts import extract_market_facts

BULLISH_PHRASES = ["全线上涨", "普涨", "情绪积极", "情绪高涨", "赚钱效应强", "风险偏好提升"]
GROWTH_BULLISH_PHRASES = ["成长风格强势", "成长股强势", "科技成长强势"]


def _contains_any(text: str, phrases: List[str]) -> List[str]:
    return [p for p in phrases if p in (text or "")]


def build_conservative_market_tone(facts: Dict[str, Any]) -> str:
    direction = facts.get("market_direction", "主要指数分化")
    breadth = facts.get("breadth_direction", "涨跌均衡")
    turnover = facts.get("turnover", 0)
    up_count = facts.get("up_count", 0)
    down_count = facts.get("down_count", 0)
    limit_up = facts.get("limit_up", 0)
    limit_down = facts.get("limit_down", 0)
    return (
        f"昨日A股{direction}，成交额{turnover:.2f}亿；"
        f"市场广度{breadth}（上涨{up_count}家、下跌{down_count}家），"
        f"涨停{limit_up}家、跌停{limit_down}家，显示资金分歧较大，情绪需谨慎评估。"
    )


def validate_macro_output(market_data: Dict[str, Any], macro_result: Dict[str, Any]) -> Dict[str, Any]:
    facts = extract_market_facts(market_data)
    result = dict(macro_result or {})
    warnings: List[str] = []
    combined = " ".join(str(result.get(k, "")) for k in ["MARKET_TONE", "EMOTION_FEATURE", "US_IMPACT_ON_A", "GLOBAL_MARKET_ANALYSIS"])

    bad = []
    if facts.get("major_down_count", 0) > facts.get("major_up_count", 0):
        bad.extend(_contains_any(combined, BULLISH_PHRASES))
    if facts.get("down_count", 0) > facts.get("up_count", 0):
        bad.extend(_contains_any(combined, ["情绪积极", "情绪高涨", "赚钱效应强"]))
    cyb = next((i for i in facts.get("major_indices", []) if i.get("name") == "创业板指"), {})
    if cyb.get("pct", 0) <= -2:
        bad.extend(_contains_any(combined, GROWTH_BULLISH_PHRASES + ["风险偏好提升"]))

    if bad:
        warnings.append("macro fact conflict: " + ",".join(sorted(set(bad))))
        result["MARKET_TONE"] = build_conservative_market_tone(facts)
        floor = facts.get("sentiment_floor", "cold")
        if floor == "frozen":
            result["EMOTION_FEATURE"] = "市场情绪偏弱，主要指数下跌且跌多涨少，需控制仓位并等待企稳信号。"
        else:
            result["EMOTION_FEATURE"] = "市场情绪谨慎，指数与市场广度存在压力，短线不宜乐观追涨。"
        pred = result.get("TODAY_PREDICTION", {})
        if isinstance(pred, dict):
            pred["reasoning"] = build_conservative_market_tone(facts)
            result["TODAY_PREDICTION"] = pred

    result["_fact_guard"] = {"warnings": warnings, "facts": facts}
    return result
