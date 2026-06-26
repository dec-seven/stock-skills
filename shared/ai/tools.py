"""
Tool 封装：把现有脚本包装为 Agent 可调用的工具。

设计原则：
- 不破坏现有脚本，通过 subprocess 调用
- 每个 Tool 单一职责，输入/输出明确
- 失败返回 ToolResult(success=False)，不抛异常
- 旧路径保留，Agent 架构与旧脚本可并行运行

封装的脚本：
- fetch_data.py → FetchDataTool
- generate_ai_texts.py prepare → PreparePromptTool
- generate_ai_texts.py compile → CompileTool
- generate_report.py → RenderReportTool
- deploy_to_cloudflare.py → DeployCloudflareTool
- 飞书推送（generate_report.py --feishu-push 内置）→ PushFeishuTool
"""

import os
import sys
import json
import time
from .llm_client import LLMClient
from agents.base import Tool, ToolResult

# Python 解释器路径（项目约定）
PYTHON = sys.executable

# 脚本路径
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SKILL_DIR = os.path.join(PROJECT_ROOT, "skills", "stock-morning-brief")
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")

FETCH_DATA_SCRIPT = os.path.join(SCRIPTS_DIR, "fetch_data.py")
AI_TEXTS_SCRIPT = os.path.join(SCRIPTS_DIR, "generate_ai_texts.py")
REPORT_SCRIPT = os.path.join(SCRIPTS_DIR, "generate_report.py")
DEPLOY_SCRIPT = os.path.join(SCRIPTS_DIR, "deploy_to_cloudflare.py")


class FetchDataTool(Tool):
    """数据获取工具：调用 fetch_data.py 拉取全量市场数据。

    输入：output_path（输出 JSON 路径）
    输出：market_data.json 写入指定路径
    """
    name = "fetch_data"

    def execute(self, output_path: str, extra_args: list = None) -> ToolResult:
        cmd = [PYTHON, FETCH_DATA_SCRIPT, "--output", output_path]
        if extra_args:
            cmd.extend(extra_args)
        result = self._run_script(cmd, timeout=300)
        if result.success and os.path.exists(output_path):
            result.data = {"output_path": output_path, "size": os.path.getsize(output_path)}
        return result


class PreparePromptTool(Tool):
    """Prompt 准备工具：调用 generate_ai_texts.py prepare。

    输入：data_path（market_data.json）、output_dir
    输出：analysis_prompt.md + rule_fields.json 写入 output_dir
    """
    name = "prepare_prompt"

    def execute(self, data_path: str, output_dir: str) -> ToolResult:
        cmd = [PYTHON, AI_TEXTS_SCRIPT, "prepare", "--data", data_path, "--output-dir", output_dir]
        result = self._run_script(cmd, timeout=60)
        prompt_path = os.path.join(output_dir, "analysis_prompt.md")
        if result.success and os.path.exists(prompt_path):
            result.data = {
                "prompt_path": prompt_path,
                "rule_fields_path": os.path.join(output_dir, "rule_fields.json"),
            }
        return result


class CompileTool(Tool):
    """编译工具：调用 generate_ai_texts.py compile。

    输入：data_path、analysis_path（llm_analysis.json）、output_path（ai_texts.json）
    输出：ai_texts.json 写入指定路径
    """
    name = "compile_ai_texts"

    def execute(self, data_path: str, analysis_path: str, output_path: str) -> ToolResult:
        cmd = [
            PYTHON, AI_TEXTS_SCRIPT, "compile",
            "--data", data_path,
            "--analysis", analysis_path,
            "--output", output_path,
        ]
        result = self._run_script(cmd, timeout=60)
        if result.success and os.path.exists(output_path):
            result.data = {"output_path": output_path, "size": os.path.getsize(output_path)}
        return result


class RenderReportTool(Tool):
    """报告渲染工具：调用 generate_report.py 生成 HTML。

    输入：data_path、ai_texts_path、html_path
    输出：HTML 文件写入指定路径
    """
    name = "render_report"

    def execute(self, data_path: str, ai_texts_path: str, html_path: str,
                analysis_json: str = None, no_stock_tracker: bool = False) -> ToolResult:
        cmd = [
            PYTHON, REPORT_SCRIPT,
            "--data", data_path,
            "--ai-texts", ai_texts_path,
            "--html", html_path,
        ]
        if analysis_json:
            cmd.extend(["--analysis-json", analysis_json])
        if no_stock_tracker:
            cmd.append("--no-stock-tracker")
        result = self._run_script(cmd, timeout=180)
        if result.success and os.path.exists(html_path):
            result.data = {"html_path": html_path, "size": os.path.getsize(html_path)}
        return result


class DeployCloudflareTool(Tool):
    """Cloudflare 部署工具：调用 deploy_to_cloudflare.py。

    输入：html_path
    输出：cloudflare_url, latest_url, dated_url
    """
    name = "deploy_cloudflare"

    def execute(self, html_path: str, project: str = "stock-morning-brief") -> ToolResult:
        cmd = [PYTHON, DEPLOY_SCRIPT, "--html", html_path, "--project", project]
        result = self._run_script(cmd, timeout=300)
        if result.success:
            # 部署脚本输出 JSON，尝试解析
            try:
                # stdout 可能包含日志 + JSON，取最后一行 JSON
                lines = [l for l in result.data.strip().split("\n") if l.strip().startswith("{")]
                if lines:
                    deploy_info = json.loads(lines[-1])
                    result.data = deploy_info
            except (json.JSONDecodeError, IndexError):
                result.data = {"stdout": result.data[:500]}
        return result


class PushFeishuTool(Tool):
    """飞书推送工具：通过 generate_report.py --feishu-push 内置，或独立调用。

    输入：html_path（报告路径，用于提取摘要）、cloudflare_url
    输出：推送结果
    """
    name = "push_feishu"

    def execute(self, data_path: str, ai_texts_path: str, html_path: str,
                cloudflare_url: str = "") -> ToolResult:
        # 复用 generate_report.py 的推送逻辑
        cmd = [
            PYTHON, REPORT_SCRIPT,
            "--data", data_path,
            "--ai-texts", ai_texts_path,
            "--html", html_path,
            "--feishu-push",
        ]
        # 传递 cloudflare_url 给脚本
        if cloudflare_url:
            cmd.extend(["--cloudflare-url", cloudflare_url])
        result = self._run_script(cmd, timeout=120)
        if result.success:
            result.data = {"pushed": True, "cloudflare_url": cloudflare_url}
        return result


def build_default_tools(run_id: str = "") -> dict:
    """构建默认工具集合，供 Agent 使用。

    返回 {tool_name: Tool} 字典。
    """
    tools = {
        "fetch_data": FetchDataTool(run_id),
        "prepare_prompt": PreparePromptTool(run_id),
        "compile_ai_texts": CompileTool(run_id),
        "render_report": RenderReportTool(run_id),
        "deploy_cloudflare": DeployCloudflareTool(run_id),
        "push_feishu": PushFeishuTool(run_id),
    }
    return tools
