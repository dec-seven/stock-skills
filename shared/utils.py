#!/usr/bin/env python3
"""
共享工具函数 - 供所有 Skill 使用

用法:
    from shared.utils import safe_float, format_pct, format_amount, html_to_pdf, push_to_feishu
"""
import os
import sys
import shutil
import subprocess
import tempfile
import json
import re
from datetime import datetime


# ==================== 数据处理工具 ====================

def safe_float(val, default=0.0):
    """安全转换为浮点数"""
    try:
        if val is None or val == '' or val == '-':
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def validate_number(val, field_name=""):
    """校验数字是否有效（非零、非空）"""
    if val is None or val == 0 or val == 0.0:
        return False
    return True


def format_pct(val):
    """格式化涨跌幅（中国股市：红涨绿跌）"""
    if val is None:
        return "—"
    if val > 0:
        return f"+{val:.2f}%"
    if val < 0:
        return f"{val:.2f}%"
    return "0.00%"


def format_amount(val):
    """格式化金额（亿）"""
    if val is None:
        return "—"
    if abs(val) >= 10000:
        return f"{val/10000:.2f}万亿"
    return f"{val:.2f}亿"


def pct_class(pct):
    """涨跌样式类（中国股市：红涨绿跌）"""
    if pct is None:
        return ""
    return "up" if pct >= 0 else "down"


# ==================== JSON 工具 ====================

import json
import re


def load_json_safe(path):
    """安全加载 JSON，自动修复内联引号问题"""
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
    """修复 JSON 中的内联引号"""
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
                result.append('\u300c')
            elif in_string and ch == '\u201d':
                result.append('\u300d')
            else:
                result.append(ch)
    fixed = ''.join(result)
    fixed = re.sub(r'([\u4e00-\u9fff])"([^"]*?)"([\u4e00-\u9fff])',
                   r'\1\u300c\2\u300d\3', fixed)
    return fixed


# ==================== 文件工具 ====================

def html_to_pdf(html_path, pdf_path):
    """HTML 转 PDF（WeasyPrint 优先，Chrome headless 备选）"""
    # 尝试 WeasyPrint
    try:
        from weasyprint import HTML
        HTML(filename=html_path).write_pdf(pdf_path)
        return True
    except Exception:
        pass

    # 回退到 Chrome headless
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


# ==================== 飞书推送工具 ====================

LARK_CLI = "lark-cli"


def get_feishu_user_id():
    """获取飞书用户 Open ID"""
    return os.environ.get("FEISHU_USER_OPEN_ID", "")


def push_to_feishu(html_path, data, ai_texts=None, cloudflare_url=None, user_id=None):
    """推送早报/日报摘要到飞书，包含 Cloudflare 链接，不发送 HTML 文件

    Args:
        html_path: HTML 文件路径（不再发送，仅用于日志）
        data: market_data.json 字典
        ai_texts: ai_texts.json 字典（可选）
        cloudflare_url: Cloudflare 部署链接（可选）
        user_id: 用户 Open ID（可选）
    """
    if user_id is None:
        user_id = get_feishu_user_id()

    if not user_id:
        print("[WARN] 未配置 FEISHU_USER_OPEN_ID，跳过飞书推送", file=sys.stderr)
        return False

    # ── 从 data 提取关键信息 ──
    title = "A股盘前早报"
    today_str = datetime.now().strftime("%Y-%m-%d")
    indices = data.get("yesterday", {}).get("indices", [])
    turnover = data.get("yesterday", {}).get("turnover", {}).get("total", 0)
    breadth = data.get("yesterday", {}).get("market_breadth", {})
    up_count = breadth.get("up_count", 0)
    down_count = breadth.get("down_count", 0)
    limit_up = breadth.get("limit_up", 0)
    limit_down = breadth.get("limit_down", 0)

    # 指数涨跌
    index_lines = []
    for idx in indices[:4]:
        name = idx.get("name", "")
        close = idx.get("close", "")
        pct = idx.get("pct", 0)
        emoji = "📈" if pct >= 0 else "📉"
        index_lines.append(f"{emoji} {name} {close} ({pct:+.2f}%)")

    # ── 从 ai_texts 提取策略 ──
    direction = ""
    position = ""
    stocks = []
    if ai_texts:
        title = "A股盘前早报"
        direction = ai_texts.get("DIRECTION_JUDGMENT", "")
        sh_low = ai_texts.get("SH_RANGE_LOW", "")
        sh_high = ai_texts.get("SH_RANGE_HIGH", "")
        position = ai_texts.get("POSITION_ADVICE", "")
        # 提取选股
        stock_html = ai_texts.get("STOCK_SELECTION", "")
        if stock_html:
            stocks = re.findall(r'<span class="stock-name">([^<]+)</span>', stock_html)

    # ── 构建 Markdown 摘要 ──
    lines = [f"**{today_str} {title}**", ""]

    if index_lines:
        lines.append("**📊 市场概况**")
        lines.extend(index_lines)
        lines.append(f"成交额: {turnover:.0f}亿 | 涨{up_count} 跌{down_count} | 涨停{limit_up} 跌停{limit_down}")
        lines.append("")

    if direction:
        lines.append(f"**🎯 方向判断: {direction}**")
        if sh_low and sh_high:
            lines.append(f"区间: {sh_low} - {sh_high}")
        if position:
            lines.append(f"仓位: {position}")
        lines.append("")

    if stocks:
        lines.append(f"**⭐ 选股: {', '.join(stocks[:5])}**")
        lines.append("")

    if cloudflare_url:
        lines.append(f"**[📄 查看完整报告]({cloudflare_url})**")
        lines.append(f"[📈 股票跟踪]({cloudflare_url.rstrip('/')}/stock-tracker/)")
    else:
        lines.append("⚠️ 报告暂未部署到线上")

    markdown = "\n".join(lines)

    # ── 发送摘要 ──
    try:
        subprocess.run(
            [LARK_CLI, "im", "+messages-send",
             "--user-id", user_id,
             "--markdown", markdown, "--as", "bot"],
            check=True, timeout=30, capture_output=True,
        )
        print("[feishu] 摘要已推送", file=sys.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[feishu] 推送失败: {e.stderr.decode()[:200]}", file=sys.stderr)
        return False


# ==================== 重试工具 ====================

import time


def retry(func, max_retries=2, delay=1.0, description=""):
    """带重试的函数调用"""
    for attempt in range(max_retries):
        try:
            result = func()
            return result
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"[WARN] {description} 第{attempt+1}次失败: {str(e)[:60]}，{delay}s后重试", file=sys.stderr)
                time.sleep(delay)
            else:
                print(f"[ERROR] {description} 重试{max_retries}次均失败: {str(e)[:80]}", file=sys.stderr)
    return None
