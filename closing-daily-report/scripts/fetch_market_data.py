#!/usr/bin/env python3
"""
AkShare 数据获取脚本
用法: python3 fetch_market_data.py [--date 2026-06-09]
输出: JSON 到 stdout
"""
import akshare as ak
import json
import sys
import argparse
import time
import functools
from datetime import datetime, timedelta


def retry(max_retries=3, delay=2, backoff=2):
    """重试装饰器，用于处理网络不稳定"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (backoff ** attempt)
                        print(f"[RETRY] {func.__name__} 第{attempt+1}次失败，{wait_time}秒后重试: {str(e)[:100]}", file=sys.stderr)
                        time.sleep(wait_time)
            print(f"[ERROR] {func.__name__} 重试{max_retries}次后仍失败: {last_exception}", file=sys.stderr)
            raise last_exception
        return wrapper
    return decorator


@retry(max_retries=3, delay=3, backoff=2)
def fetch_with_retry(api_func, *args, **kwargs):
    """带重试的 API 调用"""
    return api_func(*args, **kwargs)


def get_indices():
    """主要指数行情"""
    result = []
    index_map = {
        "000001": "上证指数",
        "399001": "深证成指",
        "399006": "创业板指",
        "000688": "科创50",
        "899050": "北证50",
        "000300": "沪深300",
    }
    for code, name in index_map.items():
        try:
            symbol = f"sh{code}" if code.startswith("000") or code.startswith("899") else f"sz{code}"
            df = fetch_with_retry(ak.stock_zh_index_daily, symbol=symbol)
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                prev = df.iloc[-2] if len(df) > 1 else latest
                close = float(latest["close"])
                prev_close = float(prev["close"])
                pct = round((close - prev_close) / prev_close * 100, 2)
                change = round(close - prev_close, 2)
                result.append({
                    "code": code, "name": name,
                    "close": close, "pct": pct, "change": change,
                    "high": float(latest.get("high", close)),
                    "low": float(latest.get("low", close)),
                    "open": float(latest.get("open", close)),
                    "prev_close": prev_close,
                    "date": str(latest.name) if hasattr(latest, 'name') else str(latest.get("date", "")),
                })
        except Exception as e:
            result.append({"code": code, "name": name, "error": str(e)})
    return result


def get_market_breadth():
    """涨跌家数 + 涨停板"""
    result = {"up_count": 0, "down_count": 0, "flat_count": 0,
              "limit_up_count": 0, "limit_down_count": 0,
              "limit_up_list": [], "limit_down_list": []}
    try:
        # 涨停池
        df_zt = fetch_with_retry(ak.stock_zt_pool_em, date=datetime.now().strftime("%Y%m%d"))
        if df_zt is not None and not df_zt.empty:
            result["limit_up_count"] = len(df_zt)
            for _, row in df_zt.head(15).iterrows():
                result["limit_up_list"].append({
                    "code": str(row.get("代码", "")),
                    "name": str(row.get("名称", "")),
                    "pct": float(row.get("涨跌幅", 0)),
                    "reason": str(row.get("所属行业", "")),
                })
    except Exception as e:
        result["limit_up_error"] = str(e)

    try:
        # 跌停池
        df_dt = fetch_with_retry(ak.stock_zt_pool_dtgc_em, date=datetime.now().strftime("%Y%m%d"))
        if df_dt is not None and not df_dt.empty:
            result["limit_down_count"] = len(df_dt)
    except Exception as e:
        result["limit_down_error"] = str(e)

    try:
        # A股列表算涨跌家数 - 使用更多重试次数
        df = fetch_with_retry(ak.stock_zh_a_spot_em)
        if df is not None and not df.empty:
            result["up_count"] = int((df["涨跌幅"] > 0).sum())
            result["down_count"] = int((df["涨跌幅"] < 0).sum())
            result["flat_count"] = int((df["涨跌幅"] == 0).sum())
    except Exception as e:
        result["breadth_error"] = str(e)

    return result


def get_sectors():
    """申万一级行业涨跌 + 资金流向"""
    result = []
    try:
        df = fetch_with_retry(ak.stock_board_industry_name_em)
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                result.append({
                    "name": str(row.get("板块名称", "")),
                    "code": str(row.get("板块代码", "")),
                    "pct": float(row.get("涨跌幅", 0)),
                    "main_net": float(row.get("主力净流入-净额", 0)) if "主力净流入-净额" in df.columns else 0,
                    "main_pct": float(row.get("主力净流入-净占比", 0)) if "主力净流入-净占比" in df.columns else 0,
                })
    except Exception as e:
        return [{"error": str(e)}]
    return result


def get_concepts():
    """概念板块涨跌 TOP"""
    result = {"top": [], "bottom": []}
    try:
        df = fetch_with_retry(ak.stock_board_concept_name_em)
        if df is not None and not df.empty:
            sorted_df = df.sort_values("涨跌幅", ascending=False)
            for _, row in sorted_df.head(10).iterrows():
                result["top"].append({
                    "name": str(row.get("板块名称", "")),
                    "pct": float(row.get("涨跌幅", 0)),
                })
            for _, row in sorted_df.tail(10).iterrows():
                result["bottom"].append({
                    "name": str(row.get("板块名称", "")),
                    "pct": float(row.get("涨跌幅", 0)),
                })
    except Exception as e:
        result["error"] = str(e)
    return result


def get_north_bound():
    """北向资金"""
    result = {"latest": {}, "daily_records": []}
    try:
        # 使用 stock_hsgt_hist_em 获取北向资金历史数据
        df = fetch_with_retry(ak.stock_hsgt_hist_em, symbol="北向资金")
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            result["latest"] = {
                "date": str(latest.get("日期", "")),
                "net_amount": float(latest.get("北向资金-净流入", 0)) if "北向资金-净流入" in df.columns else 0,
            }
            for _, row in df.tail(5).iterrows():
                result["daily_records"].append({
                    "date": str(row.get("日期", "")),
                    "net_amount": float(row.get("北向资金-净流入", 0)) if "北向资金-净流入" in df.columns else 0,
                })
    except Exception as e:
        result["error"] = str(e)
    return result


def get_dragon_tiger(date_str):
    """龙虎榜"""
    result = []
    try:
        df = fetch_with_retry(ak.stock_lhb_detail_em, start_date=date_str, end_date=date_str)
        if df is not None and not df.empty:
            for _, row in df.head(20).iterrows():
                result.append({
                    "code": str(row.get("代码", "")),
                    "name": str(row.get("名称", "")),
                    "pct": float(row.get("涨跌幅", 0)),
                    "reason": str(row.get("上榜原因", "")),
                    "buy_amount": float(row.get("买入额", 0)) if "买入额" in df.columns else 0,
                    "sell_amount": float(row.get("卖出额", 0)) if "卖出额" in df.columns else 0,
                    "net_amount": float(row.get("净额", 0)) if "净额" in df.columns else 0,
                })
    except Exception as e:
        return [{"error": str(e)}]
    return result


def get_margin_trading():
    """融资融券余额"""
    result = {}
    try:
        # 使用 stock_margin_sse 获取上交所融资融券数据
        # 参数是 start_date 和 end_date
        today = datetime.now().strftime("%Y%m%d")
        df = fetch_with_retry(ak.stock_margin_sse, start_date=today, end_date=today)
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            result["total_balance"] = float(latest.get("融资融券余额", 0)) if "融资融券余额" in df.columns else 0
            result["fin_balance"] = float(latest.get("融资余额", 0)) if "融资余额" in df.columns else 0
            result["margin_balance"] = float(latest.get("融券余额", 0)) if "融券余额" in df.columns else 0
    except Exception as e:
        result["error"] = str(e)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    trade_date = args.date.replace("-", "")

    data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trade_date": args.date,
        "indices": get_indices(),
        "market_breadth": get_market_breadth(),
        "sectors": get_sectors(),
        "concepts": get_concepts(),
        "north_bound": get_north_bound(),
        "dragon_tiger": get_dragon_tiger(trade_date),
        "margin_trading": get_margin_trading(),
    }

    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
