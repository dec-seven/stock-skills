<template>
  <div class="min-h-screen bg-navy-deep pt-6">
    <main class="max-w-7xl mx-auto px-4 py-6">
      <div class="bg-navy-card rounded-xl border border-border p-4 mb-6">
        <div class="flex items-center gap-4">
          <span class="text-text-secondary text-sm">选择日期</span>
          <div class="flex gap-2">
            <button v-for="date in recentDates" :key="date" @click="selectedDate = date" :class="['px-3 py-1.5 rounded-lg text-sm transition-all', selectedDate === date ? 'bg-blue-accent text-navy-deep font-bold' : 'bg-navy-light hover:bg-blue-accent/20 text-text-secondary hover:text-text-primary']">{{ formatDateShort(date) }}</button>
          </div>
        </div>
      </div>
      <div v-if="brief" class="space-y-6">
        <div class="grid grid-cols-3 gap-6">
          <div class="col-span-2 bg-navy-card rounded-xl border border-border p-6">
            <div class="flex items-start justify-between mb-4">
              <div>
                <h2 class="text-xl font-bold text-text-primary">{{ brief.marketTone }}</h2>
                <p class="text-text-secondary text-sm mt-2">{{ brief.emotionFeature }}</p>
              </div>
              <div :class="getSentimentClass(brief.sentimentClass)" class="px-3 py-1.5 rounded-full text-sm font-bold">{{ getSentimentText(brief.sentimentClass) }}</div>
            </div>
            <div class="mt-4 pt-4 border-t border-border">
              <div class="text-text-muted text-xs mb-1">美股影响</div>
              <p class="text-text-secondary text-sm">{{ brief.usImpact }}</p>
            </div>
          </div>
          <div class="bg-navy-card rounded-xl border border-border p-6">
            <h3 class="text-lg font-bold text-gold mb-4">今日预测</h3>
            <div class="space-y-3">
              <div class="flex justify-between items-center"><span class="text-text-secondary text-sm">方向判断</span><span class="text-text-primary font-bold">{{ brief.todayPrediction.direction }}</span></div>
              <div class="flex justify-between items-center"><span class="text-text-secondary text-sm">上证区间</span><span class="text-text-primary font-bold">{{ brief.todayPrediction.range[0] }} - {{ brief.todayPrediction.range[1] }}</span></div>
              <div class="flex justify-between items-center"><span class="text-text-secondary text-sm">仓位建议</span><span class="text-gold font-bold">{{ brief.todayPrediction.position }}</span></div>
              <div class="flex justify-between items-center"><span class="text-text-secondary text-sm">参与节奏</span><span class="text-text-primary font-bold">{{ brief.todayPrediction.rhythm }}</span></div>
            </div>
          </div>
        </div>
        <div class="grid grid-cols-3 gap-6">
          <div class="bg-navy-card rounded-xl border border-border p-6">
            <h3 class="text-base font-bold text-text-primary mb-4">核心指数</h3>
            <div class="space-y-3">
              <div v-for="index in brief.indices" :key="index.name" class="flex justify-between items-center">
                <span class="text-text-secondary text-sm">{{ index.name }}</span>
                <div class="text-right">
                  <div class="font-bold" :class="index.pct >= 0 ? 'text-red-up' : 'text-green-down'">{{ index.value.toFixed(2) }}</div>
                  <div class="text-xs" :class="index.pct >= 0 ? 'text-red-up' : 'text-green-down'">{{ index.pct >= 0 ? '+' : '' }}{{ index.pct.toFixed(2) }}%</div>
                </div>
              </div>
            </div>
          </div>
          <div class="bg-navy-card rounded-xl border border-border p-6">
            <h3 class="text-base font-bold text-text-primary mb-4">北向资金</h3>
            <div class="mb-4">
              <div class="text-text-muted text-xs mb-1">今日净流入</div>
              <div class="text-2xl font-bold" :class="(brief.northBound?.netInflow || 0) >= 0 ? 'text-red-up' : 'text-green-down'">{{ brief.northBound?.netInflow && brief.northBound.netInflow >= 0 ? '+' : '' }}{{ brief.northBound?.netInflow?.toFixed(2) || '-' }}亿</div>
            </div>
            <div v-if="brief.northBound?.history" class="h-16 flex items-end gap-1">
              <div v-for="h in brief.northBound.history" :key="h.date" :class="['flex-1 rounded-t transition-all', h.netInflow >= 0 ? 'bg-red-up/60' : 'bg-green-down/60']" :style="{ height: Math.min(Math.abs(h.netInflow) / 2 + 10, 100) + '%' }"></div>
            </div>
          </div>
          <div class="bg-navy-card rounded-xl border border-border p-6">
            <h3 class="text-base font-bold text-text-primary mb-4">市场情绪</h3>
            <div class="grid grid-cols-2 gap-3">
              <div class="bg-navy-deep/50 rounded-lg p-3"><div class="text-text-muted text-xs">上涨/下跌</div><div class="text-sm font-bold mt-1"><span class="text-red-up">{{ brief.marketBreadth?.upCount }}</span><span class="text-text-muted">/</span><span class="text-green-down">{{ brief.marketBreadth?.downCount }}</span></div></div>
              <div class="bg-navy-deep/50 rounded-lg p-3"><div class="text-text-muted text-xs">涨停/跌停</div><div class="text-sm font-bold mt-1"><span class="text-red-up">{{ brief.marketBreadth?.limitUp }}</span><span class="text-text-muted">/</span><span class="text-green-down">{{ brief.marketBreadth?.limitDown }}</span></div></div>
              <div class="bg-navy-deep/50 rounded-lg p-3"><div class="text-text-muted text-xs">上涨比例</div><div class="text-sm font-bold text-text-primary mt-1">{{ ((brief.marketBreadth?.upRatio || 0) * 100).toFixed(1) }}%</div></div>
              <div class="bg-navy-deep/50 rounded-lg p-3"><div class="text-text-muted text-xs">涨跌停比</div><div class="text-sm font-bold text-text-primary mt-1">{{ (brief.marketBreadth?.limitRatio || 0).toFixed(2) }}</div></div>
            </div>
          </div>
        </div>
        <div class="grid grid-cols-2 gap-6">
          <div class="bg-navy-card rounded-xl border border-border p-6">
            <h3 class="text-base font-bold text-red-up mb-4">领涨板块</h3>
            <div class="space-y-2">
              <div v-for="(sector, idx) in brief.topGainers" :key="sector.name" class="flex items-center gap-3">
                <span class="w-5 h-5 rounded bg-red-up/20 text-red-up text-xs flex items-center justify-center font-bold">{{ idx + 1 }}</span>
                <div class="flex-1"><div class="flex justify-between items-center"><span class="text-text-primary text-sm">{{ sector.name }}</span><span class="text-red-up font-bold text-sm">+{{ sector.pct.toFixed(2) }}%</span></div><div v-if="sector.logic" class="text-text-muted text-xs mt-0.5">{{ sector.logic }}</div></div>
              </div>
            </div>
          </div>
          <div class="bg-navy-card rounded-xl border border-border p-6">
            <h3 class="text-base font-bold text-green-down mb-4">领跌板块</h3>
            <div class="space-y-2">
              <div v-for="(sector, idx) in brief.topLosers" :key="sector.name" class="flex items-center gap-3">
                <span class="w-5 h-5 rounded bg-green-down/20 text-green-down text-xs flex items-center justify-center font-bold">{{ idx + 1 }}</span>
                <div class="flex-1"><div class="flex justify-between items-center"><span class="text-text-primary text-sm">{{ sector.name }}</span><span class="text-green-down font-bold text-sm">{{ sector.pct.toFixed(2) }}%</span></div><div v-if="sector.logic" class="text-text-muted text-xs mt-0.5">{{ sector.logic }}</div></div>
              </div>
            </div>
          </div>
        </div>
        <div class="bg-navy-card rounded-xl border border-border p-6">
          <h3 class="text-lg font-bold text-gold mb-4">精选标的</h3>
          <div class="grid grid-cols-3 gap-4">
            <div v-for="stock in brief.stocks" :key="stock.symbol" class="bg-navy-deep/50 rounded-lg p-4">
              <div class="flex justify-between items-start mb-2">
                <div><div class="text-text-primary font-bold">{{ stock.name }}</div><div class="text-text-muted text-xs">{{ stock.symbol }}</div></div>
                <div class="text-right"><div class="text-gold font-bold text-lg">{{ stock.score }}分</div><div class="text-gold-soft text-xs">{{ '★'.repeat(stock.stars) }}</div></div>
              </div>
              <div class="flex gap-1.5 flex-wrap mb-2"><span v-for="tag in stock.tags" :key="tag" class="px-2 py-0.5 rounded text-xs bg-blue-accent/20 text-blue-accent">{{ tag }}</span></div>
              <p class="text-text-secondary text-xs line-clamp-2">{{ stock.logic }}</p>
              <div v-if="stock.risks?.length" class="mt-2 pt-2 border-t border-border"><div class="text-text-muted text-xs mb-1">风险提示</div><div class="flex gap-1 flex-wrap"><span v-for="risk in stock.risks" :key="risk" class="text-xs text-yellow-warn">{{ risk }}</span></div></div>
            </div>
          </div>
        </div>
        <div v-if="brief.riskAlerts?.length" class="bg-navy-card rounded-xl border border-border p-6">
          <h3 class="text-base font-bold text-yellow-warn mb-4">风险提示</h3>
          <div class="grid grid-cols-2 gap-3">
            <div v-for="alert in brief.riskAlerts" :key="alert.title" :class="['rounded-lg p-3 border', alert.level === 'high' ? 'bg-red-up/10 border-red-up/30' : alert.level === 'medium' ? 'bg-yellow-warn/10 border-yellow-warn/30' : 'bg-navy-light/30 border-border']">
              <div class="font-bold text-sm" :class="alert.level === 'high' ? 'text-red-up' : alert.level === 'medium' ? 'text-yellow-warn' : 'text-text-secondary'">{{ alert.title }}</div>
              <div class="text-text-secondary text-xs mt-1">{{ alert.content }}</div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="text-center text-text-secondary py-20"><div class="text-4xl mb-4">📊</div><div>加载中...</div></div>
    </main>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import type { MorningBrief } from '../types'
import { mockBrief } from '../utils/mockData'
import dayjs from 'dayjs'

const selectedDate = ref(dayjs().format('YYYY-MM-DD'))
const brief = ref<MorningBrief | null>(null)
const recentDates = ref<string[]>([])

onMounted(async () => {
  const dates = []
  for (let i = 0; i < 7; i++) { dates.push(dayjs().subtract(i, 'day').format('YYYY-MM-DD')) }
  recentDates.value = dates
  await loadBrief()
})

watch(selectedDate, async () => { await loadBrief() })

async function loadBrief() {
  setTimeout(() => { brief.value = mockBrief }, 300)
}

function formatDateShort(date: string) { return dayjs(date).format('MM-DD') }

function getSentimentClass(sentiment: string) {
  const classes: Record<string, string> = {
    'sentiment-hot': 'bg-red-up/20 text-red-up',
    'sentiment-warm': 'bg-gold/20 text-gold',
    'sentiment-cold': 'bg-blue-accent/20 text-blue-accent',
    'sentiment-frozen': 'bg-navy-light text-text-secondary',
  }
  return classes[sentiment] || 'bg-navy-light text-text-secondary'
}

function getSentimentText(sentiment: string) {
  const texts: Record<string, string> = {
    'sentiment-hot': '🔥 热情期',
    'sentiment-warm': '🌡️ 温暖期',
    'sentiment-cold': '❄️ 寒冷期',
    'sentiment-frozen': '🧊 冰冻期',
  }
  return texts[sentiment] || '❓ 未知'
}
</script>
<style scoped>
.border-border { border-color: rgba(79, 195, 247, 0.18); }
.line-clamp-2 { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
</style>
