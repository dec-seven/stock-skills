# 股市早报可视化前端

基于 Vue 3 + Vite + TailwindCSS 的股市早报可视化平台。

## 技术栈

- **框架**: Vue 3 + TypeScript
- **构建工具**: Vite
- **样式**: TailwindCSS
- **路由**: Vue Router 4
- **图表**: ECharts
- **HTTP**: Axios
- **日期**: Day.js

## 项目结构

```
frontend/
├── src/
│   ├── api/              # API 接口
│   ├── components/       # 公共组件
│   ├── router/           # 路由配置
│   ├── types/            # TypeScript 类型定义
│   ├── utils/            # 工具函数
│   ├── views/            # 页面视图
│   ├── App.vue           # 根组件
│   ├── main.ts           # 入口文件
│   └── style.css         # 全局样式
├── tailwind.config.js    # Tailwind 配置
├── postcss.config.js     # PostCSS 配置
└── package.json
```

## 快速开始

```bash
# 安装依赖
npm install

# 开发模式
npm run dev

# 构建
npm run build
```

## 功能模块

### 1. 首页 (`/`)
- 平台介绍
- 核心数据展示
- 功能导航

### 2. 早报浏览 (`/brief/:date?`)
- 日历选择日期
- 市场定调卡片
- 核心指数看板
- 板块动向对比
- 精选标的列表

### 3. 选股跟踪 (`/tracker`)
- 胜率统计卡片
- 累计收益曲线（ECharts）
- 标的跟踪表格

### 4. 预测复盘 (`/review`)
- 方向/区间/选股准确率饼图
- 历史验证记录

## 数据接口

前端默认从 `/data/` 目录加载 JSON 数据：

```
/data/
├── brief/
│   └── YYYY-MM-DD.json   # 早报数据
├── tracker/
│   └── stocks.json       # 跟踪数据
├── stats/
│   └── accuracy.json     # 准确率统计
└── dates.json            # 可用日期列表
```

## 主题色

深蓝商务风，延续现有 HTML 报告风格：

- 主色: `#0a1628` (深蓝)
- 卡片: `#0f2044`
- 强调: `#4fc3f7` (蓝) / `#f0c14b` (金)
- A股特色: 红涨绿跌
