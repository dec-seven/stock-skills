#!/usr/bin/env python3
"""
飞书投递：简约卡片 + PDF 附件
用法: python3 send_feishu.py --pdf /tmp/report.pdf --chat-id oc_xxxxx --data /tmp/market_data.json
"""
import subprocess
import sys
import os
import json
import argparse
import re


def run_lark_cli(args: list) -> tuple:
    """执行 lark-cli 命令"""
    cmd = ["lark-cli"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def upload_file(file_path: str) -> str:
    """上传文件到飞书，返回 file_key"""
    code, out, err = run_lark_cli(["drive", "upload", "--file", file_path])
    if code != 0:
        print(f"[ERROR] 上传失败: {err}", file=sys.stderr)
        return ""
    match = re.search(r'file_key["\s:]+([a-zA-Z0-9_]+)', out)
    if match:
        return match.group(1)
    return out if out and len(out) < 100 else ""


def send_card(chat_id: str, title: str, summary_lines: list, file_key: str):
    """发送简约卡片消息"""
    # 构建卡片内容
    elements = []

    # 核心指标区
    for line in summary_lines:
        elements.append({
            "tag": "div",
            "text": {"content": line, "tag": "lark_md"}
        })

    # 分割线
    elements.append({"tag": "hr"})

    # 底部提示
    elements.append({
        "tag": "note",
        "elements": [
            {"tag": "plain_text", "content": "📄 详细数据见附件 PDF · 仅供参考不构成投资建议"}
        ]
    })

    card = {
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": "blue"   # 蓝色标题栏，可选: blue/green/red/orange等
        },
        "elements": elements
    }

    code, out, err = run_lark_cli([
        "im", "send",
        "--chat-id", chat_id,
        "--msg-type", "interactive",
        "--content", json.dumps(card, ensure_ascii=False),
    ])
    if code != 0:
        print(f"[ERROR] 卡片发送失败: {err}", file=sys.stderr)
        return False
    print(f"[OK] 卡片已发送", file=sys.stderr)
    return True


def send_file(chat_id: str, file_key: str):
    """发送 PDF 文件附件"""
    code, out, err = run_lark_cli([
        "im", "send",
        "--chat-id", chat_id,
        "--msg-type", "file",
        "--content", json.dumps({"file_key": file_key}),
    ])
    if code != 0:
        print(f"[ERROR] 文件发送失败: {err}", file=sys.stderr)
        return False
    print(f"[OK] PDF 附件已发送", file=sys.stderr)
    return True


def build_summary_lines(data: dict, ai_summary: str = "") -> list:
    """从数据中提取核心指标，构建卡片展示行"""
    lines = []

    # 指数一行
    indices = data.get("indices", [])
    index_parts = []
    for idx in indices:
        if "error" in idx:
            continue
        name = idx.get("name", "")
        pct = idx.get("pct", 0)
        close = idx.get("close", 0)
        arrow = "🔴" if pct >= 0 else "🟢"
        sign = "+" if pct >= 0 else ""
        index_parts.append(f"{arrow} **{name}** {close:.2f}（{sign}{pct:.2f}%）")
    if index_parts:
        lines.append("\n".join(index_parts))

    # 涨跌家数
    breadth = data.get("market_breadth", {})
    up = breadth.get("up_count", 0)
    down = breadth.get("down_count", 0)
    zt = breadth.get("limit_up_count", 0)
    if up or down:
        lines.append(f"📈 上涨 **{up}** / 📉 下跌 **{down}** / 涨停 **{zt}**")

    # 成交额（从指数里取沪深之和，或单独算）
    # 北向资金
    nb = data.get("north_bound", {})
    latest = nb.get("latest", {})
    net = latest.get("net_amount", 0)
    if net:
        sign = "+" if net >= 0 else ""
        lines.append(f"💰 北向资金净流入 **{sign}{net:.2f}亿**")

    # 行业涨跌 TOP3
    sectors = data.get("sectors", [])
    valid_sectors = [s for s in sectors if "error" not in s]
    if valid_sectors:
        sorted_up = sorted(valid_sectors, key=lambda x: x.get("pct", 0), reverse=True)
        sorted_down = sorted(valid_sectors, key=lambda x: x.get("pct", 0))
        top3 = "、".join([f"**{s['name']}**+{s['pct']:.2f}%" for s in sorted_up[:3]])
        bot3 = "、".join([f"**{s['name']}**{s['pct']:.2f}%" for s in sorted_down[:3]])
        lines.append(f"🔺 领涨: {top3}")
        lines.append(f"🔻 领跌: {bot3}")

    # AI 摘要（如果有）
    if ai_summary:
        # 截取前200字
        short = ai_summary[:200] + ("..." if len(ai_summary) > 200 else "")
        lines.append(f"\n{short}")

    return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True, help="PDF 文件路径")
    parser.add_argument("--chat-id", required=True, help="飞书群 chat_id")
    parser.add_argument("--data", default=None, help="market_data.json 路径（用于生成卡片）")
    parser.add_argument("--ai-texts", default=None, help="ai_texts.json 路径（用于卡片摘要）")
    parser.add_argument("--title", default="", help="卡片标题，留空自动生成")
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        print(f"[ERROR] 文件不存在: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    # 加载数据
    data = {}
    if args.data and os.path.exists(args.data):
        with open(args.data, "r", encoding="utf-8") as f:
            data = json.load(f)

    ai_summary = ""
    if args.ai_texts and os.path.exists(args.ai_texts):
        with open(args.ai_texts, "r", encoding="utf-8") as f:
            ai_texts = json.load(f)
            ai_summary = ai_texts.get("SUMMARY", "")

    # 标题
    trade_date = data.get("trade_date", "")
    title = args.title or f"📊 A股收盘日报 · {trade_date}"

    # 1. 构建并发送简约卡片
    summary_lines = build_summary_lines(data, ai_summary)
    print("[1/2] 发送卡片...", file=sys.stderr)
    send_card(args.chat_id, title, summary_lines, "")

    # 2. 上传并发送 PDF 附件
    print("[2/2] 上传并发送 PDF...", file=sys.stderr)
    file_key = upload_file(args.pdf)
    if file_key:
        send_file(args.chat_id, file_key)

    print("[DONE] 投递完成", file=sys.stderr)


if __name__ == "__main__":
    main()
