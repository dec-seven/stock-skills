#!/usr/bin/env python3
"""
主入口：拉数据 → 校验 → 输出 JSON
用法: python3 main.py [--date 2026-06-09] [--output /tmp/market_data.json]
"""
import subprocess
import sys
import os
import json
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FETCH_SCRIPT = os.path.join(SCRIPT_DIR, "fetch_market_data.py")

def run_fetch(trade_date: str) -> dict:
    """调用 fetch_market_data.py 获取数据"""
    cmd = [sys.executable, FETCH_SCRIPT, "--date", trade_date]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(f"[ERROR] fetch failed: {result.stderr}", file=sys.stderr)
            return {}
        return json.loads(result.stdout)
    except Exception as e:
        print(f"[ERROR] fetch exception: {e}", file=sys.stderr)
        return {}

def validate(data: dict) -> bool:
    """校验核心数据完整性"""
    issues = []
    if not data.get("indices"):
        issues.append("indices 为空")
    if not data.get("market_breadth", {}).get("up_count"):
        issues.append("涨跌家数为空")
    if not data.get("sectors"):
        issues.append("行业数据为空")

    if issues:
        print(f"[WARN] 数据校验问题: {', '.join(issues)}", file=sys.stderr)
        return False
    print("[OK] 数据校验通过", file=sys.stderr)
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="交易日期 YYYY-MM-DD")
    parser.add_argument("--output", default="/tmp/market_data.json", help="输出路径")
    args = parser.parse_args()

    if not args.date:
        from datetime import datetime
        args.date = datetime.now().strftime("%Y-%m-%d")

    # 阶段1: 拉取数据
    print(f"[1/3] 拉取 {args.date} 数据...", file=sys.stderr)
    data = run_fetch(args.date)

    # 阶段2: 校验
    print("[2/3] 校验数据...", file=sys.stderr)
    is_valid = validate(data)

    # 阶段3: 输出
    print(f"[3/3] 输出到 {args.output}", file=sys.stderr)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    if not is_valid:
        print("[WARN] 数据不完整，SKILL 将使用 WebSearch 回退补充", file=sys.stderr)
        sys.exit(2)  # 特殊退出码：部分数据缺失

    print("[DONE] 数据拉取完成", file=sys.stderr)

if __name__ == "__main__":
    main()
