#!/usr/bin/env python3
"""
save_prediction_snapshot.py
从当日早报数据中提取预测快照，保存到 data/predictions/YYYY-MM-DD.json

数据源（按优先级自动探测）：
  1. tmp/llm_analysis.json（早报生成时的AI选股分析，结构最完整）
  2. tmp/ai_texts.json（早报AI文本，可回退提取板块/方向）
  3. tmp/market_data.json（市场行情数据）

在 generate_report.py 生成早报后调用本脚本，
或单独运行：python3 save_prediction_snapshot.py --date 2026-06-17
"""

import json
import os
import sys
import argparse
import re
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = os.path.join(SCRIPT_DIR, "..", "tmp")
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
PREDICTION_DIR = os.path.join(DATA_DIR, "predictions")


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_total(fund_scores, tech_scores):
    """根据映射法/技术面评分计算总分"""
    fund_total = sum(fund_scores.values()) if fund_scores else 0
    tech_total = sum(tech_scores.values()) if tech_scores else 0
    return fund_total, tech_total, fund_total + tech_total


def get_rating(total):
    """根据总分返回评级"""
    if total >= 85:
        return "强烈推荐"
    elif total >= 75:
        return "推荐"
    elif total >= 60:
        return "一般观察"
    else:
        return "不建议"


def extract_stocks_from_llm(llm):
    """从 llm_analysis.json 提取选股（首选数据源）"""
    stocks = []
    if not llm:
        return stocks

    for s in llm.get("STOCKS", []):
        fund_scores = s.get("fund_scores", {})
        tech_scores = s.get("tech_scores", {})
        fund_total, tech_total, total = compute_total(fund_scores, tech_scores)
        rating = get_rating(total)

        logic = s.get("logic", {})
        logic_text = logic.get("core", "") if isinstance(logic, dict) else str(logic)

        stocks.append({
            "name": s.get("name", ""),
            "code": s.get("code", ""),
            "market_tag": s.get("market_tag", ""),
            "market_class": s.get("market_class", ""),
            "fund_scores": fund_scores,
            "tech_scores": tech_scores,
            "fund_total": fund_total,
            "tech_total": tech_total,
            "total_score": total,
            "rating": rating,
            "logic": logic_text,
            "logic_detail": {
                "核心逻辑": logic.get("core", "") if isinstance(logic, dict) else "",
                "关键数据": logic.get("data", "") if isinstance(logic, dict) else "",
                "催化事件": logic.get("catalyst", "") if isinstance(logic, dict) else "",
                "风险提示": logic.get("risk", "") if isinstance(logic, dict) else "",
            },
        })
    return stocks


def extract_sectors_from_llm(llm):
    """从 llm_analysis.json 提取板块"""
    sectors = []
    if not llm:
        return sectors

    for s in llm.get("SECTORS", []):
        sectors.append({
            "name": s.get("name", ""),
            "direction": s.get("stars", ""),
            "reason": s.get("logic", ""),
        })
    return sectors


def extract_sectors_from_ai_texts(ai_texts):
    """从 ai_texts.json 的 SECTOR_DIRECTIONS 提取板块（回退）"""
    sectors = []
    if not ai_texts:
        return sectors

    sector_html = ai_texts.get("SECTOR_DIRECTIONS", "")
    if not sector_html:
        return sectors

    rows = re.findall(r"<tr>(.*?)</tr>", sector_html, re.DOTALL)
    for row in rows:
        cols = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cols) >= 2:
            name = re.sub(r"<[^>]+>", "", cols[0]).strip()
            if not name or name == "板块":
                continue
            direction = re.sub(r"<[^>]+>", "", cols[1]).strip() if len(cols) > 1 else ""
            reason = re.sub(r"<[^>]+>", "", cols[2]).strip() if len(cols) > 2 else ""
            sectors.append({
                "name": name,
                "direction": direction,
                "reason": reason,
            })
    return sectors


def extract_sh_range(ai_texts, llm):
    """从 ai_texts.json 提取上证区间"""
    if ai_texts:
        low = ai_texts.get("SH_RANGE_LOW", "")
        high = ai_texts.get("SH_RANGE_HIGH", "")
        if low and high:
            return str(low), str(high)

    # 从 llm 的 TODAY_PREDICTION 文本中解析
    if llm:
        text = llm.get("TODAY_PREDICTION", "")
        m = re.search(r"(\d{4})\s*[-~到至]\s*(\d{4})", text)
        if m:
            return m.group(1), m.group(2)
    return "", ""


def save_prediction_snapshot(date_str, tmp_dir=None):
    """保存预测快照（从tmp目录的真实早报数据提取）"""
    if tmp_dir is None:
        tmp_dir = TMP_DIR

    os.makedirs(PREDICTION_DIR, exist_ok=True)

    # 加载数据源
    llm = load_json(os.path.join(tmp_dir, "llm_analysis.json"))
    ai_texts = load_json(os.path.join(tmp_dir, "ai_texts.json"))
    market_data = load_json(os.path.join(tmp_dir, "market_data.json"))

    # 提取选股
    stocks = extract_stocks_from_llm(llm)
    if not stocks:
        # 回退：尝试 ai_texts 里的 STOCK_SELECTION（HTML）
        # 暂不解析，直接用 llm 里的数据
        print("⚠️ llm_analysis.json 无选股数据，检查 ai_texts.json")
    
    # 提取板块
    sectors = extract_sectors_from_llm(llm)
    if not sectors:
        sectors = extract_sectors_from_ai_texts(ai_texts)

    # 提取上证区间
    sh_low, sh_high = extract_sh_range(ai_texts, llm)

    # 组装快照
    snapshot = {
        "date": date_str,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_source": "llm_analysis.json" if llm else "ai_texts.json",
        "market_prediction": {
            "direction": ai_texts.get("DIRECTION_JUDGMENT", "") if ai_texts else "",
            "tone": ai_texts.get("MARKET_TONE", "") if ai_texts else llm.get("MARKET_TONE", "") if llm else "",
            "sh_range_low": sh_low,
            "sh_range_high": sh_high,
            "position_advice": ai_texts.get("POSITION_ADVICE", "") if ai_texts else llm.get("POSITION_ADVICE", "") if llm else "",
        },
        "sector_predictions": sectors,
        "stock_selections": stocks,
        "operation_strategy": ai_texts.get("OPERATION_STRATEGY", "") if ai_texts else "",
        "risk_warnings": ai_texts.get("RISK_WARNINGS", "") if ai_texts else "",
        "yesterday_review": ai_texts.get("YESTERDAY_REVIEW", "") if ai_texts else llm.get("YESTERDAY_REVIEW", "") if llm else "",
    }

    output_path = os.path.join(PREDICTION_DIR, f"{date_str}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"✅ 预测快照已保存: {output_path}")
    print(f"   选股: {len(stocks)} 只")
    print(f"   板块: {len(sectors)} 个")
    if stocks:
        for s in stocks:
            print(f"   - {s['name']}({s['code']}) {s['total_score']}分 {s['rating']}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="保存早报预测快照")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="日期 (YYYY-MM-DD)，默认今天")
    parser.add_argument("--tmp-dir", default=TMP_DIR,
                        help="tmp目录路径（包含 llm_analysis.json 等）")
    
    args = parser.parse_args()
    save_prediction_snapshot(args.date, args.tmp_dir)


if __name__ == "__main__":
    main()
