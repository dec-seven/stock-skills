#!/usr/bin/env python3
"""
扩展技术指标计算模块

包含：RSI、BOLL、OBV、资金流向等指标
"""
import numpy as np
from typing import Dict, List, Tuple, Optional
from shared.logger import get_logger

logger = get_logger('technical-indicators')


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """
    计算 RSI 指标
    
    Args:
        prices: 收盘价序列（最新的在最后）
        period: 计算周期，默认 14
    
    Returns:
        RSI 值 (0-100)
    """
    if len(prices) < period + 1:
        return None
    
    prices = np.array(prices)
    deltas = np.diff(prices)
    
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return round(rsi, 2)


def calculate_boll(prices: List[float], period: int = 20, std_dev: float = 2.0) -> Dict:
    """
    计算布林带指标
    
    Args:
        prices: 收盘价序列
        period: 计算周期
        std_dev: 标准差倍数
    
    Returns:
        {"upper": 上轨, "middle": 中轨, "lower": 下轨, "width": 带宽}
    """
    if len(prices) < period:
        return None
    
    prices = np.array(prices[-period:])
    
    middle = np.mean(prices)
    std = np.std(prices)
    
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    width = (upper - lower) / middle * 100 if middle > 0 else 0
    
    return {
        "upper": round(upper, 2),
        "middle": round(middle, 2),
        "lower": round(lower, 2),
        "width": round(width, 2),
        "current": round(prices[-1], 2),
        "position": round((prices[-1] - lower) / (upper - lower) * 100, 1) if upper != lower else 50,
    }


def calculate_obv(prices: List[float], volumes: List[float]) -> Dict:
    """
    计算 OBV（能量潮）指标
    
    Args:
        prices: 收盘价序列
        volumes: 成交量序列
    
    Returns:
        {"obv": 当前OBV值, "trend": 趋势方向}
    """
    if len(prices) != len(volumes) or len(prices) < 2:
        return None
    
    obv = 0
    obv_series = [0]
    
    for i in range(1, len(prices)):
        if prices[i] > prices[i-1]:
            obv += volumes[i]
        elif prices[i] < prices[i-1]:
            obv -= volumes[i]
        obv_series.append(obv)
    
    # 判断趋势（最近 5 天）
    if len(obv_series) >= 5:
        recent = obv_series[-5:]
        trend = "up" if recent[-1] > recent[0] else "down"
        slope = (recent[-1] - recent[0]) / 5
    else:
        trend = "neutral"
        slope = 0
    
    return {
        "obv": obv,
        "trend": trend,
        "slope": round(slope, 0),
    }


def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
    """
    计算 MACD 指标
    
    Args:
        prices: 收盘价序列
        fast: 快线周期
        slow: 慢线周期
        signal: 信号线周期
    
    Returns:
        {"macd": MACD值, "signal": 信号线, "histogram": 柱状图}
    """
    if len(prices) < slow + signal:
        return None
    
    prices = np.array(prices)
    
    # EMA 计算
    def ema(data, period):
        alpha = 2 / (period + 1)
        ema_val = data[0]
        for price in data[1:]:
            ema_val = alpha * price + (1 - alpha) * ema_val
        return ema_val
    
    ema_fast = ema(prices, fast)
    ema_slow = ema(prices, slow)
    macd_line = ema_fast - ema_slow
    
    # 信号线（MACD 的 EMA）
    macd_series = []
    for i in range(len(prices) - slow):
        chunk = prices[i:i+slow+1]
        ema_f = ema(chunk, fast)
        ema_s = ema(chunk, slow)
        macd_series.append(ema_f - ema_s)
    
    signal_line = ema(np.array(macd_series), signal) if len(macd_series) >= signal else 0
    histogram = macd_line - signal_line
    
    # 判断信号
    if histogram > 0:
        signal_type = "多头" if macd_line > 0 else "弱势多头"
    else:
        signal_type = "空头" if macd_line < 0 else "弱势空头"
    
    return {
        "macd": round(macd_line, 3),
        "signal": round(signal_line, 3),
        "histogram": round(histogram, 3),
        "signal_type": signal_type,
    }


def calculate_kdj(high: List[float], low: List[float], close: List[float], 
                  n: int = 9, m1: int = 3, m2: int = 3) -> Dict:
    """
    计算 KDJ 指标
    
    Args:
        high: 最高价序列
        low: 最低价序列
        close: 收盘价序列
        n: RSV 周期
        m1: K 值平滑周期
        m2: D 值平滑周期
    
    Returns:
        {"k": K值, "d": D值, "j": J值, "signal": 信号}
    """
    if len(close) < n:
        return None
    
    # 计算 RSV
    high_n = max(high[-n:])
    low_n = min(low[-n:])
    
    if high_n == low_n:
        rsv = 50
    else:
        rsv = (close[-1] - low_n) / (high_n - low_n) * 100
    
    # 简化计算 K、D、J
    k = rsv  # 实际应该用前一天的 K 值做平滑
    d = k
    j = 3 * k - 2 * d
    
    # 判断信号
    if j > 85:
        signal = "超买"
    elif j < 20:
        signal = "超卖"
    elif k > d:
        signal = "金叉"
    elif k < d:
        signal = "死叉"
    else:
        signal = "中性"
    
    return {
        "k": round(k, 2),
        "d": round(d, 2),
        "j": round(j, 2),
        "signal": signal,
    }


def calculate_moving_averages(prices: List[float]) -> Dict:
    """
    计算均线系统
    
    Args:
        prices: 收盘价序列
    
    Returns:
        {"ma5": 5日均线, "ma10": 10日均线, "ma20": 20日均线, "trend": 趋势}
    """
    if len(prices) < 20:
        return None
    
    ma5 = np.mean(prices[-5:])
    ma10 = np.mean(prices[-10:])
    ma20 = np.mean(prices[-20:])
    current = prices[-1]
    
    # 判断多头/空头排列
    if ma5 > ma10 > ma20:
        trend = "多头排列"
        strength = 5
    elif ma5 < ma10 < ma20:
        trend = "空头排列"
        strength = 1
    elif ma5 > ma10:
        trend = "偏多"
        strength = 4
    elif ma5 < ma10:
        trend = "偏空"
        strength = 2
    else:
        trend = "缠绕"
        strength = 3
    
    # 当前价位相对位置
    if current > ma5:
        position = "MA5上方"
    elif current > ma10:
        position = "MA5-MA10之间"
    elif current > ma20:
        position = "MA10-MA20之间"
    else:
        position = "MA20下方"
    
    return {
        "ma5": round(ma5, 2),
        "ma10": round(ma10, 2),
        "ma20": round(ma20, 2),
        "trend": trend,
        "strength": strength,
        "position": position,
    }


def calculate_support_resistance(high: List[float], low: List[float], 
                                  close: List[float], period: int = 20) -> Dict:
    """
    计算支撑压力位
    
    Args:
        high: 最高价序列
        low: 最低价序列
        close: 收盘价序列
        period: 计算周期
    
    Returns:
        {"support": 支撑位, "resistance": 压力位, "distance": 距离当前价位}
    """
    if len(close) < period:
        return None
    
    recent_high = max(high[-period:])
    recent_low = min(low[-period:])
    current = close[-1]
    
    # 简单支撑压力
    support = recent_low
    resistance = recent_high
    
    # 计算距离
    support_distance = round((current - support) / current * 100, 2)
    resistance_distance = round((resistance - current) / current * 100, 2)
    
    # 判断位置
    if support_distance < 3:
        position = "接近支撑"
    elif resistance_distance < 3:
        position = "接近压力"
    elif support_distance < resistance_distance:
        position = "偏下沿"
    else:
        position = "偏上沿"
    
    return {
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "support_distance": support_distance,
        "resistance_distance": resistance_distance,
        "position": position,
    }


def calculate_all_indicators(price_data: Dict) -> Dict:
    """
    计算所有技术指标
    
    Args:
        price_data: 包含 close, high, low, volume 的字典
    
    Returns:
        所有指标的综合结果
    """
    close = price_data.get('close', [])
    high = price_data.get('high', [])
    low = price_data.get('low', [])
    volume = price_data.get('volume', [])
    
    results = {}
    
    # RSI
    rsi = calculate_rsi(close)
    if rsi:
        results['rsi'] = rsi
        results['rsi_signal'] = "超买" if rsi > 70 else ("超卖" if rsi < 30 else "中性")
    
    # BOLL
    boll = calculate_boll(close)
    if boll:
        results['boll'] = boll
    
    # OBV
    if volume:
        obv = calculate_obv(close, volume)
        if obv:
            results['obv'] = obv
    
    # MACD
    macd = calculate_macd(close)
    if macd:
        results['macd'] = macd
    
    # KDJ
    kdj = calculate_kdj(high, low, close)
    if kdj:
        results['kdj'] = kdj
    
    # 均线
    ma = calculate_moving_averages(close)
    if ma:
        results['ma'] = ma
    
    # 支撑压力
    sr = calculate_support_resistance(high, low, close)
    if sr:
        results['support_resistance'] = sr
    
    # 综合评分
    results['tech_score'] = _calculate_tech_score(results)
    
    logger.info("技术指标计算完成", score=results.get('tech_score'))
    
    return results


def _calculate_tech_score(indicators: Dict) -> int:
    """
    基于技术指标计算综合得分
    
    Returns:
        技术面得分 (0-30)
    """
    score = 0
    
    # RSI (0-5)
    rsi = indicators.get('rsi', 50)
    if 40 <= rsi <= 60:
        score += 5  # 中性偏多
    elif 30 <= rsi <= 70:
        score += 3
    elif rsi < 30:
        score += 4  # 超卖机会
    
    # BOLL 位置 (0-5)
    boll = indicators.get('boll', {})
    position = boll.get('position', 50)
    if position < 20:
        score += 5  # 接近下轨
    elif position > 80:
        score += 1  # 接近上轨风险
    else:
        score += 3
    
    # MACD (0-8)
    macd = indicators.get('macd', {})
    signal_type = macd.get('signal_type', '')
    if '多头' in signal_type:
        score += 8
    elif '弱势多头' in signal_type:
        score += 5
    elif '弱势空头' in signal_type:
        score += 3
    else:
        score += 2
    
    # KDJ (0-7)
    kdj = indicators.get('kdj', {})
    j_value = kdj.get('j', 50)
    if j_value < 20:
        score += 7  # 超卖
    elif j_value > 85:
        score += 2
    else:
        score += 5
    
    # 均线 (0-5)
    ma = indicators.get('ma', {})
    strength = ma.get('strength', 3)
    score += strength
    
    return min(score, 30)


if __name__ == "__main__":
    # 测试数据
    test_data = {
        'close': [10, 10.5, 11, 10.8, 11.2, 11.5, 11.3, 11.8, 12, 11.9,
                  12.2, 12.5, 12.3, 12.6, 12.8, 12.5, 12.7, 13, 13.2, 13.1,
                  13.4, 13.6, 13.5, 13.8, 14, 13.9, 14.2, 14.5, 14.3, 14.6],
        'high': [10.2, 10.7, 11.2, 11, 11.4, 11.7, 11.5, 12, 12.2, 12.1,
                 12.4, 12.7, 12.5, 12.8, 13, 12.7, 12.9, 13.2, 13.4, 13.3,
                 13.6, 13.8, 13.7, 14, 14.2, 14.1, 14.4, 14.7, 14.5, 14.8],
        'low': [9.8, 10.3, 10.8, 10.6, 11, 11.3, 11.1, 11.6, 11.8, 11.7,
                12, 12.3, 12.1, 12.4, 12.6, 12.3, 12.5, 12.8, 13, 12.9,
                13.2, 13.4, 13.3, 13.6, 13.8, 13.7, 14, 14.3, 14.1, 14.4],
        'volume': [100, 120, 150, 130, 140, 160, 145, 170, 180, 165,
                   190, 200, 185, 210, 220, 195, 205, 230, 240, 225,
                   250, 260, 245, 270, 280, 265, 290, 300, 285, 310],
    }
    
    results = calculate_all_indicators(test_data)
    
    print("\n=== 技术指标分析 ===\n")
    print(f"RSI: {results.get('rsi')} ({results.get('rsi_signal')})")
    print(f"BOLL: 上轨 {results['boll']['upper']} | 中轨 {results['boll']['middle']} | 下轨 {results['boll']['lower']}")
    print(f"MACD: {results['macd']['signal_type']}")
    print(f"KDJ: K={results['kdj']['k']} D={results['kdj']['d']} J={results['kdj']['j']} ({results['kdj']['signal']})")
    print(f"均线: {results['ma']['trend']} ({results['ma']['position']})")
    print(f"支撑压力: 支撑 {results['support_resistance']['support']} | 压力 {results['support_resistance']['resistance']}")
    print(f"\n综合技术得分: {results['tech_score']}/30")
