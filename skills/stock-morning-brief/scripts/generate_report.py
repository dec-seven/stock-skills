#!/usr/bin/env python3
"""
报告生成：读取 JSON 数据 + AI 文本 → 填充 HTML 模板 → 生成 PDF
用法: python3 generate_report.py --data /tmp/market_data.json --ai-texts /tmp/ai_texts.json --html out.html --pdf out.pdf
      python3 generate_report.py --data /tmp/market_data.json --ai-texts /tmp/ai_texts.json --html out.html --deploy-cloudflare

核心改动：所有表格数据从 market_data.json 动态生成，不再硬编码。
"""

import os
import sys
import json
import argparse
import subprocess
import shutil
import re
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from logger import get_logger
from run_context import get_run_id
from utils import format_pct, format_amount, pct_class, push_to_feishu
logger = get_logger('generate_report')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
WORKSPACE_DIR = os.path.abspath(os.path.join(SKILL_DIR, "..", ".."))
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "..", "templates", "report_template.html")


def load_env_file(path):
    """加载本地 .env 文件；仅填充当前进程未设置的环境变量。"""
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as e:
        logger.exception(f"加载环境变量文件失败 {path}: {e}")


# 飞书推送配置：优先系统环境变量，其次读取 workspace/skill 本地 .env（已 gitignore）
for env_path in [
    os.path.join(WORKSPACE_DIR, ".env"),
    os.path.join(SKILL_DIR, ".env"),
]:
    load_env_file(env_path)

FEISHU_USER_OPEN_ID = os.environ.get("FEISHU_USER_OPEN_ID")
if not FEISHU_USER_OPEN_ID:
    logger.info("[WARN] FEISHU_USER_OPEN_ID 未设置，飞书推送功能将被禁用")
LARK_CLI = "lark-cli"


def load_json_safe(path):
    """安全加载 JSON，自动修复内联引号问题"""
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.info(f"[WARN] JSON 解析失败 ({path}): {e}")
        try:
            fixed = _fix_inline_quotes(raw)
            result = json.loads(fixed)
            logger.info("[OK] 自动修复成功")
            return result
        except json.JSONDecodeError as e2:
            logger.info(f"[ERROR] 自动修复失败: {e2}")
            raise


def _fix_inline_quotes(raw):
    """修复 JSON 中的内联引号"""
    result = []
    in_string = False
    escape_next = False
    for ch in raw:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == '\\':
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            if not in_string:
                in_string = True
                result.append(ch)
            else:
                in_string = False
                result.append(ch)
        else:
            if in_string and ch == '\u201c':
                result.append('\u300c')
            elif in_string and ch == '\u201d':
                result.append('\u300d')
            else:
                result.append(ch)
    fixed = ''.join(result)
    fixed = re.sub(r'([\u4e00-\u9fff])"([^"]*?)"([\u4e00-\u9fff])',
                   r'\1\u300c\2\u300d\3', fixed)
    return fixed


def us_reason_fallback(key, item, us_data):
    """为隔夜美股/大宗品种生成关键信息兜底，禁止表格出现空白原因。"""
    reason = (item or {}).get("reason")
    if reason:
        return reason

    pct = (item or {}).get("pct")
    sox_pct = (us_data.get("sox") or {}).get("pct")
    nvda_pct = (us_data.get("nvda") or {}).get("pct")
    vix_pct = (us_data.get("vix") or {}).get("pct")
    oil_pct = (us_data.get("oil") or {}).get("pct")
    gold_pct = (us_data.get("gold") or {}).get("pct")

    if key == "dow":
        if isinstance(pct, (int, float)) and pct > 0:
            return "传统蓝筹相对抗跌，对A股权重情绪有支撑，但需结合纳指与半导体表现判断成长线压力。"
        return "传统蓝筹走弱，外部风险偏好偏谨慎，对A股权重板块形成扰动。"
    if key == "sp500":
        if isinstance(pct, (int, float)) and pct < 0:
            return "宽基指数回落，说明美股风险偏好降温，对A股早盘情绪偏压制。"
        return "宽基指数上涨，外部风险偏好改善，对A股整体情绪偏友好。"
    if key == "nasdaq":
        parts = []
        if isinstance(sox_pct, (int, float)):
            parts.append(f"费城半导体{format_pct(sox_pct)}")
        if isinstance(nvda_pct, (int, float)):
            parts.append(f"英伟达{format_pct(nvda_pct)}")
        detail = "、".join(parts)
        if isinstance(pct, (int, float)) and pct < 0:
            return f"科技成长承压{('，' + detail) if detail else ''}，对A股AI硬件、半导体链形成短线压制。"
        return f"科技成长反弹{('，' + detail) if detail else ''}，有利于A股AI与半导体链情绪修复。"
    if key == "vix":
        if isinstance(vix_pct, (int, float)) and vix_pct > 0:
            return "避险波动抬升，提示外盘扰动增强。"
        return "波动率回落，系统性风险压力有限。"
    if key == "sox":
        return "A股半导体、AI硬件链的重要映射指标，跌幅扩大时需防高位科技股兑现。"
    if key == "nvda":
        return "AI算力链核心锚，影响A股CPO、PCB、服务器和半导体情绪。"
    if key == "oil":
        if isinstance(oil_pct, (int, float)) and oil_pct < 0:
            return "油价回落缓和通胀预期，但也提示全球需求预期偏弱。"
        return "油价上涨强化通胀和资源品线索，关注能源化工链传导。"
    if key == "gold":
        if isinstance(gold_pct, (int, float)) and gold_pct > 0:
            return "黄金走强说明避险需求仍在，关注贵金属与风险偏好的跷跷板。"
        return "黄金回落说明避险降温，对风险资产情绪相对友好。"
    return "需结合涨跌幅、美元、油价和半导体链同步判断对A股的传导。"


# ==================== 动态生成 HTML 片段 ====================

def build_us_cards_html(us_data):
    """生成隔夜美股三大指数卡片 HTML"""
    cards_html = '<div class="us-cards">'
    
    # 三大指数
    major_keys = [
        ("dow", "道琼斯工业指数"),
        ("nasdaq", "纳斯达克指数"),
        ("sp500", "标普500指数"),
    ]
    
    for key, label in major_keys:
        item = us_data.get(key, {})
        close = item.get("close")
        pct = item.get("pct")
        reason = us_reason_fallback(key, item, us_data)
        
        if close is not None and not item.get("need_websearch"):
            cls = pct_class(pct)
            close_str = f"{close:,.0f}" if close > 1000 else f"{close:,.2f}"
            cards_html += f'''<div class="us-card">
                <div class="label">{label}</div>
                <div class="value {cls}">{close_str}</div>
                <div class="change {cls}">{format_pct(pct)}</div>
                <div class="reason">{reason}</div>
            </div>'''
        else:
            cards_html += f'''<div class="us-card">
                <div class="label">{label}</div>
                <div class="value">—</div>
                <div class="change">—</div>
                <div class="reason">数据待补充</div>
            </div>'''
    
    cards_html += '</div>'
    return cards_html


def build_us_table_html(us_data):
    """生成隔夜美股详细数据表格 HTML——仅三大指数，其余品种在扩展网格中展示"""
    # 只保留三大指数（VIX/SOX/NVDA/TSLA/Oil/Gold 由 us_extended_grid 展示）
    table_rows = [
        ("dow", "道琼斯"),
        ("sp500", "标普500"),
        ("nasdaq", "纳斯达克"),
    ]
    
    tbody = ""
    for key, name in table_rows:
        item = us_data.get(key, {})
        close = item.get("close")
        pct = item.get("pct")
        info = us_reason_fallback(key, item, us_data)
        
        if close is not None and not item.get("need_websearch"):
            cls = pct_class(pct)
            close_str = f"{close:,.0f}" if close > 1000 else f"{close:,.2f}"
            tbody += f'<tr><td>{name}</td><td class="num">{close_str}</td><td class="{cls}">{format_pct(pct)}</td><td>{info}</td></tr>'
        else:
            tbody += f'<tr><td>{name}</td><td class="num">—</td><td>—</td><td>待补充</td></tr>'
    
    html = '<table class="data-table">\n'
    html += '    <thead>\n'
    html += '        <tr><th>指数/品种</th><th>收盘点位</th><th>涨跌幅</th><th>关键信息</th></tr>\n'
    html += '    </thead>\n'
    html += f'    <tbody>{tbody}</tbody>\n'
    html += '</table>'
    return html


def build_us_extended_grid_html(us_data):
    """生成美股扩展网格（VIX/SOX/NVDA/TSLA/原油/黄金）"""
    items = [
        ("vix", "VIX恐慌"),
        ("sox", "费城半导体"),
        ("nvda", "英伟达"),
        ("tsla", "特斯拉"),
        ("oil", "WTI原油"),
        ("gold", "COMEX黄金"),
    ]
    html = '<div class="us-extended-grid">\n'
    for key, label in items:
        item = us_data.get(key, {})
        close = item.get("close")
        pct = item.get("pct")
        reason = us_reason_fallback(key, item, us_data)
        if close is not None and not item.get("need_websearch"):
            cls = pct_class(pct)
            close_str = f"{close:,.2f}" if close < 1000 else f"{close:,.0f}"
            html += f'''  <div class="us-ext-card">
                <div class="name">{label}</div>
                <div class="price {cls}">{close_str}</div>
                <div class="pct {cls}">{format_pct(pct)}</div>
                <div style="font-size:10px;color:var(--text-muted);margin-top:4px;">{reason}</div>
            </div>\n'''
        else:
            html += f'''  <div class="us-ext-card">
                <div class="name">{label}</div>
                <div class="price">—</div>
                <div class="pct">—</div>
                <div style="font-size:10px;color:var(--text-muted);margin-top:4px;">数据待补充</div>
            </div>\n'''
    html += '</div>'
    return html


def build_global_market_html(data):
    """生成全球市场概览 HTML（亚太 + 汇率大宗）"""
    # 从 data 顶层读取 global_markets
    global_markets = dict(data.get("global_markets", {}))  # 创建副本，避免修改原数据
    
    # 修复：如果 global_markets 中没有 gold，尝试从 overnight_us 中读取
    if "gold" not in global_markets:
        gold_from_us = data.get("overnight_us", {}).get("gold", {})
        if gold_from_us and not gold_from_us.get("need_websearch"):
            global_markets["gold"] = gold_from_us
    
    # 亚太市场
    asia_rows = ""
    for key, name in [("nikkei", "日经225"), ("hsi", "恒生指数")]:
        item = global_markets.get(key, {})
        close = item.get("close")
        pct = item.get("pct")
        if close is not None and not item.get("need_websearch"):
            cls = pct_class(pct)
            close_str = f"{close:,.0f}" if close > 1000 else f"{close:,.2f}"
            asia_rows += f'<tr><td>{name}</td><td class="{cls}">{close_str}({format_pct(pct)})</td></tr>'
        else:
            asia_rows += f'<tr><td>{name}</td><td>—</td></tr>'
    
    # 汇率与大宗
    fx_rows = ""
    for key, name in [("dxy", "美元指数DXY"), ("cnh", "离岸人民币"), ("gold", "COMEX黄金")]:
        item = global_markets.get(key, {})
        close = item.get("close")
        pct = item.get("pct")
        if close is not None and not item.get("need_websearch"):
            cls = pct_class(pct)
            close_str = f"{close:,.2f}"
            fx_rows += f'<tr><td>{name}</td><td class="{cls}">{close_str}({format_pct(pct)})</td></tr>'
        else:
            fx_rows += f'<tr><td>{name}</td><td>—</td></tr>'
    
    html = '<div class="global-grid">\n'
    html += '    <div class="global-box">\n'
    html += '        <div class="box-label">亚太市场</div>\n'
    html += f'        <table class="data-table"><tbody>{asia_rows}</tbody></table>\n'
    html += '    </div>\n'
    html += '    <div class="global-box">\n'
    html += '        <div class="box-label">汇率与大宗</div>\n'
    html += f'        <table class="data-table"><tbody>{fx_rows}</tbody></table>\n'
    html += '    </div>\n'
    html += '</div>'
    return html


def build_a_review_table_html(data):
    """生成昨日A股回顾表格 HTML"""
    yesterday = data.get("yesterday", {})
    breadth = yesterday.get("market_breadth", {})
    north = yesterday.get("north_bound", {})
    turnover = yesterday.get("turnover", {})
    sectors = yesterday.get("sectors", {})
    
    rows = ""
    
    # 成交额
    turnover_total = turnover.get("total", 0)
    if turnover_total > 0:
        turnover_str = format_amount(turnover_total) if turnover_total >= 10000 else f"{turnover_total:.0f}亿"
        turnover_note = turnover.get("note", "")
        rows += f'<tr><td>两市成交额</td><td class="num">{turnover_str}</td><td>{turnover_note}</td></tr>'
    else:
        rows += f'<tr><td>两市成交额</td><td class="num">—</td><td>待补充</td></tr>'
    
    # 涨跌家数
    up_count = breadth.get("up_count") or 0
    down_count = breadth.get("down_count") or 0
    limit_up = breadth.get("limit_up") or 0
    limit_down = breadth.get("limit_down") or 0
    if up_count > 0 or down_count > 0:
        breadth_note = "涨多跌少" if up_count > down_count else "跌多涨少"
        if limit_up > 0 or limit_down > 0:
            breadth_note += f"，涨停{limit_up}/跌停{limit_down}"
        rows += f'<tr><td>上涨/下跌家数</td><td class="num">{up_count:,} / {down_count:,}</td><td>{breadth_note}</td></tr>'
    else:
        rows += f'<tr><td>上涨/下跌家数</td><td class="num">—</td><td>待补充</td></tr>'
    
    # 北向资金 - 修复：读取 net_inflow 字段，处理 NaN/None
    import math
    north_amount = north.get("net_inflow")
    is_nan = north_amount is None or (isinstance(north_amount, float) and math.isnan(north_amount))
    
    if not is_nan and north_amount != 0:
        north_cls = "up" if north_amount > 0 else "down"
        north_sign = "+" if north_amount > 0 else ""
        north_note = "外资净流入" if north_amount > 0 else "外资净流出"
        color_var = "red-up" if north_amount > 0 else "green-down"
        rows += f'<tr><td>北向资金</td><td class="num" style="color:var(--{color_var});">净流入 {north_sign}{north_amount:.0f}亿</td><td>{north_note}</td></tr>'
    else:
        rows += f'<tr><td>北向资金</td><td class="num">—</td><td>数据停更</td></tr>'
    
    # 领涨领跌板块
    top_gainers = sectors.get("top_gainers", [])
    top_losers = sectors.get("top_losers", [])
    
    def _format_sector_items(items):
        formatted = []
        for s in items[:3]:
            if "name" not in s:
                continue
            pct = s.get("pct")
            if isinstance(pct, (int, float)):
                formatted.append(f'{s["name"]}({pct:+.2f}%)')
            else:
                formatted.append(f'{s["name"]}(—)')
        return "、".join(formatted)

    if top_gainers and len(top_gainers) > 0 and not top_gainers[0].get("need_websearch"):
        top_str = _format_sector_items(top_gainers)
        rows += f'<tr><td>领涨板块</td><td colspan="2">{top_str}</td></tr>'
    else:
        rows += f'<tr><td>领涨板块</td><td colspan="2">—</td></tr>'
    
    if top_losers and len(top_losers) > 0 and not top_losers[0].get("need_websearch"):
        bottom_str = _format_sector_items(top_losers)
        rows += f'<tr><td>领跌板块</td><td colspan="2">{bottom_str}</td></tr>'
    else:
        rows += f'<tr><td>领跌板块</td><td colspan="2">—</td></tr>'
    
    html = '<table class="data-table">\n'
    html += '    <thead>\n'
    html += '        <tr><th>项目</th><th>数值</th><th>备注</th></tr>\n'
    html += '    </thead>\n'
    html += f'    <tbody>{rows}</tbody>\n'
    html += '</table>'
    return html


def build_index_card_block(idx):
    """构建指数卡片 HTML"""
    if not idx or "error" in idx or idx.get("need_websearch"):
        return '<div class="price">—</div><div class="pct">—</div>'
    
    close = idx.get("close", 0)
    pct = idx.get("pct", 0)
    cls = "up" if pct >= 0 else "down"
    
    return f'<div class="price {cls}">{close:,.2f}</div><div class="pct {cls}">{format_pct(pct)}</div>'


def build_today_prediction_table_html(ai_texts):
    """生成今日预判表格 HTML（从 AI 文本中提取字段）"""
    direction = ai_texts.get("DIRECTION_JUDGMENT", "—")
    signal_class = ai_texts.get("DIRECTION_SIGNAL_CLASS", "neutral")
    range_low = ai_texts.get("SH_RANGE_LOW", "—")
    range_high = ai_texts.get("SH_RANGE_HIGH", "—")
    position = ai_texts.get("POSITION_ADVICE", "—")
    pace = ai_texts.get("PARTICIPATION_PACE", "—")
    
    range_str = f"{range_low} ~ {range_high}"
    
    html = '<table class="data-table">\n'
    html += '    <thead>\n'
    html += '        <tr><th>方向判断</th><th>上证区间</th><th>仓位建议</th><th>参与节奏</th></tr>\n'
    html += '    </thead>\n'
    html += '    <tbody>\n'
    html += f'        <tr>'
    html += f'<td><span class="signal-badge {signal_class}">{direction}</span></td>'
    html += f'<td class="num">{range_str}</td>'
    html += f'<td>{position}</td>'
    html += f'<td>{pace}</td>'
    html += '</tr>\n'
    html += '    </tbody>\n'
    html += '</table>'
    return html


def build_event_timeline_html(data):
    """生成近期重磅事件时间线 HTML——支持结构化数据（含日期/时间/影响），禁止空时间线。"""
    news_events = data.get("news_events", {})
    items = news_events.get("events", [])

    if not items:
        items = build_event_fallbacks(data)

    if items and isinstance(items[0], dict):
        timeline_html = '<div class="timeline">\n'
        for i, item in enumerate(items):
            css_class = item.get("css_class") or ("done" if i % 3 == 0 else ("bullish" if i % 3 == 1 else "bearish"))
            item_date = item.get("date") or item.get("time") or "待确认"
            text = item.get("text") or item.get("title") or ""
            impact = item.get("impact") or ""
            if impact:
                text = f"{text}：{impact}" if text else impact
            if not text:
                continue
            tag_html = ""
            tag = item.get("tag") or item.get("level") or ""
            if tag:
                tag_html = f'<span class="timeline-tag {css_class}">{tag}</span>'
            timeline_html += f'    <div class="timeline-item {css_class}">\n'
            timeline_html += f'        <div class="timeline-date">{item_date}</div>\n'
            timeline_html += f'        <div class="timeline-text">{text}{tag_html}</div>\n'
            timeline_html += f'    </div>\n'
        timeline_html += '</div>'
        return timeline_html

    if items:
        timeline_html = '<div class="timeline">\n'
        for i, item in enumerate(items):
            css_class = "done" if i % 3 == 0 else ("bullish" if i % 3 == 1 else "bearish")
            timeline_html += f'    <div class="timeline-item {css_class}">\n'
            timeline_html += f'        <div class="timeline-date">重点</div>\n'
            timeline_html += f'        <div class="timeline-text">{item}</div>\n'
            timeline_html += f'    </div>\n'
        timeline_html += '</div>'
        return timeline_html

    return '<div class="timeline"><div class="timeline-item bearish"><div class="timeline-date">待补充</div><div class="timeline-text">重大事件数据缺失，请优先补齐国内外对A股影响最大的事件。</div></div></div>'


def build_event_fallbacks(data):
    """当 news_events 缺失时，生成重大事件日历兜底，而不是盘面分析事件。"""
    report_date = data.get("report_date", "") or "今日"
    return [
        {
            "date": report_date,
            "text": "重磅事件日历待补齐",
            "impact": "该模块只写近期重大国内外事件，如美联储主席/新主席讲话、美国CPI/PPI/非农、国内LPR/PMI/社融、重要政策会议、AI/半导体/新能源重大发布会；禁止用指数涨跌、北向资金、板块涨跌、成交额等盘面复盘替代。",
            "tag": "需补充",
            "css_class": "bearish",
        }
    ]


# ==================== 模板填充 ====================

def fill_template(template_html, data, ai_texts):
    """填充 HTML 模板"""
    yesterday = data.get("yesterday", {})
    indices = yesterday.get("indices", [])
    
    # 构建指数卡片
    idx_map = {idx.get("name", ""): idx for idx in indices if "error" not in idx}
    
    sh_idx = idx_map.get("上证指数", {})
    sz_idx = idx_map.get("深证成指", {})
    cyb_idx = idx_map.get("创业板指", {})
    hs300_idx = idx_map.get("沪深300", {})
    
    # 计算日期
    report_date = data.get("report_date", datetime.now().strftime("%Y-%m-%d"))
    dt = datetime.strptime(report_date, "%Y-%m-%d")
    yesterday_date = (dt - timedelta(days=1)).strftime("%m月%d日")
    data_cutoff = (dt - timedelta(days=1)).strftime("%Y-%m-%d") + " 15:00"
    
    # 计算学习进度
    samples_dir = os.path.join(SCRIPT_DIR, "..", "references", "samples")
    sample_count = 0
    if os.path.exists(samples_dir):
        sample_count = len([f for f in os.listdir(samples_dir) if f.endswith(".txt")])
    learning_day = sample_count
    learning_progress = min(100, sample_count * 10)
    
    # 美股数据
    us_data = data.get("overnight_us", {})
    
    # 动态生成 HTML 片段
    replacements = {
        "{{REPORT_DATE}}": report_date,
        "{{REPORT_DATETIME}}": data.get("generated_at", ""),
        "{{DATA_CUTOFF_DATETIME}}": data_cutoff,
        "{{YESTERDAY_DATE}}": yesterday_date,
        "{{LEARNING_DAY}}": str(learning_day),
        "{{LEARNING_PROGRESS}}": str(learning_progress),
        # A股指数卡片
        "{{SH_INDEX_CARD_BLOCK}}": build_index_card_block(sh_idx),
        "{{SZ_INDEX_CARD_BLOCK}}": build_index_card_block(sz_idx),
        "{{CYB_INDEX_CARD_BLOCK}}": build_index_card_block(cyb_idx),
        "{{HS300_INDEX_CARD_BLOCK}}": build_index_card_block(hs300_idx),
        # 隔夜美股（动态生成）
        "{{US_CARDS_HTML}}": build_us_cards_html(us_data),
        "{{US_TABLE_HTML}}": build_us_table_html(us_data),
        "{{US_EXTENDED_GRID_HTML}}": build_us_extended_grid_html(us_data),
        # 全球市场（动态生成）- 修复：传入完整 data
        "{{GLOBAL_MARKET_HTML}}": build_global_market_html(data),
        # A股回顾表格（动态生成）
        "{{A_REVIEW_TABLE_HTML}}": build_a_review_table_html(data),
        # 事件时间线
        "{{EVENT_TIMELINE}}": build_event_timeline_html(data),
        # 今日预判表格（从 AI 文本字段动态生成）
        "{{TODAY_PREDICTION_TABLE_HTML}}": build_today_prediction_table_html(ai_texts),
        # 板块方向（AI 文本生成）
        "{{SECTOR_DIRECTIONS_HTML}}": ai_texts.get("SECTOR_DIRECTIONS", ""),
        # 风险提示（AI 文本生成）
        "{{RISK_WARNINGS}}": ai_texts.get("RISK_WARNINGS", ""),
        # 操作策略（AI 文本生成）
        "{{OPERATION_STRATEGY}}": ai_texts.get("OPERATION_STRATEGY", ""),
        # 方法论沉淀（AI 文本生成）
        "{{STYLE_SUMMARY}}": ai_texts.get("STYLE_SUMMARY", ""),
        # 昨日回顾补充
        "{{YESTERDAY_REVIEW}}": ai_texts.get("YESTERDAY_REVIEW", ""),
        # 🆕 心态管理（从盘前策略吸收）
        "{{MENTALITY_MANAGEMENT_CONTENT}}": ai_texts.get("MENTALITY_MANAGEMENT", ""),
        # 🆕 操作纪律条目（从盘前策略吸收）
        "{{OPERATION_DISCIPLINE_ITEMS}}": ai_texts.get("OPERATION_DISCIPLINE", ""),
        # 🆕 全球市场对A股影响分析
        "{{GLOBAL_MARKET_ANALYSIS}}": ai_texts.get("GLOBAL_MARKET_ANALYSIS", ""),
    }
    
    # 添加 AI 文本（兼容旧字段名）
    for key, val in ai_texts.items():
        placeholder = f"{{{{{key}}}}}"
        if placeholder not in replacements:
            replacements[placeholder] = str(val) if not isinstance(val, str) else val
    
    result = template_html
    for key, val in replacements.items():
        result = result.replace(key, str(val))
    
    return result


def html_to_pdf(html_path, pdf_path):
    """HTML 转 PDF"""
    # 尝试 WeasyPrint
    try:
        from weasyprint import HTML
        HTML(filename=html_path).write_pdf(pdf_path)
        return True
    except Exception as e:
        logger.exception(f"WeasyPrint PDF 生成失败: {e}")

    # 回退到 Chrome headless
    chrome = shutil.which("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not chrome:
        chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if chrome:
        try:
            subprocess.run(
                [chrome, "--headless", "--disable-gpu", "--no-sandbox",
                 f"--print-to-pdf={os.path.abspath(pdf_path)}",
                 os.path.abspath(html_path)],
                check=True, timeout=60,
            )
            return True
        except Exception as e:
            logger.exception(f"Chrome headless PDF 生成失败: {e}")

    logger.info("[WARN] PDF 生成失败，仅保存 HTML")
    return False


def update_stock_tracker(args, data):
    """维护早报入选股票跟踪 JSON，并生成独立 HTML 表格。"""
    if args.no_stock_tracker:
        return

    report_date = data.get("report_date", datetime.now().strftime("%Y-%m-%d"))
    analysis_path = args.analysis_json

    if not analysis_path:
        ai_texts_dir = os.path.dirname(os.path.abspath(args.ai_texts))
        candidates = [
            os.path.join(ai_texts_dir, "llm_analysis.json"),
            os.path.join(os.path.dirname(ai_texts_dir), "llm_analysis.json"),
            os.path.join(SCRIPT_DIR, "..", "tmp", "llm_analysis.json"),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                analysis_path = candidate
                break

    if not analysis_path or not os.path.exists(analysis_path):
        logger.info("[WARN] 未找到 llm_analysis.json，跳过股票跟踪更新")
        return

    tracker_json = args.stock_tracker_json or os.path.join(SKILL_DIR, "data", "stock_selection_tracker.json")
    # deploy_to_cloudflare.py publishes SKILL_DIR/tmp/stock_tracker.html.
    # Keep the default tracker HTML in the same location to avoid deploying stale pages.
    tracker_html = args.stock_tracker_html or os.path.join(SKILL_DIR, "tmp", "stock_tracker.html")
    tracker_script = os.path.join(SCRIPT_DIR, "stock_tracker.py")
    if not os.path.exists(tracker_script):
        legacy_script = os.path.join(SCRIPT_DIR, "legacy", "stock_tracker.py")
        if os.path.exists(legacy_script):
            tracker_script = legacy_script

    cmd = [
        sys.executable,
        tracker_script,
        "update",
        "--analysis", analysis_path,
        "--date", report_date,
        "--current-date", report_date,
        "--tracker", tracker_json,
        "--html", tracker_html,
    ]
    env = os.environ.copy()
    # legacy/stock_tracker.py imports utils.py living in SCRIPT_DIR; ensure it's importable.
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = SCRIPT_DIR + (os.pathsep + existing_pp if existing_pp else "")
    if env.get("MARKET_DATA_USE_PROXY", "0") != "1":
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env.pop(key, None)
        no_proxy_hosts = ["push2his.eastmoney.com", "push2.eastmoney.com", "qt.gtimg.cn", "ifzq.gtimg.cn"]
        existing = env.get("NO_PROXY") or env.get("no_proxy") or ""
        merged = [item.strip() for item in existing.split(",") if item.strip()]
        for host in no_proxy_hosts:
            if host not in merged:
                merged.append(host)
        env["NO_PROXY"] = ",".join(merged)
        env["no_proxy"] = env["NO_PROXY"]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=90, env=env)
        logger.info(f"[OK] 股票跟踪已更新: {tracker_json}")
        if result.stdout.strip():
            logger.info(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        logger.info(f"[WARN] 股票跟踪更新失败: {(e.stderr or e.stdout or '')[:300]}")
    except Exception as e:
        logger.info(f"[WARN] 股票跟踪更新异常: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="market_data.json 路径")
    parser.add_argument("--ai-texts", required=True, help="AI 生成文本 JSON 路径")
    parser.add_argument("--html", default=None, help="输出 HTML 路径（可选）")
    parser.add_argument("--pdf", default=None, help="输出 PDF 路径")
    parser.add_argument("--feishu-push", action="store_true", default=False, help="生成后自动推送到飞书")
    parser.add_argument("--deploy-cloudflare", action="store_true", default=False, help="生成后自动部署到 Cloudflare Pages")
    parser.add_argument("--cloudflare-project", default="stock-morning-brief", help="Cloudflare Pages 项目名")
    parser.add_argument("--cloudflare-no-history", action="store_true", default=False, help="Cloudflare 部署时不按日期保留历史版本")
    parser.add_argument("--analysis-json", default=None, help="llm_analysis.json 路径，用于维护入选股票跟踪")
    parser.add_argument("--stock-tracker-json", default=None, help="股票跟踪 JSON 路径")
    parser.add_argument("--stock-tracker-html", default=None, help="股票跟踪 HTML 输出路径")
    parser.add_argument("--no-stock-tracker", action="store_true", default=False, help="跳过入选股票跟踪更新")
    parser.add_argument("--cloudflare-url", default=None, help="Cloudflare Pages 部署 URL（用于飞书推送）")
    args = parser.parse_args()
    
    if not args.html and not args.pdf:
        logger.info("[ERROR] 至少需要 --html 或 --pdf 之一")
        sys.exit(1)
    
    data = load_json_safe(args.data)
    ai_texts = load_json_safe(args.ai_texts)
    
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()
    
    report_html = fill_template(template, data, ai_texts)
    
    html_path = args.html
    is_temp = False
    if not html_path and args.pdf:
        fd, html_path = tempfile.mkstemp(suffix=".html", prefix="morning_brief_")
        os.close(fd)
        is_temp = True
    
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(report_html)
    if not is_temp:
        logger.info(f"[OK] HTML 已生成: {html_path}")

    if args.pdf:
        ok = html_to_pdf(html_path, args.pdf)
        if ok:
            logger.info(f"[OK] PDF 已生成: {args.pdf}")
        else:
            logger.info(f"[WARN] PDF 生成失败，HTML 在: {html_path}")
    
    update_stock_tracker(args, data)
    
    cloudflare_url = None
    if args.deploy_cloudflare:
        deploy_script = os.path.join(SCRIPT_DIR, "deploy_to_cloudflare.py")
        deploy_cmd = [
            sys.executable,
            deploy_script,
            "--html", html_path,
            "--project", args.cloudflare_project,
        ]
        if args.cloudflare_no_history:
            deploy_cmd.append("--no-history")
        try:
            result = subprocess.run(
                deploy_cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=360,
            )
            combined_output = (result.stdout or "") + "\n" + (result.stderr or "")
            json_match = re.search(r'\{[^\n]*"cloudflare_url"[^\n]*\}', combined_output)
            if json_match:
                deploy_info = json.loads(json_match.group(0))
                cloudflare_url = deploy_info.get("cloudflare_url")
                logger.info(f"[OK] Cloudflare 已部署: {cloudflare_url}")
                print(json.dumps(deploy_info, ensure_ascii=False))
            else:
                match = re.search(r"https://[^\s]+", combined_output)
                if match:
                    cloudflare_url = match.group(0).rstrip(".,)")
                    logger.info(f"[OK] Cloudflare 已部署: {cloudflare_url}")
                    print(json.dumps({"cloudflare_url": cloudflare_url}, ensure_ascii=False))
                else:
                    logger.info("[WARN] Cloudflare 部署成功，但未解析到URL")
                    print(result.stdout)
        except subprocess.CalledProcessError as e:
            logger.info(f"[ERROR] Cloudflare 部署失败: {(e.stderr or e.stdout or '')[:500]}")
            sys.exit(1)
        except Exception as e:
            logger.info(f"[ERROR] Cloudflare 部署异常: {e}")
            sys.exit(1)
    
    if args.feishu_push:
        # 优先使用命令行传入的 cloudflare_url，否则使用部署生成的
        push_to_feishu(html_path, data, ai_texts, args.cloudflare_url or cloudflare_url)
    
    if is_temp and args.pdf:
        try:
            os.unlink(html_path)
        except Exception as e:
            logger.exception(f"删除临时 HTML 文件失败: {e}")


if __name__ == "__main__":
    main()
