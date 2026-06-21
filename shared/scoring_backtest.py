#!/usr/bin/env python3
"""
评分体系回测模块

功能：
1. 历史选股数据回测
2. 各维度权重优化建议
3. 预测准确率统计
"""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import statistics

from shared.logger import get_logger

logger = get_logger('scoring-backtest')


class ScoringBacktest:
    """评分体系回测分析"""
    
    def __init__(self, tracker_file: str = None):
        self.tracker_file = tracker_file or os.path.join(
            os.path.dirname(__file__), '..',
            'skills/stock-morning-brief/data/stock_selection_tracker.json'
        )
        self.data = self._load_tracker_data()
    
    def _load_tracker_data(self) -> Dict:
        """加载选股跟踪数据"""
        if not os.path.exists(self.tracker_file):
            logger.warning(f"跟踪数据文件不存在: {self.tracker_file}")
            return {}
        
        with open(self.tracker_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def analyze_dimension_weights(self) -> Dict:
        """分析各评分维度的预测效果"""
        if not self.data:
            return {"error": "无历史数据"}
        
        results = {
            "by_dimension": defaultdict(list),
            "by_score_range": defaultdict(list),
            "total_stocks": 0,
            "avg_return": 0,
        }
        
        total_return = 0
        valid_count = 0
        
        for date, stocks in self.data.items():
            for stock in stocks if isinstance(stocks, list) else [stocks]:
                if not isinstance(stock, dict):
                    continue
                
                # 获取评分和后续表现
                fund_scores = stock.get('fund_scores', {})
                tech_scores = stock.get('tech_scores', {})
                returns = stock.get('returns', {})
                
                total_score = sum(fund_scores.values()) + sum(tech_scores.values())
                
                # 使用 3 日或 5 日收益作为验证
                actual_return = returns.get('3d') or returns.get('5d') or returns.get('7d')
                
                if actual_return is None:
                    continue
                
                valid_count += 1
                total_return += actual_return
                
                # 按评分维度记录
                for dim, score in fund_scores.items():
                    results["by_dimension"][dim].append({
                        "score": score,
                        "return": actual_return,
                    })
                
                # 按总分区间记录
                score_range = self._get_score_range(total_score)
                results["by_score_range"][score_range].append(actual_return)
        
        # 计算各维度的相关性
        dimension_correlation = {}
        for dim, records in results["by_dimension"].items():
            if len(records) >= 5:  # 至少 5 条数据
                scores = [r["score"] for r in records]
                returns = [r["return"] for r in records]
                
                # 简单相关性：高分是否对应高收益
                high_score_returns = [r["return"] for r in records if r["score"] >= 7]
                low_score_returns = [r["return"] for r in records if r["score"] <= 3]
                
                if high_score_returns and low_score_returns:
                    avg_high = statistics.mean(high_score_returns)
                    avg_low = statistics.mean(low_score_returns)
                    dimension_correlation[dim] = {
                        "avg_high_score_return": round(avg_high, 2),
                        "avg_low_score_return": round(avg_low, 2),
                        "effectiveness": round(avg_high - avg_low, 2),
                    }
        
        # 按评分区间统计
        range_stats = {}
        for score_range, returns in results["by_score_range"].items():
            if returns:
                range_stats[score_range] = {
                    "count": len(returns),
                    "avg_return": round(statistics.mean(returns), 2),
                    "win_rate": round(len([r for r in returns if r > 0]) / len(returns) * 100, 1),
                }
        
        results["dimension_correlation"] = dimension_correlation
        results["range_stats"] = range_stats
        results["total_stocks"] = valid_count
        results["avg_return"] = round(total_return / valid_count, 2) if valid_count > 0 else 0
        
        logger.info("评分回测完成", total_stocks=valid_count, avg_return=results["avg_return"])
        
        return results
    
    def _get_score_range(self, score: int) -> str:
        """获取评分区间"""
        if score >= 85:
            return "85+"
        elif score >= 75:
            return "75-84"
        elif score >= 60:
            return "60-74"
        else:
            return "<60"
    
    def suggest_weight_adjustments(self) -> Dict:
        """基于回测结果建议权重调整"""
        analysis = self.analyze_dimension_weights()
        
        if "error" in analysis:
            return analysis
        
        suggestions = []
        dimension_correlation = analysis.get("dimension_correlation", {})
        
        for dim, stats in dimension_correlation.items():
            effectiveness = stats["effectiveness"]
            
            if effectiveness > 2:
                suggestions.append({
                    "dimension": dim,
                    "current_weight": 10,
                    "suggested_weight": 12,
                    "reason": f"高分比低分平均多赚 {effectiveness}%，建议提权",
                })
            elif effectiveness < -1:
                suggestions.append({
                    "dimension": dim,
                    "current_weight": 10,
                    "suggested_weight": 8,
                    "reason": f"高分反而表现差 {abs(effectiveness)}%，建议降权",
                })
        
        return {
            "suggestions": suggestions,
            "analysis_date": datetime.now().strftime('%Y-%m-%d'),
            "sample_size": analysis["total_stocks"],
        }
    
    def validate_rating_system(self) -> Dict:
        """验证评级体系有效性"""
        analysis = self.analyze_dimension_weights()
        
        if "error" in analysis:
            return analysis
        
        range_stats = analysis.get("range_stats", {})
        
        validation = {
            "valid": True,
            "issues": [],
        }
        
        # 检查逻辑：高分应该对应更高收益
        expected_order = ["<60", "60-74", "75-84", "85+"]
        returns = []
        
        for range_name in expected_order:
            if range_name in range_stats:
                returns.append(range_stats[range_name]["avg_return"])
        
        # 检查是否单调递增
        is_monotonic = all(returns[i] <= returns[i+1] for i in range(len(returns)-1))
        
        if not is_monotonic:
            validation["valid"] = False
            validation["issues"].append("评分体系非单调：高分区间收益未高于低分区间")
        
        # 检查胜率
        for range_name, stats in range_stats.items():
            if range_name in ["85+", "75-84"] and stats["win_rate"] < 50:
                validation["valid"] = False
                validation["issues"].append(f"{range_name} 区间胜率仅 {stats['win_rate']}%，低于 50%")
        
        validation["range_stats"] = range_stats
        
        return validation


def run_backtest():
    """运行回测分析"""
    backtest = ScoringBacktest()
    
    print("\n=== 评分体系回测报告 ===\n")
    
    # 分析维度权重
    analysis = backtest.analyze_dimension_weights()
    print(f"样本数量: {analysis.get('total_stocks', 0)}")
    print(f"平均收益: {analysis.get('avg_return', 0)}%")
    
    print("\n--- 各评分区间表现 ---")
    for range_name, stats in analysis.get("range_stats", {}).items():
        print(f"  {range_name}: 平均收益 {stats['avg_return']}%, 胜率 {stats['win_rate']}%")
    
    # 权重调整建议
    suggestions = backtest.suggest_weight_adjustments()
    if suggestions.get("suggestions"):
        print("\n--- 权重调整建议 ---")
        for s in suggestions["suggestions"]:
            print(f"  {s['dimension']}: {s['current_weight']} → {s['suggested_weight']} ({s['reason']})")
    
    # 验证评级体系
    validation = backtest.validate_rating_system()
    print(f"\n--- 评级体系验证 ---")
    print(f"  有效性: {'✓ 通过' if validation['valid'] else '✗ 存在问题'}")
    if validation.get("issues"):
        for issue in validation["issues"]:
            print(f"    - {issue}")
    
    return analysis


if __name__ == "__main__":
    run_backtest()
