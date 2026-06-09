---
name: closing-daily-report
description: |
  A股收盘日报生成。每个交易日收盘后，自动拉取行情数据、资金流向、行业表现等，
  结合 AI 分析生成 18 模块的完整 PDF 收盘报告。
  触发词：生成收盘报告、A股复盘、今日复盘、收盘日报、daily report
  与 stock-analysis skill 的关系：
  - stock-analysis：单只股票/组合分析，侧重投资决策
  - a-share-daily-report：全市场收盘复盘，侧重信息汇总与呈现
agent_created: true

---

# A股收盘日报生成 Skill

## 概述

每个交易日收盘后（15:30 以后），生成一份完整的 A 股收盘日报 HTML/PDF。
报告包含 18 个模块，覆盖指数、资金、行业、概念、龙虎榜、技术面、公告等。
支持 `--feishu-push` 一键推送飞书。

## 目录结构

```
closing-daily-report/
├── SKILL.md                    # Skill 定义（本文件）
├── requirements.txt            # Python 依赖
├── scripts/
│   ├── main.py                 # 主入口：调度数据拉取 + 校验
│   ├── fetch_market_data.py    # AkShare 数据获取
│   ├── generate_report.py      # HTML 模板填充 + PDF 生成
│   └── send_feishu.py          # 飞书群投递（可选）
└── references/
    └── report_template.html    # 报告 HTML 模板
```

---

## 首次使用 · 环境配置

### Python 环境（关键）

WorkBuddy 环境下有多个 Python 版本可用，**必须使用系统 Python 3.9**（managed Python 3.13 的 numpy 在 macOS 上有签名冲突）：

```bash
# 1. 创建专用 venv（只需一次）
/Library/Frameworks/Python.framework/Versions/3.9/bin/python3 -m venv /Users/DecSeven/.workbuddy/binaries/python/envs/closing-daily39

# 2. 安装依赖（只需一次）
/Users/DecSeven/.workbuddy/binaries/python/envs/closing-daily39/bin/pip install -r {{SKILL_DIR}}/requirements.txt

# 3. 后续所有 python3 调用都使用此路径
PYTHON=/Users/DecSeven/.workbuddy/binaries/python/envs/closing-daily39/bin/python3
```

### 依赖清单

- Python 3.9（系统版本，非 managed）
- AkShare >= 1.14（核心数据源，免费开源）
- WeasyPrint 或 Chrome（PDF 生成后端，至少一个）
- lark-cli（飞书投递，可选）

### 验证安装

```bash
$PYTHON -c "import akshare; import weasyprint; print('OK')"
```

---

## 工作流（按顺序执行）

### 阶段 1：确认交易日

- 检查当前时间是否在 A 股交易时段后（>15:00 CST）
- 如果是周末或节假日，提示用户今天非交易日，询问是否查看最近交易日
- 确定 `TRADE_DATE`（格式 YYYY-MM-DD）

### 阶段 2：拉取结构化数据

```bash
$PYTHON {{SKILL_DIR}}/scripts/main.py --date TRADE_DATE --output /tmp/market_data.json
```

退出码含义：

| 退出码 | 含义 | 动作 |
|--------|------|------|
| **0** | 数据完整 | 直接跳到阶段 4 |
| **2** | 部分缺失 / 超时 | **自动进入阶段 2B WebSearch 回退** |
| **1** | 严重错误 | 检查日志后进入阶段 2B |

> **重要**：main.py 超时（120秒）也返回退出码 2，不要重试 AkShare，直接走 WebSearch 回退。

### 阶段 2B：WebSearch 回退（数据不完整时）

AkShare 经常因网络原因超时，**不要反复重试**。直接使用 WebSearch + WebFetch 从以下来源拉取：

**搜索策略（按优先级并行搜索）：**

1. `"YYYY-MM-DD" A股收盘 上证指数 创业板指 涨跌幅 成交额` — 指数、成交额、涨跌家数
2. `"YYYY-MM-DD" 北向资金 净流入 北向资金流向` — 北向资金数据
3. `"YYYY-MM-DD" A股 概念板块 涨幅 龙虎榜` — 行业概念、龙虎榜
4. `"YYYY-MM-DD" A股 重大公告 利好利空` — 公告和宏观新闻
5. `"YYYY-MM-DD" 两融余额 融资融券 A股` — 两融数据

用 WebFetch 抓取排名靠前的搜索结果页提取精确数字。

**回退数据整理 → market_data.json 标准格式：**

WebSearch 回退时，需手动构建符合 generate_report.py 期望的 JSON 结构：

```json
{
  "trade_date": "YYYY-MM-DD",
  "generated_at": "YYYY-MM-DD HH:MM:SS",
  "total_turnover": 26400.0,
  "prev_turnover": 27924.0,
  "main_net_flow": 125.30,
  "northbound_turnover": 1850.0,
  "margin_balance": 28800.0,
  "etf_net_flow": 45.60,
  "rmb_mid_rate": 7.1845,
  "indices": [
    {"name": "上证指数", "code": "000001", "close": 4010.03, "pct": 1.28, "change": 50.63, "open": 3998.50, "high": 4078.93, "low": 3990.12, "amplitude": 2.22},
    {"name": "深证成指", "code": "399001", "close": 15268.71, "pct": 3.02, "change": 447.52, "open": 15100.30, "high": 15350.00, "low": 15050.00, "amplitude": 1.98},
    {"name": "创业板指", "code": "399006", "close": 3961.75, "pct": 3.93, "change": 149.72, "open": 3900.00, "high": 4000.00, "low": 3890.00, "amplitude": 2.82}
  ],
  "sectors": [
    {"name": "半导体", "pct": 4.50, "main_net": 85.30},
    {"name": "煤炭开采", "pct": -2.30, "main_net": -35.60}
  ],
  "market_breadth": {
    "up_count": 3322,
    "down_count": 2049,
    "limit_up_count": 142,
    "limit_down_count": 16,
    "limit_up_excl_st": 120,
    "limit_down_excl_st": 12,
    "limit_up_list": [
      {"name": "沪硅产业", "code": "688126", "pct": 20.01, "reason": "半导体大硅片龙头"}
    ]
  }
}
```

**字段说明：**
- `total_turnover`: 全市场总成交额（亿），用于市场快照标签栏
- `main_net_flow`: 主力资金净流入（亿），正=红/流入，负=绿/流出
- `northbound_turnover`: 北向资金成交额（亿）
- `margin_balance`: 两融余额（亿）
- `etf_net_flow`: 股票ETF净流向（亿），正=净流入
- `rmb_mid_rate`: 人民币中间价（元/美元，保留4位小数）
- `indices`: 每条新增 `open` `high` `low` `amplitude`（振幅%），用于日内走势 OHLC 行
- `market_breadth.limit_up_excl_st` / `limit_down_excl_st`: 不含ST的涨跌停家数（可选，缺失时回退到 `limit_up_count` / `limit_down_count`）

### 阶段 3：数据校验

无论数据来自 AkShare 还是 WebSearch，检查核心字段：

- `indices` 至少 3 条（上证、深证、创业板），各有 `close` 和 `pct`
- `market_breadth.up_count` > 0
- `sectors` 至少 5 条
- 缺失则回到阶段 2B 补充

### 阶段 4：AI 生成分析段落

基于数据 + WebSearch 结果，AI 生成以下 14 段内容，保存到 `/tmp/ai_texts.json`：

| 序号 | 段落 | 占位符 | 字数 | 说明 |
|------|------|--------|------|------|
| 1 | 核心摘要 | SUMMARY | 200-350 | 市场定调 + 关键数据 + 核心矛盾 |
| 2 | 日内走势复盘 | INTRADAY_REVIEW | 200-300 | 分上午/下午描述，引用分时高低点 |
| 3 | 宏观背景 | MACRO_BACKGROUND | 150-250 | 当日政策/事件 + 全球市场联动 |
| 4 | 北向资金叙述 | NORTH_BOUND_NARRATIVE | 100-200 | 北向资金动向分析 |
| 5 | 概念表现 | CONCEPT_NARRATIVE | 150-200 | 涨跌概念 + 催化原因 |
| 6 | 技术面分析 | TECHNICAL_ANALYSIS | 150-200 | 支撑/阻力位 + 形态判断 |
| 7 | 重点个股表格 | KEY_STOCKS_TABLE | — | HTML `<tr>` 行，6-8 只精选个股 |
| 8 | 龙虎榜 | DRAGON_TIGER | 100-200 | 机构动向 |
| 9 | 两融 | MARGIN_TRADING | 100-150 | 融资融券情况 |
| 10 | 重大公告 | ANNOUNCEMENTS | 100-200 | 利好利空公告，HTML `<br>` 分隔 |
| 11 | 关注清单 | WATCHLIST | 100-150 | 后续事件日历，HTML `<br>` 分隔 |
| 12 | 预案框架 | SCENARIO_PLANS | 200-250 | 两套 HTML `<div class="scenario">` |
| 13 | 风险提示 | RISK_WARNINGS | — | 4 条，各用 `<div class="risk-box">` |
| 14 | 总结 | CONCLUSION | 200-300 | 积极信号 + 谨慎信号 + 综合判断 |

**⚠️ JSON 安全规则（必须遵守）：**

- 所有文本值中**禁止出现 ASCII 双引号 `"`**（会炸 JSON 解析），改用中文引号 `「」` 或 `「」`
- KEY_STOCKS_TABLE / SCENARIO_PLANS / RISK_WARNINGS 的值是 HTML 片段，内部的属性引号用 `\` 转义：`class=\"up\"`
- 写完后必须用 `python3 -c "import json; json.load(open('/tmp/ai_texts.json'))"` 验证通过
- 如果验证失败，用 `python3 -c` 定位错误字符后 fix 再重试

**AI 文本格式规则（必须遵守）：**

- **SUMMARY（核心摘要）**：对上涨品种/指数使用 `<span class="up">...</span>`（红色），下跌使用 `<span class="down">...</span>`（绿色）；关键数据、政策名称等加粗 `<b>...</b>`。示例：`<b>半导体板块</b>全天大涨<span class="up">+4.50%</span>`
- **INTRADAY_REVIEW（日内走势复盘）**：AI 只需生成 `<div class="intraday-block">` 段落（OHLC 行由脚本自动生成）。格式规范：
  - 上午段：`<div class="intraday-block am"><div class="block-title">🔵 上午：低开高走，个股普涨</div><ul><li>沪指低开12点至4044.83...</li></ul></div>`
  - 下午段：`<div class="intraday-block pm"><div class="block-title">🔴 下午：冲高回落</div><ul><li>午后高价股跳水...</li></ul></div>`
  - 警告行：`<div class="warn-line">⚠ 连续两日呈"上午冲高、下午回落"形态</div>`
  - 参考用户提供的格式样例，确保 `<ul>` 内用 `●` 开头的 `<li>` 条目

ai_texts.json 格式：

```json
{
  "SUMMARY": "今日A股三大指数高开高走...",
  "INTRADAY_REVIEW": "上午盘沪指在3980-4010区间...",
  "MACRO_BACKGROUND": "产业层面...",
  "NORTH_BOUND_NARRATIVE": "北向资金延续净流入...",
  "CONCEPT_NARRATIVE": "半导体产业链全面爆发...",
  "TECHNICAL_ANALYSIS": "上证指数放量收复4000点...",
  "KEY_STOCKS_TABLE": "<tr><td>...</td></tr>",
  "DRAGON_TIGER": "今日龙虎榜数据显示...",
  "MARGIN_TRADING": "两融余额整体维持高位...",
  "ANNOUNCEMENTS": "1. 比亚迪入局人形机器人...",
  "WATCHLIST": "1. 沪指4000点能否站稳...",
  "SCENARIO_PLANS": "<div class=\"scenario\">...",
  "RISK_WARNINGS": "<div class=\"risk-box\">...",
  "CONCLUSION": "6月9日A股走出强势反弹..."
}
```

### 阶段 5：生成报告

```bash
# 基础：生成 HTML + PDF，并自动推送到飞书
$PYTHON {{SKILL_DIR}}/scripts/generate_report.py \
  --data /tmp/market_data.json \
  --ai-texts /tmp/ai_texts.json \
  --html /tmp/market_report_TRADE_DATE.html \
  --pdf /tmp/A-Share_Closing_TRADE_DATE.pdf \
  --feishu-push

# 仅 PDF（HTML 中间产物自动清理）
$PYTHON {{SKILL_DIR}}/scripts/generate_report.py \
  --data /tmp/market_data.json \
  --ai-texts /tmp/ai_texts.json \
  --pdf /tmp/A-Share_Closing_TRADE_DATE.pdf

# 仅 HTML
$PYTHON {{SKILL_DIR}}/scripts/generate_report.py \
  --data /tmp/market_data.json \
  --ai-texts /tmp/ai_texts.json \
  --html /tmp/market_report_TRADE_DATE.html
```

**参数说明：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `--data` | ✅ | market_data.json 路径 |
| `--ai-texts` | ✅ | AI 文本 JSON 路径 |
| `--html` | 条件 | 输出 HTML 路径；与 --pdf 至少给一个 |
| `--pdf` | 条件 | 输出 PDF 路径；与 --html 至少给一个 |
| `--feishu-push` | 否 | 生成后自动推送摘要 + HTML 文件到飞书私聊 |

> `--feishu-push` 依赖 lark-cli 已认证。推送目标通过环境变量 `FEISHU_USER_OPEN_ID` 配置。如未配置环境变量，可在脚本顶部 `FEISHU_USER_OPEN_ID` 常量设置默认值。

仅给 `--pdf` 时，HTML 自动生成到临时文件并在 PDF 完成后清理。PDF 需要 WeasyPrint 或 Chrome 可用；失败时会保留 HTML 并提示。

### 阶段 6：飞书投递

如果阶段 5 未使用 `--feishu-push`，但仍需手动推送到飞书：

```bash
$PYTHON {{SKILL_DIR}}/scripts/send_feishu.py \
  --pdf /tmp/A-Share_Closing_TRADE_DATE.pdf \
  --chat-id CHAT_ID \
  --title "A股收盘日报 · TRADE_DATE" \
  --summary "核心摘要前100字..."
```

推荐使用 `--feishu-push`（阶段 5）一键完成生成+推送，省去手动步骤。

### 阶段 7：输出

- 将 HTML 和 PDF 从 `/tmp/` 复制到 workspace 根目录
- 使用 `deliver_attachments` 交付 PDF 和 HTML 文件
- 使用 `preview_url` 预览 HTML 报告
- 简要总结今日市场核心要点（3-5 条）

---

## 数据源清单

| 数据模块 | AkShare 接口 | WebSearch 备选关键词 |
|----------|-------------|---------------------|
| 指数行情 | stock_zh_index_daily | 收盘指数 涨跌幅 |
| 涨跌家数 | stock_zh_a_spot_em | 涨跌家数 |
| 申万行业涨跌 | stock_board_industry_name_em | 行业板块 涨跌幅 |
| 概念板块 | stock_board_concept_name_em | 概念板块 涨幅榜 |
| 北向资金 | stock_hsgt_north_net_flow_in_em | 北向资金 净流入 |
| 龙虎榜 | stock_lhb_detail_em | 龙虎榜 机构 |
| 两融余额 | stock_margin_underlying_info_sz_sh | 两融余额 融资融券 |
| 涨停池 | stock_zt_pool_em | 涨停板 涨停家数 |
| 公告/新闻 | 无（始终用 WebSearch） | 重大公告 利好利空 |
| 宏观/政策 | 无（始终用 WebSearch） | 央行 逆回购 宏观政策 |

---

## 数字格式化规范

- 涨跌幅：保留 2 位小数，正数加 +（如 +1.33%、-0.74%）
- 成交额：超 1 万亿用 X.XX 万亿，否则用 X.XX 亿
- 主力资金：统一用亿，保留 1-2 位小数

## 颜色语义（中国股市惯例）

- 涨（正数）→ 红色 #e8403c
- 跌（负数）→ 绿色 #22b86b
- 平（0）→ 灰色

---

## 常见陷阱

| 陷阱 | 现象 | 解决 |
|------|------|------|
| **Python 3.13 numpy 签名冲突** | `ImportError: numpy C-extensions failed` | 切回系统 Python 3.9 venv |
| **AkShare 120s 超时** | main.py 返回退出码 2 | 直接走 WebSearch 回退，不要重试 |
| **ai_texts.json 解析失败** | `Expecting ',' delimiter` 在第 6 行附近 | 文本中误用了 ASCII `"`，替换为 `「」` |
| **market_data 字段不匹配** | 报告卡片空白 | WebSearch 回退时必须用 `indices[] + sectors[] + market_breadth{}` 结构 |
| **weasyprint 系统依赖缺失** | PDF 生成失败 | Chrome headless 自动回退，或仅使用 HTML |

---

## 注意事项

- `{{SKILL_DIR}}` 由 Skill 运行时自动展开为绝对路径
- AkShare 接口字段可能随版本变化，报 KeyError 时打印 df.columns 查看实际列名
- 报告免责声明：仅供参考，不构成投资建议
- 如果全部 PDF 后端不可用，保存 HTML 并提示用户手动打印
- 每天收盘后 ~15:30 是理想触发时间，18:00 后数据最全
