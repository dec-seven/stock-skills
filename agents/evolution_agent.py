"""
Evolution Agent：策略进化引擎，从复盘中提炼方法论，持续优化知识库。

职责：
- 分析复盘报告，提炼可复用的分析方法
- 识别市场规律、关键模式、风险控制规则
- 自动更新知识库版本，沉淀策略经验
- 驱动系统自我进化，提升分析能力

输入：
{
  "source_type": "morning_brief" | "stock_selection" | "review" | "feedback",
  "source_date": "2026-06-23",
  "source_title": "6.23 盘前策略学习素材",
  "content": "...",
  "force_update": false  # 是否强制更新（即使已有记录）
}

输出：
{
  "success": true,
  "summary": "本次学习内容摘要",
  "key_patterns": [...],    # 提炼的关键分析模式
  "market_regime": [...],   # 识别的市场状态分类规则
  "rule_updates": [...],    # 规则变更列表
  "files_updated": [...]    # 更新的文件路径
}
"""

import os
import json
import re
from datetime import datetime
from typing import Dict, List, Any, Optional

from .base import BaseAgent, AgentResult, Tool, ToolResult

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class EvolutionAgent(BaseAgent):
    """策略进化 Agent"""

    name = "evolution_agent"
    description = "策略进化：从复盘中提炼方法论，持续优化知识库"

    # 知识库路径
    KB_DIR = os.path.join(PROJECT_ROOT, "knowledge-bases", "stock-methodology")
    MEMORY_DIR = os.path.join(PROJECT_ROOT, ".workbuddy", "memory")

    # 学习记录文件（防重复学习）
    LEARNING_LOG = os.path.join(KB_DIR, "learning_log.json")

    def run(self, input_data: dict) -> AgentResult:
        """执行进化流程

        流程：
        1. 检查是否已处理过（防重复）
        2. 提炼核心方法论（使用 LLM 或规则提取）
        3. 判断更新目标文件（早报指南 vs 选股指南 vs 两者）
        4. 合并到知识库（不覆盖，只增量）
        5. 更新版本号和学习记录
        """
        source_type = input_data.get("source_type", "morning_brief")
        source_date = input_data.get("source_date", datetime.now().strftime("%Y-%m-%d"))
        source_title = input_data.get("source_title", "")
        content = input_data.get("content", "")
        force_update = input_data.get("force_update", False)

        if not content:
            return AgentResult(
                success=False,
                agent_name=self.name,
                errors=["输入内容为空"]
            )

        # 1. 检查是否已学习过
        if not force_update and self._already_learned(source_title, source_date):
            return AgentResult(
                success=True,
                agent_name=self.name,
                data={"summary": "该素材已学习过，跳过", "skipped": True}
            )

        # 2. 提炼方法论
        extraction = self._extract_methodology(content, source_type)

        # 3. 确定更新目标
        target_files = self._determine_targets(source_type, extraction)

        # 4. 更新知识库
        updates = self._update_knowledge_base(target_files, extraction, source_date, source_title)

        # 5. 记录学习日志
        self._log_learning(source_title, source_date, extraction, updates)

        return AgentResult(
            success=True,
            agent_name=self.name,
            data={
                "summary": extraction.get("summary", ""),
                "key_patterns": extraction.get("key_patterns", []),
                "market_regime": extraction.get("market_regime", []),
                "rule_updates": updates,
                "files_updated": target_files
            }
        )

    def _already_learned(self, title: str, date: str) -> bool:
        """检查是否已学习过"""
        if not os.path.exists(self.LEARNING_LOG):
            return False

        try:
            with open(self.LEARNING_LOG, "r", encoding="utf-8") as f:
                log = json.load(f)
            for entry in log.get("entries", []):
                if entry.get("source_title") == title and entry.get("source_date") == date:
                    return True
        except Exception:
            pass
        return False

    def _extract_methodology(self, content: str, source_type: str) -> Dict[str, Any]:
        """提炼方法论（优先使用 LLM，离线时用规则提取）"""
        if self.llm and self.llm.mode == "online":
            return self._llm_extract(content, source_type)
        else:
            return self._rule_extract(content, source_type)

    def _llm_extract(self, content: str, source_type: str) -> Dict[str, Any]:
        """使用 LLM 提炼方法论"""
        prompt = f"""你是一个股市分析方法论提炼专家。

任务：从以下{'盘前策略' if source_type == 'morning_brief' else '选股逻辑' if source_type == 'stock_selection' else '复盘'}素材中，提炼可复用的分析方法。

素材内容：
{content}

请提取：
1. **核心方法论**（不是具体股票/事件，而是分析框架）
   - 市场判断规则
   - 信号识别方法
   - 决策逻辑链条
   - 风险控制规则

2. **关键模式**（识别模式和应对策略）
   - 形态识别（如"底部洗盘"、"分歧后延"）
   - 资金行为模式
   - 情绪周期规律

3. **市场状态分类**（如何区分市场阶段）
   - 上涨/下跌/震荡的特征
   - 主线持续/分化的判断标准

输出格式（JSON）：
{{
  "summary": "本次学习内容的一句话摘要",
  "methodology": [
    {{
      "rule_name": "规则名称",
      "description": "规则描述",
      "conditions": ["条件1", "条件2"],
      "actions": ["动作1", "动作2"],
      "target_section": "早报指南/选股指南/两者"
    }}
  ],
  "key_patterns": [
    {{
      "pattern_name": "模式名称",
      "recognition_rules": ["识别规则1", "识别规则2"],
      "tactical_implications": ["战术含义1", "战术含义2"]
    }}
  ],
  "market_regime": [
    {{
      "regime_name": "市场状态名称",
      "features": ["特征1", "特征2"],
      "position_advice": "仓位建议"
    }}
  ]
}}

注意：
- 只提取方法论，不提取具体股票、具体事件、具体日期
- 规则要可执行、可验证，避免模糊表述
- 每个规则要说明适用场景和边界条件
"""

        try:
            result = self.llm.chat(
                system_prompt="你是股市分析方法论提炼专家，只输出 JSON 格式。",
                user_prompt=prompt
            )

            # 解析 JSON
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"[EvolutionAgent] LLM 提取失败: {e}")

        # 失败时回退到规则提取
        return self._rule_extract(content, source_type)

    def _rule_extract(self, content: str, source_type: str) -> Dict[str, Any]:
        """规则提取（离线模式或 LLM 失败时）"""
        # 简单提取：识别"规律"、"方法"、"策略"等关键词后的句子
        patterns = {
            "key_patterns": [],
            "market_regime": [],
            "methodology": []
        }

        # 提取包含"规律"、"模式"、"特征"的句子
        keywords = ["规律", "模式", "特征", "信号", "判断", "策略", "规则"]
        lines = content.split("\n")
        for line in lines:
            for kw in keywords:
                if kw in line and len(line) > 20:
                    patterns["key_patterns"].append({
                        "pattern_name": f"自动识别-{kw}",
                        "recognition_rules": [line.strip()],
                        "tactical_implications": []
                    })
                    break

        patterns["summary"] = f"规则提取：识别到 {len(patterns['key_patterns'])} 条关键模式"
        return patterns

    def _determine_targets(self, source_type: str, extraction: Dict) -> List[str]:
        """确定更新目标文件"""
        targets = []

        # 根据素材类型
        if source_type == "morning_brief":
            targets.append(os.path.join(self.KB_DIR, "stock_morning_brief_guide.md"))
        elif source_type == "stock_selection":
            targets.append(os.path.join(self.KB_DIR, "stock_selection_guide.md"))
        elif source_type == "review":
            targets.append(os.path.join(self.KB_DIR, "stock_morning_brief_guide.md"))
        else:
            # 根据方法论目标自动判断
            for rule in extraction.get("methodology", []):
                target_section = rule.get("target_section", "")
                if "早报" in target_section:
                    mb_path = os.path.join(self.KB_DIR, "stock_morning_brief_guide.md")
                    if mb_path not in targets:
                        targets.append(mb_path)
                if "选股" in target_section:
                    ss_path = os.path.join(self.KB_DIR, "stock_selection_guide.md")
                    if ss_path not in targets:
                        targets.append(ss_path)

        # 默认两个都更新
        if not targets:
            targets = [
                os.path.join(self.KB_DIR, "stock_morning_brief_guide.md"),
                os.path.join(self.KB_DIR, "stock_selection_guide.md")
            ]

        return targets

    def _update_knowledge_base(self, target_files: List[str], extraction: Dict, source_date: str, source_title: str) -> List[Dict]:
        """更新知识库文件"""
        updates = []

        for filepath in target_files:
            if not os.path.exists(filepath):
                continue

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()

                # 查找版本号
                version_match = re.search(r'>\s*\*\*版本\*\*:\s*v(\d+\.\d+)', content)
                current_version = float(version_match.group(1)) if version_match else 1.0
                new_version = f"{current_version + 0.1:.1f}"

                # 查找"版本记录"章节
                version_section_match = re.search(r'##\s*\d+\.\s*版本记录', content)
                if not version_section_match:
                    version_section_match = re.search(r'##\s*版本记录', content)

                # 生成变更内容
                change_summary = extraction.get("summary", "")
                new_entry = f"| v{new_version} | {source_date} | {change_summary}（来源：{source_title}） |\n"

                # 插入到版本记录表格
                if version_section_match:
                    # 找到版本记录后的第一个表格
                    table_start = content.find("| 版本 |", version_section_match.start())
                    if table_start == -1:
                        table_start = content.find("|", version_section_match.start() + 100)

                    if table_start != -1:
                        # 找到第二行（表头分隔符）
                        line_end = content.find("\n", table_start)
                        line_end = content.find("\n", line_end + 1)

                        if line_end != -1:
                            # 在第三行插入新记录
                            new_content = content[:line_end + 1] + new_entry + content[line_end + 1:]

                            # 更新版本号
                            new_content = re.sub(
                                r'>\s*\*\*版本\*\*:\s*v[\d.]+',
                                f'> **版本**: v{new_version}',
                                new_content
                            )

                            # 更新"最后更新"日期
                            new_content = re.sub(
                                r'>\s*\*\*最后更新\*\*:\s*[\d-]+',
                                f'> **最后更新**: {source_date}',
                                new_content
                            )

                            # 写回文件
                            with open(filepath, "w", encoding="utf-8") as f:
                                f.write(new_content)

                            updates.append({
                                "file": filepath,
                                "old_version": f"v{current_version}",
                                "new_version": f"v{new_version}",
                                "change": change_summary
                            })
            except Exception as e:
                print(f"[EvolutionAgent] 更新 {filepath} 失败: {e}")

        return updates

    def _log_learning(self, title: str, date: str, extraction: Dict, updates: List[Dict]):
        """记录学习日志"""
        log_data = {"entries": []}

        # 读取现有日志
        if os.path.exists(self.LEARNING_LOG):
            try:
                with open(self.LEARNING_LOG, "r", encoding="utf-8") as f:
                    log_data = json.load(f)
            except Exception:
                pass

        # 添加新记录
        log_data["entries"].append({
            "source_title": title,
            "source_date": date,
            "learned_at": datetime.now().isoformat(),
            "summary": extraction.get("summary", ""),
            "files_updated": [u["file"] for u in updates]
        })

        # 写回日志
        os.makedirs(os.path.dirname(self.LEARNING_LOG), exist_ok=True)
        with open(self.LEARNING_LOG, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
