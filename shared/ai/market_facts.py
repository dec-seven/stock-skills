#!/usr/bin/env python3
"""市场事实抽取：统一字段访问。"""

from typing import Dict, Any, List


def _num(value, default=0.0):
    try:
        if value is None or value == "" or value == "-":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct(item: Dict[str, Any]) -> float:
    return _num(item.get("pct", item.get("pct_change", 0.0)))


def _fmt_pct(value: float) -> str:
    return f"{value:+.2f}%"


def extract_market_facts(market_data: Dict[str, Any]) -> Dict[str, Any]:
    """从 market_data.json 抽取不可改写事实。"""
    yesterday = market_data.get("yesterday", {}) or {}
    indices = yesterday.get("indices", []) or []
    breadth = yesterday.get("market_breadth", {}) or {}
    turnover = yesterday.get("turnover", {}) or {}

    major_names = {"上证指数", "深证成指", "创业板指", "沪深300"}
    all_indices: List[Dict[str, Any]] = []
    major_indices: List[Dict[str, Any]] = []

    for idx in indices:
        row = {
            "name": idx.get("name", ""),
            "close": idx.get("close", ""),
            "pct": _pct(idx),
        }
        all_indices.append(row)
        if row["name"] in major_names:
            major_indices.append(row)

    if not major_indices:
        major_indices = all_indices[:4]

    major_up = sum(1 for i in major_indices if i["pct"] > 0)
    major_down = sum(1 for i in major_indices if i["pct"] < 0)
    all_up = sum(1 for i in all_indices if i["pct"] > 0)
    all_down = sum(1 for i in all_indices if i["pct"] < 0)

    up_count = int(_num(breadth.get("up_count", breadth.get("advancing", 0)), 0))
    down_count = int(_num(breadth.get("down_count", breadth.get("declining", 0)), 0))
    flat_count = int(_num(breadth.get("flat_count", 0), 0))
    limit_up = int(_num(breadth.get("limit_up", 0), 0))
    limit_down = int(_num(breadth.get("limit_down", 0), 0))
    turnover_total = _num(turnover.get("total", 0), 0)

    if major_indices and major_down == len(major_indices):
        market_direction = "主要指数全线下跌"
    elif major_indices and major_up == len(major_indices):
        market_direction = "主要指数全线上涨"
    elif major_down > major_up:
        market_direction = "主要指数多数下跌"
    elif major_up > major_down:
        market_direction = "主要指数多数上涨"
    else:
        market_direction = "主要指数分化"

    if down_count > up_count:
        breadth_direction = "跌多涨少"
    elif up_count > down_count:
        breadth_direction = "涨多跌少"
    else:
        breadth_direction = "涨跌均衡"

    sentiment_floor = "warm"
    if major_down > major_up or down_count > up_count:
        sentiment_floor = "cold"
    if major_down >= 3 and down_count >= up_count * 2:
        sentiment_floor = "frozen"

    return {
        "report_date": market_data.get("report_date", ""),
        "all_indices": all_indices,
        "major_indices": major_indices,
        "major_up_count": major_up,
        "major_down_count": major_down,
        "index_up_count": all_up,
        "index_down_count": all_down,
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": flat_count,
        "limit_up": limit_up,
        "limit_down": limit_down,
        "turnover": turnover_total,
        "market_direction": market_direction,
        "breadth_direction": breadth_direction,
        "sentiment_floor": sentiment_floor,
    }


def build_facts_summary(facts: Dict[str, Any]) -> str:
    lines = ["## 不可改写事实", ""]
    lines.append(f"- 市场方向：{facts.get('market_direction', '')}")
    lines.append(f"- 市场广度：{facts.get('breadth_direction', '')}，上涨{facts.get('up_count', 0)}家，下跌{facts.get('down_count', 0)}家")
    lines.append(f"- 涨跌停：涨停{facts.get('limit_up', 0)}家，跌停{facts.get('limit_down', 0)}家")
    lines.append(f"- 成交额：{facts.get('turnover', 0):.2f}亿")
    lines.append("- 主要指数：")
    for idx in facts.get("major_indices", []):
        lines.append(f"  - {idx.get('name')}: {idx.get('close')} ({_fmt_pct(idx.get('pct', 0))})")
    lines.append("")
    lines.append("硬约束：上述事实不得被改写；若指数多数下跌，禁止写全线上涨/普涨；若跌多涨少，禁止写情绪积极/赚钱效应强。")
    return "\n".join(lines)
