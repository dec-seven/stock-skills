<template>
  <div class="min-h-screen bg-navy-deep pt-6">
    <main class="max-w-7xl mx-auto px-4 py-6">
      <div class="flex items-center justify-between mb-6">
        <div class="flex items-center gap-3">
          <h1 class="text-2xl font-bold text-text-primary">市场快讯</h1>
          <div class="flex items-center gap-2 text-sm">
            <span :class="connected ? 'text-green-down' : 'text-red-up'">{{ connected ? '实时' : '离线' }}</span>
            <span class="text-text-muted">{{ newsList.length }} 条</span>
          </div>
        </div>
        <button @click="clearNews" class="px-3 py-1.5 bg-navy-light text-text-secondary rounded-lg text-sm hover:bg-navy-card transition-all">清空</button>
      </div>

      <div class="space-y-3">
        <div v-for="news in newsList" :key="news.id" class="bg-navy-card rounded-xl border border-border p-4 hover:border-blue-accent/50 transition-all">
          <div class="flex items-start gap-3">
            <span class="text-xs text-text-muted whitespace-nowrap mt-0.5">{{ news.time }}</span>
            <div class="flex-1">
              <p class="text-text-primary text-sm leading-relaxed" v-html="formatContent(news.content)"></p>
              <div v-if="news.importance && news.importance > 0" class="mt-2">
                <span class="px-2 py-0.5 bg-gold/20 text-gold text-xs rounded">重要</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="newsList.length === 0" class="text-center py-20">
        <div class="text-4xl mb-4">📡</div>
        <p class="text-text-secondary">等待快讯推送...</p>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

interface News {
  id: number
  title: string
  content: string
  time: string
  source: string
  importance: number
}

const newsList = ref<News[]>([])
const connected = ref(false)
let eventSource: EventSource | null = null

const SSE_URL = 'http://localhost:8765/events'

const connectSSE = () => {
  eventSource = new EventSource(SSE_URL)
  
  eventSource.onopen = () => {
    connected.value = true
    console.log('[SSE] 已连接')
  }
  
  eventSource.onmessage = (event) => {
    try {
      const news: News = JSON.parse(event.data)
      newsList.value = [news, ...newsList.value].slice(0, 200)
    } catch (e) {
      console.error('[SSE] 解析失败:', e)
    }
  }
  
  eventSource.onerror = () => {
    connected.value = false
    console.log('[SSE] 连接断开，5秒后重连...')
    eventSource?.close()
    setTimeout(connectSSE, 5000)
  }
}

const formatContent = (content: string) => {
  return content.replace(/<b>/g, '<span class="text-gold font-bold">').replace(/<\/b>/g, '</span>')
}

const clearNews = () => {
  newsList.value = []
}

onMounted(() => {
  connectSSE()
})

onUnmounted(() => {
  eventSource?.close()
})
</script>

<style scoped>
.border-border {
  border-color: rgba(79, 195, 247, 0.18);
}
</style>
