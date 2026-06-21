import pytest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

@pytest.fixture
def sample_market_data():
    """示例市场数据"""
    return {
        "a_indices": [
            {"name": "上证指数", "close": 3150.0, "pct": 1.5, "source": "akshare"},
            {"name": "深证成指", "close": 9500.0, "pct": 2.1, "source": "akshare"},
        ],
        "market_breadth": {
            "up_count": 2800,
            "down_count": 2100,
            "limit_up": 45,
            "limit_down": 12,
        }
    }

@pytest.fixture
def sample_stock_data():
    """示例选股数据"""
    return {
        "name": "测试股票",
        "code": "000001",
        "fund_scores": {
            "业务纯正度": 10,
            "行业地位": 7,
            "涨价受益度": 3,
            "业绩验证": 10,
            "催化剂临近": 7,
            "估值位置": 10,
            "特殊标签加分": 5,
        },
        "tech_scores": {
            "MACD": 8,
            "KDJ": 7,
            "成交量趋势": 6,
            "均线系统": 5,
            "支撑压力位": 4,
        },
        "logic": "测试选股逻辑",
    }

@pytest.fixture
def sample_index_data():
    """示例指数数据"""
    return {
        "name": "上证指数",
        "code": "000001",
        "close": 3150.32,
        "pct": 1.25,
        "change": 38.95,
        "high": 3160.0,
        "low": 3110.0,
        "open": 3120.0,
        "prev_close": 3111.37,
        "amplitude": 1.59,
        "source": "akshare"
    }
