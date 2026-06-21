#!/usr/bin/env python3
"""
fetch_closing_data.py
获取当日收盘数据，保存到 skills/stock-morning-brief/data/closing_data/YYYY-MM-DD.json

运行：python3 fetch_closing_data.py --date 2026-06-17

数据源：AKShare 日K线接口（在代理环境更稳定）+ 涨跌停池
"""

import json
import os
import sys
import argparse
import subprocess
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

# 禁用代理
for proxy_key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
    os.environ.pop(proxy_key, None)
os.environ["NO_PROXY"] = "*"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_DIR = os.path.join(DATA_DIR, "closing_data")


def init_akshare():
    try:
        import akshare as ak
        return ak
    except ImportError:
        print("❌ akshare 未安装，正在安装...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-q", "akshare",
            "-i", "https://mirrors.tencent.com/pypi/simple/"
        ])
        import akshare as ak
        return ak


def fetch_index_closing(ak, date_str):
    """获取指数收盘数据 - 使用日K线接口（更稳定）"""
    results = []
    target_indices = [
        ("sh000001", "上证指数", "000001", "sh"),
        ("sz399001", "深证成指", "399001", "sz"),
        ("sz399006", "创业板指", "399006", "sz"),
        ("sh000300", "沪深300", "000300", "sh"),
    ]
    
    for symbol, name, code, market in target_indices:
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            if df is not None and not df.empty:
                # 取指定日期的数据
                row_match = df[df["date"] == date_str]
                if not row_match.empty:
                    row = row_match.iloc[0]
                else:
                    # 取最近的一行
                    row = df.iloc[-1]
                
                # 计算涨跌幅
                idx = df.index[df["date"] == row["date"]][0]
                if idx > 0:
                    prev_close = df.iloc[idx-1]["close"]
                    change_pct = (row["close"] - prev_close) / prev_close * 100
                else:
                    change_pct = 0
                
                results.append({
                    "name": name,
                    "code": code,
                    "market": market,
                    "close": float(row["close"]),
                    "change_pct": round(change_pct, 2),
                    "change": round(float(row["close"] - prev_close), 2) if idx > 0 else 0,
                    "volume": float(row.get("volume", 0)),
                })
        except Exception as e:
            print(f"  ⚠️ {name} 获取失败: {e}")
    return results


def fetch_sector_top(ak):
    """获取板块涨跌排行 - 尝试多接口，回退到历史数据"""
    # 尝试1: stock_board_industry_spot_em
    try:
        df = ak.stock_board_industry_spot_em()
        if df is not None and not df.empty:
            df_sorted = df.sort_values(by="涨跌幅", ascending=False)
            top_gainers = []
            top_losers = []
            for _, row in df_sorted.iterrows():
                item = {
                    "name": row.get("板块名称", ""),
                    "change_pct": float(row.get("涨跌幅", 0)),
                }
                if item["change_pct"] > 0 and len(top_gainers) < 10:
                    top_gainers.append(item)
                elif item["change_pct"] < 0:
                    top_losers.append(item)
            top_losers = sorted(top_losers, key=lambda x: x["change_pct"])[:10]
            return {"top_gainers": top_gainers, "top_losers": top_losers}
    except Exception as e:
        print(f"  ⚠️ 板块实时接口失败: {e}")
    
    # 尝试2: stock_board_industry_summary_ths
    try:
        df = ak.stock_board_industry_summary_ths()
        if df is not None and not df.empty:
            df_sorted = df.sort_values(by="涨跌幅", ascending=False)
            top_gainers = []
            top_losers = []
            for _, row in df_sorted.iterrows():
                item = {
                    "name": row.get("板块", ""),
                    "change_pct": float(row.get("涨跌幅", 0)),
                }
                if item["change_pct"] > 0 and len(top_gainers) < 10:
                    top_gainers.append(item)
                elif item["change_pct"] < 0:
                    top_losers.append(item)
            top_losers = sorted(top_losers, key=lambda x: x["change_pct"])[:10]
            return {"top_gainers": top_gainers, "top_losers": top_losers}
    except Exception as e:
        print(f"  ⚠️ 板块备用接口失败: {e}")
    
    return {"top_gainers": [], "top_losers": []}


def code_to_symbol(code):
    """股票代码转 akshare symbol（带市场前缀）"""
    code = str(code).strip()
    if code.startswith("6"):
        return f"sh{code}"
    elif code.startswith(("0", "3", "2")):
        return f"sz{code}"
    elif code.startswith(("4", "8")):
        return f"bj{code}"
    return code


def fetch_stock_closing(ak, stock_codes, date_str):
    """获取个股收盘数据 - 使用 stock_zh_a_daily 接口（更稳定）"""
    results = []
    # 计算日期范围
    from datetime import datetime, timedelta
    end_dt = datetime.strptime(date_str, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=10)  # 拉10天数据，确保能算涨跌幅
    start_str = start_dt.strftime("%Y%m%d")
    end_str = end_dt.strftime("%Y%m%d")
    
    for code in stock_codes:
        symbol = code_to_symbol(code)
        try:
            df = ak.stock_zh_a_daily(
                symbol=symbol,
                start_date=start_str,
                end_date=end_str,
                adjust="qfq"
            )
            if df is not None and not df.empty:
                df["date"] = df["date"].astype(str)
                # 找指定日期
                row_match = df[df["date"] == date_str]
                if not row_match.empty:
                    row = row_match.iloc[0]
                else:
                    row = df.iloc[-1]
                
                # 计算涨跌幅
                idx = df.index[df["date"] == row["date"]][0]
                if idx > 0:
                    prev_close = float(df.iloc[idx-1]["close"])
                    change_pct = (float(row["close"]) - prev_close) / prev_close * 100
                    change = float(row["close"]) - prev_close
                else:
                    change_pct = 0
                    change = 0
                
                results.append({
                    "code": code,
                    "name": code,  # 名字需要从其他途径获取
                    "close": float(row["close"]),
                    "change_pct": round(change_pct, 2),
                    "change": round(change, 2),
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "volume": float(row.get("volume", 0)),
                    "amount": float(row.get("amount", 0)),
                    "turnover": float(row.get("turnover", 0)) * 100 if row.get("turnover") else 0,
                })
            else:
                print(f"  ⚠️ {code} 无数据")
        except Exception as e:
            print(f"  ⚠️ {code} 获取失败: {e}")
    return results


def fetch_limit_stats(ak, date_str):
    """获取涨跌停统计"""
    limit_up = 0
    limit_down = 0
    
    try:
        date_nostr = date_str.replace("-", "")
        df_up = ak.stock_zt_pool_em(date=date_nostr)
        if df_up is not None:
            limit_up = len(df_up)
    except Exception:
        pass
    
    try:
        date_nostr = date_str.replace("-", "")
        df_down = ak.stock_dt_pool_em(date=date_nostr)
        if df_down is not None:
            limit_down = len(df_down)
    except Exception:
        pass
    
    return {"limit_up": limit_up, "limit_down": limit_down}


def main():
    parser = argparse.ArgumentParser(description="获取A股收盘数据")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="日期 (YYYY-MM-DD)，默认今天")
    parser.add_argument("--stocks", nargs="*", default=[],
                        help="需要查询的个股代码列表")
    parser.add_argument("--prediction-json", default=None,
                        help="预测快照JSON路径，自动提取个股代码")
    args = parser.parse_args()

    ak = init_akshare()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    date_str = args.date

    # 加载预测快照中的个股代码
    stock_codes = list(args.stocks)
    stock_name_map = {}  # code -> name
    if args.prediction_json and os.path.exists(args.prediction_json):
        with open(args.prediction_json, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
            for s in snapshot.get("stock_selections", []):
                code = str(s.get("code", ""))
                name = s.get("name", "")
                if code and code not in stock_codes:
                    stock_codes.append(code)
                if code:
                    stock_name_map[code] = name
        print(f"📋 从预测快照加载 {len(snapshot.get('stock_selections', []))} 只个股")

    print(f"📊 获取 {date_str} 收盘数据...")

    # 获取指数数据（日K线）
    indices = fetch_index_closing(ak, date_str)
    print(f"  指数: {len(indices)} 条")

    # 获取板块数据
    sectors = fetch_sector_top(ak)
    print(f"  板块: 涨{len(sectors['top_gainers'])} 跌{len(sectors['top_losers'])}")

    # 获取个股数据
    if stock_codes:
        stocks = fetch_stock_closing(ak, stock_codes, date_str)
        # 补上股票名字
        for s in stocks:
            if s.get("name") == s.get("code") or not s.get("name"):
                s["name"] = stock_name_map.get(s["code"], s["code"])
        print(f"  个股: {len(stocks)}/{len(stock_codes)} 只")
    else:
        stocks = []
        print("  个股: 无")

    # 获取涨跌停统计
    limit_stats = fetch_limit_stats(ak, date_str)
    print(f"  涨跌停: 涨停{limit_stats['limit_up']} 跌停{limit_stats['limit_down']}")

    # 组装输出
    closing_data = {
        "date": date_str,
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "indices": indices,
        "sectors": sectors,
        "stocks": stocks,
        "limit_stats": limit_stats,
    }

    output_path = os.path.join(OUTPUT_DIR, f"{date_str}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(closing_data, f, ensure_ascii=False, indent=2)

    print(f"✅ 收盘数据已保存: {output_path}")
    return output_path


if __name__ == "__main__":
    main()
