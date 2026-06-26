<template>
  <div class="min-h-screen bg-navy-deep pt-6">
    <main class="max-w-7xl mx-auto px-4">
      <div class="mb-6">
        <h1 class="text-2xl font-bold bg-gradient-to-r from-gold via-white to-blue-accent bg-clip-text text-transparent">板块热力图</h1>
        <p class="text-text-secondary text-sm mt-1">实时追踪板块资金流向与涨跌分布</p>
      </div>

      <div class="grid grid-cols-4 gap-4 mb-6">
        <div class="bg-navy-card rounded-xl border border-border p-4">
          <div class="text-text-secondary text-sm mb-2">上涨板块</div>
          <div class="text-2xl font-bold text-red-up">{{ upCount }}</div>
        </div>
        <div class="bg-navy-card rounded-xl border border-border p-4">
          <div class="text-text-secondary text-sm mb-2">下跌板块</div>
          <div class="text-2xl font-bold text-green-down">{{ downCount }}</div>
        </div>
        <div class="bg-navy-card rounded-xl border border-border p-4">
          <div class="text-text-secondary text-sm mb-2">最强板块</div>
          <div class="text-lg font-bold text-red-up">{{ topSector?.name || '-' }}</div>
        </div>
        <div class="bg-navy-card rounded-xl border border-border p-4">
          <div class="text-text-secondary text-sm mb-2">最弱板块</div>
          <div class="text-lg font-bold text-green-down">{{ bottomSector?.name || '-' }}</div>
        </div>
      </div>

      <div class="bg-navy-card rounded-xl border border-border p-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-bold text-text-primary">板块涨跌幅</h2>
        </div>
        <div class="grid grid-cols-6 gap-2">
          <div v-for="sector in sectors" :key="sector.code" class="heatmap-cell rounded-lg p-3 cursor-pointer transition-all hover:scale-105" :style="getHeatmapStyle(sector.change)" @click="selectedSector = sector">
            <div class="text-sm font-bold text-white mb-1">{{ sector.name }}</div>
            <div class="text-xs text-white/90">{{ sector.change >= 0 ? '+' : '' }}{{ sector.change.toFixed(2) }}%</div>
            <div class="text-xs text-white/70 mt-1">领涨: {{ sector.leader }}</div>
          </div>
        </div>
      </div>

      <div v-if="selectedSector" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click="selectedSector = null">
        <div class="bg-navy-card rounded-2xl border border-border p-6 w-[600px]" @click.stop>
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-xl font-bold text-text-primary">{{ selectedSector.name }}</h3>
            <button @click="selectedSector = null" class="text-text-secondary hover:text-text-primary">X</button>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="bg-navy-light rounded-lg p-4">
              <div class="text-text-secondary text-sm mb-1">板块涨幅</div>
              <div :class="selectedSector.change >= 0 ? 'text-red-up' : 'text-green-down'" class="text-2xl font-bold">{{ selectedSector.change >= 0 ? '+' : '' }}{{ selectedSector.change.toFixed(2) }}%</div>
            </div>
            <div class="bg-navy-light rounded-lg p-4">
              <div class="text-text-secondary text-sm mb-1">成交量</div>
              <div class="text-2xl font-bold text-text-primary">{{ selectedSector.volume }}</div>
            </div>
            <div class="bg-navy-light rounded-lg p-4">
              <div class="text-text-secondary text-sm mb-1">领涨股</div>
              <div class="text-lg font-bold text-red-up">{{ selectedSector.leader }}</div>
            </div>
            <div class="bg-navy-light rounded-lg p-4">
              <div class="text-text-secondary text-sm mb-1">资金净流入</div>
              <div :class="selectedSector.netInflow >= 0 ? 'text-red-up' : 'text-green-down'" class="text-lg font-bold">{{ selectedSector.netInflow >= 0 ? '+' : '' }}{{ Math.abs(selectedSector.netInflow).toFixed(1) }}亿</div>
            </div>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-6 mt-6">
        <div class="bg-navy-card rounded-xl border border-border p-6">
          <h3 class="text-lg font-bold text-red-up mb-4">资金净流入TOP10</h3>
          <div class="space-y-2">
            <div v-for="(item, idx) in topInflowSectors" :key="item.code" class="flex items-center justify-between p-3 bg-navy-light rounded-lg">
              <div class="flex items-center gap-3">
                <span class="text-gold font-bold w-6">{{ idx + 1 }}</span>
                <span class="text-text-primary font-medium">{{ item.name }}</span>
              </div>
              <div class="text-right">
                <div class="text-red-up font-bold">+{{ Math.abs(item.netInflow).toFixed(1) }}亿</div>
              </div>
            </div>
          </div>
        </div>
        <div class="bg-navy-card rounded-xl border border-border p-6">
          <h3 class="text-lg font-bold text-green-down mb-4">资金净流出TOP10</h3>
          <div class="space-y-2">
            <div v-for="(item, idx) in topOutflowSectors" :key="item.code" class="flex items-center justify-between p-3 bg-navy-light rounded-lg">
              <div class="flex items-center gap-3">
                <span class="text-gold font-bold w-6">{{ idx + 1 }}</span>
                <span class="text-text-primary font-medium">{{ item.name }}</span>
              </div>
              <div class="text-right">
                <div class="text-green-down font-bold">{{ Math.abs(item.netInflow).toFixed(1) }}亿</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Sector {
  code: string
  name: string
  change: number
  volume: string
  leader: string
  netInflow: number
}

const sectors = ref<Sector[]>([
  { code: 'BK0001', name: '半导体', change: 3.52, volume: '892亿', leader: '中芯国际', netInflow: 45.2 },
  { code: 'BK0002', name: '人工智能', change: 2.87, volume: '1256亿', leader: '科大讯飞', netInflow: 38.5 },
  { code: 'BK0003', name: '新能源汽车', change: 2.34, volume: '2341亿', leader: '比亚迪', netInflow: 32.1 },
  { code: 'BK0004', name: '光伏', change: 1.95, volume: '876亿', leader: '隆基绿能', netInflow: 18.7 },
  { code: 'BK0005', name: '白酒', change: 1.23, volume: '654亿', leader: '贵州茅台', netInflow: 12.3 },
  { code: 'BK0006', name: '医药生物', change: 0.87, volume: '1234亿', leader: '恒瑞医药', netInflow: 8.9 },
  { code: 'BK0007', name: '银行', change: -0.45, volume: '456亿', leader: '招商银行', netInflow: -5.6 },
  { code: 'BK0008', name: '房地产', change: -1.23, volume: '321亿', leader: '万科A', netInflow: -12.4 },
  { code: 'BK0009', name: '钢铁', change: -1.87, volume: '234亿', leader: '宝钢股份', netInflow: -8.9 },
  { code: 'BK0010', name: '煤炭', change: -2.34, volume: '189亿', leader: '中国神华', netInflow: -15.6 },
  { code: 'BK0011', name: '军工', change: 1.56, volume: '567亿', leader: '中航沈飞', netInflow: 14.5 },
  { code: 'BK0012', name: '通信', change: 1.12, volume: '456亿', leader: '中兴通讯', netInflow: 9.8 },
  { code: 'BK0013', name: '传媒', change: 0.67, volume: '345亿', leader: '分众传媒', netInflow: 5.4 },
  { code: 'BK0014', name: '有色', change: -0.34, volume: '678亿', leader: '紫金矿业', netInflow: -3.2 },
  { code: 'BK0015', name: '电力', change: 0.23, volume: '543亿', leader: '长江电力', netInflow: 2.1 },
  { code: 'BK0016', name: '化工', change: -0.78, volume: '789亿', leader: '万华化学', netInflow: -6.5 },
  { code: 'BK0017', name: '计算机', change: 2.12, volume: '876亿', leader: '金山办公', netInflow: 22.3 },
  { code: 'BK0018', name: '建材', change: -1.45, volume: '321亿', leader: '海螺水泥', netInflow: -9.8 },
])

const selectedSector = ref<Sector | null>(null)

const upCount = computed(() => sectors.value.filter(s => s.change > 0).length)
const downCount = computed(() => sectors.value.filter(s => s.change < 0).length)
const topSector = computed(() => [...sectors.value].sort((a, b) => b.change - a.change)[0])
const bottomSector = computed(() => [...sectors.value].sort((a, b) => a.change - b.change)[0])

const topInflowSectors = computed(() => 
  [...sectors.value].sort((a, b) => b.netInflow - a.netInflow).slice(0, 10)
)
const topOutflowSectors = computed(() => 
  [...sectors.value].sort((a, b) => a.netInflow - b.netInflow).slice(0, 10)
)

function getHeatmapStyle(change: number) {
  const absChange = Math.abs(change)
  const intensity = Math.min(absChange / 3, 1)
  if (change >= 0) {
    return { backgroundColor: 'rgba(239, 68, 68, ' + (0.3 + intensity * 0.6) + ')' }
  } else {
    return { backgroundColor: 'rgba(34, 197, 94, ' + (0.3 + intensity * 0.6) + ')' }
  }
}
</script>

<style scoped>
.border-border { border-color: rgba(79, 195, 247, 0.18); }
.heatmap-cell { min-height: 100px; }
</style>
