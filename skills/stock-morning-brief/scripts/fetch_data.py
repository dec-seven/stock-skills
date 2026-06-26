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

# ==================== 日志系统 ====================
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from logger import get_logger
from run_context import get_run_id
from utils import safe_float

logger = get_logger('fetch_data')

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
    except Exception as e:
        logger.exception(f"新浪美股行情获取失败: {e}")
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
        logger.info(f"腾讯API错误: {str(e)[:50]}")
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
    except Exception as e:
        logger.exception(f"东方财富实时行情获取失败: {e}")
    return None


# ==================== A股指数获取（多数据源） ====================

def fill_a_indices(data):
    """填充A股指数 - 多数据源尝试，优先腾讯财经"""
    logger.info("\n=== 填充 A股指数 ===")

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
                    logger.info(f"腾讯 {name}: {close:.2f} ({pct:+.2f}%)")
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
                            logger.info(f"AkShare {name}: {close:.2f}")
                            continue
                except Exception as e:
                    logger.exception(f"AkShare获取指数数据失败: {e}")

            mark_websearch(idx, "所有数据源失败")

        # 保存成交额到 turnover
        if total_amount > 0:
            data["yesterday"]["turnover"]["total"] = round(total_amount / 1e8, 2)
            data["yesterday"]["turnover"]["source"] = "tencent"
            data["yesterday"]["turnover"]["need_websearch"] = False
            logger.info(f"两市成交额: {total_amount/1e8:.2f}亿")

    except Exception as e:
        logger.info(f"腾讯批量查询失败: {str(e)[:60]}")
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
                logger.info(f"腾讯 {name}: {tencent_data['close']:.2f}")
            else:
                mark_websearch(idx, "获取失败")


# ==================== 市场情绪数据 ====================

def fill_market_breadth(data):
    """填充涨跌家数 - 优先用乐咕市场活跃度(轻量稳定)，全量接口作兜底"""
    logger.info("\n=== 填充涨跌家数 ===")
    breadth = data["yesterday"]["market_breadth"]

    # 1. 优先：乐咕市场活跃度（单次轻量接口，避免拉全量5000股被风控）
    if AKSHARE_AVAILABLE:
        try:
            df = ak.stock_market_activity_legu()
            if df is not None and not df.empty:
                kv = {str(r["item"]).strip(): r["value"] for _, r in df.iterrows()}
                def _num(k):
                    try:
                        return int(float(kv.get(k)))
                    except Exception as e:
                        logger.debug(f"数值转换失败: {k} -> {kv.get(k)}", key=k, value=kv.get(k), error=str(e))
                        return None
                up = _num("上涨"); down = _num("下跌"); flat = _num("平盘")
                limit_up = _num("涨停"); limit_down = _num("跌停")
                if up is not None and down is not None:
                    breadth.update({
                        "up_count": up,
                        "down_count": down,
                        "flat_count": flat,
                        "limit_up": limit_up,
                        "limit_down": limit_down,
                        "total_count": (up + down + (flat or 0)) if up is not None else None,
                        "source": "akshare_legu",
                        "need_websearch": False,
                    })
                    logger.info(f"乐咕活跃度 上涨:{up} 下跌:{down} 涨停:{limit_up} 跌停:{limit_down}")
                    return
        except Exception as e:
            logger.info(f"乐咕活跃度失败: {str(e)[:50]}")

    # 2. 兜底：全量行情统计（易被东财风控，可能 RemoteDisconnected）
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
                logger.info(f"上涨:{up} 下跌:{down} 涨停:{limit_up}")
                return
        except Exception as e:
            logger.info(f"全量行情统计失败: {str(e)[:50]}")

    mark_websearch(breadth, "获取失败")


def fill_turnover(data):
    """填充成交额"""
    logger.info("\n=== 填充成交额 ===")
    turnover = data["yesterday"]["turnover"]

    # 如果已有成交额数据（来自腾讯财经），跳过
    if turnover.get("total") and turnover.get("source") == "tencent":
        logger.info(f"成交额已由腾讯财经填充: {turnover['total']:.2f}亿")
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
                logger.info(f"两市成交额: {turnover['total']:.2f}亿")
                return
        except Exception as e:
            logger.exception(f"AkShare获取成交额失败: {e}")

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
            logger.info(f"两市成交额: {turnover['total']:.2f}亿")
            return
    except Exception as e:
        logger.exception(f"东方财富获取成交额失败: {e}")

    mark_websearch(turnover, "获取失败")


def fill_north_bound(data):
    """填充北向资金
    注意: 沪深港通自2024-08-19起停止披露每日净买入额，
    stock_hsgt_hist_em 的净额列(当日成交净买额/当日资金流入)已恒为 NaN。
    此处尝试取净额，取不到则标记 websearch(由 Agent 补成交额等替代口径)。
    """
    logger.info("\n=== 填充北向资金 ===")
    nb = data["yesterday"]["north_bound"]

    if AKSHARE_AVAILABLE:
        try:
            df = ak.stock_hsgt_hist_em(symbol="北向资金")
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                # 优先实际列名: 当日成交净买额 / 当日资金流入
                for col in ["当日成交净买额", "当日资金流入"]:
                    if col in df.columns:
                        net = safe_float(latest.get(col))
                        if net is not None:
                            nb.update({
                                "net_inflow": round(net, 2),
                                "source": "akshare",
                                "need_websearch": False,
                            })
                            logger.info(f"北向净流入: {net:.2f}亿 ({col})")
                            return
                logger.info("北向净额列为 NaN(官方2024-08起停披露)，转 WebSearch 补成交额")
        except Exception as e:
            logger.info(f"北向获取失败: {str(e)[:50]}")

    mark_websearch(nb, "官方停披露净额,需补成交额口径")


def fill_fund_flow(data):
    """
    填充主力资金流向（行业 + 大盘）
    新增到 data["yesterday"]["fund_flow"]，供 ai_texts 生成资金面判断
    """
    logger.info("\n=== 填充主力资金流向 ===")

    if not AKSHARE_AVAILABLE:
        logger.info("AKShare 不可用，跳过资金流向")
        return

    fund_flow = data["yesterday"].setdefault("fund_flow", {
        "market_main_net":   None,   # 全市场主力净流入（亿）
        "market_main_pct":   None,   # 净占比 %
        "top_inflow_sectors": [],    # 资金净流入最多的5个行业
        "top_outflow_sectors":[],    # 资金净流出最多的5个行业
        "need_websearch": True
    })

    # 1. 行业资金流向（即时）
    try:
        df = ak.stock_fund_flow_industry(symbol='即时')
        if df is not None and not df.empty:
            df = df.sort_values(by='净额', ascending=False)
            top_in  = df.head(5)
            top_out = df.tail(5)

            fund_flow["top_inflow_sectors"] = []
            for _, row in top_in.iterrows():
                fund_flow["top_inflow_sectors"].append({
                    "name":       str(row.get("行业", "")),
                    "net_inflow": round(float(row.get("净额", 0)), 2),
                    "pct_change": round(float(row.get("行业-涨跌幅", 0)), 2),
                    "leader":     str(row.get("领涨股", "")),
                    "leader_pct": round(float(row.get("领涨股-涨跌幅", 0)), 2)
                })

            fund_flow["top_outflow_sectors"] = []
            for _, row in top_out.iterrows():
                fund_flow["top_outflow_sectors"].append({
                    "name":        str(row.get("行业", "")),
                    "net_outflow": round(float(row.get("净额", 0)), 2),
                    "pct_change":  round(float(row.get("行业-涨跌幅", 0)), 2)
                })

            fund_flow["need_websearch"] = False
            logger.info(f"行业资金流向: 净流入前5={[s['name'] for s in fund_flow['top_inflow_sectors']]}")
    except Exception as e:
        logger.info(f"行业资金流向获取失败: {e}")

    # 2. 大盘主力资金净流入（历史日度）
    try:
        df_mkt = ak.stock_market_fund_flow()
        if df_mkt is not None and not df_mkt.empty:
            latest = df_mkt.iloc[-1]
            for col in df_mkt.columns:
                if "主力净流入" in str(col) and "净额" in str(col):
                    val = float(latest[col]) / 1e8  # 转亿
                    fund_flow["market_main_net"] = round(val, 2)
                if "主力净流入" in str(col) and "净占比" in str(col):
                    fund_flow["market_main_pct"] = round(float(latest[col]), 2)
            if fund_flow["market_main_net"] is not None:
                logger.info(f"全市场主力净流入: {fund_flow['market_main_net']:.1f}亿 ({fund_flow['market_main_pct']}%)")
    except Exception as e:
        logger.info(f"大盘资金流向获取失败: {e}")


def fill_sectors(data):
    """填充行业板块 - 东财优先，新浪行业作兜底(东财全量易被风控)"""
    logger.info("\n=== 填充行业板块 ===")
    sectors = data["yesterday"]["sectors"]

    # 1. 东财行业板块
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
                logger.info("东财行业板块")
                return
        except Exception as e:
            logger.info(f"东财行业板块失败(转新浪): {str(e)[:50]}")

    # 2. 新浪行业兜底(分类较粗,但稳定)
    if AKSHARE_AVAILABLE:
        try:
            df = ak.stock_sector_spot(indicator="新浪行业")
            if df is not None and not df.empty and "涨跌幅" in df.columns:
                df["涨跌幅"] = df["涨跌幅"].astype(float)
                df = df.sort_values(by="涨跌幅", ascending=False)
                for i, item in enumerate(sectors["top_gainers"]):
                    if i < len(df):
                        row = df.iloc[i]
                        item["name"] = str(row.get("板块", ""))
                        item["pct"] = round(float(row.get("涨跌幅", 0)), 2)
                        item["need_websearch"] = False
                for i, item in enumerate(sectors["top_losers"]):
                    if i < len(df):
                        row = df.iloc[-(i+1)]
                        item["name"] = str(row.get("板块", ""))
                        item["pct"] = round(float(row.get("涨跌幅", 0)), 2)
                        item["need_websearch"] = False
                logger.info("新浪行业板块(兜底)")
                return
        except Exception as e:
            logger.info(f"新浪行业板块失败: {str(e)[:50]}")

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
    except Exception as e:
        logger.exception(f"腾讯美股行情获取失败: {e}")
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
    except Exception as e:
        logger.exception(f"东方财富美股行情获取失败: {e}")
    return None


def fetch_sina_us_full(sina_code):
    """新浪美股/指数行情（gb_ 美股个股与指数, 含 gb_$ 指数）
    格式: var hq_str_gb_nvda="英伟达,现价,涨跌幅,时间,涨跌额,昨收,开盘,最高,最低,..."
    解析: parts[1]=现价 parts[2]=涨跌幅 parts[5]=昨收
    """
    url = f"http://hq.sinajs.cn/list={sina_code}"
    try:
        resp = requests.get(url, timeout=8, headers={"Referer": "https://finance.sina.com.cn"})
        resp.encoding = "gbk"
        match = re.search(r'="([^"]*)"', resp.text)
        if match and match.group(1):
            parts = match.group(1).split(",")
            if len(parts) >= 3:
                close = safe_float(parts[1])
                pct = safe_float(parts[2])
                if close is not None and pct is not None:
                    return {"close": round(close, 2), "pct": round(pct, 2), "source": "sina"}
    except Exception as e:
        logger.exception(f"新浪美股/指数行情获取失败: {e}")
    return None


def fetch_sina_futures(sina_code):
    """新浪国际期货行情（hf_CL 原油, hf_GC 黄金）
    格式: var hq_str_hf_CL="当前价,,买价,卖价,最高,最低,时间,开盘,昨收,...,日期,名称,..."
    parts[0]=当前价 parts[8]=昨收
    """
    url = f"http://hq.sinajs.cn/list={sina_code}"
    try:
        resp = requests.get(url, timeout=8, headers={"Referer": "https://finance.sina.com.cn"})
        resp.encoding = "gbk"
        match = re.search(r'="([^"]*)"', resp.text)
        if match and match.group(1):
            parts = match.group(1).split(",")
            if len(parts) >= 9:
                close = safe_float(parts[0])
                prev_close = safe_float(parts[8])
                if close is not None and prev_close:
                    pct = round((close - prev_close) / prev_close * 100, 2)
                    return {"close": round(close, 2), "pct": pct, "source": "sina"}
    except Exception as e:
        logger.exception(f"新浪国际期货行情获取失败: {e}")
    return None


def fill_us_data(data):
    """填充美股数据 - 多数据源优先级：腾讯 > 东方财富 > 新浪 > yfinance"""
    logger.info("\n=== 填充美股数据 ===")

    # 数据源映射：(key, 腾讯代码, 东方财富secid, yfinance代码, 新浪代码, 新浪类型)
    # 新浪类型: 'gb'=美股/指数(gb_), 'hf'=国际期货(hf_)
    ticker_map = {
        "dow":    ("DJI",  None,        "^DJI",  "gb_$dji",  "gb"),
        "sp500":  ("INX",  None,        "^GSPC", "gb_$inx",  "gb"),
        "nasdaq": ("IXIC", None,        "^IXIC", "gb_$ixic", "gb"),
        "vix":    ("VIX",  None,        "^VIX",  "gb_$vix",  "gb"),
        "sox":    (None,   None,        "^SOX",  "gb_$sox",  "gb"),   # 费城半导体(新浪)
        "nvda":   (None,   None,        "NVDA",  "gb_nvda",  "gb"),   # 英伟达(新浪,东财个股换算不可靠)
        "tsla":   (None,   None,        "TSLA",  "gb_tsla",  "gb"),   # 特斯拉(新浪,东财个股换算不可靠)
        "oil":    (None,   None,        "CL=F",  "hf_CL",    "hf"),   # WTI原油
        "gold":   (None,   None,        "GC=F",  "hf_GC",    "hf"),   # 黄金
    }

    for key, (tencent_symbol, em_secid, yf_symbol, sina_symbol, sina_type) in ticker_map.items():
        if key not in data["overnight_us"]:
            continue

        item = data["overnight_us"][key]
        result = None

        # 1. 优先尝试腾讯美股（指数）
        if tencent_symbol and not result:
            result = fetch_tencent_us_quote(tencent_symbol)
            if result:
                logger.info(f"腾讯 {item['name']}: {result['close']:.2f} ({result['pct']:+.2f}%)")

        # 2. 尝试东方财富美股（个股）
        if em_secid and not result:
            result = fetch_em_us_quote(em_secid)
            if result:
                logger.info(f"东方财富 {item['name']}: {result['close']:.2f} ({result['pct']:+.2f}%)")

        # 3. 尝试新浪（最稳定的备用源，覆盖 SOX/NVDA/TSLA/原油/黄金）
        if sina_symbol and not result:
            if sina_type == "gb":
                result = fetch_sina_us_full(sina_symbol)
            elif sina_type == "hf":
                result = fetch_sina_futures(sina_symbol)
            if result:
                logger.info(f"新浪 {item['name']}: {result['close']:.2f} ({result['pct']:+.2f}%)")

        # 4. 尝试 yfinance（最后备选，常被限流）
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
                    logger.info(f"yfinance {item['name']}: {close:.2f}")
            except Exception as e:
                err_str = str(e)
                if "RateLimit" not in err_str:
                    logger.info(f"yfinance {item['name']}: {err_str[:50]}")

        if result:
            item.update(result)
            item["need_websearch"] = False
        else:
            mark_websearch(item, "获取失败")


def fetch_sina_intl_index(sina_code):
    """新浪国际指数(int_ 前缀, 如 int_hangseng 恒生指数)
    格式: var hq_str_int_hangseng="恒生指数,现价,涨跌额,涨跌幅"
    parts[1]=现价 parts[3]=涨跌幅
    """
    url = f"http://hq.sinajs.cn/list={sina_code}"
    try:
        resp = requests.get(url, timeout=8, headers={"Referer": "https://finance.sina.com.cn"})
        resp.encoding = "gbk"
        match = re.search(r'="([^"]*)"', resp.text)
        if match and match.group(1):
            parts = match.group(1).split(",")
            if len(parts) >= 4:
                close = safe_float(parts[1])
                pct = safe_float(parts[3])
                if close is not None and pct is not None:
                    return {"close": round(close, 2), "pct": round(pct, 2), "source": "sina"}
    except Exception as e:
        logger.exception(f"新浪国际指数获取失败: {e}")
    return None


def fetch_sina_fx_cnh(sina_code="fx_susdcnh"):
    """新浪离岸人民币(fx_susdcnh)
    格式: var hq_str_fx_susdcnh="时间,开,高,低,?,买,卖,昨收,现价,名称,..."
    末段含现价与昨收, 取倒数解析较稳: parts[8]=现价? 需稳健提取数字
    实测: 09:32:11,6.7759,6.7779,6.7771,45,6.7779,6.7797,6.7752,6.7759,离岸人民币...
    parts[1]=今开 parts[8]=现价 ... 用 parts[8] 现价, parts[3]=昨收? 不稳，改用现价+无pct
    """
    url = f"http://hq.sinajs.cn/list={sina_code}"
    try:
        resp = requests.get(url, timeout=8, headers={"Referer": "https://finance.sina.com.cn"})
        resp.encoding = "gbk"
        match = re.search(r'="([^"]*)"', resp.text)
        if match and match.group(1):
            parts = match.group(1).split(",")
            # 提取所有形如汇率的数字(6.x)
            rates = [safe_float(p) for p in parts if p and re.match(r'^6\.\d+$', p.strip())]
            if rates:
                cur = rates[-1] if len(rates) >= 1 else None
                # 现价取中间偏后的一个稳定值
                cur = safe_float(parts[8]) or cur
                if cur:
                    return {"close": round(cur, 4), "pct": 0.0, "source": "sina"}
    except Exception as e:
        logger.exception(f"新浪离岸人民币获取失败: {e}")
    return None


def fill_global_markets(data):
    """填充全球市场 - yfinance 优先，新浪 int_/gb_$ 作备用"""
    logger.info("\n=== 填充全球市场 ===")

    # (key, yfinance代码, 新浪代码, 新浪类型) 类型: 'gb'=gb_$指数, 'int'=int_国际指数
    global_map = {
        "nikkei": ("^N225", None,           None),    # 日经225 新浪无稳定源 -> websearch
        "hsi":    ("^HSI",  "int_hangseng", "int"),   # 恒生指数
        "dxy":    ("DX-Y.NYB", None,        None),     # 美元指数 -> websearch
    }

    for key, (symbol, sina_symbol, sina_type) in global_map.items():
        if key not in data["global_markets"]:
            continue

        item = data["global_markets"][key]
        done = False

        # 1. yfinance
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
                    logger.info(f"yfinance {item['name']}: {close:.2f}")
                    done = True
            except Exception as e:
                logger.exception(f"yfinance获取{item['name']}失败: {e}")

        # 2. 新浪备用
        if not done and sina_symbol:
            r = fetch_sina_intl_index(sina_symbol) if sina_type == "int" else fetch_sina_us_full(sina_symbol)
            if r:
                item.update({
                    "close": r["close"],
                    "pct": r["pct"],
                    "source": "sina",
                    "need_websearch": False,
                })
                logger.info(f"新浪 {item['name']}: {r['close']:.2f} ({r['pct']:+.2f}%)")
                done = True

        if not done:
            mark_websearch(item, "获取失败")

    # 离岸人民币单独处理
    if "cnh" in data["global_markets"]:
        r = fetch_sina_fx_cnh()
        if r:
            data["global_markets"]["cnh"].update({
                "close": r["close"],
                "pct": r["pct"],
                "source": "sina",
                "need_websearch": False,
            })
            logger.info(f"新浪 离岸人民币: {r['close']:.4f}")
        else:
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
        "2026-06-19", "2026-06-20", "2026-06-21",  # 端午（上交所公告：6/19-6/21休市，6/22起开市）
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

    logger.info(f"报告日期: {args.date}")
    
    # 交易日检查
    if not args.force:
        is_trading, reason = is_trading_day(args.date)
        if not is_trading:
            logger.info(f"{args.date} 不是交易日：{reason}")
            logger.info("使用 --force 参数可强制执行")
            logger.info("如需生成报告，请指定最近的交易日日期")
            sys.exit(0)
        else:
            logger.info("交易日检查通过")
    
    logger.info(f"AkShare: {'可用' if AKSHARE_AVAILABLE else '不可用'}")
    logger.info(f"yfinance: {'可用' if YFINANCE_AVAILABLE else '不可用'}")

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
    fill_fund_flow(data)      # 新增：主力资金流向（行业净流入 + 大盘主力）
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

    logger.info(f"\n需 WebSearch 补充: {websearch_count} 项")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"已保存: {args.output}")


if __name__ == "__main__":
    main()
