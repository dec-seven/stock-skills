# Agent-Skills

A股智能分析专家团，基于每天喂养的素材+策略，提取分析框架，反哺知识库，增强方法论；基于迭代优化的方法论生成每日早报

## Skills 一览

| Skill | 说明 | 触发词 |
|-------|------|--------|
| **stock-morning-brief** | 每日盘前早报：数据获取 → LLM 分析 → HTML 报告 → Cloudflare 部署 → 飞书推送 | 早评、股市早评、每日早报、morning brief |
| **stock-daily-report** | A股收盘日报：18 模块 HTML/PDF 报告 | 收盘报告、A股复盘、今日复盘、daily report |
| **stock-methodology-updater** | 方法论更新器：从样例中提取分析框架，反哺知识库 | 更新方法论、学习方法论、新样例 |

## 项目结构

```
STOCK-SKILLS/
├── config/                          # 配置文件
│   ├── base.yaml                    #   基础配置
│   ├── development.yaml             #   开发环境配置
│   └── production.yaml              #   生产环境配置
├── knowledge-bases/                 # 方法论知识库
│   ├── stock-methodology/           #   早报/选股方法论（核心）
│   └── stock-samples/               #   样例数据（gitignore）
├── shared/                          # 共享代码模块
│   ├── cache.py                     #   SQLite 数据缓存
│   ├── config_loader.py             #   配置加载器
│   ├── data_fetcher.py              #   数据获取器（AKShare / yfinance）
│   ├── history_data.py              #   历史数据管理
│   ├── logger.py                    #   结构化日志系统
│   ├── scoring_backtest.py          #   评分回测模块
│   ├── technical_indicators.py      #   技术指标计算
│   └── utils.py                     #   工具函数（飞书推送等）
├── tests/                           # 单元测试
│   ├── conftest.py                  #   pytest 配置
│   ├── test_data_fetcher.py         #   数据获取测试
│   ├── test_scoring.py              #   评分系统测试
│   └── test_utils.py                #   工具函数测试
├── logs/                            # 日志文件
└── skills/                          # 技能模块
    ├── stock-morning-brief/         #   盘前早报
    │   ├── SKILL.md                 #     技能定义
    │   ├── scripts/                 #     Python 脚本
    │   ├── templates/               #     HTML 模板
    │   ├── references/              #     风格指南 & 样例
    │   └── docs/                    #     部署指南
    ├── stock-daily-report/          #   收盘日报
    └── stock-methodology-updater/   #   方法论更新器
```

## 快速开始

### 环境要求

- Python 3.9+
- Node.js 22+（Cloudflare 部署需要）
- [WorkBuddy](https://www.codebuddy.cn) 桌面端


### 配置系统

项目使用 YAML 配置文件 + 环境变量覆盖的方式管理配置：

```
config/
├── base.yaml          # 基础配置（所有环境共享）
├── development.yaml   # 开发环境配置
└── production.yaml    # 生产环境配置
```

通过环境变量 `STOCK_SKILLS_ENV` 切换环境（默认 `development`）：

```bash
# 开发环境
export STOCK_SKILLS_ENV=development

# 生产环境
export STOCK_SKILLS_ENV=production
```

关键环境变量：

| 变量 | 说明 |
|------|------|
| `STOCK_SKILLS_ENV` | 运行环境（development/production） |
| `STOCK_SKILLS_LOG_LEVEL` | 日志级别 |
| `FEISHU_USER_OPEN_ID` | 飞书用户 ID（推送用） |

### 测试框架

项目使用 pytest 进行单元测试：

```bash
# 运行所有测试
python3 -m pytest tests/ -v

# 运行单个测试文件
python3 -m pytest tests/test_scoring.py -v
```

测试覆盖：
- `test_data_fetcher.py` - 数据获取模块测试
- `test_scoring.py` - 评分系统测试
- `test_utils.py` - 工具函数测试

### 安装依赖

```bash
# 早报 Skill
pip install -r skills/stock-morning-brief/requirements.txt

# 收盘日报 Skill
pip install -r skills/stock-daily-report/requirements.txt
```

### 环境变量

```bash
# 飞书推送（可选）
export FEISHU_USER_OPEN_ID=your_feishu_user_open_id_here
```

也可参考 `skills/stock-daily-report/.env.example`。

### 生成早报

```bash
# 仅生成 HTML
python3 skills/stock-morning-brief/scripts/generate_report.py

# 生成 + 部署 Cloudflare + 飞书推送
python3 skills/stock-morning-brief/scripts/generate_report.py \
  --deploy-cloudflare --feishu-push
```

### 生成收盘日报

```bash
python3 skills/stock-daily-report/scripts/main.py
```

## 核心架构

### 数据源优先级

国内数据：AKShare > WebSearch | 海外数据：yfinance > WebSearch

所有数据经 `validate_market_data.py` 校验后才进入报告，WebSearch 补充的数据标记 `source: "websearch"` 并需交叉验证。

### 早报工作流

```
fetch_data.py          获取市场数据（A股/美股/大宗/汇率）
        ↓
generate_ai_texts.py   LLM 分析 → 结构化 JSON（22 个字段）
        ↓
generate_report.py     填充 HTML 模板 + 可选 PDF
        ↓
deploy_to_cloudflare   自动部署到 Cloudflare Pages
        ↓
push_to_feishu         飞书私聊推送摘要 + 链接
```

### 选股评分体系

三层映射法（70 分）+ 技术面（30 分）= 总分 100 分

| 维度 | 项目 | 分值 |
|------|------|------|
| 映射法 | 业务纯正度 / 行业地位 / 涨价受益度 / 业绩验证 / 催化剂临近 / 估值位置 / 特殊标签 | 各 10 |
| 技术面 | MACD(8) / KDJ(7) / 成交量(6) / 均线(5) / 支撑压力(4) | 合计 30 |

评级：≥85 强烈推荐⭐5 / 75-84 推荐⭐4 / 60-74 一般观察⭐3 / <60 不建议⭐2

### 入选股票跟踪

每只入选标的自动跟踪次日 / 3 日 / 5 日 / 7 日累计涨跌幅，数据存储在 `data/stock_selection_tracker.json`，可视化页面部署到 Cloudflare `/stock-tracker/`。

## 报告示例

- 早报在线预览：`https://<your-project>.pages.dev/`
- 根路径访问最新报告，日期路径 `/YYYY-MM-DD/` 访问历史报告
- 股票跟踪页面：`/stock-tracker/`

> 详见 [Cloudflare 部署指南](skills/stock-morning-brief/docs/CLOUDFLARE_DEPLOY_GUIDE.md)

## 方法论体系

知识库位于 `knowledge-bases/stock-methodology/`，包含：

| 文件 | 说明 |
|------|------|
| `stock_morning_brief_guide.md` | 早报分析方法论（核心框架） |
| `stock_morning_brief_templates.md` | 早报模板与样例表述 |
| `stock_selection_guide.md` | 选股方法论 |

方法论更新通过 `stock-methodology-updater` Skill 进行，遵循"提取方法、不搬运事实"原则。

## 注意事项

- 本项目仅供学习研究，**不构成任何投资建议**
- 股市有风险，投资需谨慎
- 报告中的选股仅为分析方法演示，不作为买卖依据

## License

MIT
