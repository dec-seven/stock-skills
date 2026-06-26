"""
FastAPI 后端服务 - 提供实时股票数据 API
支持本地开发，后续可部署到云服务器
"""
import sys
import os
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# 导入数据获取模块
from shared.data_fetcher import (
    get_a_indices,
    get_market_breadth,
    get_sectors,
    get_north_bound,
    get_turnover,
    get_us_data,
    is_trade_date,
    check_availability,
)

app = FastAPI(
    title="Stock Skills API",
    description="A股实时数据服务",
    version="1.0.0"
)

# 配置跨域（允许 Cloudflare Pages 访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # 本地开发
        "http://localhost:4173",  # 本地预览
        "https://your-site.pages.dev",  # 替换成你的 Cloudflare Pages 域名
        "*"  # 开发阶段允许所有，生产环境建议限制
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== 响应模型 =====

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    data_sources: Dict[str, bool]

class IndexData(BaseModel):
    code: str
    name: str
    close: float
    pct: float
    change: float
    high: float
    low: float
    open: float
    prev_close: float
    amplitude: float
    source: str

class SectorData(BaseModel):
    name: str
    pct: float
    amount: Optional[float] = None
    change: Optional[float] = None
    leader: Optional[str] = None
    source: str

class HeatmapData(BaseModel):
    name: str
    value: float      # 市值/成交额（控制面积）
    change: float     # 涨跌幅（控制颜色）
    leader: str
    netInflow: float  # 资金净流入


# ===== API 路由 =====

@app.get("/", tags=["root"])
async def root():
    """API 根路径"""
    return {
        "message": "Stock Skills API",
        "docs": "/docs",
        "version": "1.0.0"
    }


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check():
    """健康检查 - 检查数据源可用性"""
    availability = check_availability()
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        data_sources=availability
    )


@app.get("/api/indices", response_model=List[IndexData], tags=["market"])
async def get_indices():
    """获取 A 股主要指数数据"""
    try:
        data = get_a_indices()
        if data is None:
            raise HTTPException(status_code=503, detail="数据源不可用")
        return [IndexData(**item) for item in data if "error" not in item]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/market-breadth", tags=["market"])
async def get_market_breadth():
    """获取市场宽度数据（涨跌家数）"""
    try:
        data = get_market_breadth()
        if data is None:
            raise HTTPException(status_code=503, detail="数据源不可用")
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sectors", response_model=List[SectorData], tags=["market"])
async def get_sectors_list():
    """获取板块涨跌幅数据"""
    try:
        data = get_sectors()
        if data is None:
            raise HTTPException(status_code=503, detail="数据源不可用")
        return [SectorData(**item) for item in data if "error" not in item]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/heatmap", response_model=List[HeatmapData], tags=["market"])
async def get_heatmap():
    """
    获取板块热力图数据（ECharts Treemap 格式）
    
    返回字段：
    - name: 板块名称
    - value: 市值/成交额（控制方块面积）
    - change: 涨跌幅（控制颜色，红涨绿跌）
    - leader: 领涨股
    - netInflow: 资金净流入（亿）
    """
    try:
        sectors = get_sectors()
        if sectors is None:
            raise HTTPException(status_code=503, detail="数据源不可用")
        
        # 转换为热力图格式
        heatmap_data = []
        for s in sectors:
            if "error" in s:
                continue
            
            # 计算市值/成交额（作为面积权重）
            # 这里用成交额作为示例，实际可用市值
            amount = s.get("amount", 1000) or 1000
            value = amount / 100  # 缩放比例
            
            heatmap_data.append(HeatmapData(
                name=s.get("name", ""),
                value=round(value, 2),
                change=s.get("pct", 0) or 0,
                leader=s.get("leader", "-"),
                netInflow=s.get("netInflow", 0) or 0
            ))
        
        return heatmap_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/north-bound", tags=["capital"])
async def get_north_bound_flow():
    """获取北向资金流向"""
    try:
        data = get_north_bound()
        if data is None:
            raise HTTPException(status_code=503, detail="数据源不可用")
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/turnover", tags=["market"])
async def get_turnover_data():
    """获取成交量数据"""
    try:
        data = get_turnover()
        if data is None:
            raise HTTPException(status_code=503, detail="数据源不可用")
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/us-data", tags=["global"])
async def get_us_market():
    """获取美股及全球市场数据"""
    try:
        data = get_us_data()
        if data is None:
            raise HTTPException(status_code=503, detail="数据源不可用")
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trade-date", tags=["system"])
async def check_trade_date(date: Optional[str] = None):
    """检查是否为交易日"""
    try:
        is_trade = is_trade_date(date)
        return {
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "is_trade_date": is_trade
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== 早报相关接口 =====

@app.get("/api/brief/{date}", tags=["brief"])
async def get_morning_brief(date: str):
    """获取指定日期的早报数据"""
    # TODO: 从数据库或文件读取
    brief_path = Path(__file__).parent.parent / "frontend" / "public" / "data" / "brief" / f"{date}.json"
    
    if brief_path.exists():
        import json
        with open(brief_path, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        raise HTTPException(status_code=404, detail=f"未找到 {date} 的早报数据")


@app.get("/api/brief-dates", tags=["brief"])
async def get_available_brief_dates():
    """获取可用的早报日期列表"""
    dates_path = Path(__file__).parent.parent / "frontend" / "public" / "data" / "dates.json"
    
    if dates_path.exists():
        import json
        with open(dates_path, "r", encoding="utf-8") as f:
            return {"dates": json.load(f)}
    else:
        return {"dates": []}


# ===== 选股跟踪相关接口 =====

@app.get("/api/tracker/stocks", tags=["tracker"])
async def get_tracker_stocks():
    """获取选股跟踪列表"""
    stocks_path = Path(__file__).parent.parent / "frontend" / "public" / "data" / "tracker" / "stocks.json"
    
    if stocks_path.exists():
        import json
        with open(stocks_path, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return []


# ===== 启动说明 =====

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*50)
    print("🚀 Stock Skills API 服务启动")
    print("="*50)
    print("📍 本地地址: http://localhost:8000")
    print("📖 API 文档: http://localhost:8000/docs")
    print("🔧 数据源状态:")
    availability = check_availability()
    for source, available in availability.items():
        status = "✅" if available else "❌"
        print(f"   {status} {source}")
    print("="*50 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
