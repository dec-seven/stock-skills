<template>
  <div class="min-h-screen bg-navy-deep">
    <header class="bg-navy-card border-b border-border">
      <div class="max-w-7xl mx-auto px-4 py-6">
        <div class="flex items-center justify-between">
          <div>
            <h1 class="text-3xl font-bold bg-gradient-to-r from-gold via-white to-blue-accent bg-clip-text text-transparent">
              预测复盘
            </h1>
            <p class="text-text-secondary text-sm mt-1">持续优化方法论</p>
          </div>
          <nav class="flex gap-4">
            <router-link to="/" class="nav-link">首页</router-link>
            <router-link to="/brief" class="nav-link">早报</router-link>
            <router-link to="/tracker" class="nav-link">选股跟踪</router-link>
          </nav>
        </div>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 py-8">
      <!-- 准确率卡片 -->
      <div class="grid grid-cols-3 gap-6 mb-8">
        <div class="bg-navy-card rounded-2xl border border-border p-6">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-text-secondary">方向准确率</div>
              <div class="text-4xl font-bold text-gold mt-2">{{ accuracy.directionAccuracy.toFixed(1) }}%</div>
            </div>
            <div ref="directionChartRef" style="width: 120px; height: 120px;"></div>
          </div>
        </div>
        <div class="bg-navy-card rounded-2xl border border-border p-6">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-text-secondary">区间命中率</div>
              <div class="text-4xl font-bold text-blue-accent mt-2">{{ accuracy.rangeAccuracy.toFixed(1) }}%</div>
            </div>
            <div ref="rangeChartRef" style="width: 120px; height: 120px;"></div>
          </div>
        </div>
        <div class="bg-navy-card rounded-2xl border border-border p-6">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-text-secondary">选股胜率</div>
              <div class="text-4xl font-bold text-red-up mt-2">{{ accuracy.stockWinRate.toFixed(1) }}%</div>
            </div>
            <div ref="stockChartRef" style="width: 120px; height: 120px;"></div>
          </div>
        </div>
      </div>

      <!-- 历史验证列表 -->
      <div class="bg-navy-card rounded-2xl border border-border p-6">
        <h3 class="text-lg font-bold text-text-primary mb-4">历史验证记录</h3>
        <div class="space-y-4">
          <div v-for="record in historyRecords" :key="record.date" class="bg-navy-deep/50 rounded-lg p-4">
            <div class="flex items-center justify-between mb-3">
              <div class="text-text-primary font-bold">{{ record.date }}</div>
              <div class="flex gap-2">
                <span :class="record.directionCorrect ? 'text-red-up' : 'text-green-down'" class="text-sm">
                  {{ record.directionCorrect ? '✓ 方向正确' : '✗ 方向错误' }}
                </span>
                <span :class="record.rangeCorrect ? 'text-red-up' : 'text-green-down'" class="text-sm">
                  {{ record.rangeCorrect ? '✓ 区间命中' : '✗ 区间未中' }}
                </span>
              </div>
            </div>
            <div class="grid grid-cols-3 gap-4 text-sm">
              <div>
                <span class="text-text-secondary">预测:</span>
                <span class="text-text-primary ml-2">{{ record.predictedDirection }}</span>
              </div>
              <div>
                <span class="text-text-secondary">实际:</span>
                <span class="text-text-primary ml-2">{{ record.actualDirection }}</span>
              </div>
              <div>
                <span class="text-text-secondary">选股:</span>
                <span :class="record.stockWinRate >= 50 ? 'text-red-up' : 'text-green-down'" class="ml-2">
                  {{ record.stockWinRate.toFixed(0) }}% 胜率
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import * as echarts from 'echarts'

const directionChartRef = ref<HTMLElement>()
const rangeChartRef = ref<HTMLElement>()
const stockChartRef = ref<HTMLElement>()

const accuracy = ref({
  directionAccuracy: 85.3,
  rangeAccuracy: 72.6,
  stockWinRate: 68.4,
})

const historyRecords = ref([
  {
    date: '2026-06-25',
    predictedDirection: '偏多',
    actualDirection: '偏多',
    directionCorrect: true,
    rangeCorrect: true,
    stockWinRate: 75,
  },
  {
    date: '2026-06-24',
    predictedDirection: '震荡',
    actualDirection: '偏空',
    directionCorrect: false,
    rangeCorrect: false,
    stockWinRate: 45,
  },
  {
    date: '2026-06-23',
    predictedDirection: '偏多',
    actualDirection: '偏多',
    directionCorrect: true,
    rangeCorrect: true,
    stockWinRate: 80,
  },
])

onMounted(() => {
  initPieChart(directionChartRef.value!, accuracy.value.directionAccuracy)
  initPieChart(rangeChartRef.value!, accuracy.value.rangeAccuracy)
  initPieChart(stockChartRef.value!, accuracy.value.stockWinRate)
})

function initPieChart(element: HTMLElement, value: number) {
  const chart = echarts.init(element)

  const option = {
    backgroundColor: 'transparent',
    series: [
      {
        type: 'pie',
        radius: ['70%', '90%'],
        avoidLabelOverlap: false,
        label: { show: false },
        data: [
          { value: value, itemStyle: { color: '#f0c14b' } },
          { value: 100 - value, itemStyle: { color: 'rgba(79, 195, 247, 0.1)' } },
        ],
      },
    ],
  }

  chart.setOption(option)
}
</script>

<style scoped>
.nav-link {
  @apply px-4 py-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-navy-light transition-all;
}

.router-link-active {
  @apply bg-blue-accent/20 text-blue-accent;
}

.border-border {
  border-color: rgba(79, 195, 247, 0.18);
}
</style>
