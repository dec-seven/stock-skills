<template>
  <div class="min-h-screen bg-navy-deep pt-6">
    <main class="max-w-7xl mx-auto px-4 py-6">
      <div class="grid grid-cols-5 gap-4 mb-6">
        <div class="bg-navy-card rounded-xl border border-border p-5">
          <div class="text-text-secondary text-sm mb-2">总胜率</div>
          <div class="text-3xl font-bold text-gold">{{ stats.winRate.toFixed(1) }}%</div>
          <div class="text-text-muted text-xs mt-1">{{ stats.winCount }}/{{ stats.totalCount }} 胜</div>
        </div>
        <div class="bg-navy-card rounded-xl border border-border p-5">
          <div class="text-text-secondary text-sm mb-2">平均收益</div>
          <div class="text-3xl font-bold" :class="stats.avgReturn >= 0 ? 'text-red-up' : 'text-green-down'">{{ stats.avgReturn >= 0 ? '+' : '' }}{{ stats.avgReturn.toFixed(2) }}%</div>
          <div class="text-text-muted text-xs mt-1">7日持有</div>
        </div>
        <div class="bg-navy-card rounded-xl border border-border p-5">
          <div class="text-text-secondary text-sm mb-2">跟踪标的</div>
          <div class="text-3xl font-bold text-text-primary">{{ stocks.length }}</div>
          <div class="text-text-muted text-xs mt-1">累计入选</div>
        </div>
        <div class="bg-navy-card rounded-xl border border-border p-5">
          <div class="text-text-secondary text-sm mb-2">最大回撤</div>
          <div class="text-3xl font-bold text-green-down">{{ stats.maxDrawdown.toFixed(2) }}%</div>
          <div class="text-text-muted text-xs mt-1">单标的</div>
        </div>
        <div class="bg-navy-card rounded-xl border border-border p-5">
          <div class="text-text-secondary text-sm mb-2">夏普比率</div>
          <div class="text-3xl font-bold text-blue-accent">{{ stats.sharpe.toFixed(2) }}</div>
          <div class="text-text-muted text-xs mt-1">风险调整收益</div>
        </div>
      </div>
      <div class="grid grid-cols-4 gap-4 mb-6">
        <div v-for="(item, key) in winRateByScore" :key="key" class="bg-navy-card rounded-xl border border-border p-4">
          <div class="flex items-center justify-between mb-2">
            <span class="text-text-secondary text-sm">{{ getScoreLabel(key) }}</span>
            <span class="text-gold text-sm">{{ '★'.repeat(getScoreStars(key)) }}</span>
          </div>
          <div class="text-2xl font-bold text-text-primary">{{ item.winRate.toFixed(1) }}%</div>
          <div class="text-text-muted text-xs mt-1">平均收益 {{ item.avgReturn >= 0 ? '+' : '' }}{{ item.avgReturn.toFixed(2) }}%</div>
          <div class="mt-2 h-2 bg-navy-deep rounded-full overflow-hidden">
            <div class="h-full bg-gold rounded-full" :style="{ width: item.winRate + '%' }"></div>
          </div>
        </div>
      </div>
      <div class="bg-navy-card rounded-xl border border-border p-6 mb-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-bold text-text-primary">累计收益曲线</h3>
          <div class="flex gap-4 text-sm">
            <span class="flex items-center gap-2"><span class="w-3 h-3 rounded bg-gold"></span>策略收益</span>
            <span class="flex items-center gap-2"><span class="w-3 h-3 rounded bg-blue-accent"></span>沪深300</span>
          </div>
        </div>
        <div ref="cumulativeChartRef" style="width: 100%; height: 350px;"></div>
      </div>
      <div class="grid grid-cols-2 gap-6 mb-6">
        <div class="bg-navy-card rounded-xl border border-border p-6">
          <h3 class="text-lg font-bold text-text-primary mb-4">月度收益</h3>
          <div ref="monthlyChartRef" style="width: 100%; height: 280px;"></div>
        </div>
        <div class="bg-navy-card rounded-xl border border-border p-6">
          <h3 class="text-lg font-bold text-text-primary mb-4">收益分布</h3>
          <div class="grid grid-cols-3 gap-3">
            <div class="bg-navy-deep/50 rounded-lg p-4 text-center">
              <div class="text-2xl font-bold text-red-up">{{ distribution.positive }}</div>
              <div class="text-text-muted text-xs mt-1">盈利标的</div>
            </div>
            <div class="bg-navy-deep/50 rounded-lg p-4 text-center">
              <div class="text-2xl font-bold text-green-down">{{ distribution.negative }}</div>
              <div class="text-text-muted text-xs mt-1">亏损标的</div>
            </div>
            <div class="bg-navy-deep/50 rounded-lg p-4 text-center">
              <div class="text-2xl font-bold text-text-secondary">{{ distribution.flat }}</div>
              <div class="text-text-muted text-xs mt-1">持平标的</div>
            </div>
          </div>
          <div class="mt-4 pt-4 border-t border-border">
            <div class="grid grid-cols-2 gap-4">
              <div><span class="text-text-muted text-xs">最大单笔收益</span><div class="text-red-up font-bold">+{{ distribution.maxWin.toFixed(2) }}%</div></div>
              <div><span class="text-text-muted text-xs">最大单笔亏损</span><div class="text-green-down font-bold">{{ distribution.maxLose.toFixed(2) }}%</div></div>
            </div>
          </div>
        </div>
      </div>
      <div class="bg-navy-card rounded-xl border border-border p-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-bold text-text-primary">跟踪标的</h3>
          <select v-model="sortBy" class="bg-navy-light border border-border rounded-lg px-3 py-1.5 text-sm text-text-primary">
            <option value="date">按日期</option>
            <option value="score">按评分</option>
            <option value="return">按收益</option>
          </select>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead><tr class="border-b border-border text-text-secondary text-sm">
              <th class="text-left py-3 px-3">股票</th>
              <th class="text-center py-3 px-3">评分</th>
              <th class="text-center py-3 px-3">入选日期</th>
              <th class="text-center py-3 px-3">入选价</th>
              <th class="text-center py-3 px-3">次日</th>
              <th class="text-center py-3 px-3">3日</th>
              <th class="text-center py-3 px-3">5日</th>
              <th class="text-center py-3 px-3">7日</th>
            </tr></thead>
            <tbody>
              <tr v-for="stock in sortedStocks" :key="stock.symbol + stock.date" class="border-b border-border/50 hover:bg-navy-light/20">
                <td class="py-3 px-3"><div class="text-text-primary font-bold">{{ stock.name }}</div><div class="text-text-muted text-xs">{{ stock.symbol }}</div></td>
                <td class="text-center py-3 px-3"><span class="text-gold font-bold">{{ stock.score }}</span><span class="text-gold-soft text-xs ml-1">{{ '★'.repeat(stock.stars) }}</span></td>
                <td class="text-center py-3 px-3 text-text-secondary text-sm">{{ stock.date }}</td>
                <td class="text-center py-3 px-3 text-text-secondary text-sm">{{ stock.entryPrice?.toFixed(2) || '-' }}</td>
                <td class="text-center py-3 px-3 text-sm font-bold" :class="getReturnClass(stock.returns.nextDay)">{{ formatReturn(stock.returns.nextDay) }}</td>
                <td class="text-center py-3 px-3 text-sm font-bold" :class="getReturnClass(stock.returns.day3)">{{ formatReturn(stock.returns.day3) }}</td>
                <td class="text-center py-3 px-3 text-sm font-bold" :class="getReturnClass(stock.returns.day5)">{{ formatReturn(stock.returns.day5) }}</td>
                <td class="text-center py-3 px-3 text-sm font-bold" :class="getReturnClass(stock.returns.day7)">{{ formatReturn(stock.returns.day7) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </main>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import * as echarts from 'echarts'
import type { TrackerStock, WinRateByScore } from '../types'
import { mockTrackerStocks, mockWinRateByScore, mockCumulativeReturns, mockMonthlyReturns } from '../utils/mockData'

const cumulativeChartRef = ref<HTMLElement>()
const monthlyChartRef = ref<HTMLElement>()
const stocks = ref<TrackerStock[]>([])
const winRateByScore = ref<WinRateByScore>(mockWinRateByScore)
const sortBy = ref('date')

const stats = computed(() => {
  if (stocks.value.length === 0) return { winRate: 0, avgReturn: 0, maxDrawdown: 0, sharpe: 0, winCount: 0, totalCount: 0 }
  let winCount = 0, totalReturn = 0, maxDD = 0, returns: number[] = []
  stocks.value.forEach(s => { const r = s.returns.day7 || 0; if (r > 0) winCount++; totalReturn += r; if (r < maxDD) maxDD = r; returns.push(r) })
  const avgRet = totalReturn / stocks.value.length
  const std = Math.sqrt(returns.reduce((sum, r) => sum + Math.pow(r - avgRet, 2), 0) / returns.length)
  const sharpe = std > 0 ? (avgRet / std) * Math.sqrt(52) : 0
  return { winRate: (winCount / stocks.value.length) * 100, avgReturn: avgRet, maxDrawdown: maxDD, sharpe, winCount, totalCount: stocks.value.length }
})

const distribution = computed(() => {
  let positive = 0, negative = 0, flat = 0, maxWin = 0, maxLose = 0
  stocks.value.forEach(s => { const r = s.returns.day7 || 0; if (r > 0.5) { positive++; if (r > maxWin) maxWin = r } else if (r < -0.5) { negative++; if (r < maxLose) maxLose = r } else flat++ })
  return { positive, negative, flat, maxWin, maxLose }
})

const sortedStocks = computed(() => {
  const arr = [...stocks.value]
  if (sortBy.value === 'score') return arr.sort((a, b) => b.score - a.score)
  if (sortBy.value === 'return') return arr.sort((a, b) => (b.returns.day7 || 0) - (a.returns.day7 || 0))
  return arr.sort((a, b) => b.date.localeCompare(a.date))
})

onMounted(async () => { stocks.value = mockTrackerStocks; initCharts() })

function initCharts() {
  if (cumulativeChartRef.value) {
    const chart = echarts.init(cumulativeChartRef.value)
    const data = mockCumulativeReturns
    chart.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', backgroundColor: 'rgba(15, 32, 68, 0.9)', borderColor: 'rgba(79, 195, 247, 0.18)', textStyle: { color: '#e8e8e8' } },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: data.map(d => d.date), axisLine: { lineStyle: { color: 'rgba(79, 195, 247, 0.18)' } }, axisLabel: { color: '#8899aa', fontSize: 10 } },
      yAxis: { type: 'value', axisLine: { lineStyle: { color: 'rgba(79, 195, 247, 0.18)' } }, axisLabel: { color: '#8899aa' }, splitLine: { lineStyle: { color: 'rgba(79, 195, 247, 0.1)' } } },
      series: [
        { name: '策略', type: 'line', data: data.map(d => d.strategy), smooth: true, lineStyle: { color: '#f0c14b', width: 2 }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(240, 193, 75, 0.2)' }, { offset: 1, color: 'rgba(240, 193, 75, 0)' }] } } },
        { name: '基准', type: 'line', data: data.map(d => d.benchmark), smooth: true, lineStyle: { color: '#4fc3f7', width: 2, type: 'dashed' } },
      ],
    })
    window.addEventListener('resize', () => chart.resize())
  }
  if (monthlyChartRef.value) {
    const chart = echarts.init(monthlyChartRef.value)
    const data = mockMonthlyReturns
    chart.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', backgroundColor: 'rgba(15, 32, 68, 0.9)', borderColor: 'rgba(79, 195, 247, 0.18)', textStyle: { color: '#e8e8e8' } },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: data.map(d => d.month), axisLine: { lineStyle: { color: 'rgba(79, 195, 247, 0.18)' } }, axisLabel: { color: '#8899aa' } },
      yAxis: { type: 'value', axisLine: { lineStyle: { color: 'rgba(79, 195, 247, 0.18)' } }, axisLabel: { color: '#8899aa' }, splitLine: { lineStyle: { color: 'rgba(79, 195, 247, 0.1)' } } },
      series: [{ type: 'bar', data: data.map(d => ({ value: d.returnPct, itemStyle: { color: d.returnPct >= 0 ? '#ff5252' : '#69f0ae' } })), barWidth: '50%' }],
    })
    window.addEventListener('resize', () => chart.resize())
  }
}

function formatReturn(value?: number) { return value === undefined ? '-' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}%` }
function getReturnClass(value?: number) { return value === undefined ? 'text-text-secondary' : value >= 0 ? 'text-red-up' : 'text-green-down' }
function getScoreLabel(key: string) { const labels: Record<string, string> = { score5: '强烈推荐', score4: '推荐', score3: '观察', score2: '不建议' }; return labels[key] || key }
function getScoreStars(key: string) { const stars: Record<string, number> = { score5: 5, score4: 4, score3: 3, score2: 2 }; return stars[key] || 0 }
</script>
<style scoped>
.border-border { border-color: rgba(79, 195, 247, 0.18); }
</style>
