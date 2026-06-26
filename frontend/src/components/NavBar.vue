<template>
  <header class="bg-navy-card border-b border-border fixed top-0 left-0 right-0 z-50">
    <div class="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
      <div class="flex items-center gap-8">
        <router-link to="/" class="text-xl font-bold bg-gradient-to-r from-gold via-white to-blue-accent bg-clip-text text-transparent">
          股市早报
        </router-link>
        <nav class="flex gap-1">
          <router-link to="/" class="nav-item">
            <span class="nav-icon">🏠</span>
            <span>首页</span>
          </router-link>
          <router-link to="/tracker" class="nav-item">
            <span class="nav-icon">🎯</span>
            <span>选股跟踪</span>
          </router-link>
          <router-link to="/brief" class="nav-item">
            <span class="nav-icon">📊</span>
            <span>早报</span>
          </router-link>
          <router-link to="/heatmap" class="nav-item">
            <span class="nav-icon">🔥</span>
            <span>板块热力图</span>
          </router-link>
          <router-link to="/news" class="nav-item">
            <span class="nav-icon">📡</span>
            <span>市场快讯</span>
          </router-link>
        </nav>
      </div>
      <div class="flex items-center gap-3 text-sm text-text-secondary">
        <span>{{ today }}</span>
        <span class="w-2 h-2 rounded-full bg-green-down animate-pulse"></span>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import dayjs from 'dayjs'

const today = computed(() => dayjs().format('YYYY-MM-DD'))
</script>

<style scoped>
.border-border {
  border-color: rgba(79, 195, 247, 0.18);
}
.nav-item {
  @apply flex items-center gap-1.5 px-3 py-2 rounded-lg text-text-secondary text-sm hover:text-text-primary hover:bg-navy-light/50 transition-all;
}
.nav-item.router-link-active {
  @apply bg-blue-accent/15 text-blue-accent;
}
.nav-icon {
  @apply text-base;
}
</style>
