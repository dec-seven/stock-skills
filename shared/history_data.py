#!/usr/bin/env python3
"""
数据历史回溯模块

功能：
1. 获取历史市场数据
2. 计算趋势和动量
3. 支持多日回溯分析
"""
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from shared.logger import get_logger
from shared.cache import get_cache

logger = get_logger('history-data')
cache = get_cache()


class HistoryDataManager:
    """历史数据管理器"""
    
    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir or os.path.join(
            os.path.dirname(__file__), '..',
            'skills/stock-morning-brief/data'
        )
    
    def get_historical_indices(self, days: int = 5) -> Dict:
        """
        获取历史指数数据
        
        Args:
            days: 回溯天数
        
        Returns:
            按日期组织的历史数据
        """
        result = {}
        
        # 尝试从缓存获取
        cache_key = f'history_indices_{days}d'
        cached = cache.get('history', {'key': cache_key})
        if cached:
            logger.debug("从缓存获取历史指数数据", days=days)
            return cached
        
        # 从已有数据文件获取
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            daily_data = self._load_daily_data(date)
            if daily_data:
                result[date] = daily_data
        
        # 缓存结果
        if result:
            cache.set('history', result, {'key': cache_key}, ttl=1800)
        
        logger.info("获取历史数据完成", days=len(result))
        return result
    
    def _load_daily_data(self, date: str) -> Optional[Dict]:
        """加载指定日期的数据"""
        # 尝试从多个可能的位置加载
        possible_paths = [
            os.path.join(self.data_dir, 'closing_data', f'{date}.json'),
            os.path.join(self.data_dir, 'predictions', f'{date}.json'),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"加载日期数据失败: {date}", error=str(e))
        
        return None
    
    def calculate_trend(self, index_name: str, days: int = 5) -> Dict:
        """
        计算指定指数的趋势
        
        Args:
            index_name: 指数名称
            days: 回溯天数
        
        Returns:
            趋势分析结果
        """
        history = self.get_historical_indices(days)
        
        values = []
        for date, data in sorted(history.items()):
            # 从数据中提取指数值
            if 'a_indices' in data:
                for idx in data['a_indices']:
                    if idx.get('name') == index_name and 'close' in idx:
                        values.append({
                            'date': date,
                            'close': idx['close'],
                            'pct': idx.get('pct', 0),
                        })
                        break
        
        if not values:
            return {"error": f"无 {index_name} 的历史数据"}
        
        # 计算趋势
        closes = [v['close'] for v in values]
        pcts = [v['pct'] for v in values]
        
        total_change = round((closes[-1] - closes[0]) / closes[0] * 100, 2)
        avg_change = round(sum(pcts) / len(pcts), 2)
        
        # 判断趋势方向
        if total_change > 2:
            trend = "强势上涨"
        elif total_change > 0:
            trend = "震荡上涨"
        elif total_change > -2:
            trend = "震荡下跌"
        else:
            trend = "持续下跌"
        
        # 计算波动率
        if len(pcts) > 1:
            volatility = round(sum(abs(p) for p in pcts) / len(pcts), 2)
        else:
            volatility = 0
        
        return {
            "index": index_name,
            "days": len(values),
            "total_change": total_change,
            "avg_daily_change": avg_change,
            "trend": trend,
            "volatility": volatility,
            "high": max(closes),
            "low": min(closes),
            "current": closes[-1],
            "data": values,
        }
    
    def get_market_momentum(self, days: int = 5) -> Dict:
        """
        计算市场整体动量
        
        Args:
            days: 回溯天数
        
        Returns:
            市场动量指标
        """
        history = self.get_historical_indices(days)
        
        if not history:
            return {"error": "无历史数据"}
        
        # 按日期统计涨跌
        daily_stats = []
        for date, data in sorted(history.items()):
            if 'market_breadth' in data:
                breadth = data['market_breadth']
                up = breadth.get('up_count', 0)
                down = breadth.get('down_count', 0)
                total = up + down
                if total > 0:
                    daily_stats.append({
                        'date': date,
                        'up_ratio': round(up / total * 100, 1),
                        'limit_up': breadth.get('limit_up', 0),
                        'limit_down': breadth.get('limit_down', 0),
                    })
        
        if not daily_stats:
            return {"error": "无市场宽度数据"}
        
        # 计算动量
        up_ratios = [d['up_ratio'] for d in daily_stats]
        avg_up_ratio = round(sum(up_ratios) / len(up_ratios), 1)
        
        # 动量方向
        if avg_up_ratio > 60:
            momentum = "多头强势"
        elif avg_up_ratio > 50:
            momentum = "偏多震荡"
        elif avg_up_ratio > 40:
            momentum = "偏空震荡"
        else:
            momentum = "空头主导"
        
        return {
            "days": len(daily_stats),
            "avg_up_ratio": avg_up_ratio,
            "momentum": momentum,
            "daily_stats": daily_stats,
        }
    
    def compare_periods(self, index_name: str, period1_days: int = 3, period2_days: int = 5) -> Dict:
        """
        比较两个周期的表现
        
        Args:
            index_name: 指数名称
            period1_days: 短周期天数
            period2_days: 长周期天数
        
        Returns:
            周期对比分析
        """
        trend1 = self.calculate_trend(index_name, period1_days)
        trend2 = self.calculate_trend(index_name, period2_days)
        
        if "error" in trend1 or "error" in trend2:
            return {"error": "数据不足"}
        
        # 比较动量变化
        short_avg = trend1['avg_daily_change']
        long_avg = trend2['avg_daily_change']
        
        if short_avg > long_avg + 0.5:
            acceleration = "加速上涨"
        elif short_avg > long_avg:
            acceleration = "温和上涨"
        elif short_avg < long_avg - 0.5:
            acceleration = "加速下跌"
        elif short_avg < long_avg:
            acceleration = "温和下跌"
        else:
            acceleration = "趋势平稳"
        
        return {
            "index": index_name,
            "short_period": {
                "days": period1_days,
                "change": trend1['total_change'],
                "avg_daily": short_avg,
            },
            "long_period": {
                "days": period2_days,
                "change": trend2['total_change'],
                "avg_daily": long_avg,
            },
            "acceleration": acceleration,
        }


def get_trend_context(index_name: str = "上证指数", days: int = 5) -> str:
    """
    获取趋势上下文描述（供 LLM 使用）
    
    Args:
        index_name: 指数名称
        days: 回溯天数
    
    Returns:
        自然语言的趋势描述
    """
    manager = HistoryDataManager()
    trend = manager.calculate_trend(index_name, days)
    
    if "error" in trend:
        return f"无{index_name}最近{days}天的历史数据"
    
    return (
        f"{index_name}近{trend['days']}个交易日{trend['trend']}，"
        f"累计涨跌幅{trend['total_change']:+.2f}%，"
        f"日均涨跌{trend['avg_daily_change']:+.2f}%，"
        f"波动率{trend['volatility']:.2f}%，"
        f"区间最高{trend['high']:.2f}，最低{trend['low']:.2f}。"
    )


if __name__ == "__main__":
    manager = HistoryDataManager()
    
    print("\n=== 历史数据分析 ===\n")
    
    # 获取上证指数趋势
    trend = manager.calculate_trend("上证指数", 5)
    if "error" not in trend:
        print(f"上证指数趋势: {trend['trend']}")
        print(f"累计涨跌: {trend['total_change']}%")
        print(f"日均涨跌: {trend['avg_daily_change']}%")
    
    # 获取市场动量
    momentum = manager.get_market_momentum(5)
    if "error" not in momentum:
        print(f"\n市场动量: {momentum['momentum']}")
        print(f"平均上涨比例: {momentum['avg_up_ratio']}%")
    
    # 趋势上下文
    print(f"\n趋势描述: {get_trend_context('上证指数', 5)}")
