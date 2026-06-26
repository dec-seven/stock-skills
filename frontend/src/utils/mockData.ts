import type { MorningBrief, TrackerStock, WinRateByScore, MonthlyReturn, CumulativeReturn } from '../types'

// ===== 北向资金历史 =====
function generateNorthBoundHistory() {
  const history = []
  let cumulative = 0
  for (let i = 4; i >= 0; i--) {
    const date = new Date()
    date.setDate(date.getDate() - i)
    const inflow = (Math.random() - 0.3) * 100
    cumulative += inflow
    history.push({
      date: date.toISOString().split('T')[0],
      netInflow: parseFloat(inflow.toFixed(2)),
      cumulative: parseFloat(cumulative.toFixed(2)),
    })
  }
  return history
}

// ===== 完整早报模拟数据 =====
export const mockBrief: MorningBrief = {
  date: '2026-06-26',
  marketTone: '市场震荡偏强，科技股领涨两市',
  usImpact: '美股隔夜上涨，科技股表现强劲，对A股科技板块形成正面催化，纳指涨1.2%，费城半导体指数涨2.1%',
  emotionFeature: '市场情绪回暖，投资者信心逐步恢复，成交额有所放大，两市成交额突破1.2万亿',
  sentimentClass: 'sentiment-warm',
  todayPrediction: {
    direction: '偏多',
    range: [3350, 3420],
    position: '6-7成',
    rhythm: '逢低布局，快进快出',
  },
  indices: [
    { name: '上证指数', value: 3389.55, pct: 0.85, volume: 4856 },
    { name: '深证成指', value: 10567.32, pct: 1.23, volume: 7234 },
    { name: '创业板指', value: 2234.89, pct: 1.56, volume: 2891 },
  ],
  topGainers: [
    { name: '半导体', pct: 3.45, funds: 45.6, logic: 'AI算力需求爆发，国产替代加速' },
    { name: '人工智能', pct: 2.89, funds: 38.2, logic: '大模型持续迭代，应用落地加速' },
    { name: '芯片', pct: 2.67, funds: 32.1, logic: '设备材料国产化突破' },
    { name: '消费电子', pct: 2.34, funds: 28.5, logic: '新款手机发布，换机周期来临' },
  ],
  topLosers: [
    { name: '房地产', pct: -1.23, funds: -12.3, logic: '政策预期落空，市场信心不足' },
    { name: '银行', pct: -0.89, funds: -8.7, logic: '息差收窄压力持续' },
    { name: '保险', pct: -0.67, funds: -5.4, logic: '投资收益下滑担忧' },
    { name: '基建', pct: -0.45, funds: -3.2, logic: '项目进度放缓' },
  ],
  stocks: [
    {
      symbol: '002371',
      name: '北方华创',
      score: 86,
      stars: 5,
      tags: ['半导体设备', '国产替代', '业绩高增'],
      logic: '半导体设备龙头，业绩持续超预期，国产替代加速推进，订单饱满',
      risks: ['估值较高', '下游需求波动'],
      scoreDetail: {
        businessPurity: 10, industryPosition: 9, priceBenefit: 7, earningsVerify: 10,
        catalystProximity: 8, valuationPosition: 6, specialTag: 5,
        macd: 7, kdj: 8, volume: 7, ma: 5, support: 4,
      },
    },
    {
      symbol: '002436',
      name: '兴森科技',
      score: 81,
      stars: 4,
      tags: ['PCB', '半导体', 'CCL'],
      logic: 'PCB+IC载板双轮驱动，受益AI服务器需求爆发',
      risks: ['原材料价格波动'],
      scoreDetail: {
        businessPurity: 8, industryPosition: 7, priceBenefit: 8, earningsVerify: 7,
        catalystProximity: 9, valuationPosition: 7, specialTag: 3,
        macd: 8, kdj: 7, volume: 6, ma: 6, support: 5,
      },
    },
    {
      symbol: '300750',
      name: '宁德时代',
      score: 78,
      stars: 4,
      tags: ['新能源', '储能', '龙头'],
      logic: '全球动力电池龙头，储能业务高增长',
      risks: ['行业竞争加剧', '原材料价格'],
      scoreDetail: {
        businessPurity: 9, industryPosition: 10, priceBenefit: 6, earningsVerify: 8,
        catalystProximity: 6, valuationPosition: 5, specialTag: 4,
        macd: 6, kdj: 6, volume: 7, ma: 5, support: 6,
      },
    },
  ],
  northBound: {
    netInflow: 45.6,
    history: generateNorthBoundHistory(),
  },
  marketBreadth: {
    upCount: 2845,
    downCount: 1987,
    flatCount: 342,
    limitUp: 68,
    limitDown: 12,
    upRatio: 0.55,
    limitRatio: 5.67,
  },
  riskAlerts: [
    { level: 'medium', title: '成交量萎缩风险', content: '近期成交量持续萎缩，需关注量能变化' },
    { level: 'low', title: '外部不确定性', content: '美联储议息会议临近，关注外部市场波动' },
  ],
  sectorFundFlow: [
    { name: '半导体', pct: 3.45, fundInflow: 45.6, leadingStocks: ['北方华创', '中微公司'], logic: 'AI算力需求爆发' },
    { name: '人工智能', pct: 2.89, fundInflow: 38.2, leadingStocks: ['科大讯飞', '云从科技'], logic: '大模型应用落地' },
    { name: '消费电子', pct: 2.34, fundInflow: 28.5, leadingStocks: ['立讯精密', '歌尔股份'], logic: '换机周期来临' },
  ],
}

// ===== 跟踪标的数据 =====
export const mockTrackerStocks: TrackerStock[] = [
  { symbol: '002371', name: '北方华创', score: 86, stars: 5, date: '2026-06-25', returns: { nextDay: 2.3, day3: 4.5, day5: 6.7, day7: 8.9 }, entryPrice: 285.5, currentPrice: 312.3, tags: ['半导体设备', '国产替代'], logic: '半导体设备龙头' },
  { symbol: '002436', name: '兴森科技', score: 81, stars: 4, date: '2026-06-24', returns: { nextDay: 1.8, day3: 3.2, day5: 5.1, day7: 7.2 }, entryPrice: 18.5, currentPrice: 19.8, tags: ['PCB', 'IC载板'], logic: 'AI服务器需求驱动' },
  { symbol: '300750', name: '宁德时代', score: 78, stars: 4, date: '2026-06-23', returns: { nextDay: -0.5, day3: 1.2, day5: 2.8, day7: 4.5 }, entryPrice: 185.2, currentPrice: 193.5, tags: ['新能源', '储能'], logic: '全球动力电池龙头' },
  { symbol: '603259', name: '药明康德', score: 75, stars: 4, date: '2026-06-22', returns: { nextDay: 0.8, day3: -1.2, day5: 1.5, day7: 2.1 }, entryPrice: 45.6, currentPrice: 46.8, tags: ['CXO', '创新药'], logic: 'CXO龙头复苏' },
  { symbol: '000858', name: '五粮液', score: 72, stars: 3, date: '2026-06-21', returns: { nextDay: -1.2, day3: -2.3, day5: -1.8, day7: 0.5 }, entryPrice: 125.8, currentPrice: 126.4, tags: ['白酒', '消费'], logic: '消费复苏预期' },
]

// ===== 分星级胜率 =====
export const mockWinRateByScore: WinRateByScore = {
  score5: { win: 12, total: 15, winRate: 80.0, avgReturn: 6.8 },
  score4: { win: 18, total: 28, winRate: 64.3, avgReturn: 3.2 },
  score3: { win: 8, total: 20, winRate: 40.0, avgReturn: 0.5 },
  score2: { win: 2, total: 10, winRate: 20.0, avgReturn: -2.1 },
}

// ===== 月度收益 =====
export const mockMonthlyReturns: MonthlyReturn[] = [
  { month: '2026-01', returnPct: 5.2, winCount: 8, loseCount: 4 },
  { month: '2026-02', returnPct: -1.8, winCount: 5, loseCount: 7 },
  { month: '2026-03', returnPct: 8.5, winCount: 12, loseCount: 3 },
  { month: '2026-04', returnPct: 3.2, winCount: 7, loseCount: 5 },
  { month: '2026-05', returnPct: 6.7, winCount: 10, loseCount: 4 },
  { month: '2026-06', returnPct: 4.5, winCount: 8, loseCount: 3 },
]

// ===== 累计收益曲线 =====
export const mockCumulativeReturns: CumulativeReturn[] = (() => {
  const data: CumulativeReturn[] = []
  let strategy = 100
  let benchmark = 100
  for (let i = 90; i >= 0; i--) {
    const date = new Date()
    date.setDate(date.getDate() - i)
    strategy += (Math.random() - 0.45) * 1.5
    benchmark += (Math.random() - 0.48) * 1.2
    data.push({
      date: date.toISOString().split('T')[0],
      strategy: parseFloat(strategy.toFixed(2)),
      benchmark: parseFloat(benchmark.toFixed(2)),
    })
  }
  return data
})()
