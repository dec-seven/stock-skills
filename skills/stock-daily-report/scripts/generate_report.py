#!/usr/bin/env python3
"""
报告生成：读取 JSON 数据 + AI 文本 → 填充 HTML 模板 → 生成 PDF
用法: python3 generate_report.py --data /tmp/market_data.json [--html out.html] --pdf out.pdf
"""
import os
import sys
import json
import argparse
import subprocess
import shutil
import re
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from utils import format_pct, format_amount, push_to_feishu

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "..", "references", "report_template.html")

# ───────────────────────────────────────────────
# 飞书推送配置
# ───────────────────────────────────────────────
FEISHU_USER_OPEN_ID = os.environ.get("FEISHU_USER_OPEN_ID", "")
LARK_CLI = "lark-cli"


# ───────────────────────────────────────────────
# JSON 安全加载
# ───────────────────────────────────────────────
def load_json_safe(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[WARN] JSON 解析失败 ({path}): {e}", file=sys.stderr)
        try:
            fixed = _fix_inline_quotes(raw)
            result = json.loads(fixed)
            print("[OK] 自动修复成功", file=sys.stderr)
            return result
        except json.JSONDecodeError as e2:
            print(f"[ERROR] 自动修复失败: {e2}", file=sys.stderr)
            raise


def _fix_inline_quotes(raw):
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
                result.append('「')
            elif in_string and ch == '\u201d':
                result.append('」')
            else:
                result.append(ch)
    fixed = ''.join(result)
    fixed = re.sub(r'([\u4e00-\u9fff])"([^"]*?)"([\u4e00-\u9fff])',
                   r'\1「\2」\3', fixed)
    return fixed


# ───────────────────────────────────────────────
# 指数简称映射
# ───────────────────────────────────────────────
INDEX_SHORT_NAMES = {
    "上证指数": "沪指",
    "深证成指": "深成指",
    "创业板指": "创业板",
    "北证50":   "北证50",
    "科创50":   "科创50",
    "沪深300":  "沪深300",
    "中证500":  "中证500",
}


# ───────────────────────────────────────────────
# 市场快照标签栏（放在 header 暗色区域）
# ────────────────────────────────────────────────
def build_snap_tags(indices, breadth, total_turnover=None):
    tags = []
    index_order = ["上证指数", "深证成指", "创业板指", "北证50", "科创50"]
    idx_map = {idx.get("name", ""): idx for idx in indices if "error" not in idx}

    for name in index_order:
        if name not in idx_map:
            continue
        idx = idx_map[name]
        pct = idx.get("pct", 0)
        close = idx.get("close", 0)
        cls = "index-up" if pct >= 0 else "index-down"
        arrow = "▲" if pct > 0 else ("▼" if pct < 0 else "—")
        label = INDEX_SHORT_NAMES.get(name, name)
        val_str = f"{close:.2f}"
        tags.append(
            f'<span class="snap-tag {cls}">'
            f'<span class="tag-label">{label}</span>'
            f'<span class="tag-value">{val_str}</span>'
            f'<span class="tag-pct">{arrow}{pct:+.2f}%</span>'
            f'</span>'
        )

    tags.append('<span class="snap-divider"></span>')

    if total_turnover is not None and total_turnover > 0:
        vol_str = format_amount(total_turnover)
        tags.append(
            f'<span class="snap-tag volume-tag">'
            f'<span class="tag-label">成交额</span>'
            f'<span class="tag-value">{vol_str}</span>'
            f'</span>'
        )
        tags.append('<span class="snap-divider"></span>')

    up = breadth.get("up_count", 0)
    down = breadth.get("down_count", 0)
    tags.append(f'<span class="snap-tag breadth-up"><span class="tag-label">涨</span>'
               f'<span class="tag-value">{up}</span></span>')
    tags.append(f'<span class="snap-tag breadth-down"><span class="tag-label">跌</span>'
               f'<span class="tag-value">{down}</span></span>')

    return "".join(tags)


# ───────────────────────────────────────────────
# 关键指标一览卡片
# 颜色规则：涨/涨停/流入 = 红(up)，跌/跌停/流出 = 绿(down)
# ───────────────────────────────────────────────
def build_key_indicators_cards(data):
    breadth = data.get("market_breadth", {})
    prev_turnover = data.get("prev_turnover")

    indicators = [
        # (label, value, mode, unit, force_cls)
        # force_cls: "up"/"down"/"flat"/None(按正负自动)
        # mode: 0=家数, 1=金额, 2=汇率, "turnover"=成交额(含昨日对比)
        ("成交额",    data.get("total_turnover"),    "turnover", "",   None),
        ("上涨家数",   breadth.get("up_count", 0),    0,          "家", "up"),
        ("下跌家数",   breadth.get("down_count", 0),    0,          "家", "down"),
        ("涨停(非ST)", breadth.get("limit_up_excl_st",
                          breadth.get("limit_up_count", 0)), 0, "家", "up"),
        ("跌停(非ST)", breadth.get("limit_down_excl_st",
                          breadth.get("limit_down_count", 0)), 0, "家", "down"),
        ("主力资金流向", data.get("main_net_flow"),    1,          "亿", None),
        ("北向成交额",  data.get("northbound_turnover"), 1,          "亿", "flat"),
        ("两融余额",   data.get("margin_balance"),    1,          "亿", "flat"),
        ("ETF净流向",   data.get("etf_net_flow"),     1,          "亿", None),
        ("人民币中间价", data.get("rmb_mid_rate"),    2,          "",   "flat"),
    ]

    html = ""
    for label, val, mode, unit, force_cls in indicators:
        if val is None:
            val_str = "—"
            cls = "flat"
            extra_html = ""
        else:
            # 确定颜色 class
            if force_cls in ("up", "down", "flat"):
                cls = force_cls
            elif mode == 1:
                # 流向类：正=红 负=绿
                cls = "up" if val >= 0 else "down"
            else:
                cls = "flat"

            # 格式化数值
            if mode == 0:       # 家数
                val_str = f"{val}"
                extra_html = ""
            elif mode == 1:   # 金额
                val_str = format_amount(val)
                extra_html = ""
            elif mode == 2:   # 汇率
                val_str = f"{val:.4f}"
                extra_html = ""
            elif mode == "turnover":
                val_str = format_amount(val)
                # 计算相对昨日变化
                if prev_turnover is not None and prev_turnover > 0:
                    diff = val - prev_turnover
                    if abs(diff) < 0.01:
                        extra_html = " <span style='font-size:0.75em;opacity:0.6'>(持平)</span>"
                    elif diff > 0:
                        # 放量 = 绿(down)
                        extra_html = (f" <span class='down' style='font-size:0.75em'>"
                                     f"(放量+{format_amount(diff)})</span>")
                    else:
                        # 缩量 = 红(up)
                        extra_html = (f" <span class='up' style='font-size:0.75em'>"
                                     f"(缩量{format_amount(abs(diff))})</span>")
                else:
                    extra_html = ""
            else:
                val_str = str(val)
                extra_html = ""

        # 单位 HTML（成交额不显示单位，因为已含在数值里）
        if mode == "turnover":
            unit_html = ""
        elif unit:
            unit_html = f"<div class='unit'>{unit}</div>"
        else:
            unit_html = ""

        html += (
            f"<div class='key-card'>"
            f"<div class='label'>{label}</div>"
            f"<div class='value {cls}'>{val_str}{extra_html}</div>"
            f"{unit_html}"
            f"</div>\n"
        )
    return html


# ───────────────────────────────────────────────
# 日内走势 OHLC 行
# ────────────────────────────────────────────────
def build_intraday_ohlc(indices):
    """取沪指（第一条）的 OHLC，生成一行展示"""
    if not indices or "error" in indices[0]:
        return '<div class="intraday-ohlc">（数据缺失）</div>'

    sh = indices[0]
    name = sh.get("name", "沪指")
    open_ = sh.get("open")
    high_ = sh.get("high")
    low_  = sh.get("low")
    close = sh.get("close", 0)
    amp   = sh.get("amplitude")

    def _fmt(v):
        return f"{v:.2f}" if v is not None else "—"

    amp_str = f"{amp:.2f}%" if amp is not None else "—"

    html = (
        f'<div class="intraday-ohlc">'
        f'<span class="ohlc-item"><span class="ohlc-label">开盘</span>'
        f'<span class="ohlc-val">{_fmt(open_)}</span></span>'
        f'<span class="ohlc-item"><span class="ohlc-label">最高</span>'
        f'<span class="ohlc-val up">{_fmt(high_)}</span></span>'
        f'<span class="ohlc-item"><span class="ohlc-label">最低</span>'
        f'<span class="ohlc-val down">{_fmt(low_)}</span></span>'
        f'<span class="ohlc-item"><span class="ohlc-label">收盘</span>'
        f'<span class="ohlc-val">{_fmt(close)}</span></span>'
        f'<span class="ohlc-item"><span class="ohlc-label">振幅</span>'
        f'<span class="ohlc-val">{amp_str}</span></span>'
        f'</div>'
    )
    return html


# ───────────────────────────────────────────────
# 行业涨跌 & 主力资金表格
# ────────────────────────────────────────────────
def build_sector_tables(sectors):
    valid = [s for s in sectors if "error" not in s]
    sorted_by_pct = sorted(valid, key=lambda x: x.get("pct", 0), reverse=True)
    top5    = sorted_by_pct[:5]
    bottom5 = sorted_by_pct[-5:] if len(sorted_by_pct) >= 5 else sorted_by_pct

    top_html = ""
    for s in top5:
        cls = "up" if s.get("pct", 0) >= 0 else "down"
        top_html += (f'<tr><td>{s.get("name","")}</td>'
                    f'<td class="num {cls}">{format_pct(s.get("pct"))}</td></tr>\n')

    bottom_html = ""
    for s in bottom5:
        cls = "up" if s.get("pct", 0) >= 0 else "down"
        bottom_html += (f'<tr><td>{s.get("name","")}</td>'
                      f'<td class="num {cls}">{format_pct(s.get("pct"))}</td></tr>\n')

    sorted_by_net = sorted(valid, key=lambda x: x.get("main_net", 0), reverse=True)
    inflow_html = ""
    for s in sorted_by_net[:8]:
        v = s.get("main_net", 0)
        cls = "up" if v >= 0 else "down"
        inflow_html += (f'<tr><td>{s.get("name","")}</td>'
                       f'<td class="num {cls}">{v:.2f}</td>'
                       f'<td class="num {cls}">{format_pct(s.get("pct"))}</td></tr>\n')
    outflow_html = ""
    for s in sorted_by_net[-6:]:
        v = s.get("main_net", 0)
        cls = "up" if v >= 0 else "down"
        outflow_html += (f'<tr><td>{s.get("name","")}</td>'
                        f'<td class="num {cls}">{v:.2f}</td>'
                        f'<td class="num {cls}">{format_pct(s.get("pct"))}</td></tr>\n')
    return top_html, bottom_html, inflow_html, outflow_html


# ───────────────────────────────────────────────
# 涨停板表格
# ────────────────────────────────────────────────
def build_limit_up_table(breadth):
    html = ""
    for item in breadth.get("limit_up_list", [])[:10]:
        cls = "up"
        html += (f'<tr><td>{item.get("name","")}</td>'
                  f'<td>{item.get("code","")}</td>'
                  f'<td class="num {cls}">{format_pct(item.get("pct"))}</td>'
                  f'<td>{item.get("reason","")}</td></tr>\n')
    return html


# ───────────────────────────────────────────────
# 填充模板
# ────────────────────────────────────────────────
def fill_template(template_html, data, ai_texts):
    indices  = data.get("indices", [])
    sectors  = data.get("sectors", [])
    breadth  = data.get("market_breadth", {})
    top_html, bottom_html, inflow_html, outflow_html = build_sector_tables(sectors)

    trade_date = data.get("trade_date", datetime.now().strftime("%Y-%m-%d"))
    dt = datetime.strptime(trade_date, "%Y-%m-%d")
    weekdays = ["周一","周二","周三","周四","周五","周六","周日"]
    weekday = weekdays[dt.weekday()]

    replacements = {
        "{{TRADE_DATE}}":           trade_date,
        "{{WEEKDAY}}":              weekday,
        "{{YEAR}}":                 str(dt.year),
        "{{GENERATED_AT}}":         data.get("generated_at", ""),
        "{{SNAP_TAGS}}":            build_snap_tags(indices, breadth, data.get("total_turnover")),
        "{{KEY_INDICATORS_CARDS}}": build_key_indicators_cards(data),
        "{{INTRADAY_OHLC}}":       build_intraday_ohlc(indices),
        "{{SECTOR_TOP_TABLE}}":     top_html,
        "{{SECTOR_BOTTOM_TABLE}}":  bottom_html,
        "{{MAIN_INFLOW_TABLE}}":    inflow_html,
        "{{MAIN_OUTFLOW_TABLE}}":   outflow_html,
        "{{LIMIT_UP_TABLE}}":       build_limit_up_table(breadth),
    }

    for key, val in ai_texts.items():
        replacements[f"{{{{{key}}}}}"] = val

    result = template_html
    for key, val in replacements.items():
        result = result.replace(key, str(val))
    return result


# ───────────────────────────────────────────────
# HTML → PDF
# ────────────────────────────────────────────────
def html_to_pdf(html_path, pdf_path):
    try:
        from weasyprint import HTML
        HTML(filename=html_path).write_pdf(pdf_path)
        return True
    except Exception:
        pass

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
        except Exception:
            pass

    print("[WARN] PDF 生成失败，仅保存 HTML", file=sys.stderr)
    return False


# ───────────────────────────────────────────────
# 主入口
# ────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data",     required=True,                     help="market_data.json 路径")
    parser.add_argument("--ai-texts", default=None,                      help="AI 生成文本 JSON 路径")
    parser.add_argument("--html",     default=None,                      help="输出 HTML 路径（可选）")
    parser.add_argument("--pdf",      default=None,                      help="输出 PDF 路径")
    parser.add_argument("--feishu-push", action="store_true", default=False, help="生成后自动推送到飞书")
    args = parser.parse_args()

    if not args.html and not args.pdf:
        print("[ERROR] 至少需要 --html 或 --pdf 之一", file=sys.stderr)
        sys.exit(1)

    data = load_json_safe(args.data)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    ai_texts = {}
    if args.ai_texts:
        ai_texts = load_json_safe(args.ai_texts)

    report_html = fill_template(template, data, ai_texts)

    html_path = args.html
    is_temp = False
    if not html_path and args.pdf:
        fd, html_path = tempfile.mkstemp(suffix=".html", prefix="market_report_")
        os.close(fd)
        is_temp = True

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(report_html)
    if not is_temp:
        print(f"[OK] HTML 已生成: {html_path}", file=sys.stderr)

    if args.pdf:
        ok = html_to_pdf(html_path, args.pdf)
        if ok:
            print(f"[OK] PDF 已生成: {args.pdf}", file=sys.stderr)
        else:
            print(f"[WARN] PDF 生成失败，HTML 在: {html_path}", file=sys.stderr)

    if args.feishu_push:
        push_to_feishu(html_path, data, ai_texts)

    if is_temp and args.pdf:
        try:
            os.unlink(html_path)
        except Exception:
            pass


if __name__ == "__main__":
    main()
