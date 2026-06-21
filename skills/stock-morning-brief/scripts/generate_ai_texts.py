#!/usr/bin/env python3
"""
AI 文本生成辅助脚本：读取 market_data.json → 自动推导规则字段 → 构建 LLM 提示词 → 解析 LLM 输出 → 生成 ai_texts.json

设计原则：
- 脚本管 FORMAT（HTML模板、评分条、卡片渲染）
- LLM 管 INSIGHT（市场定调、选股逻辑、风险解读）
- 规则推导自动化（情绪色彩、方向信号、区间估算）

用法：
  # Step 1: 准备 LLM 提示词 + 规则推导字段
  python3 generate_ai_texts.py prepare --data ./tmp/market_data.json --output-dir ./tmp/

  # Step 2: Agent 读取 analysis_prompt.md，完成分析后输出 llm_analysis.json

  # Step 3: 编译最终 ai_texts.json（合并规则字段 + LLM 分析 + HTML 模板）
  python3 generate_ai_texts.py compile --data ./tmp/market_data.json --analysis ./tmp/llm_analysis.json --output ./tmp/ai_texts.json
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ==================== 数据验证工具 ====================

def validate_required_fields(data, required_fields, context="数据"):
    """验证必需字段是否存在"""
    missing = []
    for field in required_fields:
        if field not in data or data[field] is None:
            missing.append(field)
    if missing:
        print(f"[WARN] {context}缺失字段: {', '.join(missing)}", file=sys.stderr)
    return len(missing) == 0


def validate_stock_data(stock):
    """验证选股数据完整性"""
    required = ['name', 'code', 'fund_scores', 'tech_scores', 'logic']
    missing = [f for f in required if f not in stock]
    if missing:
        name = stock.get('name', stock.get('code', '未知股票'))
        print(f"[WARN] 选股 {name} 缺失字段: {', '.join(missing)}", file=sys.stderr)
        return False
    
    # 验证 fund_scores 和 tech_scores 是字典
    if not isinstance(stock.get('fund_scores'), dict):
        print(f"[WARN] 选股 {stock['name']} 的 fund_scores 不是字典", file=sys.stderr)
        return False
    if not isinstance(stock.get('tech_scores'), dict):
        print(f"[WARN] 选股 {stock['name']} 的 tech_scores 不是字典", file=sys.stderr)
        return False
    
    return True


def safe_get(data, *keys, default=None):
    """安全的多层字典访问"""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        else:
            return default
    return data


# ==================== 数据格式化工具 ====================

def format_pct(val):
    """格式化涨跌幅"""
    if val is None:
        return "—"
    if val > 0:
        return f"+{val:.2f}%"
    if val < 0:
        return f"{val:.2f}%"
    return "0.00%"


def format_amount(val):
    """格式化金额（亿）"""
    if val is None:
        return "—"
    if abs(val) >= 10000:
        return f"{val/10000:.2f}万亿"
    return f"{val:.0f}亿"


# ==================== 规则推导引擎 ====================

def derive_direction_signal(indices):
    """从指数涨跌推导方向信号类"""
    pcts = [idx.get("pct", 0) for idx in indices if "pct" in idx and not idx.get("need_websearch")]
    if not pcts:
        return "neutral"
    avg_pct = sum(pcts) / len(pcts)
    if avg_pct > 1.0:
        return "bullish"
    elif avg_pct > 0:
        return "neutral-bull"
    elif avg_pct > -1.0:
        return "neutral-bear"
    else:
        return "bearish"


def derive_direction_judgment(indices):
    """从指数涨跌推导方向判断文字"""
    pcts = [idx.get("pct", 0) for idx in indices if "pct" in idx and not idx.get("need_websearch")]
    if not pcts:
        return "震荡"
    avg_pct = sum(pcts) / len(pcts)
    max_pct = max(pcts)
    min_pct = min(pcts)
    spread = max_pct - min_pct
    
    if avg_pct > 1.5:
        return "看涨"
    elif avg_pct > 0.5:
        return "震荡偏多"
    elif avg_pct > 0:
        return "温和偏多"
    elif avg_pct > -0.5:
        return "温和偏空"
    elif avg_pct > -1.5:
        return "震荡偏空"
    else:
        return "看跌"


def derive_sentiment_class(data):
    """推导市场情绪色彩类"""
    breadth = data.get("yesterday", {}).get("market_breadth", {})
    indices = data.get("yesterday", {}).get("indices", [])
    
    up_count = breadth.get("up_count") or 0
    down_count = breadth.get("down_count") or 0
    limit_up = breadth.get("limit_up") or 0
    
    total = up_count + down_count
    if total == 0:
        return "sentiment-warm"
    
    up_ratio = up_count / total
    pcts = [idx.get("pct", 0) for idx in indices if "pct" in idx and not idx.get("need_websearch")]
    avg_pct = sum(pcts) / len(pcts) if pcts else 0
    
    # 高涨：大涨+涨停潮
    if avg_pct > 2.0 and limit_up > 150:
        return "sentiment-hot"
    # 温和：温和上涨
    elif avg_pct > 0.3 and up_ratio > 0.55:
        return "sentiment-warm"
    # 寒冷：下跌调整
    elif avg_pct < -0.5 or up_ratio < 0.4:
        return "sentiment-cold"
    # 极寒：暴跌
    elif avg_pct < -2.0 and up_ratio < 0.2:
        return "sentiment-frozen"
    else:
        return "sentiment-warm"


def derive_sentiment_label(sentiment_class):
    """情绪类名 → 中文标签"""
    mapping = {
        "sentiment-hot": "🔴 情绪高涨 · 狂热期",
        "sentiment-warm": "🟡 情绪温和 · 乐观期",
        "sentiment-cold": "🟢 情绪寒冷 · 恐慌期",
        "sentiment-frozen": "🔵 情绪极寒 · 冰点期",
    }
    return mapping.get(sentiment_class, "🟡 情绪温和")


def derive_sh_range(indices):
    """从上证指数推导区间"""
    for idx in indices:
        if idx.get("name") == "上证指数" and not idx.get("need_websearch"):
            close = idx.get("close", 3000)
            high = idx.get("high", close * 1.01)
            low = idx.get("low", close * 0.99)
            # 区间 = 昨日低点 ~ 昨日高点扩展
            range_low = int(low - (high - low) * 0.5)
            range_high = int(high + (high - low) * 0.5)
            # 取整到10
            range_low = range_low // 10 * 10
            range_high = range_high // 10 * 10
            return str(range_low), str(range_high)
    return "3900", "4100"


# ==================== HTML 模板函数 ====================

def build_signal_monitor_html(signals):
    """生成见底信号监控表格 HTML"""
    if not signals:
        return '<table class="data-table scoring-table"><thead><tr><th>信号</th><th>状态</th><th>评分</th></tr></thead><tbody><tr><td colspan="3">暂无信号数据</td></tr></tbody></table>'
    
    rows = ""
    total_score = 0
    max_score = 0
    for sig in signals:
        name = sig.get("name", "")
        status = sig.get("status", "")
        score = sig.get("score", 0)
        max_s = sig.get("max", 10)
        total_score += score
        max_score += max_s
        
        # 评分颜色
        if score / max_s >= 0.7:
            score_color = "#69f0ae"
            status_icon = "✅"
        elif score / max_s >= 0.4:
            score_color = "#ffd740"
            status_icon = "⚠️"
        else:
            score_color = "#ff5252"
            status_icon = "❌"
        
        rows += f'<tr><td>{name}</td><td>{status_icon} {status}</td><td style="color:{score_color}">{score}/{max_s}</td></tr>'
    
    # 综合评分颜色
    if total_score / max_score >= 0.7:
        total_color = "#69f0ae"
        label = "信号充足"
    elif total_score / max_score >= 0.4:
        total_color = "#ffd740"
        label = "信号一般"
    else:
        total_color = "#ff5252"
        label = "信号不足"
    
    html = '<table class="data-table scoring-table">'
    html += '<thead><tr><th>信号</th><th>状态</th><th>评分</th></tr></thead>'
    html += f'<tbody>{rows}</tbody>'
    html += f'<tfoot><tr><td colspan="2" style="text-align:right">综合评分</td><td style="color:{total_color};font-weight:700">{total_score}/{max_score} · {label}</td></tr></tfoot>'
    html += '</table>'
    return html


def build_mentality_html(sentiment_class, advice_lines):
    """生成心态管理模块 HTML"""
    label = derive_sentiment_label(sentiment_class)
    advice_html = "<br>".join([f"{'①②③④⑤'[i]} {line}" for i, line in enumerate(advice_lines)])
    return f'<div class="mentality-box {sentiment_class}"><div class="mentality-stage">{label}</div><div class="advice">{advice_html}</div></div>'


def build_discipline_html(items):
    """生成操作纪律条目 HTML"""
    html = ""
    for item in items:
        title = item.get("title", "")
        desc = item.get("desc", "")
        html += f'<li><b>{title}</b>：{desc}</li>'
    return html


def build_risk_warnings_html(risks):
    """生成风险提示 HTML"""
    html = ""
    for i, risk in enumerate(risks, 1):
        title = risk.get("title", f"风险{i}")
        desc = risk.get("desc", "")
        html += f'<div class="risk-box"><div class="risk-title">⚠️ {title}</div><div class="risk-desc">{desc}</div></div>'
    return html


def build_strategy_html(items):
    """生成操作策略 HTML"""
    html = '<ul class="strategy-list">'
    for item in items:
        title = item.get("title", "")
        desc = item.get("desc", "")
        html += f'<li><b>{title}</b>：{desc}</li>'
    html += '</ul>'
    return html


def build_sector_table_html(sectors):
    """生成板块方向表格 HTML"""
    rows = ""
    for s in sectors:
        priority = s.get("priority", "")
        name = s.get("name", "")
        stars = s.get("stars", "⭐⭐⭐")
        logic = s.get("logic", "")
        rows += f'<tr><td>{priority}</td><td>{name}</td><td class="star">{stars}</td><td>{logic}</td></tr>'
    
    html = '<table class="data-table sector-table">'
    html += '<thead><tr><th>优先级</th><th>板块方向</th><th>星级</th><th>核心逻辑</th></tr></thead>'
    html += f'<tbody>{rows}</tbody>'
    html += '</table>'
    return html


def build_style_summary_html(items):
    """生成方法论沉淀 HTML"""
    html = '<ul class="style-summary-list">'
    for item in items:
        icon = item.get("icon", "💡")
        title = item.get("title", "")
        desc = item.get("desc", "")
        html += f'<li>{icon} <b>{title}</b>：{desc}</li>'
    html += '</ul>'
    return html


def build_stock_card_html(stock):
    """生成单只选股卡片 HTML（v3评分条样式）"""
    # 数据完整性验证
    if not validate_stock_data(stock):
        return '<div class="stock-card error">数据不完整</div>'
    
    name = stock.get("name", "")
    code = stock.get("code", "")
    market_tag = stock.get("market_tag", "")
    market_class = stock.get("market_class", "sz")
    # 评分条
    fund_scores = stock.get("fund_scores", {})  # 三层映射法7项
    tech_scores = stock.get("tech_scores", {})   # 技术面5项
    
    fund_total = sum(v for v in fund_scores.values()) if fund_scores else 0
    tech_total = sum(v for v in tech_scores.values()) if tech_scores else 0
    total_score = fund_total + tech_total  # 从子项自动计算总分
    
    # 评级
    if total_score >= 85:
        rating = "⭐⭐⭐⭐⭐ 强烈推荐"
    elif total_score >= 75:
        rating = "⭐⭐⭐⭐ 推荐"
    elif total_score >= 60:
        rating = "⭐⭐⭐ 一般观察"
    else:
        rating = "⭐⭐ 不建议"
    
    # 评分条HTML
    score_bars_html = ""
    
    # 映射法7项
    fund_dims = [
        ("业务纯正度", 10), ("行业地位", 10), ("涨价受益度", 10),
        ("业绩验证", 10), ("催化剂临近", 10), ("估值位置", 10), ("特殊标签", 10)
    ]
    for dim, max_s in fund_dims:
        val = fund_scores.get(dim, 0)
        score_bars_html += _build_score_bar_row(dim, val, max_s)
    
    # 技术面5项
    tech_dims = [
        ("MACD", 8), ("KDJ", 7), ("成交量", 6), ("均线系统", 5), ("支撑压力", 4)
    ]
    for dim, max_s in tech_dims:
        val = tech_scores.get(dim, 0)
        score_bars_html += _build_score_bar_row(dim, val, max_s)
    
    # 核心逻辑
    logic = stock.get("logic", {})
    logic_html = ""
    for key, label, color in [
        ("core", "核心逻辑", "var(--blue-accent)"),
        ("data", "关键数据", "var(--blue-accent)"),
        ("catalyst", "催化事件", "var(--blue-accent)"),
        ("risk", "风险提示", "#ff5252"),
    ]:
        if key in logic and logic[key]:
            logic_html += f'<span class="label" style="color:{color}">{label}：</span>{logic[key]}<br>'
    
    html = f'''<div class="stock-card">
  <div class="stock-header">
    <span class="stock-name">{name}</span>
    <span class="stock-code">{code}</span>
    <span class="stock-market {market_class}">{market_tag}</span>
    <div class="stock-total-score">
      <div class="score-val">{total_score}</div>
      <div class="score-label">总分 / 100</div>
      <div class="stock-stars">{rating}</div>
    </div>
  </div>
  <div class="score-bars">{score_bars_html}</div>
  <div class="score-summary">
    <div class="sum-item"><span class="sum-label">三层映射:</span><span class="sum-val-fund">{fund_total}/70</span></div>
    <span class="sum-divider">|</span>
    <div class="sum-item"><span class="sum-label">技术面:</span><span class="sum-val-tech">{tech_total}/30</span></div>
  </div>
  <div class="stock-logic">{logic_html}</div>
</div>'''
    return html


def _build_score_bar_row(label, val, max_val):
    """生成单行评分条 HTML"""
    pct = val / max_val * 100 if max_val > 0 else 0
    if pct >= 70:
        cls = "good"
    elif pct >= 40:
        cls = "mid"
    else:
        cls = "bad"
    return f'<div class="score-bar-row"><span class="score-bar-label">{label}</span><div class="score-bar-track"><div class="score-bar-fill {cls}" style="width:{pct:.0f}%"></div></div><span class="score-bar-val {cls}">{val}/{max_val}</span></div>'


def build_stock_cards_html(stocks):
    """生成全部选股卡片 HTML"""
    if not stocks:
        return '<div class="no-data">暂无选股推荐</div>'
    
    cards = ""
    valid_count = 0
    for s in stocks:
        if validate_stock_data(s):
            cards += build_stock_card_html(s)
            valid_count += 1
        else:
            name = s.get('name', s.get('code', '未知'))
            print(f"[WARN] 跳过无效选股: {name}", file=sys.stderr)
    
    if valid_count == 0:
        return '<div class="no-data">无有效选股数据</div>'
    
    return f'<div class="stock-cards">{cards}</div>'


def build_event_timeline_html(events):
    """生成事件时间线 HTML（从结构化数据）"""
    if not events:
        return '<div class="timeline"><div class="timeline-item"><span class="timeline-text">暂无重大事件</span></div></div>'
    
    html = '<div class="timeline">\n'
    for ev in events:
        date = ev.get("date", "")
        text = ev.get("text", "")
        tag = ev.get("tag", "")
        css_class = ev.get("css_class", "tag-normal")
        tag_html = f'<span class="timeline-tag {css_class}">{tag}</span>' if tag else ""
        html += f'    <div class="timeline-item">\n'
        html += f'        <div class="timeline-date">{date}</div>\n'
        html += f'        <div class="timeline-content">{tag_html}{text}</div>\n'
        html += f'    </div>\n'
    html += '</div>'
    return html


# ==================== 数据摘要生成（给 LLM 的提示词） ====================

def build_data_summary(data):
    """将 market_data.json 压缩成 LLM 友好的文本摘要"""
    lines = []
    yesterday = data.get("yesterday", {})
    us = data.get("overnight_us", {})
    global_m = data.get("global_markets", {})
    news = data.get("news_events", {})
    
    # A股指数
    lines.append("## A股昨日行情")
    for idx in yesterday.get("indices", []):
        if not idx.get("need_websearch"):
            lines.append(f"- {idx['name']}: {idx['close']:,.2f} ({format_pct(idx['pct'])})")
    
    # 市场广度
    breadth = yesterday.get("market_breadth", {})
    if breadth and not breadth.get("need_websearch"):
        lines.append(f"\n## 市场广度")
        lines.append(f"- 上涨/下跌: {breadth.get('up_count', 0)} / {breadth.get('down_count', 0)}")
        lines.append(f"- 涨停/跌停: {breadth.get('limit_up', 0)} / {breadth.get('limit_down', 0)}")
    
    # 成交额
    turnover = yesterday.get("turnover", {})
    if turnover and turnover.get("total", 0) > 0:
        lines.append(f"- 两市成交: {format_amount(turnover['total'])}")
    
    # 北向资金
    north = yesterday.get("north_bound", {})
    if north and north.get("net_inflow") is not None:
        nf = north["net_inflow"]
        sign = "+" if nf > 0 else ""
        lines.append(f"- 北向资金: 净流入 {sign}{nf:.0f}亿")
    
    # 板块
    sectors = yesterday.get("sectors", {})
    gainers = sectors.get("top_gainers", [])
    losers = sectors.get("top_losers", [])
    if gainers:
        lines.append(f"\n## 领涨板块")
        for s in gainers[:3]:
            if not s.get("need_websearch"):
                lines.append(f"- {s['name']} ({format_pct(s['pct'])})")
    if losers:
        lines.append(f"\n## 领跌板块")
        for s in losers[:3]:
            if not s.get("need_websearch"):
                lines.append(f"- {s['name']} ({format_pct(s['pct'])})")
    
    # 隔夜美股
    lines.append(f"\n## 隔夜美股")
    for key in ["dow", "sp500", "nasdaq", "vix", "sox", "nvda", "tsla", "oil", "gold"]:
        item = us.get(key, {})
        if item and not item.get("need_websearch"):
            name = item.get("name", key)
            close = item.get("close")
            pct = item.get("pct")
            reason = item.get("reason", "")
            close_str = f"{close:,.2f}" if close is not None else "—"
            line = f"- {name}: {close_str} ({format_pct(pct)})"
            if reason:
                line += f" — {reason}"
            lines.append(line)
    
    # 全球市场
    lines.append(f"\n## 全球市场")
    for key in ["nikkei", "hsi", "dxy", "cnh"]:
        item = global_m.get(key, {})
        if item and not item.get("need_websearch"):
            name = item.get("name", key)
            close = item.get("close")
            pct = item.get("pct")
            close_str = f"{close:,.2f}" if close is not None else "—"
            lines.append(f"- {name}: {close_str} ({format_pct(pct)})")
    
    # 新闻事件
    items = news.get("items", [])
    if items:
        lines.append(f"\n## 近期事件")
        for item in items:
            date = item.get("date", "")
            text = item.get("text", "")
            tag = item.get("tag", "")
            lines.append(f"- [{date}] {tag}: {text}")
    
    return "\n".join(lines)


# ==================== PREPARE 命令 ====================

def cmd_prepare(args):
    """生成 LLM 分析提示词 + 规则推导字段"""
    data = json.load(open(args.data, encoding="utf-8"))
    
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. 规则推导
    indices = data.get("yesterday", {}).get("indices", [])
    direction_signal = derive_direction_signal(indices)
    direction_judgment = derive_direction_judgment(indices)
    sentiment_class = derive_sentiment_class(data)
    range_low, range_high = derive_sh_range(indices)
    
    # 2. 生成规则字段 JSON
    rule_fields = {
        "DIRECTION_SIGNAL_CLASS": direction_signal,
        "DIRECTION_JUDGMENT": direction_judgment,
        "SENTIMENT_CLASS": sentiment_class,
        "SH_RANGE_LOW": range_low,
        "SH_RANGE_HIGH": range_high,
        "_meta": {
            "derived_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "rules_applied": [
                "direction_signal: avg_pct > 1.0 → bullish, 0.5~1.0 → neutral-bull, etc.",
                "sentiment_class: avg_pct + up_ratio + limit_up → hot/warm/cold/frozen",
                "sh_range: yesterday high/low ± 0.5 * range"
            ]
        }
    }
    
    rule_path = os.path.join(output_dir, "ai_texts_rules.json")
    with open(rule_path, "w", encoding="utf-8") as f:
        json.dump(rule_fields, f, ensure_ascii=False, indent=2)
    print(f"[OK] 规则推导字段已保存: {rule_path}")
    
    # 3. 生成数据摘要
    summary = build_data_summary(data)
    
    # 4. 生成 LLM 提示词
    prompt = f"""# 股市早报 LLM 分析请求

> 日期: {data.get('report_date', '')}
> 数据截止: {data.get('data_cutoff', '')}

---

## 市场数据摘要

{summary}

---

## 规则推导结果（已自动计算，无需重复）

| 字段 | 推导值 |
|------|--------|
| DIRECTION_JUDGMENT | {direction_judgment} |
| DIRECTION_SIGNAL_CLASS | {direction_signal} |
| SENTIMENT_CLASS | {sentiment_class} |
| SH_RANGE_LOW | {range_low} |
| SH_RANGE_HIGH | {range_high} |

---

## 需要你分析的字段

请基于以上市场数据，输出以下 JSON 格式的分析结果。**注意：只输出 JSON，不要输出 HTML，HTML 模板由脚本自动渲染。**

### 重磅事件时间线规则

`market_data.news_events.events` 只允许写近期重大国内外事件日历，例如：美联储主席/新主席讲话、美国CPI/PPI/非农、国内LPR/PMI/社融、重要政策会议、AI/半导体/新能源重大发布会。禁止把指数涨跌、北向资金、板块领涨、成交额变化等盘面复盘写入重磅时间线；这些内容应放入昨日回顾、市场温度计或板块方向。若缺少可靠事件日程，必须 WebSearch 验证后补充，不得编造。

```json
{{
  "MARKET_TONE": "市场定调（1-2句话，概括市场特征和关键信号）",
  "EMOTION_FEATURE": "情绪特征（1句话，描述当前市场情绪状态）",
  "US_IMPACT_ON_A": "美股对A股影响判断（2-3句，结合美股涨跌和VIX分析）",
  "GLOBAL_MARKET": "全球市场简析（2-3句，亚太+汇率+大宗商品综合）",
  "GLOBAL_MARKET_ANALYSIS": "全球市场对A股影响分析（1-2句，基于上面数据推导对A股的传导逻辑）",
  "TODAY_PREDICTION": "今日预判（3-4句，结合技术面+消息面+资金面预判今日走势）",
  "YESTERDAY_REVIEW": "昨日回顾补充（2-3句，补充数据表格未涵盖的关键观察）",
  "POSITION_ADVICE": "仓位建议（如：5-6成仓位）",
  "PARTICIPATION_PACE": "参与节奏（一句话，如：低吸不追高，逢分歧布局低位方向）",
  "MENTALITY_ADVICE": ["心态建议条目1", "心态建议条目2", "心态建议条目3"],
  "SIGNALS": [
    {{"name": "补跌完成", "status": "高位股大幅回调", "score": 8, "max": 10}},
    {{"name": "量能放大", "status": "成交额激增", "score": 9, "max": 10}},
    {{"name": "技术支撑", "status": "关键支撑位站稳", "score": 8, "max": 10}},
    {{"name": "情绪回暖", "status": "赚钱效应强但有分歧", "score": 6, "max": 10}},
    {{"name": "资金回流", "status": "北向资金净流入", "score": 9, "max": 10}}
  ],
  "SECTORS": [
    {{"priority": 1, "name": "板块名", "stars": "⭐⭐⭐⭐⭐", "logic": "核心逻辑"}},
    {{"priority": 2, "name": "板块名", "stars": "⭐⭐⭐⭐", "logic": "核心逻辑"}}
  ],
  "RISKS": [
    {{"title": "风险1标题", "desc": "风险1描述"}},
    {{"title": "风险2标题", "desc": "风险2描述"}}
  ],
  "STRATEGY": [
    {{"title": "仓位控制", "desc": "描述"}},
    {{"title": "参与节奏", "desc": "描述"}},
    {{"title": "方向优先", "desc": "描述"}},
    {{"title": "节奏建议", "desc": "描述"}}
  ],
  "DISCIPLINES": [
    {{"title": "止损纪律", "desc": "描述"}},
    {{"title": "仓位纪律", "desc": "描述"}},
    {{"title": "追涨纪律", "desc": "描述"}},
    {{"title": "情绪纪律", "desc": "描述"}}
  ],
  "STYLE_SUMMARY": [
    {{"icon": "💰", "title": "涨价逻辑优先", "desc": "描述"}},
    {{"icon": "🔄", "title": "风格切换确认", "desc": "描述"}}
  ],
  "STOCKS": [
    {{
      "name": "股票名", "code": "601899", "market_tag": "沪(60)", "market_class": "sh",
      "fund_scores": {{"业务纯正度": 9, "行业地位": 10, "涨价受益度": 8, "业绩验证": 8, "催化剂临近": 7, "估值位置": 6, "特殊标签": 7}},
      "tech_scores": {{"MACD": 7, "KDJ": 5, "成交量": 5, "均线系统": 4, "支撑压力": 3}},
      "logic": {{
        "core": "核心逻辑描述",
        "data": "关键数据描述",
        "catalyst": "催化事件描述",
        "risk": "风险提示描述"
      }}
    }}
  ]
}}
```

### 分析要求

1. **MARKET_TONE**：必须包含关键数据（如突破点位、成交额变化），不含空话
2. **SIGNALS**：5项信号，每项 0-10 分，需结合当日数据具体描述状态
3. **SECTORS**：3-4个板块，优先级排序，逻辑需有数据支撑
4. **RISKS**：至少2项风险，含具体触发条件和影响
5. **STOCKS**：3-5只标的，评分需有依据（三层映射法70分+技术面30分）
6. **选股评分**：每项打分要有逻辑，不要所有股票分数都差不多
7. **POSITION_ADVICE**：与市场判断一致，震荡偏多时仓位5-6成
"""

    prompt_path = os.path.join(output_dir, "analysis_prompt.md")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"[OK] LLM 分析提示词已保存: {prompt_path}")
    
    # 5. 输出事件时间线 HTML（可从数据直接生成）
    events = data.get("news_events", {}).get("events", [])
    if events:
        event_html = build_event_timeline_html(events)
        event_path = os.path.join(output_dir, "event_timeline_auto.html")
        with open(event_path, "w", encoding="utf-8") as f:
            f.write(event_html)
        print(f"[OK] 事件时间线HTML已自动生成: {event_path}")
    
    print(f"\n[INFO] 下一步: Agent 读取 {prompt_path}，完成分析后输出 llm_analysis.json")
    print(f"[INFO] 然后运行: python3 generate_ai_texts.py compile --data {args.data} --analysis ./tmp/llm_analysis.json --output ./tmp/ai_texts.json")


# ==================== COMPILE 命令 ====================

def cmd_compile(args):
    """合并规则字段 + LLM 分析 + HTML 模板 → 生成 ai_texts.json"""
    data = json.load(open(args.data, encoding="utf-8"))
    
    # 1. 加载规则推导字段
    output_dir = os.path.dirname(os.path.abspath(args.output))
    rule_path = os.path.join(output_dir, "ai_texts_rules.json")
    if os.path.exists(rule_path):
        rule_fields = json.load(open(rule_path, encoding="utf-8"))
        print(f"[OK] 规则推导字段已加载: {rule_path}")
    else:
        # 重新推导
        print("[WARN] ai_texts_rules.json 不存在，重新推导规则字段", file=sys.stderr)
        indices = data.get("yesterday", {}).get("indices", [])
        rule_fields = {
            "DIRECTION_SIGNAL_CLASS": derive_direction_signal(indices),
            "DIRECTION_JUDGMENT": derive_direction_judgment(indices),
            "SENTIMENT_CLASS": derive_sentiment_class(data),
            "SH_RANGE_LOW": derive_sh_range(indices)[0],
            "SH_RANGE_HIGH": derive_sh_range(indices)[1],
        }
    
    # 2. 加载 LLM 分析结果
    try:
        analysis = json.load(open(args.analysis, encoding="utf-8"))
        print(f"[OK] LLM 分析结果已加载: {args.analysis}")
    except json.JSONDecodeError as e:
        print(f"[ERROR] LLM 分析 JSON 格式错误: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"[ERROR] 文件不存在: {args.analysis}", file=sys.stderr)
        sys.exit(1)
    
    # 验证 LLM 分析必需字段
    required_analysis_fields = [
        "MARKET_TONE", "EMOTION_FEATURE", "US_IMPACT_ON_A",
        "TODAY_PREDICTION", "SIGNALS", "SECTORS", "STOCKS"
    ]
    validate_required_fields(analysis, required_analysis_fields, "LLM分析")
    
    # 3. 组装 ai_texts
    ai_texts = {}
    
    # --- 纯文本字段（直接从 LLM 分析取） ---
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
    
    # --- HTML 模板字段（脚本自动渲染） ---
    sentiment_class = ai_texts["SENTIMENT_CLASS"]
    
    # 见底信号表格
    signals = analysis.get("SIGNALS", [])
    ai_texts["SIGNAL_MONITOR"] = build_signal_monitor_html(signals)
    
    # 心态管理
    mentality_advice = analysis.get("MENTALITY_ADVICE", [])
    ai_texts["MENTALITY_MANAGEMENT"] = build_mentality_html(sentiment_class, mentality_advice)
    
    # 操作纪律
    disciplines = analysis.get("DISCIPLINES", [])
    ai_texts["OPERATION_DISCIPLINE"] = build_discipline_html(disciplines)
    
    # 风险提示
    risks = analysis.get("RISKS", [])
    ai_texts["RISK_WARNINGS"] = build_risk_warnings_html(risks)
    
    # 操作策略
    strategy = analysis.get("STRATEGY", [])
    ai_texts["OPERATION_STRATEGY"] = build_strategy_html(strategy)
    
    # 板块方向
    sectors = analysis.get("SECTORS", [])
    ai_texts["SECTOR_DIRECTIONS"] = build_sector_table_html(sectors)
    
    # 方法论沉淀
    style_items = analysis.get("STYLE_SUMMARY", [])
    ai_texts["STYLE_SUMMARY"] = build_style_summary_html(style_items)
    
    # 选股卡片
    stocks = analysis.get("STOCKS", [])
    ai_texts["STOCK_SELECTION"] = build_stock_cards_html(stocks)
    
    # 事件时间线（优先从数据自动生成，LLM 可覆盖）
    events = data.get("news_events", {}).get("events", [])
    ai_texts["EVENT_TIMELINE"] = build_event_timeline_html(events)
    
    # 4. 写入 ai_texts.json
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(ai_texts, f, ensure_ascii=False, indent=2)
    
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
        print(f"[WARN] 以下字段为空: {', '.join(missing)}", file=sys.stderr)
    else:
        print(f"[OK] 全部 {len(required_fields)} 个字段已填充")
    
    print(f"[OK] ai_texts.json 已保存: {args.output}")


# ==================== 主入口 ====================

def main():
    parser = argparse.ArgumentParser(description="AI 文本生成辅助脚本")
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # prepare 命令
    prep_parser = subparsers.add_parser("prepare", help="生成 LLM 提示词 + 规则推导字段")
    prep_parser.add_argument("--data", required=True, help="market_data.json 路径")
    prep_parser.add_argument("--output-dir", default="./tmp/", help="输出目录")
    
    # compile 命令
    comp_parser = subparsers.add_parser("compile", help="编译最终 ai_texts.json")
    comp_parser.add_argument("--data", required=True, help="market_data.json 路径")
    comp_parser.add_argument("--analysis", required=True, help="LLM 分析结果 JSON 路径")
    comp_parser.add_argument("--output", required=True, help="输出 ai_texts.json 路径")
    
    args = parser.parse_args()
    
    if args.command == "prepare":
        cmd_prepare(args)
    elif args.command == "compile":
        cmd_compile(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
