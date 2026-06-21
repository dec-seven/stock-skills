#!/usr/bin/env python3
"""
股票入选跟踪器：维护每日早报入选股票及后续收益表现，并生成独立 HTML 表格。

用法：
  python3 stock_tracker.py update \
    --analysis ./tmp/llm_analysis.json \
    --date 2026-06-15 \
    --tracker ./data/stock_selection_tracker.json \
    --html ./tmp/stock_tracker.html

字段：入选日期、股票、入选原因（10字以内）、入选评分、入选时价格、入选日/T+1...T+7单日涨跌幅、累计涨跌幅。
"""

import argparse
import json
import os
import re
import sys
from html import escape
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

try:
    import akshare as ak
except ImportError:
    ak = None


def configure_market_data_network():
    """行情接口默认不走本机代理，避免 akshare/东方财富被代理连接拖死。"""
    if os.environ.get("MARKET_DATA_USE_PROXY", "0") == "1":
        return
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(key, None)
    no_proxy_hosts = [
        "push2his.eastmoney.com",
        "push2.eastmoney.com",
        "qt.gtimg.cn",
        "ifzq.gtimg.cn",
    ]
    existing = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    merged = [item.strip() for item in existing.split(",") if item.strip()]
    for host in no_proxy_hosts:
        if host not in merged:
            merged.append(host)
    os.environ["NO_PROXY"] = ",".join(merged)
    os.environ["no_proxy"] = os.environ["NO_PROXY"]


configure_market_data_network()

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
WORKSPACE_DIR = SKILL_DIR.parent.parent
DEFAULT_TRACKER = SKILL_DIR / "data" / "stock_selection_tracker.json"
DEFAULT_HTML = WORKSPACE_DIR / "tmp" / "stock_tracker.html"
MAX_RECORDS = 100
RETURN_KEYS = ["selected_day"] + [f"t_plus_{i}" for i in range(1, 8)]
DISPLAY_RETURN_KEYS = ["selected_day", "t_plus_1", "t_plus_3", "t_plus_5", "t_plus_7"]


# ==================== 基础工具 ====================

def load_json(path, default):
    path = Path(path)
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def parse_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def normalize_code(code):
    return str(code).strip().zfill(6)


def infer_market_prefix(code, market_class=""):
    code = normalize_code(code)
    market_class = (market_class or "").lower()
    if market_class in ("sh", "sz", "bj"):
        return market_class
    if code.startswith(("60", "68", "90")):
        return "sh"
    if code.startswith(("00", "30", "20")):
        return "sz"
    if code.startswith(("43", "83", "87", "92")):
        return "bj"
    return "sh"


def tencent_symbol(code, market_class=""):
    return f"{infer_market_prefix(code, market_class)}{normalize_code(code)}"


def safe_float(value, default=None):
    try:
        if value in (None, "", "-"):
            return default
        return float(value)
    except Exception:
        return default


def get_stock_logic(stock):
    logic = stock.get("logic", {})
    if not isinstance(logic, dict):
        logic = {"core": str(logic or "")}
    return {
        "core": logic.get("core") or logic.get("核心逻辑", ""),
        "data": logic.get("data") or logic.get("关键数据", ""),
        "catalyst": logic.get("catalyst") or logic.get("催化事件", ""),
        "risk": logic.get("risk") or logic.get("风险提示", ""),
    }


def normalize_logic_detail(detail):
    """将 logic_detail 统一成 {核心逻辑, 关键数据, 催化事件, 风险提示} 结构。"""
    if not isinstance(detail, dict):
        return {label: "" for label in ["核心逻辑", "关键数据", "催化事件", "风险提示"]}
    return {
        "核心逻辑": detail.get("core") or detail.get("核心逻辑", ""),
        "关键数据": detail.get("data") or detail.get("关键数据", ""),
        "催化事件": detail.get("catalyst") or detail.get("催化事件", ""),
        "风险提示": detail.get("risk") or detail.get("风险提示", ""),
    }


def calc_score_summary(stock):
    fund_scores = stock.get("fund_scores", {}) or {}
    tech_scores = stock.get("tech_scores", {}) or {}
    fund_total = sum(safe_float(v, 0) or 0 for v in fund_scores.values())
    tech_total = sum(safe_float(v, 0) or 0 for v in tech_scores.values())
    return {
        "total": int(round(fund_total + tech_total)),
        "fund_total": int(round(fund_total)),
        "tech_total": int(round(tech_total)),
        "fund_scores": fund_scores,
        "tech_scores": tech_scores,
    }


def short_reason(stock):
    """从选股逻辑中压缩入选原因到10字以内。"""
    text = ""
    logic = get_stock_logic(stock)
    text = logic.get("core") or logic.get("catalyst") or logic.get("data") or ""

    candidates = [
        ("有色", "有色涨价"),
        ("黄金", "黄金高位"),
        ("铜", "铜价上涨"),
        ("钼", "钼价上涨"),
        ("航天", "航天催化"),
        ("低空", "低空催化"),
        ("电池", "电池修复"),
        ("储能", "储能催化"),
        ("券商", "券商修复"),
        ("资金", "资金流入"),
        ("涨停", "涨停带动"),
        ("业绩", "业绩验证"),
        ("龙头", "行业龙头"),
    ]
    for key, reason in candidates:
        if key in text:
            return reason[:10]
    return "逻辑入选"


# ==================== 行情获取 ====================

def fetch_tencent_quote(code, market_class=""):
    """腾讯行情接口，返回当前价。"""
    if requests is None:
        return None
    symbol = tencent_symbol(code, market_class)
    url = f"http://qt.gtimg.cn/q={symbol}"
    try:
        resp = requests.get(url, timeout=10)
        resp.encoding = "gbk"
        match = re.search(r'="([^"]+)"', resp.text)
        if not match:
            return None
        parts = match.group(1).split("~")
        if len(parts) < 5:
            return None
        name = parts[1]
        close = safe_float(parts[3])
        prev_close = safe_float(parts[4])
        pct = safe_float(parts[32]) if len(parts) > 32 else None
        if close is None:
            return None
        return {
            "name": name,
            "code": normalize_code(code),
            "market_class": infer_market_prefix(code, market_class),
            "close": close,
            "prev_close": prev_close,
            "pct": pct,
            "source": "tencent",
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as exc:
        print(f"[WARN] 腾讯行情获取失败 {code}: {exc}", file=sys.stderr)
        return None


def fetch_price(code, market_class=""):
    quote = fetch_tencent_quote(code, market_class)
    if quote:
        return quote
    return {
        "name": "",
        "code": normalize_code(code),
        "market_class": infer_market_prefix(code, market_class),
        "close": None,
        "source": "unavailable",
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def fetch_tencent_prev_close(code, target_date, market_class=""):
    """开盘前用腾讯实时行情的昨收回填上一交易日收盘价。"""
    if datetime.now().date() <= parse_date(target_date):
        return None
    quote = fetch_tencent_quote(code, market_class)
    prev_close = quote.get("prev_close") if quote else None
    if prev_close is None:
        return None
    return {
        "price": prev_close,
        "date": target_date,
        "trade_day": 1,
        "source": "tencent_prev_close",
    }


def calc_return(base_price, current_price):
    if base_price in (None, 0) or current_price is None:
        return None
    return round((current_price - base_price) / base_price * 100, 2)


def _history_date_range(selected_date, current_date):
    """给历史K线留足前后缓冲，避免停牌/节假日导致目标交易日缺失。"""
    start = (parse_date(selected_date) - timedelta(days=10)).strftime("%Y%m%d")
    end = (parse_date(current_date) + timedelta(days=20)).strftime("%Y%m%d")
    return start, end


def get_effective_current_date(current_date):
    """15:00前不使用当天日K，避免盘中价被当作收盘价。"""
    try:
        current = parse_date(current_date)
    except Exception:
        return current_date
    now = datetime.now()
    if current == now.date() and now.hour < 15:
        return (current - timedelta(days=1)).strftime("%Y-%m-%d")
    return current_date


def fetch_tencent_daily_history(code, selected_date, current_date, market_class=""):
    """腾讯历史K线回退源，返回按日期升序排列的 [{date, close}]。"""
    if requests is None:
        return []
    current_date = get_effective_current_date(current_date)
    symbol = tencent_symbol(code, market_class)
    start = (parse_date(selected_date) - timedelta(days=10)).strftime("%Y-%m-%d")
    end = (parse_date(current_date) + timedelta(days=20)).strftime("%Y-%m-%d")
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,{start},{end},80,qfq"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        payload = resp.json()
        stock_data = payload.get("data", {}).get(symbol, {})
        raw_rows = stock_data.get("qfqday") or stock_data.get("day") or []
    except Exception as exc:
        print(f"[WARN] 腾讯历史K线获取失败 {code}: {exc}", file=sys.stderr)
        return []

    rows = []
    prev_close = None
    for row in raw_rows:
        if len(row) < 3:
            continue
        close = safe_float(row[2])
        if close is None:
            continue
        pct = calc_return(prev_close, close) if prev_close not in (None, 0) else None
        rows.append({
            "date": str(row[0])[:10],
            "close": close,
            "pct": pct,
        })
        prev_close = close
    rows.sort(key=lambda item: item["date"])
    return rows


def fetch_daily_history(code, selected_date, current_date, market_class=""):
    """获取A股日K，优先 AKShare/东方财富，失败后回退腾讯历史K线。"""
    if ak is not None:
        current_date = get_effective_current_date(current_date)
        start_date, end_date = _history_date_range(selected_date, current_date)
        try:
            df = ak.stock_zh_a_hist(
                symbol=normalize_code(code),
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="",
            )
            if df is not None and not df.empty and "日期" in df.columns and "收盘" in df.columns:
                rows = []
                for _, row in df.iterrows():
                    close = safe_float(row.get("收盘"))
                    if close is None:
                        continue
                    rows.append({
                        "date": str(row.get("日期"))[:10],
                        "close": close,
                        "pct": safe_float(row.get("涨跌幅")),
                    })
                rows.sort(key=lambda item: item["date"])
                if rows:
                    return rows
        except Exception as exc:
            print(f"[WARN] AKShare日K获取失败 {code}: {exc}", file=sys.stderr)
    else:
        print("[WARN] akshare 未安装，尝试使用腾讯历史K线", file=sys.stderr)

    return fetch_tencent_daily_history(code, selected_date, current_date, market_class)


def get_selected_day_item(history, selected_date):
    for item in history:
        if item["date"] == selected_date:
            return item
    return None


def empty_daily_returns():
    return {key: None for key in RETURN_KEYS}


def empty_return_dates():
    return {key: None for key in RETURN_KEYS}


def calc_cumulative_return(daily_returns):
    values = [safe_float(daily_returns.get(key), None) for key in RETURN_KEYS]
    valid = [value for value in values if value is not None]
    if not valid:
        return None
    return round(sum(valid), 2)


def ensure_return_v2_shape(record):
    """迁移到 v2：保留旧 returns 为 legacy_returns，新口径使用 daily_returns。"""
    if "daily_returns" not in record:
        if "returns" in record and "legacy_returns" not in record:
            record["legacy_returns"] = record.get("returns")
        if "return_prices" in record and "legacy_return_prices" not in record:
            record["legacy_return_prices"] = record.get("return_prices")
        old_dates = record.get("return_dates", {}) or {}
        record["daily_returns"] = empty_daily_returns()
        if record.get("selected_day_pct") is not None:
            record["daily_returns"]["selected_day"] = record.get("selected_day_pct")
        record["return_dates"] = empty_return_dates()
        if old_dates.get("current"):
            record["last_return_date"] = old_dates.get("current")
    else:
        daily_returns = empty_daily_returns()
        daily_returns.update(record.get("daily_returns", {}) or {})
        record["daily_returns"] = daily_returns
        return_dates = empty_return_dates()
        return_dates.update(record.get("return_dates", {}) or {})
        record["return_dates"] = return_dates
    record["cumulative_return"] = calc_cumulative_return(record.get("daily_returns", {}) or {})
    record.pop("selected_day_pct", None)
    record.pop("returns", None)
    record.pop("return_prices", None)
    return record


def get_daily_return_updates(history, selected_date, current_date):
    """返回已收盘日K对应的单日涨跌幅：入选日、T+1...T+7。"""
    effective_current_date = get_effective_current_date(current_date)
    candidates = [item for item in history if selected_date <= item["date"] <= effective_current_date]
    candidates.sort(key=lambda item: item["date"])
    updates = {}
    for idx, item in enumerate(candidates[:8]):
        key = "selected_day" if idx == 0 else f"t_plus_{idx}"
        updates[key] = {
            "pct": item.get("pct"),
            "date": item.get("date"),
            "close": item.get("close"),
        }
    return updates


# ==================== 维护逻辑 ====================

def ensure_tracker_shape(tracker):
    if not isinstance(tracker, dict):
        tracker = {}
    tracker["version"] = "2.0"
    tracker.setdefault("updated_at", "")
    tracker.setdefault("max_records", MAX_RECORDS)
    tracker.setdefault("records", [])
    return tracker


def record_key(record):
    return (record.get("selected_date"), normalize_code(record.get("code", "")))


def add_selected_stocks(tracker, analysis_path, selected_date):
    analysis = load_json(analysis_path, {})
    stocks = analysis.get("STOCKS", [])
    if not isinstance(stocks, list):
        print("[WARN] analysis.STOCKS 不是数组，跳过新增", file=sys.stderr)
        return 0

    existing = {record_key(r) for r in tracker["records"]}
    added = 0

    for stock in stocks:
        code = normalize_code(stock.get("code", ""))
        if not code or code == "000000":
            continue
        key = (selected_date, code)
        if key in existing:
            continue
        market_class = stock.get("market_class", "")
        quote = fetch_price(code, market_class)
        selected_price = quote.get("close")
        logic_detail = normalize_logic_detail(get_stock_logic(stock))
        score_summary = calc_score_summary(stock)
        record = {
            "selected_date": selected_date,
            "name": stock.get("name") or quote.get("name") or "",
            "code": code,
            "market_class": infer_market_prefix(code, market_class),
            "reason": short_reason(stock),
            "logic_detail": logic_detail,
            "score_summary": score_summary,
            "selected_price": selected_price,
            "selected_price_source": quote.get("source"),
            "selected_price_time": quote.get("fetched_at"),
            "daily_returns": empty_daily_returns(),
            "return_dates": empty_return_dates(),
            "cumulative_return": None,
            "last_return_date": None,
            "last_checked_at": "",
        }
        tracker["records"].append(record)
        existing.add(key)
        added += 1

    return added


def enrich_records_from_analysis(tracker, analysis_path):
    """用 llm_analysis.json 为既有记录补充详细逻辑与评分。"""
    if not analysis_path:
        return 0
    analysis_file = Path(analysis_path)
    if not analysis_file.exists():
        return 0
    analysis = load_json(analysis_file, {})
    stocks = analysis.get("STOCKS", [])
    if not isinstance(stocks, list):
        return 0

    stock_map = {normalize_code(s.get("code", "")): s for s in stocks if s.get("code")}
    changed = 0
    for record in tracker.get("records", []):
        stock = stock_map.get(normalize_code(record.get("code", "")))
        if not stock:
            continue
        logic_detail = normalize_logic_detail(get_stock_logic(stock))
        score_summary = calc_score_summary(stock)
        if record.get("logic_detail") != logic_detail:
            record["logic_detail"] = logic_detail
            changed += 1
        if record.get("score_summary") != score_summary:
            record["score_summary"] = score_summary
            changed += 1
    return changed


PUBLISH_DIR = Path(__file__).resolve().parent.parent / "tmp" / "cloudflare_publish"
HTML_FALLBACK_DIRS = [
    Path(__file__).resolve().parent.parent / "tmp",
    Path(__file__).resolve().parents[3],
]


def _parse_stock_card_html(card_html):
    name = re.search(r'<span class="stock-name">([^<]+)</span>', card_html)
    code = re.search(r'<span class="stock-code">([^<]+)</span>', card_html)
    total = re.search(r'<div class="score-val">\s*(\d+)\s*</div>', card_html)
    if not (name and code and total):
        return None
    bars = {}
    for m in re.finditer(
        r'<span class="score-bar-label">([^<]+)</span>.*?'
        r'<span class="score-bar-val[^"]*">\s*(\d+)\s*/\s*(\d+)\s*</span>',
        card_html, re.S,
    ):
        try:
            bars[m.group(1).strip()] = int(m.group(2))
        except ValueError:
            continue
    logic_match = re.search(r'<div class="stock-logic">(.*?)</div>', card_html, re.S)
    logic = {label: "" for label in ["核心逻辑", "关键数据", "催化事件", "风险提示"]}
    if logic_match:
        block = re.sub(r"<br\s*/?>", "\n", logic_match.group(1))
        block = re.sub(r"<[^>]+>", "", block)
        block = block.replace("&nbsp;", " ")
        for label in ["核心逻辑", "关键数据", "催化事件", "风险提示"]:
            m = re.search(rf'{label}\s*[：:]\s*([^\n]+)', block)
            if m:
                logic[label] = m.group(1).strip()
    fund_labels = ["业务纯正度", "行业地位", "涨价受益度", "业绩验证",
                   "催化剂临近", "估值位置", "特殊标签"]
    tech_labels = ["MACD", "KDJ", "成交量", "均线系统", "支撑压力"]
    return {
        "name": name.group(1).strip(),
        "code": code.group(1).strip(),
        "total": int(total.group(1)),
        "fund_scores": {k: bars[k] for k in fund_labels if k in bars},
        "tech_scores": {k: bars[k] for k in tech_labels if k in bars},
        "logic": logic,
    }


def _parse_published_brief(date_str):
    """从指定日期的发布版/工作区早报 HTML 提取 stock-card 列表。"""
    candidates = [PUBLISH_DIR / date_str / "index.html"]
    for parent in HTML_FALLBACK_DIRS:
        candidates.append(parent / f"morning_brief_{date_str}.html")
    for path in candidates:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        markers = [m.start() for m in re.finditer(r'<div class="stock-card">', text)]
        if not markers:
            continue
        cards = []
        for i, m in enumerate(markers):
            end = markers[i + 1] if i + 1 < len(markers) else m + 5000
            parsed = _parse_stock_card_html(text[m:end])
            if parsed:
                cards.append(parsed)
        if cards:
            return cards
    return []


# 手工回退：历史入选但 HTML 中没有写入选股卡的标的，按 6.15 早报主题补充。
MANUAL_FALLBACK = {
    "2026-06-15": {
        "300750": {
            "name": "宁德时代",
            "logic": {
                "core": "全球动力电池龙头，受益新能源车销量回升与储能放量，电池板块修复。",
                "data": "近期新能源车销量同比转正，储能招标量价齐升，行业排产环比改善。",
                "catalyst": "新能源车下乡+以旧换新政策延续，电池价格触底回升，板块估值修复。",
                "risk": "新能源车销量不及预期，电池产能过剩压制毛利，海外政策扰动。",
            },
            "fund_scores": {"业务纯正度": 9, "行业地位": 10, "涨价受益度": 7, "业绩验证": 8,
                            "催化剂临近": 7, "估值位置": 6, "特殊标签": 8},
            "tech_scores": {"MACD": 6, "KDJ": 5, "成交量": 5, "均线系统": 4, "支撑压力": 3},
        },
        "600547": {
            "name": "山东黄金",
            "logic": {
                "core": "国内黄金龙头，受益金价中长期上行与避险情绪升温，资源储量行业领先。",
                "data": "国际金价突破历史新高，国内黄金ETF持仓持续增加，公司Q1利润同比高增。",
                "catalyst": "地缘风险+美联储降息预期+央行购金，金价中枢上移。",
                "risk": "金价高位回吐风险，汇率波动影响，销售费用抬升。",
            },
            "fund_scores": {"业务纯正度": 10, "行业地位": 9, "涨价受益度": 9, "业绩验证": 8,
                            "催化剂临近": 8, "估值位置": 5, "特殊标签": 8},
            "tech_scores": {"MACD": 7, "KDJ": 6, "成交量": 5, "均线系统": 4, "支撑压力": 3},
        },
        "600862": {
            "name": "中航高科",
            "logic": {
                "core": "国内航空复合材料龙头，受益国产大飞机与航天发射密度提升，订单确定性强。",
                "data": "C919商业运营加速，复合材料订单饱满，公司毛利率持续改善。",
                "catalyst": "SpaceX IPO+商业航天政策+军品订单兑现，板块估值预期抬升。",
                "risk": "军品交付节奏波动，原材料价格扰动，估值短期偏高。",
            },
            "fund_scores": {"业务纯正度": 9, "行业地位": 9, "涨价受益度": 6, "业绩验证": 8,
                            "催化剂临近": 8, "估值位置": 6, "特殊标签": 8},
            "tech_scores": {"MACD": 6, "KDJ": 5, "成交量": 5, "均线系统": 4, "支撑压力": 3},
        },
        "601696": {
            "name": "中银证券",
            "logic": {
                "core": "中小型券商，受益政策底确认后市场情绪修复与成交量回升，板块弹性大。",
                "data": "两市成交额重回3万亿以上，北向资金周净流入389亿，券商板块估值仍处低位。",
                "catalyst": "政策底+流动性宽松+市场情绪修复，券商板块有补涨空间。",
                "risk": "成交量持续性不及预期，市场风格切换至防御，板块短线波动加大。",
            },
            "fund_scores": {"业务纯正度": 8, "行业地位": 7, "涨价受益度": 5, "业绩验证": 7,
                            "催化剂临近": 8, "估值位置": 7, "特殊标签": 7},
            "tech_scores": {"MACD": 6, "KDJ": 5, "成交量": 6, "均线系统": 4, "支撑压力": 3},
        },
        "601138": {
            "name": "工业富联",
            "logic": {
                "core": "AI服务器代工龙头，直接受益海外AI硬件景气和英伟达产业链需求。",
                "data": "隔夜纳指+3.07%、费城半导体+5.45%，AI硬件映射增强；公司AI服务器订单饱满。",
                "catalyst": "AI服务器排产+海外芯片股大涨+CPO/PCB链轮动，板块资金主攻。",
                "risk": "市值大、弹性弱于小票；若科技线高开低走，短线承压。",
            },
            "fund_scores": {"业务纯正度": 9, "行业地位": 10, "涨价受益度": 7, "业绩验证": 9,
                            "催化剂临近": 8, "估值位置": 6, "特殊标签": 8},
            "tech_scores": {"MACD": 7, "KDJ": 5, "成交量": 6, "均线系统": 5, "支撑压力": 3},
        },
    },
}


def _score_summary_from_dicts(fund_scores, tech_scores):
    fund_total = sum(int(v) for v in fund_scores.values())
    tech_total = sum(int(v) for v in tech_scores.values())
    return {
        "total": fund_total + tech_total,
        "fund_total": fund_total,
        "tech_total": tech_total,
        "fund_scores": fund_scores,
        "tech_scores": tech_scores,
    }


def enrich_records_from_published_html(tracker):
    """对缺 logic/score 的记录，按入选日找历史早报 HTML 补全；找不到再走手工回退。"""
    date_to_cards = {}
    date_to_manual = {}
    enriched = 0
    for record in tracker.get("records", []):
        if record.get("logic_detail") and record.get("score_summary"):
            continue
        date_str = record.get("selected_date", "")
        code = record.get("code", "")
        if not (date_str and code):
            continue
        if date_str not in date_to_cards:
            date_to_cards[date_str] = _parse_published_brief(date_str)
        cards = date_to_cards[date_str]
        match = next((c for c in cards if c["code"] == code), None)
        if not match:
            manual_pool = MANUAL_FALLBACK.get(date_str, {})
            if code not in date_to_manual:
                date_to_manual[code] = manual_pool.get(code)
            payload = date_to_manual[code]
            if not payload:
                continue
            logic_detail = payload["logic"]
            score_summary = _score_summary_from_dicts(
                payload["fund_scores"], payload["tech_scores"]
            )
        else:
            logic_detail = match["logic"]
            score_summary = _score_summary_from_dicts(
                match["fund_scores"], match["tech_scores"]
            )
        if record.get("logic_detail") != logic_detail:
            record["logic_detail"] = logic_detail
            enriched += 1
        if record.get("score_summary") != score_summary:
            record["score_summary"] = score_summary
            enriched += 1
        if not record.get("reason"):
            record["reason"] = (logic_detail.get("core") or "")[:10]
    return enriched


def update_returns(tracker, current_date):
    updated = 0

    for record in tracker["records"]:
        ensure_return_v2_shape(record)
        daily_returns = record.setdefault("daily_returns", empty_daily_returns())
        return_dates = record.setdefault("return_dates", empty_return_dates())

        selected_date = record.get("selected_date", "")
        code = record.get("code", "")
        if not selected_date or not code:
            continue

        history = fetch_daily_history(code, selected_date, current_date, record.get("market_class", ""))
        if not history:
            continue

        updates = get_daily_return_updates(history, selected_date, current_date)
        changed = False
        for key in RETURN_KEYS:
            item = updates.get(key)
            if not item:
                continue
            pct = item.get("pct")
            date_value = item.get("date")
            if daily_returns.get(key) != pct or return_dates.get(key) != date_value:
                daily_returns[key] = pct
                return_dates[key] = date_value
                updated += 1
                changed = True

        cumulative = calc_cumulative_return(daily_returns)
        if record.get("cumulative_return") != cumulative:
            record["cumulative_return"] = cumulative
            updated += 1
            changed = True

        valid_dates = [return_dates.get(key) for key in RETURN_KEYS if return_dates.get(key)]
        last_return_date = valid_dates[-1] if valid_dates else None
        if record.get("last_return_date") != last_return_date:
            record["last_return_date"] = last_return_date
            updated += 1
            changed = True

        if changed:
            record["last_checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            record["return_calc_rule"] = "daily_pct_sum_v2"

    return updated


def enforce_limit(tracker):
    max_records = int(tracker.get("max_records") or MAX_RECORDS)
    records = tracker.get("records", [])
    records.sort(key=lambda r: (r.get("selected_date", ""), r.get("code", "")))
    removed = max(0, len(records) - max_records)
    if removed:
        tracker["records"] = records[removed:]
    else:
        tracker["records"] = records
    return removed


def update_tracker(args):
    tracker = ensure_tracker_shape(load_json(args.tracker, {}))
    selected_date = args.date
    current_date = args.current_date or selected_date

    added = 0
    if args.analysis:
        added = add_selected_stocks(tracker, args.analysis, selected_date)
        enrich_records_from_analysis(tracker, args.analysis)

    enriched = enrich_records_from_published_html(tracker)

    updated = update_returns(tracker, current_date)
    removed = enforce_limit(tracker)
    tracker["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    save_json(args.tracker, tracker)
    if args.html:
        generate_html(tracker, args.html)
        # Backward compatibility: keep the old workspace-level tmp page fresh too,
        # in case an external preview/bookmark still points there.
        html_path = Path(args.html).resolve()
        legacy_html = WORKSPACE_DIR / "tmp" / "stock_tracker.html"
        if html_path != legacy_html.resolve():
            generate_html(tracker, legacy_html)

    print(json.dumps({
        "tracker": str(args.tracker),
        "html": str(args.html) if args.html else "",
        "added": added,
        "enriched_from_history": enriched,
        "updated_returns": updated,
        "removed_old_records": removed,
        "total": len(tracker.get("records", [])),
    }, ensure_ascii=False))


# ==================== HTML 渲染 ====================

def pct_class(value):
    if value is None:
        return "neutral"
    return "up" if value >= 0 else "down"


def fmt_pct(value):
    if value is None:
        return "待补"
    return f"+{value:.2f}%" if value > 0 else f"{value:.2f}%"


def fmt_return(value, date_value=None):
    text = fmt_pct(value)
    if value is None or not date_value:
        return text
    return f'{text}<br><small>{date_value}</small>'


def fmt_price(value):
    if value is None:
        return "待补"
    return f"{value:.2f}"


def score_fill_class(value, max_value):
    if value is None or max_value in (None, 0):
        return "bad"
    ratio = value / max_value
    if ratio >= 0.7:
        return "good"
    if ratio >= 0.4:
        return "mid"
    return "bad"


def render_logic_tooltip(record):
    detail = normalize_logic_detail(record.get("logic_detail", {}))
    items = [
        ("核心逻辑", detail.get("核心逻辑", "")),
        ("关键数据", detail.get("关键数据", "")),
        ("催化事件", detail.get("催化事件", "")),
        ("风险提示", detail.get("风险提示", "")),
    ]
    body = "".join(
        f'<div class="tip-row"><strong>{escape(label)}：</strong>{escape(text or "待补")}</div>'
        for label, text in items
    )
    return f'<span class="hover-cell reason-cell">{escape(record.get("reason", ""))}<span class="tooltip logic-tooltip">{body}</span></span>'


def render_score_bars(score_summary):
    if not score_summary:
        return '<div class="tip-row">评分明细待补</div>'
    fund_scores = score_summary.get("fund_scores", {}) or {}
    tech_scores = score_summary.get("tech_scores", {}) or {}
    fund_max = {
        "业务纯正度": 10, "行业地位": 10, "涨价受益度": 10, "业绩验证": 10,
        "催化剂临近": 10, "估值位置": 10, "特殊标签": 10,
    }
    tech_max = {"MACD": 8, "KDJ": 7, "成交量": 6, "均线系统": 5, "支撑压力": 4}
    rows = []
    for name, max_value in {**fund_max, **tech_max}.items():
        source = fund_scores if name in fund_max else tech_scores
        value = safe_float(source.get(name), None)
        pct = 0 if value is None else max(0, min(100, value / max_value * 100))
        cls = score_fill_class(value, max_value)
        text = "待补" if value is None else f"{value:g}/{max_value}"
        rows.append(f'''
        <div class="score-bar-row">
          <span class="score-bar-label">{escape(name)}</span>
          <div class="score-bar-track"><div class="score-bar-fill {cls}" style="width:{pct:.0f}%"></div></div>
          <span class="score-bar-val {cls}">{text}</span>
        </div>''')
    return "".join(rows)


def render_score_cell(record):
    score = record.get("score_summary", {}) or {}
    total = score.get("total")
    fund = score.get("fund_total")
    tech = score.get("tech_total")
    if total is None:
        main = '<span class="score-empty">待补</span>'
    else:
        main = f'<span class="score-main">{int(total)}</span><span class="score-sub">映射{int(fund or 0)} / 技术{int(tech or 0)}</span>'
    tooltip = f'''
      <span class="tooltip score-tooltip">
        <div class="score-tip-head">评分明细</div>
        <div class="score-tip-total">总分 {escape(str(total if total is not None else "待补"))} · 三层映射 {escape(str(fund if fund is not None else "待补"))}/70 · 技术面 {escape(str(tech if tech is not None else "待补"))}/30</div>
        <div class="score-bars">{render_score_bars(score)}</div>
      </span>
    '''
    return f'<span class="hover-cell score-cell">{main}{tooltip}</span>'


def render_rows(records):
    rows = []
    sorted_records = sorted(records, key=lambda r: (r.get("selected_date", ""), r.get("code", "")), reverse=True)
    for r in sorted_records:
        ensure_return_v2_shape(r)
        daily_returns = r.get("daily_returns", {}) or {}
        return_dates = r.get("return_dates", {}) or {}
        row = f"""
        <tr>
          <td>{r.get('selected_date', '')}</td>
          <td class="stock"><span>{escape(r.get('name', ''))}</span><em>{escape(r.get('code', ''))}</em></td>
          <td>{render_logic_tooltip(r)}</td>
          <td>{render_score_cell(r)}</td>
          <td class="num">{fmt_price(r.get('selected_price'))}</td>
          <td class="num {pct_class(daily_returns.get('selected_day'))}">{fmt_return(daily_returns.get('selected_day'), return_dates.get('selected_day'))}</td>
          <td class="num {pct_class(daily_returns.get('t_plus_1'))}">{fmt_return(daily_returns.get('t_plus_1'), return_dates.get('t_plus_1'))}</td>
          <td class="num {pct_class(daily_returns.get('t_plus_3'))}">{fmt_return(daily_returns.get('t_plus_3'), return_dates.get('t_plus_3'))}</td>
          <td class="num {pct_class(daily_returns.get('t_plus_5'))}">{fmt_return(daily_returns.get('t_plus_5'), return_dates.get('t_plus_5'))}</td>
          <td class="num {pct_class(daily_returns.get('t_plus_7'))}">{fmt_return(daily_returns.get('t_plus_7'), return_dates.get('t_plus_7'))}</td>
          <td class="num {pct_class(r.get('cumulative_return'))}">{fmt_return(r.get('cumulative_return'), r.get('last_return_date'))}</td>
        </tr>"""
        rows.append(row)
    if not rows:
        rows.append('<tr><td colspan="11" class="empty">暂无入选股票</td></tr>')
    return "\n".join(rows)


def generate_html(tracker, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records = tracker.get("records", [])
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>早报入选股票跟踪</title>
  <style>
    :root {{
      --bg: #071426;
      --card: #0f2138;
      --card2: #132b49;
      --text: #edf4ff;
      --muted: #8ea4bf;
      --line: rgba(255,255,255,.1);
      --red: #ef4444;
      --green: #22c55e;
      --gold: #f5c542;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: radial-gradient(circle at top, #15365f 0, var(--bg) 42%); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 48px; }}
    .hero {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-end; margin-bottom: 22px; }}
    h1 {{ margin: 0; font-size: 30px; letter-spacing: .5px; }}
    .sub {{ color: var(--muted); margin-top: 8px; font-size: 14px; }}
    .badge {{ border: 1px solid rgba(245,197,66,.35); color: var(--gold); border-radius: 999px; padding: 8px 14px; background: rgba(245,197,66,.08); white-space: nowrap; }}
    .card {{ background: linear-gradient(180deg, rgba(19,43,73,.96), rgba(10,25,45,.96)); border: 1px solid var(--line); border-radius: 18px; overflow: visible; box-shadow: 0 24px 80px rgba(0,0,0,.28); }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ text-align: left; color: #bfd2ea; font-weight: 700; font-size: 13px; padding: 15px 14px; background: rgba(255,255,255,.05); border-bottom: 1px solid var(--line); white-space: nowrap; }}
    td {{ padding: 14px; border-bottom: 1px solid var(--line); color: #e6eef9; font-size: 14px; }}
    tr:hover td {{ background: rgba(255,255,255,.035); }}
    .stock span {{ display: block; font-weight: 700; }}
    .stock em {{ display: block; color: var(--muted); font-style: normal; font-size: 12px; margin-top: 3px; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .up {{ color: var(--red); font-weight: 700; }}
    .down {{ color: var(--green); font-weight: 700; }}
    .neutral {{ color: var(--muted); }}
    .empty {{ text-align: center; color: var(--muted); padding: 42px; }}
    .note {{ margin-top: 14px; color: var(--muted); font-size: 12px; line-height: 1.7; }}
    .hover-cell {{ position: relative; display: inline-flex; flex-direction: column; gap: 2px; cursor: help; }}
    .reason-cell {{ border-bottom: 1px dashed rgba(79,195,247,.6); }}
    .tooltip {{ display: none; position: absolute; left: 0; top: calc(100% + 10px); z-index: 30; min-width: 360px; max-width: 520px; padding: 14px; border-radius: 12px; background: #0b1b31; border: 1px solid rgba(79,195,247,.35); box-shadow: 0 20px 60px rgba(0,0,0,.45); color: var(--text); text-align: left; white-space: normal; }}
    .hover-cell:hover .tooltip {{ display: block; }}
    .tip-row {{ font-size: 13px; line-height: 1.55; margin-bottom: 8px; color: #dbeafe; }}
    .tip-row:last-child {{ margin-bottom: 0; }}
    .tip-row strong {{ color: var(--gold); }}
    .score-cell {{ align-items: flex-end; min-width: 72px; }}
    .score-main {{ color: var(--gold); font-size: 18px; font-weight: 800; line-height: 1; }}
    .score-sub {{ color: var(--muted); font-size: 11px; white-space: nowrap; }}
    .score-empty {{ color: var(--muted); }}
    .score-tooltip {{ left: auto; right: 0; min-width: 430px; transform: translateX(0); }}
    .score-tip-head {{ color: var(--gold); font-weight: 800; margin-bottom: 6px; }}
    .score-tip-total {{ color: #dbeafe; font-size: 12px; margin-bottom: 10px; }}
    .score-bar-row {{ display: grid; grid-template-columns: 82px 1fr 46px; gap: 8px; align-items: center; margin: 7px 0; }}
    .score-bar-label {{ color: #dbeafe; font-size: 12px; }}
    .score-bar-track {{ height: 8px; border-radius: 999px; background: rgba(255,255,255,.12); overflow: hidden; }}
    .score-bar-fill {{ height: 100%; border-radius: 999px; }}
    .score-bar-fill.good {{ background: #22c55e; }}
    .score-bar-fill.mid {{ background: #f59e0b; }}
    .score-bar-fill.bad {{ background: #ef4444; }}
    .score-bar-val {{ font-size: 12px; font-weight: 700; text-align: right; }}
    .score-bar-val.good {{ color: #22c55e; }}
    .score-bar-val.mid {{ color: #f59e0b; }}
    .score-bar-val.bad {{ color: #ef4444; }}
    @media (max-width: 820px) {{
      .hero {{ display: block; }}
      .badge {{ display: inline-block; margin-top: 14px; }}
      .card {{ overflow-x: auto; }}
      table {{ min-width: 1220px; }}
      .tooltip {{ min-width: 320px; }}
      .score-tooltip {{ min-width: 390px; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div>
        <h1>早报入选股票跟踪</h1>
        <div class="sub">跟踪每日早报入选标的入选时价格、入选日涨跌幅，T+1、T+3、T+5、T+7交易日单日涨跌幅，以及按单日涨跌幅求和的累计涨跌幅。红涨绿跌，最多保留100只。</div>
      </div>
      <div class="badge">共 {len(records)} 只 · 更新于 {tracker.get('updated_at', '')}</div>
    </div>
    <div class="card">
      <table>
        <thead>
          <tr>
            <th>入选日期</th>
            <th>股票</th>
            <th>入选原因</th>
            <th class="num">入选评分</th>
            <th class="num">入选时价格</th>
            <th class="num">入选日</th>
            <th class="num">T+1日</th>
            <th class="num">T+3日</th>
            <th class="num">T+5日</th>
            <th class="num">T+7日</th>
            <th class="num">累计涨跌幅</th>
          </tr>
        </thead>
        <tbody>
          {render_rows(records)}
        </tbody>
      </table>
    </div>
    <div class="note">
      说明：入选原因和入选评分支持鼠标悬浮查看早报原始逻辑与12项评分明细；入选时价格取早报生成时的实时价，不再被入选日收盘价覆盖；入选日/T+1/T+3/T+5/T+7均为对应交易日单日涨跌幅；累计涨跌幅按“入选日涨跌幅 + T+1涨跌幅 + ... + T+7涨跌幅”求和，未到期字段不参与计算。若历史行情接口暂不可用，则显示"待补"。本页仅用于复盘跟踪，不构成投资建议。
    </div>
  </div>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")


def cmd_render(args):
    tracker = ensure_tracker_shape(load_json(args.tracker, {}))
    generate_html(tracker, args.html)
    print(json.dumps({"html": str(args.html), "total": len(tracker.get("records", []))}, ensure_ascii=False))


# ==================== 命令入口 ====================

def main():
    parser = argparse.ArgumentParser(description="早报入选股票跟踪器")
    sub = parser.add_subparsers(dest="command")

    p_update = sub.add_parser("update", help="新增当日入选股票并补充到期收益")
    p_update.add_argument("--analysis", help="llm_analysis.json 路径，用于新增当日入选股票")
    p_update.add_argument("--date", required=True, help="入选日期 YYYY-MM-DD")
    p_update.add_argument("--current-date", default=None, help="收益补充基准日期 YYYY-MM-DD，默认等于 --date")
    p_update.add_argument("--tracker", default=str(DEFAULT_TRACKER), help="跟踪JSON路径")
    p_update.add_argument("--html", default=str(DEFAULT_HTML), help="输出HTML路径")
    p_update.set_defaults(func=update_tracker)

    p_render = sub.add_parser("render", help="从现有JSON生成HTML")
    p_render.add_argument("--tracker", default=str(DEFAULT_TRACKER), help="跟踪JSON路径")
    p_render.add_argument("--html", default=str(DEFAULT_HTML), help="输出HTML路径")
    p_render.set_defaults(func=cmd_render)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
