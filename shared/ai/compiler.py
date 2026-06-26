#!/usr/bin/env python3
"""
AI 文本编译模块

合并规则推导字段 + LLM 分析结果 + HTML 模板 → 生成最终的 ai_texts.json。
提取 cmd_compile() 函数中的编译逻辑。

函数列表:
- compile_ai_texts(): 编译生成 ai_texts.json 的主函数
"""

import os
import sys
import json
from typing import Dict

# 导入日志和模块
sys.path.insert(0, str(__file__).replace('/shared/ai/compiler.py', ''))
from shared.logger import get_logger
from shared.ai.validators import validate_required_fields
from shared.ai.insight_engine import (
    derive_direction_signal,
    derive_direction_judgment,
    derive_sentiment_class,
    derive_sh_range
)
from shared.ai.html_builders import (
    build_signal_monitor_html,
    build_mentality_html,
    build_discipline_html,
    build_risk_warnings_html,
    build_strategy_html,
    build_sector_table_html,
    build_style_summary_html,
    build_stock_cards_html,
    build_event_timeline_html
)
from shared.ai.fact_guard import validate_macro_output

logger = get_logger('compiler')


def _convert_signals_format(signals_raw: list) -> list:
    """转换信号格式：LLM 输出的 strength → HTML 需要的 score/max"""
    strength_map = {"强": 8, "中": 5, "弱": 2}
    converted = []
    for i, sig in enumerate(signals_raw, 1):
        strength = sig.get("strength", "中")
        score = strength_map.get(strength, 5)
        converted.append({
            "name": sig.get("name", f"信号{i}"),
            "status": sig.get("status", ""),
            "score": score,
            "max": 10
        })
    return converted


def _convert_sectors_format(sectors_raw: list) -> list:
    """转换板块格式：LLM 输出的 direction/persistence/reasoning → HTML 需要的 priority/stars/logic"""
    converted = []
    for i, sec in enumerate(sectors_raw, 1):
        direction = sec.get("direction", "震荡")
        persistence = sec.get("persistence", "中")
        reasoning = sec.get("reasoning", "")
        
        # 星级映射：偏多+高持久性 → 5星，偏空+低持久性 → 2星
        if direction == "偏多" and persistence == "高":
            stars = "⭐⭐⭐⭐⭐"
        elif direction == "偏多" and persistence == "中":
            stars = "⭐⭐⭐⭐"
        elif direction == "震荡":
            stars = "⭐⭐⭐"
        elif direction == "偏空" and persistence == "高":
            stars = "⭐⭐"
        elif direction == "偏空":
            stars = "⭐⭐"
        else:
            stars = "⭐⭐⭐"
        
        converted.append({
            "priority": i if direction in ["偏多", "震荡"] else "",
            "name": sec.get("name", ""),
            "stars": stars,
            "logic": reasoning
        })
    return converted


def _convert_stocks_format(stocks_raw: list) -> list:
    """转换选股格式：LLM 输出的 logic 字符串 → HTML 需要的 logic dict + market_class"""
    converted = []
    for stock in stocks_raw:
        code = stock.get("code", "")
        
        # 市场判断：600/601/603/688 开头为沪市，其余为深市
        if code.startswith(("600", "601", "603", "688")):
            market_class = "sh"
            market_tag = "沪(60)"
        else:
            market_class = "sz"
            market_tag = "深(00)"
        
        # logic 转换：字符串 → dict
        logic_raw = stock.get("logic", "")
        logic_dict = {
            "core": logic_raw if logic_raw else "",
            "data": "",
            "catalyst": stock.get("catalyst", ""),
            "risk": stock.get("risk", "")
        }
        
        converted.append({
            "name": stock.get("name", ""),
            "code": code,
            "market_tag": market_tag,
            "market_class": market_class,
            "fund_scores": stock.get("fund_scores", {}),
            "tech_scores": stock.get("tech_scores", {}),
            "logic": logic_dict
        })
    return converted


def compile_ai_texts(data: Dict, analysis: Dict, output_path: str) -> Dict:
    """
    编译生成 ai_texts.json
    
    合并三个来源的数据:
    1. 规则推导字段(从 ai_texts_rules.json 加载或重新推导)
    2. LLM 分析结果(纯文本字段)
    3. HTML 模板(脚本自动渲染)
    
    Args:
        data: market_data.json 的完整数据字典
        analysis: LLM 分析结果字典(llm_analysis.json)
        output_path: 输出 ai_texts.json 的路径
    
    Returns:
        Dict: 编译完成的 ai_texts 字典
    
    Side Effects:
        - 保存 ai_texts.json 到 output_path
    
    Raises:
        JSONDecodeError: LLM 分析 JSON 格式错误
        FileNotFoundError: 文件不存在
    
    Example:
        >>> data = json.load(open("market_data.json"))
        >>> analysis = json.load(open("llm_analysis.json"))
        >>> ai_texts = compile_ai_texts(data, analysis, "./tmp/ai_texts.json")
    """
    # 1. 加载规则推导字段
    output_dir = os.path.dirname(os.path.abspath(output_path))
    rule_path = os.path.join(output_dir, "ai_texts_rules.json")
    
    if os.path.exists(rule_path):
        rule_fields = json.load(open(rule_path, encoding="utf-8"))
        logger.info(f"规则推导字段已加载", path=rule_path)
    else:
        # 重新推导
        logger.warning("ai_texts_rules.json 不存在,重新推导规则字段")
        indices = data.get("yesterday", {}).get("indices", [])
        rule_fields = {
            "DIRECTION_SIGNAL_CLASS": derive_direction_signal(indices),
            "DIRECTION_JUDGMENT": derive_direction_judgment(indices),
            "SENTIMENT_CLASS": derive_sentiment_class(data),
            "SH_RANGE_LOW": derive_sh_range(indices)[0],
            "SH_RANGE_HIGH": derive_sh_range(indices)[1],
        }
    
    # 2. 验证 LLM 分析必需字段
    required_analysis_fields = [
        "MARKET_TONE", "EMOTION_FEATURE", "US_IMPACT_ON_A",
        "TODAY_PREDICTION", "SIGNALS", "SECTORS", "STOCKS"
    ]
    validate_required_fields(analysis, required_analysis_fields, "LLM分析")
    
    # 2.5 事实校验：修复宏观幻觉
    analysis = validate_macro_output(data, analysis)
    
    # 3. 组装 ai_texts
    ai_texts = {}
    
    # --- 纯文本字段(直接从 LLM 分析取) ---
    ai_texts["MARKET_TONE"] = analysis.get("MARKET_TONE", "")
    ai_texts["EMOTION_FEATURE"] = analysis.get("EMOTION_FEATURE", "")
    ai_texts["US_IMPACT_ON_A"] = analysis.get("US_IMPACT_ON_A", "")
    ai_texts["GLOBAL_MARKET"] = analysis.get("GLOBAL_MARKET", "")
    ai_texts["GLOBAL_MARKET_ANALYSIS"] = analysis.get("GLOBAL_MARKET_ANALYSIS", "")
    ai_texts["TODAY_PREDICTION"] = analysis.get("TODAY_PREDICTION", "")
    ai_texts["YESTERDAY_REVIEW"] = analysis.get("YESTERDAY_REVIEW", "")
    ai_texts["POSITION_ADVICE"] = analysis.get("POSITION_ADVICE", "")
    ai_texts["PARTICIPATION_PACE"] = analysis.get("PARTICIPATION_PACE", "")
    
    # --- 规则推导字段 ---
    ai_texts["DIRECTION_JUDGMENT"] = rule_fields.get("DIRECTION_JUDGMENT", analysis.get("DIRECTION_JUDGMENT", "震荡"))
    ai_texts["DIRECTION_SIGNAL_CLASS"] = rule_fields.get("DIRECTION_SIGNAL_CLASS", analysis.get("DIRECTION_SIGNAL_CLASS", "neutral"))
    ai_texts["SENTIMENT_CLASS"] = rule_fields.get("SENTIMENT_CLASS", "sentiment-warm")
    ai_texts["SH_RANGE_LOW"] = rule_fields.get("SH_RANGE_LOW", "3900")
    ai_texts["SH_RANGE_HIGH"] = rule_fields.get("SH_RANGE_HIGH", "4100")
    
    # --- HTML 模板字段(脚本自动渲染) ---
    sentiment_class = ai_texts["SENTIMENT_CLASS"]
    
    # 见底信号表格（格式转换：strength → score/max）
    signals_raw = analysis.get("SIGNALS", [])
    signals = _convert_signals_format(signals_raw)
    ai_texts["SIGNAL_MONITOR"] = build_signal_monitor_html(signals)
    
    # 心态管理
    mentality_advice = analysis.get("MENTALITY_ADVICE", "")
    # 如果是字符串,按中文句号/逗号拆分成多条建议
    if isinstance(mentality_advice, str):
        # 先按句号拆,再按逗号拆
        advice_lines = []
        for part in mentality_advice.split("。"):
            for subpart in part.split("，"):
                subpart = subpart.strip()
                if subpart and len(subpart) > 2:  # 过滤太短的片段
                    advice_lines.append(subpart)
        # 如果拆分后只有1条,就直接用原字符串
        if len(advice_lines) <= 1:
            advice_lines = [mentality_advice]
    else:
        advice_lines = mentality_advice
    ai_texts["MENTALITY_MANAGEMENT"] = build_mentality_html(sentiment_class, advice_lines)
    
    # 操作纪律
    disciplines = analysis.get("DISCIPLINES", [])
    ai_texts["OPERATION_DISCIPLINE"] = build_discipline_html(disciplines)
    
    # 风险提示
    risks = analysis.get("RISKS", [])
    ai_texts["RISK_WARNINGS"] = build_risk_warnings_html(risks)
    
    # 操作策略
    strategy = analysis.get("STRATEGY", [])
    ai_texts["OPERATION_STRATEGY"] = build_strategy_html(strategy)
    
    # 板块方向（格式转换：direction/persistence/reasoning → priority/stars/logic）
    sectors_raw = analysis.get("SECTORS", [])
    sectors = _convert_sectors_format(sectors_raw)
    ai_texts["SECTOR_DIRECTIONS"] = build_sector_table_html(sectors)
    
    # 方法论沉淀
    style_items = analysis.get("STYLE_SUMMARY", [])
    ai_texts["STYLE_SUMMARY"] = build_style_summary_html(style_items)
    
    # 选股卡片（格式转换：logic 字符串 → logic dict）
    stocks_raw = analysis.get("STOCKS", [])
    stocks = _convert_stocks_format(stocks_raw)
    ai_texts["STOCK_SELECTION"] = build_stock_cards_html(stocks)
    
    # 事件时间线(优先从数据自动生成,LLM 可覆盖)
    events = data.get("news_events", {}).get("events", [])
    ai_texts["EVENT_TIMELINE"] = build_event_timeline_html(events)
    
    # 4. 写入 ai_texts.json
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(ai_texts, f, ensure_ascii=False, indent=2)
    
    logger.info(f"ai_texts.json 已保存", path=output_path)
    
    # 5. 验证字段完整性
    required_fields = [
        "MARKET_TONE", "EMOTION_FEATURE", "SIGNAL_MONITOR",
        "MENTALITY_MANAGEMENT", "US_IMPACT_ON_A", "GLOBAL_MARKET",
        "GLOBAL_MARKET_ANALYSIS", "EVENT_TIMELINE", "TODAY_PREDICTION",
        "SECTOR_DIRECTIONS", "RISK_WARNINGS", "OPERATION_STRATEGY",
        "OPERATION_DISCIPLINE", "STOCK_SELECTION", "STYLE_SUMMARY",
        "DIRECTION_JUDGMENT", "DIRECTION_SIGNAL_CLASS",
        "SH_RANGE_LOW", "SH_RANGE_HIGH", "POSITION_ADVICE",
        "PARTICIPATION_PACE", "YESTERDAY_REVIEW", "SENTIMENT_CLASS"
    ]
    
    missing = [f for f in required_fields if not ai_texts.get(f)]
    if missing:
        logger.warning(f"部分字段为空", missing_fields=missing)
    else:
        logger.info(f"全部字段已填充", field_count=len(required_fields))
    
    return ai_texts
