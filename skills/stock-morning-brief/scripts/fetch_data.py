#!/usr/bin/env python3
"""
早评数据获取脚本
用法: python3 fetch_data.py --date 2026-06-13 --output ./tmp/market_data.json

数据源优先级:
1. AkShare (优先) - A股数据
2. 新浪财经 API - 备用
3. 腾讯财经 API - 备用
4. 东方财富 API - 备用
5. yfinance - 美股数据
6. need_websearch - 最后标记，由 AI 用 WebSearch 补充

核心前提: 数据务必准确
"""

# 禁用代理（解决沙箱环境中的代理连接问题）
import os as _os
for _proxy_var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    _os.environ.pop(_proxy_var, None)

import json
import sys
import os
import argparse
import time
import re
from datetime import datetime, timedelta
import requests

# 禁用 requests 代理（解决沙箱环境中的代理连接问题）
requests.Session.trust_env = False

# ==================== 数据源导入 ====================

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


# ==================== 工具函数 ====================

def safe_float(val, default=None):
    try:
        if val is None or val == '' or val == '-':
            return default
        return float(val)
    except:
        return default


def load_template():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, "..", "templates", "market_data_template.json")
    with open(template_path, "r", encoding="utf-8") as f:
        return json.load(f)


def mark_websearch(obj, reason=""):
    if isinstance(obj, dict):
        obj["need_websearch"] = True
        if reason:
            obj["_websearch_reason"] = reason


# ==================== 新浪财经 API ====================

SINA_API = {
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "创业板指": "sz399006",
    "科创50": "sh000688",
    "北证50": "bj899050",
    "上证50": "sh000016",
    "沪深300": "sh000300",
}

def fetch_sina_quote(code):
    """新浪财经实时行情"""
    url = f"http://hq.sinajs.cn/list={code}"
    try:
        resp = requests.get(url, timeout=5)
        resp.encoding = "gbk"
        text = resp.text
        # 解析: var hq_str_sh000001="上证指数,4031.51,..."
        match = re.search(r'="([^"]+)"', text)
        if match:
            parts = match.group(1).split(",")
            if len(parts) >= 32:
                return {
                    "name": parts[0],
                    "open": safe_float(parts[1]),
                    "prev_close": safe_float(parts[2]),
                    "close": safe_float(parts[3]),
                    "high": safe_float(parts[4]),
                    "low": safe_float(parts[5]),
                    "volume": safe_float(parts[8]),
                    "amount": safe_float(parts[9]),
                }
    except Exception as e:
        pass
    return None


def fetch_sina_us_quote(symbol):
    """新浪美股行情"""
    url = f"http://hq.sinajs.cn/list=gb_{symbol.lower()}"
    try:
        resp = requests.get(url, timeout=5)
        resp.encoding = "gbk"
        text = resp.text
        match = re.search(r'="([^"]+)"', text)
        if match:
            parts = match.group(1).split(",")
            if len(parts) >= 6:
                close = safe_float(parts[1])
                change = safe_float(parts[2])
                pct = safe_float(parts[3])
                return {
                    "close": close,
                    "pct": pct,
                }
    except:
        pass
    return None


# ==================== 腾讯财经 API ====================

TENCENT_API = {
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "创业板指": "sz399006",
    "科创50": "sh000688",
    "北证50": "bj899050",
    "上证50": "sh000016",
    "沪深300": "sh000300",
}

def fetch_tencent_quote(code):
    """腾讯财经实时行情"""
    url = f"http://qt.gtimg.cn/q={code}"
    try:
        resp = requests.get(url, timeout=10)
        resp.encoding = "gbk"
        text = resp.text
        # 解析: v_sh000001="1~上证指数~000001~4031.51~..."
        match = re.search(r'="([^"]+)"', text)
        if match:
            parts = match.group(1).split("~")
            if len(parts) >= 35:
                name = parts[1]
                close = safe_float(parts[3])
                prev_close = safe_float(parts[4])
                high = safe_float(parts[33]) if len(parts) > 33 else close
                low = safe_float(parts[34]) if len(parts) > 34 else close
                pct = safe_float(parts[32]) if len(parts) > 32 else 0
                change = round(close - prev_close, 2) if close and prev_close else 0
                return {
                    "name": name,
                    "close": close,
                    "prev_close": prev_close,
                    "high": high,
                    "low": low,
                    "pct": pct,
                    "change": change,
                }
    except Exception as e:
        print(f"[DEBUG] 腾讯API错误: {str(e)[:50]}", file=sys.stderr)
    return None


# ==================== 东方财富 API ====================

EM_INDEX_MAP = {
    "上证指数": "1.000001",
    "深证成指": "0.399001",
    "创业板指": "0.399006",
    "科创50": "1.000688",
    "北证50": "0.899050",
    "上证50": "1.000016",
    "沪深300": "1.000300",
}

def fetch_em_quote(secid):
    """东方财富实时行情"""
    url = f"http://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f44,f45,f46,f47,f48,f169,f170"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data and 'data' in data and data['data']:
            d = data['data']
            close = d.get('f43', 0) / 100 if d.get('f43') else None
            pct = d.get('f170', 0) / 100 if d.get('f170') else None
            high = d.get('f44', 0) / 100 if d.get('f44') else close
            low = d.get('f45', 0) / 100 if d.get('f45') else close
            if close:
                return {
                    "close": close,
                    "pct": pct,
                    "high": high,
                    "low": low,
                }
    except:
        pass
    return None


# ==================== A股指数获取（多数据源） ====================

def fill_a_indices(data):
    """填充A股指数 - 多数据源尝试，优先腾讯财经"""
    print("\n[INFO] === 填充 A股指数 ===", file=sys.stderr)

    index_map = {
        "上证指数": ("000001", "sh"),
        "深证成指": ("399001", "sz"),
        "创业板指": ("399006", "sz"),
        "科创50": ("000688", "sh"),
        "北证50": ("899050", "bj"),
        "上证50": ("000016", "sh"),
        "沪深300": ("000300", "sh"),
    }

    # 1. 首先尝试腾讯财经批量查询（更快）
    tencent_codes = [f"{prefix}{code}" for name, (code, prefix) in index_map.items()]
    tencent_url = "http://qt.gtimg.cn/q=" + ",".join(tencent_codes)

    total_amount = 0  # 用于累计成交额

    try:
        resp = requests.get(tencent_url, timeout=10)
        resp.encoding = "gbk"
        text = resp.text

        for idx in data["yesterday"]["indices"]:
            name = idx["name"]
            if name not in index_map:
                continue

            code, prefix = index_map[name]
            tencent_code = f"{prefix}{code}"

            # 从腾讯返回中解析
            pattern = rf'v_{tencent_code}="([^"]+)"'
            match = re.search(pattern, text)
            if match:
                parts = match.group(1).split("~")
                if len(parts) >= 35:
                    close = safe_float(parts[3])
                    prev_close = safe_float(parts[4])
                    high = safe_float(parts[33]) if len(parts) > 33 else close
                    low = safe_float(parts[34]) if len(parts) > 34 else close
                    pct = safe_float(parts[32]) if len(parts) > 32 else 0
                    change = round(close - prev_close, 2) if close and prev_close else 0

                    # 解析成交额: parts[35] 格式为 "收盘价/成交量/成交额"
                    # 只累计上证和深证（避免重复计算）
                    if len(parts) > 35 and name in ["上证指数", "深证成指"]:
                        amount_parts = parts[35].split("/")
                        if len(amount_parts) >= 3:
                            amount = safe_float(amount_parts[2])
                            if amount:
                                total_amount += amount

                    idx.update({
                        "close": close,
                        "pct": round(pct, 2),
                        "change": change,
                        "high": high,
                        "low": low,
                        "source": "tencent",
                        "need_websearch": False,
                    })
                    print(f"[OK] 腾讯 {name}: {close:.2f} ({pct:+.2f}%)", file=sys.stderr)
                    continue

            # 腾讯失败，尝试 AkShare
            if AKSHARE_AVAILABLE:
                try:
                    symbol = f"{prefix}{code}"
                    df = ak.stock_zh_index_daily(symbol=symbol)
                    if df is not None and len(df) >= 2:
                        latest = df.iloc[-1]
                        prev = df.iloc[-2]
                        close = safe_float(latest.get("close"))
                        prev_close = safe_float(prev.get("close"))
                        if close and prev_close:
                            idx.update({
                                "close": round(close, 2),
                                "pct": round((close - prev_close) / prev_close * 100, 2),
                                "change": round(close - prev_close, 2),
                                "high": round(safe_float(latest.get("high", close), close), 2),
                                "low": round(safe_float(latest.get("low", close), close), 2),
                                "source": "akshare",
                                "need_websearch": False,
                            })
                            print(f"[OK] AkShare {name}: {close:.2f}", file=sys.stderr)
                            continue
                except:
                    pass

            mark_websearch(idx, "所有数据源失败")

        # 保存成交额到 turnover
        if total_amount > 0:
            data["yesterday"]["turnover"]["total"] = round(total_amount / 1e8, 2)
            data["yesterday"]["turnover"]["source"] = "tencent"
            data["yesterday"]["turnover"]["need_websearch"] = False
            print(f"[OK] 两市成交额: {total_amount/1e8:.2f}亿", file=sys.stderr)

    except Exception as e:
        print(f"[WARN] 腾讯批量查询失败: {str(e)[:60]}", file=sys.stderr)
        # 回退到逐个获取
        for idx in data["yesterday"]["indices"]:
            name = idx["name"]
            if name not in index_map:
                continue
            code, prefix = index_map[name]
            tencent_data = fetch_tencent_quote(f"{prefix}{code}")
            if tencent_data and tencent_data.get("close"):
                idx.update({
                    "close": round(tencent_data["close"], 2),
                    "pct": round(tencent_data["pct"], 2),
                    "change": tencent_data["change"],
                    "high": round(tencent_data["high"], 2),
                    "low": round(tencent_data["low"], 2),
                    "source": "tencent",
                    "need_websearch": False,
                })
                print(f"[OK] 腾讯 {name}: {tencent_data['close']:.2f}", file=sys.stderr)
            else:
                mark_websearch(idx, "获取失败")


# ==================== 市场情绪数据 ====================

def fill_market_breadth(data):
    """填充涨跌家数"""
    print("\n[INFO] === 填充涨跌家数 ===", file=sys.stderr)
    breadth = data["yesterday"]["market_breadth"]

    # 尝试 AkShare
    if AKSHARE_AVAILABLE:
        try:
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                up = down = flat = limit_up = limit_down = 0
                for _, row in df.iterrows():
                    pct = safe_float(row.get("涨跌幅", 0), 0)
                    if pct > 0: up += 1
                    elif pct < 0: down += 1
                    else: flat += 1
                    if pct >= 9.9: limit_up += 1
                    elif pct <= -9.9: limit_down += 1

                breadth.update({
                    "up_count": up,
                    "down_count": down,
                    "flat_count": flat,
                    "limit_up": limit_up,
                    "limit_down": limit_down,
                    "total_count": up + down + flat,
                    "source": "akshare",
                    "need_websearch": False,
                })
                print(f"[OK] 上涨:{up} 下跌:{down} 涨停:{limit_up}", file=sys.stderr)
                return
        except:
            pass

    mark_websearch(breadth, "获取失败")


def fill_turnover(data):
    """填充成交额"""
    print("\n[INFO] === 填充成交额 ===", file=sys.stderr)
    turnover = data["yesterday"]["turnover"]

    # 如果已有成交额数据（来自腾讯财经），跳过
    if turnover.get("total") and turnover.get("source") == "tencent":
        print(f"[OK] 成交额已由腾讯财经填充: {turnover['total']:.2f}亿", file=sys.stderr)
        return

    # 尝试 AkShare
    if AKSHARE_AVAILABLE:
        try:
            df = ak.stock_zh_a_spot_em()
            if df is not None and "成交额" in df.columns:
                total = df["成交额"].sum() / 1e8
                turnover.update({
                    "total": round(total, 2),
                    "source": "akshare",
                    "need_websearch": False,
                })
                print(f"[OK] 两市成交额: {turnover['total']:.2f}亿", file=sys.stderr)
                return
        except:
            pass

    # 尝试东方财富
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=5000&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f6"
        resp = requests.get(url, timeout=10)
        d = resp.json()
        if d and 'data' in d and d['data'] and 'diff' in d['data']:
            total = sum(s.get('f6', 0) for s in d['data']['diff'] if isinstance(s, dict)) / 1e8
            turnover.update({
                "total": round(total, 2),
                "source": "eastmoney",
                "need_websearch": False,
            })
            print(f"[OK] 两市成交额: {turnover['total']:.2f}亿", file=sys.stderr)
            return
    except:
        pass

    mark_websearch(turnover, "获取失败")


def fill_north_bound(data):
    """填充北向资金"""
    print("\n[INFO] === 填充北向资金 ===", file=sys.stderr)
    nb = data["yesterday"]["north_bound"]

    if AKSHARE_AVAILABLE:
        try:
            df = ak.stock_hsgt_hist_em(symbol="北向资金")
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                for col in df.columns:
                    if "净流入" in str(col):
                        net = safe_float(latest.get(col))
                        if net:
                            nb.update({
                                "net_inflow": round(net, 2),
                                "source": "akshare",
                                "need_websearch": False,
                            })
                            print(f"[OK] 北向净流入: {net:.2f}亿", file=sys.stderr)
                            return
        except:
            pass

    mark_websearch(nb, "获取失败")


def fill_sectors(data):
    """填充行业板块"""
    print("\n[INFO] === 填充行业板块 ===", file=sys.stderr)
    sectors = data["yesterday"]["sectors"]

    if AKSHARE_AVAILABLE:
        try:
            df = ak.stock_board_industry_name_em()
            if df is not None and not df.empty:
                df = df.sort_values(by="涨跌幅", ascending=False)
                for i, item in enumerate(sectors["top_gainers"]):
                    if i < len(df):
                        row = df.iloc[i]
                        item["name"] = str(row.get("板块名称", ""))
                        item["pct"] = safe_float(row.get("涨跌幅"))
                        item["need_websearch"] = False
                for i, item in enumerate(sectors["top_losers"]):
                    if i < len(df):
                        row = df.iloc[-(i+1)]
                        item["name"] = str(row.get("板块名称", ""))
                        item["pct"] = safe_float(row.get("涨跌幅"))
                        item["need_websearch"] = False
                print(f"[OK] 行业板块", file=sys.stderr)
                return
        except:
            pass

    for item in sectors["top_gainers"] + sectors["top_losers"]:
        mark_websearch(item, "获取失败")


# ==================== 美股数据 ====================

def fetch_tencent_us_quote(symbol):
    """腾讯美股行情（支持指数）"""
    url = f"http://qt.gtimg.cn/q=us.{symbol}"
    try:
        resp = requests.get(url, timeout=10)
        resp.encoding = "gbk"
        text = resp.text
        if "pv_none_match" in text:
            return None
        match = re.search(r'="([^"]+)"', text)
        if match:
            parts = match.group(1).split("~")
            if len(parts) >= 5:
                close = safe_float(parts[3])
                prev_close = safe_float(parts[4])
                pct = round((close - prev_close) / prev_close * 100, 2) if close and prev_close else 0
                return {"close": close, "pct": pct, "source": "tencent"}
    except:
        pass
    return None


def fetch_em_us_quote(secid):
    """东方财富美股行情（支持个股）"""
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f44,f45,f46,f47,f48,f169,f170"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data and "data" in data and data["data"]:
            d = data["data"]
            close = d.get("f43", 0) / 100 if d.get("f43") else None
            prev_close = d.get("f46", 0) / 100 if d.get("f46") else None
            pct = d.get("f170", 0) / 100 if d.get("f170") else None
            if close:
                return {"close": close, "prev_close": prev_close, "pct": pct, "source": "eastmoney"}
    except:
        pass
    return None


def fill_us_data(data):
    """填充美股数据 - 多数据源优先级：腾讯 > 东方财富 > yfinance"""
    print("\n[INFO] === 填充美股数据 ===", file=sys.stderr)

    # 数据源映射：(key, 腾讯代码, 东方财富secid, yfinance代码)
    ticker_map = {
        "dow": ("DJI", None, "^DJI"),           # 道琼斯 - 腾讯可用
        "sp500": ("INX", None, "^GSPC"),         # 标普500 - 腾讯可用
        "nasdaq": ("IXIC", None, "^IXIC"),       # 纳斯达克 - 腾讯可用
        "vix": ("VIX", None, "^VIX"),            # VIX - 腾讯可用
        "sox": (None, None, "^SOX"),             # 费城半导体 - 仅yfinance
        "nvda": (None, "105.NVDA", "NVDA"),      # 英伟达 - 东方财富可用
        "tsla": (None, "105.TSLA", "TSLA"),      # 特斯拉 - 东方财富可用
        "oil": (None, "105.CL", "CL=F"),         # 原油
        "gold": (None, "105.GC", "GC=F"),        # 黄金
    }

    for key, (tencent_symbol, em_secid, yf_symbol) in ticker_map.items():
        if key not in data["overnight_us"]:
            continue

        item = data["overnight_us"][key]
        result = None

        # 1. 优先尝试腾讯美股（指数）
        if tencent_symbol and not result:
            result = fetch_tencent_us_quote(tencent_symbol)
            if result:
                print(f"[OK] 腾讯 {item['name']}: {result['close']:.2f} ({result['pct']:+.2f}%)", file=sys.stderr)

        # 2. 尝试东方财富美股（个股）
        if em_secid and not result:
            result = fetch_em_us_quote(em_secid)
            if result:
                print(f"[OK] 东方财富 {item['name']}: {result['close']:.2f} ({result['pct']:+.2f}%)", file=sys.stderr)

        # 3. 尝试 yfinance（备选）
        if YFINANCE_AVAILABLE and yf_symbol and not result:
            try:
                ticker = yf.Ticker(yf_symbol)
                hist = ticker.history(period='2d')
                if hist is not None and len(hist) >= 2:
                    close = float(hist.iloc[-1]['Close'])
                    prev_close = float(hist.iloc[-2]['Close'])
                    result = {
                        "close": round(close, 2),
                        "pct": round((close - prev_close) / prev_close * 100, 2),
                        "source": "yfinance",
                    }
                    print(f"[OK] yfinance {item['name']}: {close:.2f}", file=sys.stderr)
            except Exception as e:
                err_str = str(e)
                if "RateLimit" not in err_str:
                    print(f"[WARN] yfinance {item['name']}: {err_str[:50]}", file=sys.stderr)

        if result:
            item.update(result)
            item["need_websearch"] = False
        else:
            mark_websearch(item, "获取失败")


def fill_global_markets(data):
    """填充全球市场"""
    print("\n[INFO] === 填充全球市场 ===", file=sys.stderr)

    # 尝试 yfinance 获取
    global_map = {
        "nikkei": "^N225",
        "hsi": "^HSI",
        "dxy": "DX-Y.NYB",
    }

    for key, symbol in global_map.items():
        if key not in data["global_markets"]:
            continue

        item = data["global_markets"][key]

        if YFINANCE_AVAILABLE:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='2d')
                if hist is not None and len(hist) >= 2:
                    close = float(hist.iloc[-1]['Close'])
                    prev_close = float(hist.iloc[-2]['Close'])
                    item.update({
                        "close": round(close, 2),
                        "pct": round((close - prev_close) / prev_close * 100, 2),
                        "source": "yfinance",
                        "need_websearch": False,
                    })
                    print(f"[OK] yfinance {item['name']}: {close:.2f}", file=sys.stderr)
                    continue
            except:
                pass

        mark_websearch(item, "获取失败")

    # 离岸人民币单独处理
    if "cnh" in data["global_markets"]:
        mark_websearch(data["global_markets"]["cnh"], "需WebSearch")


# ==================== 主函数 ====================

def is_trading_day(date_str):
    """判断是否为交易日（简化版：排除周末和主要节假日）"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    
    # 排除周末
    if dt.weekday() >= 5:  # 周六=5, 周日=6
        return False, f"周末（{['周一','周二','周三','周四','周五','周六','周日'][dt.weekday()]}）"
    
    # 排除主要节假日（简化版，可后续扩展）
    holidays_2026 = [
        "2026-01-01", "2026-01-02", "2026-01-03",  # 元旦
        "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",  # 春节
        "2026-04-04", "2026-04-05", "2026-04-06",  # 清明
        "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05",  # 劳动节
        "2026-06-25", "2026-06-26", "2026-06-27",  # 端午
        "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", 
        "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08",  # 国庆
    ]
    
    if date_str in holidays_2026:
        return False, "法定节假日"
    
    return True, "交易日"


def main():
    parser = argparse.ArgumentParser(description="早评数据获取")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--force", action="store_true", help="强制执行，跳过交易日检查")
    args = parser.parse_args()

    print(f"[INFO] 报告日期: {args.date}", file=sys.stderr)
    
    # 交易日检查
    if not args.force:
        is_trading, reason = is_trading_day(args.date)
        if not is_trading:
            print(f"[WARN] {args.date} 不是交易日：{reason}", file=sys.stderr)
            print(f"[INFO] 使用 --force 参数可强制执行", file=sys.stderr)
            print(f"[INFO] 如需生成报告，请指定最近的交易日日期", file=sys.stderr)
            sys.exit(0)
        else:
            print(f"[INFO] 交易日检查通过", file=sys.stderr)
    
    print(f"[INFO] AkShare: {'可用' if AKSHARE_AVAILABLE else '不可用'}", file=sys.stderr)
    print(f"[INFO] yfinance: {'可用' if YFINANCE_AVAILABLE else '不可用'}", file=sys.stderr)

    # 加载模板
    data = load_template()

    # 填充基础信息
    data["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["report_date"] = args.date
    dt = datetime.strptime(args.date, "%Y-%m-%d")
    data["data_cutoff"] = (dt - timedelta(days=1)).strftime("%Y-%m-%d") + " 15:00"

    # 填充数据
    fill_a_indices(data)
    fill_market_breadth(data)
    fill_turnover(data)
    fill_north_bound(data)
    fill_sectors(data)
    fill_us_data(data)
    fill_global_markets(data)

    # 统计
    websearch_count = 0
    def count_ws(obj):
        nonlocal websearch_count
        if isinstance(obj, dict):
            if obj.get("need_websearch"):
                websearch_count += 1
            for v in obj.values():
                count_ws(v)
        elif isinstance(obj, list):
            for i in obj:
                count_ws(i)
    count_ws(data)

    print(f"\n[INFO] 需 WebSearch 补充: {websearch_count} 项", file=sys.stderr)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] 已保存: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
