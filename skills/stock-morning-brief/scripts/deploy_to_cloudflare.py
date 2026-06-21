#!/usr/bin/env python3
"""
部署HTML报告到Cloudflare Pages
用法: python3 deploy_to_cloudflare.py --html ./tmp/morning_brief_2026-06-15.html --project stock-morning-brief

核心功能：
1. 检查wrangler是否安装
2. 部署HTML到Cloudflare Pages
3. 返回公开访问URL
4. 支持历史版本（按日期保留）

依赖：
- Node.js (wrangler CLI)
- Cloudflare账号（需先登录或配置API Token）
"""

import os
import sys
import json
import re
import argparse
import subprocess
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

# Cloudflare Pages项目名（可配置）
DEFAULT_PROJECT_NAME = "stock-morning-brief"

# Cloudflare Pages域名模板
CF_PAGES_DOMAIN_TEMPLATE = "https://{project}.pages.dev"


def check_wrangler_installed():
    """检查wrangler是否已安装"""
    try:
        result = subprocess.run(
            ["npx", "wrangler", "--version"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            version = result.stdout.strip().split()[-1]
            print(f"[OK] wrangler 版本: {version}", file=sys.stderr)
            return True
    except subprocess.TimeoutExpired:
        print("[ERROR] wrangler 检查超时", file=sys.stderr)
    except FileNotFoundError:
        pass

    print("[ERROR] wrangler 未安装，请先安装：", file=sys.stderr)
    print("  npm install -g wrangler", file=sys.stderr)
    print("  或使用: npx wrangler", file=sys.stderr)
    return False


def check_wrangler_auth():
    """检查wrangler是否已登录"""
    try:
        result = subprocess.run(
            ["npx", "wrangler", "whoami"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print(f"[OK] {result.stdout.strip()}", file=sys.stderr)
            return True
        else:
            print("[WARN] wrangler 未登录", file=sys.stderr)
            print("请执行: npx wrangler login", file=sys.stderr)
            return False
    except Exception as e:
        print(f"[ERROR] 检查登录状态失败: {e}", file=sys.stderr)
        return False


def extract_date_from_filename(html_file):
    """从HTML文件名提取日期（如morning_brief_2026-06-15.html → 2026-06-15）"""
    basename = os.path.basename(html_file)
    # 匹配 YYYY-MM-DD 格式
    import re
    match = re.search(r'(\d{4}-\d{2}-\d{2})', basename)
    if match:
        return match.group(1)
    # 回退到当前日期
    return datetime.now().strftime("%Y-%m-%d")


def deploy_to_cloudflare(html_file, project_name, keep_history=True):
    """
    部署HTML文件到Cloudflare Pages

    默认部署策略：
    - 根路径 / 指向最新报告
    - 日期路径 /YYYY-MM-DD/ 指向指定日期报告
    - 使用本地持久发布目录累积历史报告，避免每次部署覆盖历史目录

    Args:
        html_file: HTML文件路径
        project_name: Cloudflare Pages项目名
        keep_history: 是否保留历史版本（按日期命名）

    Returns:
        dict: {
            "success": bool,
            "url": str,  # 最新报告URL（根路径）
            "dated_url": str,  # 指定日期报告URL
            "deployment_id": str,
            "message": str
        }
    """

    # 1. 检查HTML文件是否存在
    if not os.path.exists(html_file):
        return {
            "success": False,
            "url": "",
            "deployment_id": "",
            "message": f"HTML文件不存在: {html_file}"
        }

    # 2. 检查wrangler是否安装
    if not check_wrangler_installed():
        return {
            "success": False,
            "url": "",
            "deployment_id": "",
            "message": "wrangler未安装"
        }

    # 3. 检查登录状态（仅警告，不阻止部署）
    check_wrangler_auth()

    # 4. 提取日期（用于历史版本）
    date_str = extract_date_from_filename(html_file)

    # 5. 准备发布目录（Cloudflare Pages部署整个目录）
    # 需要持久目录来保留历史：每次部署都包含既有日期目录 + 最新根路径
    publish_dir = Path(__file__).resolve().parent.parent / "tmp" / "cloudflare_publish"
    publish_dir.mkdir(parents=True, exist_ok=True)
    tmpdir = str(publish_dir)
    print(f"[INFO] 发布目录: {tmpdir}", file=sys.stderr)

    # 复制HTML文件
    if keep_history:
        # 结构：publish_dir/index.html                    → 最新报告
        #      publish_dir/2026-06-15/index.html         → 指定日期报告
        date_dir = publish_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)
        dated_dest_file = date_dir / "index.html"
        latest_dest_file = publish_dir / "index.html"
        shutil.copy2(html_file, dated_dest_file)
        shutil.copy2(html_file, latest_dest_file)
        print(f"[OK] 已复制到日期路径: {html_file} → {dated_dest_file}", file=sys.stderr)
        print(f"[OK] 已复制到最新路径: {html_file} → {latest_dest_file}", file=sys.stderr)
    else:
        # 结构：publish_dir/index.html → 最新报告
        latest_dest_file = publish_dir / "index.html"
        shutil.copy2(html_file, latest_dest_file)
        print(f"[OK] 已复制: {html_file} → {latest_dest_file}", file=sys.stderr)

    # 6. 同步独立股票跟踪页面（如存在）
    # Primary path must match generate_report.py/stock_tracker.py default output.
    skill_dir = Path(__file__).resolve().parent.parent
    workspace_dir = skill_dir.parent.parent
    tracker_candidates = [
        skill_dir / "tmp" / "stock_tracker.html",
        workspace_dir / "tmp" / "stock_tracker.html",
    ]
    tracker_html = next((p for p in tracker_candidates if p.exists()), None)
    if tracker_html:
        tracker_dir = publish_dir / "stock-tracker"
        tracker_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tracker_html, tracker_dir / "index.html")
        print(f"[OK] 股票跟踪页已复制: {tracker_html} → {tracker_dir / 'index.html'}", file=sys.stderr)
    else:
        print(f"[WARN] 未找到股票跟踪页，已检查: {', '.join(str(p) for p in tracker_candidates)}", file=sys.stderr)

    # 7. 执行部署命令
    print(f"\n[INFO] 部署到 Cloudflare Pages: {project_name}", file=sys.stderr)
    print(f"[INFO] 部署目录: {tmpdir}", file=sys.stderr)

    try:
        result = subprocess.run(
            [
                "npx", "wrangler", "pages", "deploy", tmpdir,
                "--project-name", project_name,
                "--branch", "main",  # 部署到生产分支，确保 pages.dev 主域名可访问
                "--commit-dirty",  # 允许部署未提交的更改
            ],
            capture_output=True,
            text=True,
            timeout=300  # Cloudflare Pages deploy can exceed 2 minutes when history is included
        )

        # 7. 解析部署结果
        if result.returncode == 0:
            # 成功部署
            print(f"\n[SUCCESS] 部署成功！", file=sys.stderr)

            # Cloudflare Pages 会返回两类域名：
            # 1) 正式项目域名：https://<project>.pages.dev/              —— 推荐给用户使用
            # 2) 本次部署预览域名：https://<deployment-id>.<project>.pages.dev/ —— 仅用于回溯/预览
            output = result.stdout + result.stderr
            deployment_match = re.search(r'https://[a-f0-9-]+\.' + re.escape(project_name) + r'\.pages\.dev', output)
            deployment_domain = deployment_match.group(0) if deployment_match else ""

            production_domain = CF_PAGES_DOMAIN_TEMPLATE.format(project=project_name)
            latest_url = f"{production_domain}/"
            dated_url = f"{production_domain}/{date_str}/" if keep_history else latest_url
            tracker_exists = tracker_html is not None and tracker_html.exists()
            tracker_url = f"{production_domain}/stock-tracker/" if tracker_exists else ""
            deployment_url = f"{deployment_domain}/" if deployment_domain else ""
            deployment_dated_url = f"{deployment_domain}/{date_str}/" if deployment_domain and keep_history else deployment_url
            deployment_tracker_url = f"{deployment_domain}/stock-tracker/" if deployment_domain and tracker_exists else ""
            public_url = latest_url

            print(f"[URL] 最新报告: {latest_url}", file=sys.stderr)
            if keep_history:
                print(f"[URL] 指定日期: {dated_url}", file=sys.stderr)
            if tracker_url:
                print(f"[URL] 股票跟踪: {tracker_url}", file=sys.stderr)
            if deployment_url:
                print(f"[URL] 本次部署预览: {deployment_url}", file=sys.stderr)

            return {
                "success": True,
                "url": public_url,
                "latest_url": latest_url,
                "dated_url": dated_url,
                "tracker_url": tracker_url,
                "deployment_url": deployment_url,
                "deployment_dated_url": deployment_dated_url,
                "deployment_tracker_url": deployment_tracker_url,
                "deployment_id": date_str,
                "message": f"部署成功！最新报告: {latest_url}；指定日期: {dated_url}"
            }
        else:
            # 部署失败
            error_msg = result.stderr or result.stdout
            print(f"\n[ERROR] 部署失败:", file=sys.stderr)
            print(error_msg, file=sys.stderr)

            return {
                "success": False,
                "url": "",
                "latest_url": "",
                "dated_url": "",
                "deployment_id": "",
                "message": f"部署失败: {error_msg}"
            }

    except subprocess.TimeoutExpired:
        print(f"[ERROR] 部署超时（>300秒）", file=sys.stderr)
        return {
            "success": False,
            "url": "",
            "latest_url": "",
            "dated_url": "",
            "deployment_id": "",
            "message": "部署超时"
        }
    except Exception as e:
        print(f"[ERROR] 部署异常: {e}", file=sys.stderr)
        return {
            "success": False,
            "url": "",
            "latest_url": "",
            "dated_url": "",
            "deployment_id": "",
            "message": f"部署异常: {e}"
        }


def main():
    parser = argparse.ArgumentParser(
        description="部署HTML报告到Cloudflare Pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 部署早报（保留历史）
  python3 deploy_to_cloudflare.py --html ./tmp/morning_brief_2026-06-15.html

  # 自定义项目名
  python3 deploy_to_cloudflare.py --html report.html --project my-stock-report

  # 覆盖部署（不保留历史）
  python3 deploy_to_cloudflare.py --html report.html --no-history

首次使用：
  1. 安装Node.js
  2. 登录Cloudflare: npx wrangler login
  3. 在Cloudflare控制台创建Pages项目（或首次部署时自动创建）
        """
    )

    parser.add_argument(
        "--html",
        required=True,
        help="HTML文件路径"
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT_NAME,
        help=f"Cloudflare Pages项目名（默认: {DEFAULT_PROJECT_NAME}）"
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="不保留历史版本（每次覆盖部署）"
    )

    args = parser.parse_args()

    # 执行部署
    result = deploy_to_cloudflare(
        html_file=args.html,
        project_name=args.project,
        keep_history=not args.no_history
    )

    # 输出结果
    print("\n" + "="*60)
    if result["success"]:
        print(f"✅ {result['message']}")
        print(f"   最新报告: {result['latest_url']}")
        print(f"   指定日期: {result['dated_url']}")
        if result.get("tracker_url"):
            print(f"   股票跟踪: {result['tracker_url']}")
        print(json.dumps({
            "cloudflare_url": result["url"],
            "latest_url": result["latest_url"],
            "dated_url": result["dated_url"],
            "tracker_url": result.get("tracker_url", ""),
            "deployment_url": result.get("deployment_url", ""),
            "deployment_dated_url": result.get("deployment_dated_url", ""),
            "deployment_tracker_url": result.get("deployment_tracker_url", ""),
            "deployment_id": result["deployment_id"]
        }, ensure_ascii=False))
    else:
        print(f"❌ {result['message']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
