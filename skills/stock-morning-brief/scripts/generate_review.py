#!/usr/bin/env python3
"""
generate_review.py
收盘复盘主脚本：对比早报预测 vs 实际收盘，生成复盘报告

用法：
  python3 generate_review.py --date 2026-06-17
  python3 generate_review.py --date 2026-06-17 --deploy-cloudflare --feishu-push
"""

import json
import os
import sys
import argparse
import subprocess
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
PREDICTION_DIR = os.path.join(DATA_DIR, "predictions")
CLOSING_DIR = os.path.join(DATA_DIR, "closing_data")
TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "..", "templates")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "tmp")


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_closing_data(date_str):
    """调用 fetch_closing_data.py 获取收盘数据"""
    script_path = os.path.join(SCRIPT_DIR, "fetch_closing_data.py")
    prediction_path = os.path.join(PREDICTION_DIR, f"{date_str}.json")
    
    cmd = [sys.executable, script_path, "--date", date_str]
    if os.path.exists(prediction_path):
        cmd.extend(["--prediction-json", prediction_path])
    
    print(f"📊 获取收盘数据...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"⚠️ 获取收盘数据失败: {result.stderr}")
        return None
    
    closing_path = os.path.join(CLOSING_DIR, f"{date_str}.json")
    return load_json(closing_path)


def compare_indices(prediction, closing):
    """对比指数预测 vs 实际"""
    results = []
    sh_range_low = prediction.get("market_prediction", {}).get("sh_range_low", "")
    sh_range_high = prediction.get("market_prediction", {}).get("sh_range_high", "")
    
    for idx in closing.get("indices", []):
        name = idx.get("name", "")
        actual_pct = idx.get("change_pct", 0)
        
        # 判断预测方向是否正确
        direction = prediction.get("market_prediction", {}).get("direction", "")
        predicted_up = "涨" in direction or "多" in direction
        actual_up = actual_pct > 0
        
        correct = predicted_up == actual_up
        
        result = {
            "name": name,
            "actual_close": idx.get("close", 0),
            "actual_change_pct": actual_pct,
            "predicted_direction": direction,
            "correct": correct,
            "sh_range": f"{sh_range_low}-{sh_range_high}" if name == "上证指数" else "",
        }
        results.append(result)
    
    return results


def compare_stocks(prediction_stocks, closing_stocks):
    """对比选股预测 vs 实际"""
    results = []
    for ps in prediction_stocks:
        code = ps.get("code", "")
        name = ps.get("name", "")
        
        # 查找实际数据
        actual = None
        for cs in closing_stocks:
            if cs.get("code") == code:
                actual = cs
                break
        
        if actual:
            result = {
                "name": name,
                "code": code,
                "predicted_score": ps.get("total_score", 0),
                "predicted_rating": ps.get("rating", ""),
                "actual_change_pct": actual.get("change_pct", 0),
                "actual_close": actual.get("close", 0),
                "correct": actual.get("change_pct", 0) > 0,  # 简化：涨就算对
            }
        else:
            result = {
                "name": name,
                "code": code,
                "predicted_score": ps.get("total_score", 0),
                "predicted_rating": ps.get("rating", ""),
                "actual_change_pct": None,
                "actual_close": None,
                "correct": None,
            }
        results.append(result)
    
    return results


def generate_review_html(date_str, prediction, closing_data, index_comparison, stock_comparison):
    """生成复盘报告HTML"""
    template_path = os.path.join(TEMPLATE_DIR, "review_template.html")
    if not os.path.exists(template_path):
        print(f"❌ 找不到模板: {template_path}")
        return None
    
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()
    
    # 替换日期
    template = template.replace("{{DATE}}", date_str)
    
    # 生成指数卡片
    index_cards_html = ""
    for idx in index_comparison:
        up = idx["actual_change_pct"] >= 0
        direction_class = "up" if up else "down"
        symbol = "+" if up else ""
        
        # 预测是否正确
        verdict = "✅ 预测正确" if idx["correct"] else "❌ 预测错误"
        verdict_class = "correct" if idx["correct"] else "wrong"
        
        sh_range_str = f"<div class='prediction'>📊 早报预测区间: {idx['sh_range']}</div>" if idx["sh_range"] else ""
        
        index_cards_html += f"""
        <div class="index-card">
          <div class="name">{idx['name']}</div>
          <div class="price {direction_class}">{idx['actual_close']:.2f}</div>
          <div class="change {direction_class}">{symbol}{idx['actual_change_pct']:.2f}%</div>
          {sh_range_str}
          <div class="prediction {verdict_class}">早报预测: {idx['predicted_direction']} → {verdict}</div>
        </div>
        """
    template = template.replace("{{MARKET_INDEX_CARDS}}", index_cards_html)
    
    # 生成预测vs实际表格
    pred_actual_html = """
    <table class="vs-table">
      <tr>
        <th>预测项</th><th>早报预测</th><th>实际结果</th><th>判断</th>
      </tr>
    """
    
    # 市场方向
    direction = prediction.get("market_prediction", {}).get("direction", "")
    # 从收盘数据判断实际方向
    sh_idx = next((i for i in index_comparison if i["name"] == "上证指数"), None)
    actual_dir = "上涨" if sh_idx and sh_idx["actual_change_pct"] > 0 else "下跌/震荡"
    dir_correct = ("涨" in direction and sh_idx and sh_idx["actual_change_pct"] > 0) or \
                 ("跌" in direction and sh_idx and sh_idx["actual_change_pct"] < 0) or \
                 ("震荡" in direction)
    dir_class = "correct" if dir_correct else "wrong"
    
    pred_actual_html += f"""
      <tr>
        <td>市场方向</td><td>{direction}</td><td>{actual_dir}</td><td class="{dir_class}">{"✅" if dir_correct else "❌"}</td>
      </tr>
    """
    
    # 上证区间
    sh_range = prediction.get("market_prediction", {}).get("sh_range_low", "") + "-" + \
               prediction.get("market_prediction", {}).get("sh_range_high", "")
    if sh_idx:
        sh_actual = f"{sh_idx['actual_close']:.2f}"
        sh_in_range = (sh_idx['actual_close'] >= float(prediction.get("market_prediction", {}).get("sh_range_low", 0) or 0) and
                       sh_idx['actual_close'] <= float(prediction.get("market_prediction", {}).get("sh_range_high", 0) or 99999))
        range_class = "correct" if sh_in_range else "partial"
        pred_actual_html += f"""
          <tr>
            <td>上证区间</td><td>{sh_range}</td><td>{sh_actual}</td><td class="{range_class}">{"✅ 在区间内" if sh_in_range else "⚠️ 超出区间"}</td>
          </tr>
        """
    
    pred_actual_html += "</table>"
    template = template.replace("{{PREDICTION_VS_ACTUAL}}", pred_actual_html)
    
    # 生成选股复盘
    stock_review_html = ""
    for sr in stock_comparison:
        up = sr["actual_change_pct"] is not None and sr["actual_change_pct"] >= 0
        direction_class = "up" if up else "down" if sr["actual_change_pct"] is not None else ""
        symbol = "+" if up else "" if sr["actual_change_pct"] is None else "-"
        
        if sr["correct"] is True:
            verdict_class = "correct"
            verdict_text = "✅ 上涨，预测正确"
        elif sr["correct"] is False:
            verdict_class = "wrong"
            verdict_text = "❌ 下跌，预测错误"
        else:
            verdict_class = ""
            verdict_text = "⚠️ 未获取到数据"
        
        actual_pct_str = f"{symbol}{sr['actual_change_pct']:.2f}%" if sr["actual_change_pct"] is not None else "N/A"
        
        stock_review_html += f"""
        <div class="stock-review-card">
          <div class="stock-header">
            <span class="stock-name">{sr['name']}</span>
            <span class="stock-code">{sr['code']}</span>
            <span class="prediction-score">预测得分: {sr['predicted_score']}分 ({sr['predicted_rating']})</span>
            <span class="actual-pct {direction_class}">{actual_pct_str}</span>
          </div>
          <div class="verdict {verdict_class}">{verdict_text}</div>
        </div>
        """
    
    if not stock_review_html:
        stock_review_html = "<p style='color:#8fa4c0;'>今日早报无选股推荐</p>"
    
    template = template.replace("{{STOCK_REVIEW}}", stock_review_html)
    
    # 生成对错总结（简化版，后续可由Agent增强）
    accuracy_html = f"""
    <div class="summary-box">
      <div class="summary-row">
        <span class="label">市场方向预测</span>
        <span class="value {dir_class}">{"正确 ✅" if dir_correct else "错误 ❌"}</span>
      </div>
      <div class="summary-row">
        <span class="label">上证区间预测</span>
        <span class="value {range_class}">{"正确 ✅" if sh_in_range else "部分正确 ⚠️"}</span>
      </div>
      <div class="summary-row">
        <span class="label">选股准确率</span>
        <span class="value">
          {sum(1 for s in stock_comparison if s['correct']) / max(len(stock_comparison), 1) * 100:.0f}% 
          ({sum(1 for s in stock_comparison if s['correct'])}/{len(stock_comparison)})
        </span>
      </div>
    </div>
    <p style="margin-top:12px;color:#8fa4c0;font-size:13px;">
      💡 详细对错分析将由Agent在生成复盘时补充到此处。
    </p>
    """
    template = template.replace("{{ACCURACY_SUMMARY}}", accuracy_html)
    
    # 方法论进化建议（简化版，后续可由Agent增强）
    evolution_html = """
    <div class="evolution-item">
      <span class="type reinforce">强化</span>
      <div class="content">复盘完成后，此处将显示需要强化的方法论规则。</div>
    </div>
    <div class="evolution-item">
      <span class="type adjust">调整</span>
      <div class="content">复盘完成后，此处将显示需要调整的方法论规则。</div>
    </div>
    <div class="evolution-item">
      <span class="type new">新增</span>
      <div class="content">复盘完成后，此处将显示需要新增的方法论规则。</div>
    </div>
    <p style="margin-top:12px;color:#8fa4c0;font-size:13px;">
      💡 方法论进化建议将由Agent在生成复盘时生成。
    </p>
    """
    template = template.replace("{{EVOLUTION_SUGGESTIONS}}", evolution_html)
    
    # 保存HTML
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"review_{date_str}.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(template)
    
    print(f"✅ 复盘报告已生成: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="生成A股收盘复盘报告")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="日期 (YYYY-MM-DD)，默认今天")
    parser.add_argument("--deploy-cloudflare", action="store_true",
                        help="生成后自动部署到Cloudflare Pages")
    parser.add_argument("--feishu-push", action="store_true",
                        help="生成后推送到飞书")
    args = parser.parse_args()
    
    date_str = args.date
    print(f"📊 生成 {date_str} 收盘复盘报告...")
    
    # 加载预测快照
    prediction = load_json(os.path.join(PREDICTION_DIR, f"{date_str}.json"))
    if not prediction:
        print(f"❌ 找不到预测快照: {PREDICTION_DIR}/{date_str}.json")
        print(f"   请先运行 save_prediction_snapshot.py 保存早报预测")
        sys.exit(1)
    
    # 获取收盘数据
    closing_data = fetch_closing_data(date_str)
    if not closing_data:
        print(f"⚠️ 无法获取收盘数据，将使用部分数据生成复盘")
        closing_data = {"indices": [], "stocks": [], "sectors": {"top_gainers": [], "top_losers": []}}
    
    # 对比分析
    index_comparison = compare_indices(prediction, closing_data)
    stock_comparison = compare_stocks(
        prediction.get("stock_selections", []),
        closing_data.get("stocks", [])
    )
    
    print(f"   指数对比: {len(index_comparison)} 项")
    print(f"   选股对比: {len(stock_comparison)} 只")
    
    # 生成HTML
    review_path = generate_review_html(date_str, prediction, closing_data, index_comparison, stock_comparison)
    
    # 部署到Cloudflare
    if args.deploy_cloudflare and review_path:
        print(f"📡 部署到Cloudflare Pages...")
        # TODO: 集成部署逻辑
        print(f"   (部署功能待集成)")
    
    # 推送到飞书
    if args.feishu_push:
        print(f"📤 推送到飞书...")
        # TODO: 集成推送逻辑
        print(f"   (推送功能待集成)")
    
    print(f"✅ 复盘报告生成完成!")
    return review_path


if __name__ == "__main__":
    main()
