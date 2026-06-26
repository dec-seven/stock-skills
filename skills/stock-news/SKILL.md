---
name: stock-news
description: |
  新浪财经7x24小时新闻抓取与实时推送。
  核心功能：定时抓取新浪财经重要事件，通过SSE实时推送到前端。
  触发词：新闻抓取、实时新闻、7x24、财经新闻、新闻推送
---

# 股市新闻实时推送 Skill

## 概述

从新浪财经抓取7x24小时重要事件，通过 SSE 实时推送到前端。

**架构：**
```
新浪财经API → 定时抓取(30s) → 去重 → SQLite → SSE推送 → 前端EventSource
```

## 快速开始

### 1. 启动 SSE 服务器

```bash
cd /Users/DecSeven/workspace/agent/stock-skills/skills/stock-news
python3 scripts/sse_server.py
```

服务器启动后：
- SSE 端点：`http://localhost:8765/events`
- 新闻列表 API：`http://localhost:8765/api/news`

### 2. 前端集成

```javascript
// 连接 SSE
const eventSource = new EventSource('http://localhost:8765/events');

eventSource.onmessage = (event) => {
  const news = JSON.parse(event.data);
  console.log('新新闻:', news);
  // 渲染到页面
};

eventSource.onerror = (error) => {
  console.error('SSE 连接错误:', error);
  // 浏览器会自动重连
};
```

### 3. 测试抓取（单次）

```bash
python3 scripts/fetch_news.py --once
```

## 目录结构

```
stock-news/
├── SKILL.md              # 本文件
├── requirements.txt      # Python 依赖
├── scripts/
│   ├── fetch_news.py     # 新闻抓取脚本
│   ├── sse_server.py     # SSE 推送服务器
│   └── news_db.py        # 数据库操作
├── data/
│   └── news.db           # SQLite 数据库（自动创建）
└── templates/
    └── news_item.html    # 新闻项模板
```

## API 说明

### SSE 端点

**GET /events**

返回 Server-Sent Events 流，每次有新新闻时推送：

```
data: {"id": 123, "title": "...", "content": "...", "time": "10:30", "source": "sina"}

```

### REST API

**GET /api/news?limit=50**

获取最近新闻列表：

```json
[
  {
    "id": 123,
    "title": "央行宣布降准",
    "content": "中国人民银行决定...",
    "time": "10:30",
    "source": "sina",
    "created_at": "2024-01-15T10:30:00"
  }
]
```

## 配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| NEWS_FETCH_INTERVAL | 30 | 抓取间隔（秒） |
| NEWS_DB_PATH | ./data/news.db | 数据库路径 |
| SSE_PORT | 8765 | SSE 服务端口 |

## 注意事项

1. 新浪财经 API 可能随时变更，需定期检查
2. 建议抓取间隔 ≥ 30秒，避免被封
3. SQLite 适合单机部署，分布式场景换 PostgreSQL
