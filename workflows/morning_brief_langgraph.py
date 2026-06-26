"""
早报编排工作流 - LangGraph 版本

基于 LangGraph StateGraph 实现状态机编排：
  fetch → event → macro/sector(并行) → stock → risk_manager → review → compile → render → deploy → push → learn

特性：
- 双模式 LLM（在线 DeepSeek / 离线规则推导）
- 断点续跑（通过 state.current_step）
- 并发执行（macro/sector 通过 LangGraph 并行）
- 失败回退（LLM 失败时回退到规则推导）
- Event Agent：抓取近期重大国内外事件日历

用法：
  python3 -m workflows.morning_brief_langgraph
  python3 -m workflows.morning_brief_langgraph --from-step stock
  python3 -m workflows.morning_brief_langgraph --skip-deploy --skip-push
"""

import os
import sys
import json
import time
import uuid
import argparse
import concurrent.futures
from datetime import datetime
from typing import TypedDict, Optional, Dict, Any, List, Annotated
import operator

# LangGraph 核心导入
from langgraph.graph import StateGraph, END
from langgraph.constants import START

# 项目根
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from agents.base import BaseAgent, AgentResult
from agents.macro_agent import MacroAgent
from agents.sector_agent import SectorAgent
from agents.stock_agent import StockAgent
from agents.review_agent import ReviewAgent
from agents.risk_manager_agent import RiskManagerAgent
from agents.learning_agent import LearningAgent
from agents.event_agent import EventAgent
from shared.ai.llm_client import LLMClient
from shared.ai.tools import build_default_tools
from shared.ai.fact_guard import validate_macro_output

# 默认工作目录
DEFAULT_WORK_DIR = os.path.join(PROJECT_ROOT, "skills", "stock-morning-brief", "tmp")

# 状态机步骤
STEPS = ["fetch", "event", "macro", "sector", "stock", "risk_manager", "review", "compile", "render", "deploy", "push", "learn"]


def merge_dicts(left: Dict, right: Dict) -> Dict:
    """合并两个字典（用于 Annotated reducer）"""
    if not left:
        return right or {}
    if not right:
        return left
    result = left.copy()
    result.update(right)
    return result


class MorningBriefState(TypedDict):
    """LangGraph 状态对象"""
    # 运行标识
    run_id: str
    work_dir: str
    current_step: str
    llm_mode: str  # "online" or "offline"
    
    # 文件路径
    market_data_path: str
    llm_analysis_path: str
    ai_texts_path: str
    html_path: str
    
    # 数据
    market_data: Dict[str, Any]
    
    # Agent 结果（使用 Annotated 支持合并）
    macro_result: Annotated[Dict[str, Any], merge_dicts]
    sector_result: Annotated[Dict[str, Any], merge_dicts]
    stock_result: Annotated[Dict[str, Any], merge_dicts]
    risk_manager_result: Annotated[Dict[str, Any], merge_dicts]
    review_result: Annotated[Dict[str, Any], merge_dicts]
    
    # 步骤结果
    steps: Annotated[Dict[str, Dict], merge_dicts]
    
    # 输出
    cloudflare_url: str
    success: bool
    error: str
    error_detail: str
    
    # 控制标志
    skip_deploy: bool
    skip_push: bool
    
    # LLM Client 和 Tools（非序列化）
    llm: Any
    tools: Dict[str, Any]
    
    # Agents（非序列化）
    agents: Dict[str, Any]


def create_initial_state(work_dir: str, llm_client: LLMClient = None, skip_deploy: bool = False, skip_push: bool = False) -> MorningBriefState:
    """创建初始状态"""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
    
    # 加载 .env
    env_path = os.path.join(PROJECT_ROOT, "env", ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
        except Exception:
            pass
    
    llm = llm_client or LLMClient()
    tools = build_default_tools()
    
    # 初始化 Agents
    agents = {
        "event": EventAgent(llm_client=llm, tools=tools, run_id=run_id),
        "macro": MacroAgent(llm_client=llm, tools=tools, run_id=run_id),
        "sector": SectorAgent(llm_client=llm, tools=tools, run_id=run_id),
        "stock": StockAgent(llm_client=llm, tools=tools, run_id=run_id),
        "review": ReviewAgent(llm_client=llm, tools=tools, run_id=run_id),
        "risk_manager": RiskManagerAgent(llm_client=llm, tools=tools, run_id=run_id),
        "learning": LearningAgent(llm_client=llm, tools=tools, run_id=run_id),
    }
    
    return MorningBriefState(
        run_id=run_id,
        work_dir=work_dir,
        current_step="fetch",
        llm_mode=llm.mode,
        market_data_path=os.path.join(work_dir, "market_data.json"),
        llm_analysis_path=os.path.join(work_dir, "llm_analysis.json"),
        ai_texts_path=os.path.join(work_dir, "ai_texts.json"),
        html_path=os.path.join(work_dir, "morning_brief.html"),
        market_data={},
        macro_result={},
        sector_result={},
        stock_result={},
        risk_manager_result={},
        review_result={},
        steps={},
        cloudflare_url="",
        success=False,
        error="",
        error_detail="",
        skip_deploy=skip_deploy,
        skip_push=skip_push,
        llm=llm,
        tools=tools,
        agents=agents,
    )


# ============ 节点函数 ============

def node_fetch(state: MorningBriefState) -> Dict:
    """获取市场数据"""
    print(f"\n[Workflow] run_id={state['run_id']}, LLM 模式={state['llm_mode']}")
    print("\n[1/12] 获取市场数据...")
    
    r = state["tools"]["fetch_data"].execute(output_path=state["market_data_path"])
    
    if not r.success:
        return {
            "success": False,
            "error": "fetch 失败",
            "error_detail": r.error,
            "current_step": "END",
        }
    
    # 加载市场数据
    market_data = {}
    try:
        with open(state["market_data_path"], "r", encoding="utf-8") as f:
            market_data = json.load(f)
    except Exception:
        return {
            "success": False,
            "error": "market_data.json 加载失败",
            "current_step": "END",
        }
    
    return {
        "market_data": market_data,
        "steps": {"fetch": {"success": True, "duration_ms": r.duration_ms}},
        "current_step": "event",
    }


def node_event(state: MorningBriefState) -> Dict:
    """运行 Event Agent 抓取重大事件，并写入 market_data.json"""
    print("\n[2/12] 抓取重大事件日历...")
    
    event_res = state["agents"]["event"].run({
        "market_data": state["market_data"],
        "work_dir": state["work_dir"],
    })
    
    # 将事件写入 market_data
    market_data = state["market_data"]
    if event_res.success and event_res.data:
        events = event_res.data.get("EVENTS", [])
        if "news_events" not in market_data:
            market_data["news_events"] = {}
        market_data["news_events"]["events"] = events
        market_data["news_events"]["need_websearch"] = False
        
        # 写回文件
        try:
            with open(state["market_data_path"], "w", encoding="utf-8") as f:
                json.dump(market_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    return {
        "market_data": market_data,
        "steps": {"event": {"success": event_res.success, "errors": event_res.errors}},
        "current_step": "agents_parallel",
    }


def node_agents_parallel(state: MorningBriefState) -> Dict:
    """并行运行 macro + sector Agent"""
    
    if state["llm"].is_online():
        print("\n[3-4/12] 并行运行 macro + sector Agent...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_macro = executor.submit(
                state["agents"]["macro"].run,
                {"market_data": state["market_data"], "work_dir": state["work_dir"]}
            )
            future_sector = executor.submit(
                state["agents"]["sector"].run,
                {"market_data": state["market_data"], "work_dir": state["work_dir"]}
            )
        macro_res = future_macro.result()
        sector_res = future_sector.result()
        
        # 事实校验：修复幻觉
        macro_data = macro_res.data if macro_res.success else {}
        if macro_data:
            macro_data = validate_macro_output(state["market_data"], macro_data)
        
        return {
            "macro_result": macro_data,
            "sector_result": sector_res.data if sector_res.success else {},
            "steps": {
                "macro": {"success": macro_res.success, "errors": macro_res.errors},
                "sector": {"success": sector_res.success, "errors": sector_res.errors},
            },
            "current_step": "stock",
        }
    else:
        # 离线模式：串行
        print("\n[3/12] 运行 macro Agent...")
        macro_res = state["agents"]["macro"].run({
            "market_data": state["market_data"],
            "work_dir": state["work_dir"]
        })
        
        print("\n[4/12] 运行 sector Agent...")
        sector_res = state["agents"]["sector"].run({
            "market_data": state["market_data"],
            "work_dir": state["work_dir"]
        })
        
        # 事实校验：修复幻觉
        macro_data = macro_res.data if macro_res.success else {}
        if macro_data:
            macro_data = validate_macro_output(state["market_data"], macro_data)
        
        return {
            "macro_result": macro_data,
            "sector_result": sector_res.data if sector_res.success else {},
            "steps": {
                "macro": {"success": macro_res.success, "errors": macro_res.errors},
                "sector": {"success": sector_res.success, "errors": sector_res.errors},
            },
            "current_step": "stock",
        }


def node_stock(state: MorningBriefState) -> Dict:
    """运行 stock Agent"""
    print("\n[5/12] 运行 stock Agent...")
    
    stock_res = state["agents"]["stock"].run({
        "market_data": state["market_data"],
        "macro_result": state["macro_result"],
        "sector_result": state["sector_result"],
        "work_dir": state["work_dir"],
    })
    
    return {
        "stock_result": stock_res.data if stock_res.success else {},
        "steps": {"stock": {"success": stock_res.success, "errors": stock_res.errors}},
        "current_step": "risk_manager",
    }


def node_risk_manager(state: MorningBriefState) -> Dict:
    """运行 risk_manager Agent"""
    print("\n[6/12] 运行 risk_manager Agent...")
    
    risk_res = state["agents"]["risk_manager"].run({
        "market_data": state["market_data"],
        "stock_result": state["stock_result"],
        "work_dir": state["work_dir"],
    })
    
    return {
        "risk_manager_result": risk_res.data if risk_res.success else {},
        "steps": {"risk_manager": {"success": risk_res.success, "errors": risk_res.errors}},
        "current_step": "review",
    }


def node_review(state: MorningBriefState) -> Dict:
    """运行 review Agent"""
    print("\n[7/12] 运行 review Agent...")
    
    review_res = state["agents"]["review"].run({
        "market_data": state["market_data"],
        "macro_result": state["macro_result"],
        "sector_result": state["sector_result"],
        "stock_result": state["stock_result"],
        "work_dir": state["work_dir"],
    })
    
    return {
        "review_result": review_res.data if review_res.success else {},
        "steps": {"review": {"success": review_res.success, "errors": review_res.errors}},
        "current_step": "compile",
    }


def node_compile(state: MorningBriefState) -> Dict:
    """编译 ai_texts.json"""
    print("\n[8/12] 编译 ai_texts.json...")
    
    # 在线模式：合并 Agent 输出
    if state["llm"].is_online():
        merged = {}
        for agent_data in [state["macro_result"], state["sector_result"], 
                          state["stock_result"], state["review_result"]]:
            if isinstance(agent_data, dict):
                for k, v in agent_data.items():
                    if k not in ("mode", "prompt_path", "fields"):
                        merged[k] = v
        
        if not merged:
            # 回退到离线
            return _offline_compile(state)
        
        # 写入 llm_analysis.json
        with open(state["llm_analysis_path"], "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        
        # 调 compile
        r = state["tools"]["compile_ai_texts"].execute(
            data_path=state["market_data_path"],
            analysis_path=state["llm_analysis_path"],
            output_path=state["ai_texts_path"],
        )
        
        return {
            "steps": {"compile": {"success": r.success}},
            "current_step": "render" if r.success else "END",
            "success": r.success,
            "error": "" if r.success else "compile 失败",
        }
    else:
        return _offline_compile(state)


def _offline_compile(state: MorningBriefState) -> Dict:
    """离线模式编译"""
    print("[Workflow] 离线模式：生成 prompt，等待外部执行 LLM...")
    
    r = state["tools"]["prepare_prompt"].execute(
        data_path=state["market_data_path"],
        output_dir=state["work_dir"],
    )
    
    if r.success:
        print(f"[Workflow] prompt 已生成: {r.data.get('prompt_path', '')}")
        print("[Workflow] 请外部执行 LLM 生成 llm_analysis.json，然后运行:")
        print(f"  python3 -m workflows.morning_brief_langgraph --from-step compile")
    
    return {
        "steps": {"compile": {"success": False}},
        "current_step": "END",
        "success": False,
        "error": "离线模式等待外部执行",
    }


def node_render(state: MorningBriefState) -> Dict:
    """渲染 HTML 报告"""
    print("\n[9/12] 渲染 HTML 报告...")
    
    r = state["tools"]["render_report"].execute(
        data_path=state["market_data_path"],
        ai_texts_path=state["ai_texts_path"],
        html_path=state["html_path"],
        analysis_json=state["llm_analysis_path"],
    )
    
    return {
        "steps": {"render": {"success": r.success, "error": r.error, "duration_ms": r.duration_ms}},
        "current_step": "deploy" if r.success else "END",
        "success": r.success,
        "error": "" if r.success else f"render 失败: {r.error}",
    }


def node_deploy(state: MorningBriefState) -> Dict:
    """部署到 Cloudflare"""
    
    if state["skip_deploy"]:
        print("\n[10/12] 跳过部署")
        return {"current_step": "push"}
    
    print("\n[10/12] 部署 Cloudflare...")
    
    r = state["tools"]["deploy_cloudflare"].execute(html_path=state["html_path"])
    
    cloudflare_url = ""
    if r.success and isinstance(r.data, dict):
        cloudflare_url = r.data.get("cloudflare_url", "")
    
    return {
        "steps": {"deploy": {"success": r.success, "error": r.error, "data": r.data}},
        "cloudflare_url": cloudflare_url,
        "current_step": "push",
    }


def node_push(state: MorningBriefState) -> Dict:
    """飞书推送"""
    
    if state["skip_push"]:
        print("\n[11/12] 跳过推送")
        return {"current_step": "learn"}
    
    print("\n[11/12] 飞书推送...")
    
    r = state["tools"]["push_feishu"].execute(
        data_path=state["market_data_path"],
        ai_texts_path=state["ai_texts_path"],
        html_path=state["html_path"],
        cloudflare_url=state["cloudflare_url"],
    )
    
    return {
        "steps": {"push": {"success": r.success, "error": r.error}},
        "current_step": "learn",
    }


def node_learn(state: MorningBriefState) -> Dict:
    """学习本次报告中的方法论"""
    print("\n[12/12] 运行 Learning Agent...")
    
    # 读取 ai_texts.json
    ai_texts = {}
    try:
        with open(state["ai_texts_path"], "r", encoding="utf-8") as f:
            ai_texts = json.load(f)
    except Exception:
        return {
            "steps": {"learn": {"success": False, "error": "ai_texts.json 不存在"}},
            "current_step": "END",
            "success": True,  # learn 失败不影响整体
        }
    
    # 提取学习内容
    import re
    parts = []
    
    if "MARKET_TONE" in ai_texts:
        parts.append(f"【市场定位】\n{ai_texts['MARKET_TONE']}")
    if "DIRECTION_JUDGMENT" in ai_texts:
        parts.append(f"【方向判断】\n{ai_texts['DIRECTION_JUDGMENT']}")
    if "SECTOR_DIRECTIONS" in ai_texts:
        parts.append(f"【板块方向】\n{ai_texts['SECTOR_DIRECTIONS']}")
    if "STOCK_SELECTION" in ai_texts:
        text = re.sub(r'<[^>]+>', ' ', ai_texts['STOCK_SELECTION'])
        text = re.sub(r'\s+', ' ', text).strip()
        parts.append(f"【选股逻辑】\n{text[:500]}...")
    if "RISK_WARNINGS" in ai_texts:
        text = re.sub(r'<[^>]+>', ' ', ai_texts['RISK_WARNINGS'])
        text = re.sub(r'\s+', ' ', text).strip()
        parts.append(f"【风险预警】\n{text}")
    if "OPERATION_STRATEGY" in ai_texts:
        parts.append(f"【操作策略】\n{ai_texts['OPERATION_STRATEGY']}")
    
    learning_content = "\n\n".join(parts)
    
    learn_res = state["agents"]["learning"].run({
        "source_type": "review",
        "source_date": datetime.now().strftime("%Y-%m-%d"),
        "source_title": f"早报自动复盘 {datetime.now().strftime('%Y-%m-%d')}",
        "content": learning_content,
        "force_update": False
    })
    
    return {
        "steps": {
            "learn": {
                "success": learn_res.success,
                "summary": learn_res.data.get("summary", "") if learn_res.success else "",
                "files_updated": learn_res.data.get("files_updated", []) if learn_res.success else []
            }
        },
        "current_step": "END",
        "success": True,
    }


# ============ 路由函数 ============

def route_from_fetch(state: MorningBriefState) -> str:
    """从 fetch 节点路由"""
    if state.get("error"):
        return END
    return "event"


def route_from_agents(state: MorningBriefState) -> str:
    """从 agents_parallel 节点路由"""
    if state.get("error"):
        return END
    return "stock"


def route_from_event(state: MorningBriefState) -> str:
    """从 event 节点路由"""
    if state.get("error"):
        return END
    return "agents_parallel"


def route_generic(state: MorningBriefState) -> str:
    """通用路由"""
    if state.get("error"):
        return END
    return state.get("current_step", END)


# ============ 构建图 ============

def build_graph() -> StateGraph:
    """构建 LangGraph StateGraph"""
    
    # 创建图
    graph = StateGraph(MorningBriefState)
    
    # 添加节点
    graph.add_node("fetch", node_fetch)
    graph.add_node("event", node_event)
    graph.add_node("agents_parallel", node_agents_parallel)
    graph.add_node("stock", node_stock)
    graph.add_node("risk_manager", node_risk_manager)
    graph.add_node("review", node_review)
    graph.add_node("compile", node_compile)
    graph.add_node("render", node_render)
    graph.add_node("deploy", node_deploy)
    graph.add_node("push", node_push)
    graph.add_node("learn", node_learn)
    
    # 添加边
    graph.add_edge(START, "fetch")
    graph.add_conditional_edges("fetch", route_from_fetch, {
        "event": "event",
        END: END,
    })
    graph.add_conditional_edges("event", route_from_event, {
        "agents_parallel": "agents_parallel",
        END: END,
    })
    graph.add_conditional_edges("agents_parallel", route_from_agents, {
        "stock": "stock",
        END: END,
    })
    graph.add_conditional_edges("stock", route_generic, {
        "risk_manager": "risk_manager",
        END: END,
    })
    graph.add_conditional_edges("risk_manager", route_generic, {
        "review": "review",
        END: END,
    })
    graph.add_conditional_edges("review", route_generic, {
        "compile": "compile",
        END: END,
    })
    graph.add_conditional_edges("compile", route_generic, {
        "render": "render",
        END: END,
    })
    graph.add_conditional_edges("render", route_generic, {
        "deploy": "deploy",
        END: END,
    })
    graph.add_edge("deploy", "push")
    graph.add_edge("push", "learn")
    graph.add_edge("learn", END)
    
    return graph


# ============ 主函数 ============

def run_workflow(work_dir: str = DEFAULT_WORK_DIR, from_step: str = None, 
                 skip_deploy: bool = False, skip_push: bool = False) -> Dict:
    """运行工作流"""
    
    os.makedirs(work_dir, exist_ok=True)
    
    # 创建初始状态
    initial_state = create_initial_state(work_dir, skip_deploy=skip_deploy, skip_push=skip_push)
    
    # 如果指定 from_step，调整 current_step
    if from_step and from_step in STEPS:
        initial_state["current_step"] = from_step
        # 加载已有数据
        state_path = os.path.join(work_dir, "workflow_state.json")
        if os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    saved_state = json.load(f)
                    # 恢复已保存的 Agent 结果
                    for key in ["macro_result", "sector_result", "stock_result", 
                               "risk_manager_result", "review_result", "market_data"]:
                        if key in saved_state:
                            initial_state[key] = saved_state[key]
            except Exception:
                pass
    
    # 构建并编译图
    graph = build_graph()
    app = graph.compile()
    
    # 运行
    print(f"[Workflow] run_id={initial_state['run_id']}, LLM 模式={initial_state['llm_mode']}, work_dir={work_dir}")
    
    final_state = app.invoke(initial_state)
    
    # 输出结果
    result = {
        "run_id": final_state["run_id"],
        "success": final_state.get("success", False),
        "error": final_state.get("error", ""),
        "cloudflare_url": final_state.get("cloudflare_url", ""),
        "html_path": final_state["html_path"],
        "steps": final_state.get("steps", {}),
        "mode": final_state["llm_mode"],
    }
    
    print(f"\n[Workflow] 完成 {'✓' if result['success'] else '✗'} run_id={result['run_id']}")
    if result["cloudflare_url"]:
        print(f"[Workflow] Cloudflare URL: {result['cloudflare_url']}")
    
    return result


def main():
    parser = argparse.ArgumentParser(description="早报编排工作流 (LangGraph)")
    parser.add_argument("--work-dir", default=DEFAULT_WORK_DIR, help="工作目录")
    parser.add_argument("--from-step", default=None, choices=STEPS, help="从指定步骤开始（断点续跑）")
    parser.add_argument("--skip-deploy", action="store_true", help="跳过 Cloudflare 部署")
    parser.add_argument("--skip-push", action="store_true", help="跳过飞书推送")
    args = parser.parse_args()
    
    result = run_workflow(
        work_dir=args.work_dir,
        from_step=args.from_step,
        skip_deploy=args.skip_deploy,
        skip_push=args.skip_push,
    )
    
    # 保存结果
    result_path = os.path.join(args.work_dir, "workflow_result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n[Workflow] 结果已保存: {result_path}")
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
