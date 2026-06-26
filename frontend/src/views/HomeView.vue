<template>
  <div class="min-h-screen bg-navy-deep pt-6">
    <main class="max-w-7xl mx-auto px-4 py-8">
      <div class="text-center mb-12">
        <h2 class="text-5xl font-bold text-text-primary mb-4">智能投资决策平台</h2>
        <p class="text-xl text-text-secondary">基于多Agent架构的A股分析系统</p>
        <div class="flex gap-4 justify-center mt-8">
          <router-link to="/brief" class="px-6 py-3 bg-gold text-navy-deep font-bold rounded-lg hover:bg-gold-soft transition-all">查看今日早报</router-link>
          <router-link to="/tracker" class="px-6 py-3 bg-navy-light text-text-primary rounded-lg hover:bg-blue-accent/20 transition-all">选股跟踪</router-link>
        </div>
      </div>
      <div class="grid grid-cols-3 gap-6 mt-12">
        <div class="bg-navy-card rounded-2xl border border-border p-6 hover:border-blue-accent transition-all"><div class="text-4xl mb-4">📊</div><h3 class="text-xl font-bold text-text-primary mb-2">每日早报</h3><p class="text-text-secondary">自动生成盘前策略报告</p></div>
        <div class="bg-navy-card rounded-2xl border border-border p-6 hover:border-blue-accent transition-all"><div class="text-4xl mb-4">🎯</div><h3 class="text-xl font-bold text-text-primary mb-2">选股跟踪</h3><p class="text-text-secondary">实时跟踪入选标的收益曲线</p></div>
        <div class="bg-navy-card rounded-2xl border border-border p-6 hover:border-blue-accent transition-all"><div class="text-4xl mb-4">🔄</div><h3 class="text-xl font-bold text-text-primary mb-2">预测复盘</h3><p class="text-text-secondary">盘后验证方向准确率</p></div>
      </div>
      <div class="grid grid-cols-4 gap-6 mt-12">
        <div class="bg-navy-card rounded-2xl border border-border p-6 text-center"><div class="text-3xl font-bold text-gold">7</div><div class="text-text-secondary mt-2">Agent 协作</div></div>
        <div class="bg-navy-card rounded-2xl border border-border p-6 text-center"><div class="text-3xl font-bold text-blue-accent">100+</div><div class="text-text-secondary mt-2">历史报告</div></div>
        <div class="bg-navy-card rounded-2xl border border-border p-6 text-center"><div class="text-3xl font-bold text-red-up">85%</div><div class="text-text-secondary mt-2">方向准确率</div></div>
        <div class="bg-navy-card rounded-2xl border border-border p-6 text-center"><div class="text-3xl font-bold text-green-down">12%</div><div class="text-text-secondary mt-2">平均收益</div></div>
      </div>
    </main>
  </div>
</template>
<script setup lang="ts">
</script>
<style scoped>
.border-border { border-color: rgba(79, 195, 247, 0.18); }
</style>