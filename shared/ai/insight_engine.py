#!/usr/bin/env python3
"""
市场洞察推导引擎

从市场数据自动推导规则字段,包括方向信号、情绪分类、区间估算等。
所有 derive_* 函数实现规则逻辑,不依赖 LLM,可独立运行。

函数列表:
- derive_direction_signal(): 从指数涨跌推导方向信号类
- derive_direction_judgment(): 从指数涨跌推导方向判断文字
- derive_sentiment_class(): 推导市场情绪色彩类
- derive_sentiment_label(): 情绪类名转中文标签
- derive_sh_range(): 从上证指数推导区间
"""

import sys
from typing import Dict, List, Tuple

# 导入日志
sys.path.insert(0, str(__file__).replace('/shared/ai/insight_engine.py', ''))
from shared.logger import get_logger

logger = get_logger('insight_engine')


def derive_direction_signal(indices: List[Dict]) -> str:
    """
    从指数涨跌推导方向信号类
    
    基于主要指数的平均涨跌幅推导市场方向信号分类:
    - bullish: 看涨(平均涨幅 > 1.0%)
    - neutral-bull: 中性偏多(平均涨幅 0~1.0%)
    - neutral-bear: 中性偏空(平均涨幅 -1.0%~0)
    - bearish: 看跌(平均涨幅 < -1.0%)
    
    Args:
        indices: 指数数据列表,每个元素包含 name, close, pct 等字段
    
    Returns:
        str: 方向信号类名
    
    Example:
        >>> indices = [
        ...     {"name": "上证指数", "pct": 1.5},
        ...     {"name": "深证成指", "pct": 1.2}
        ... ]
        >>> derive_direction_signal(indices)
        'bullish'
    """
    # 过滤掉需要网络搜索的指数
    pcts = [idx.get("pct", 0) for idx in indices if "pct" in idx and not idx.get("need_websearch")]
    
    if not pcts:
        logger.warning("无有效指数数据,返回默认方向信号", default="neutral")
        return "neutral"
    
    avg_pct = sum(pcts) / len(pcts)
    
    if avg_pct > 1.0:
        signal = "bullish"
    elif avg_pct > 0:
        signal = "neutral-bull"
    elif avg_pct > -1.0:
        signal = "neutral-bear"
    else:
        signal = "bearish"
    
    logger.info(
        "方向信号推导完成",
        avg_pct=round(avg_pct, 2),
        signal=signal,
        index_count=len(pcts)
    )
    
    return signal


def derive_direction_judgment(indices: List[Dict]) -> str:
    """
    从指数涨跌推导方向判断文字
    
    基于主要指数的平均涨跌幅和离散度(极差)推导更细致的方向判断:
    - 看涨: 平均涨幅 > 1.5%
    - 震荡偏多: 平均涨幅 0.5%~1.5%
    - 温和偏多: 平均涨幅 0~0.5%
    - 温和偏空: 平均涨幅 -0.5%~0
    - 震荡偏空: 平均涨幅 -1.5%~-0.5%
    - 看跌: 平均涨幅 < -1.5%
    
    Args:
        indices: 指数数据列表
    
    Returns:
        str: 方向判断文字
    
    Example:
        >>> indices = [{"name": "上证指数", "pct": 1.8}]
        >>> derive_direction_judgment(indices)
        '看涨'
    """
    pcts = [idx.get("pct", 0) for idx in indices if "pct" in idx and not idx.get("need_websearch")]
    
    if not pcts:
        return "震荡"
    
    avg_pct = sum(pcts) / len(pcts)
    max_pct = max(pcts)
    min_pct = min(pcts)
    spread = max_pct - min_pct
    
    if avg_pct > 1.5:
        judgment = "看涨"
    elif avg_pct > 0.5:
        judgment = "震荡偏多"
    elif avg_pct > 0:
        judgment = "温和偏多"
    elif avg_pct > -0.5:
        judgment = "温和偏空"
    elif avg_pct > -1.5:
        judgment = "震荡偏空"
    else:
        judgment = "看跌"
    
    logger.info(
        "方向判断推导完成",
        avg_pct=round(avg_pct, 2),
        spread=round(spread, 2),
        judgment=judgment
    )
    
    return judgment


def derive_sentiment_class(data: Dict) -> str:
    """
    推导市场情绪色彩类
    
    基于市场广度(涨跌比)、涨停数量、指数平均涨幅综合判断市场情绪:
    - sentiment-hot: 情绪高涨·狂热期(大涨+涨停潮,avg_pct>2.0且limit_up>150)
    - sentiment-warm: 情绪温和·乐观期(温和上涨,avg_pct>0.3且up_ratio>0.55)
    - sentiment-cold: 情绪寒冷·恐慌期(下跌调整,avg_pct<-0.5或up_ratio<0.4)
    - sentiment-frozen: 情绪极寒·冰点期(暴跌,avg_pct<-2.0且up_ratio<0.2)
    
    Args:
        data: 完整的市场数据字典,包含 yesterday.market_breadth 和 yesterday.indices
    
    Returns:
        str: 情绪色彩类名
    
    Example:
        >>> data = {
        ...     "yesterday": {
        ...         "market_breadth": {"up_count": 3000, "down_count": 1500, "limit_up": 200},
        ...         "indices": [{"name": "上证指数", "pct": 2.5}]
        ...     }
        ... }
        >>> derive_sentiment_class(data)
        'sentiment-hot'
    """
    breadth = data.get("yesterday", {}).get("market_breadth", {})
    indices = data.get("yesterday", {}).get("indices", [])
    
    up_count = breadth.get("up_count") or 0
    down_count = breadth.get("down_count") or 0
    limit_up = breadth.get("limit_up") or 0
    
    total = up_count + down_count
    if total == 0:
        logger.warning("市场广度数据缺失,返回默认情绪", default="sentiment-warm")
        return "sentiment-warm"
    
    up_ratio = up_count / total
    pcts = [idx.get("pct", 0) for idx in indices if "pct" in idx and not idx.get("need_websearch")]
    avg_pct = sum(pcts) / len(pcts) if pcts else 0
    
    # 高涨:大涨或涨停潮
    if (avg_pct > 1.5 and limit_up > 100) or limit_up > 150:
        sentiment = "sentiment-hot"
    # 温和:温和上涨或涨多跌少
    elif (avg_pct > 0.3 and up_ratio > 0.55) or (avg_pct > 0.5 and limit_up > 50):
        sentiment = "sentiment-warm"
    # 寒冷:下跌调整或跌多涨少
    elif avg_pct < -0.5 or (up_ratio < 0.3 and limit_up < 50):
        sentiment = "sentiment-cold"
    # 极寒:暴跌
    elif avg_pct < -2.0 and up_ratio < 0.2:
        sentiment = "sentiment-frozen"
    else:
        sentiment = "sentiment-warm"
    
    logger.info(
        "市场情绪推导完成",
        avg_pct=round(avg_pct, 2),
        up_ratio=round(up_ratio, 2),
        limit_up=limit_up,
        sentiment=sentiment
    )
    
    return sentiment


def derive_sentiment_label(sentiment_class: str) -> str:
    """
    情绪类名转中文标签
    
    将情绪色彩类名映射为带emoji的中文标签,用于 HTML 渲染。
    
    Args:
        sentiment_class: 情绪色彩类名(sentiment-hot/warm/cold/frozen)
    
    Returns:
        str: 带emoji的中文标签
    
    Example:
        >>> derive_sentiment_label("sentiment-hot")
        '🔴 情绪高涨 · 狂热期'
    """
    mapping = {
        "sentiment-hot": "🔴 情绪高涨 · 狂热期",
        "sentiment-warm": "🟡 情绪温和 · 乐观期",
        "sentiment-cold": "🟢 情绪寒冷 · 恐慌期",
        "sentiment-frozen": "🔵 情绪极寒 · 冰点期",
    }
    label = mapping.get(sentiment_class, "🟡 情绪温和")
    return label


def derive_sh_range(indices: List[Dict]) -> Tuple[str, str]:
    """
    从上证指数推导区间
    
    基于上证指数的昨日高低点,推导今日可能的运行区间。
    区间 = [昨日低点 - 0.5*振幅, 昨日高点 + 0.5*振幅],取整到10。
    
    Args:
        indices: 指数数据列表
    
    Returns:
        Tuple[str, str]: (区间下限, 区间上限)
    
    Example:
        >>> indices = [{"name": "上证指数", "close": 4000, "high": 4050, "low": 3950}]
        >>> derive_sh_range(indices)
        ('3920', '4080')
    """
    for idx in indices:
        if idx.get("name") == "上证指数" and not idx.get("need_websearch"):
            close = idx.get("close", 3000)
            high = idx.get("high", close * 1.01)
            low = idx.get("low", close * 0.99)
            
            # 区间 = 昨日低点 ~ 昨日高点扩展
            range_low = int(low - (high - low) * 0.5)
            range_high = int(high + (high - low) * 0.5)
            
            # 取整到10
            range_low = range_low // 10 * 10
            range_high = range_high // 10 * 10
            
            logger.info(
                "上证区间推导完成",
                close=close,
                high=high,
                low=low,
                range_low=range_low,
                range_high=range_high
            )
            
            return str(range_low), str(range_high)
    
    # 未找到上证指数,返回默认区间
    logger.warning("未找到上证指数数据,返回默认区间", default_range="3900-4100")
    return "3900", "4100"
