<template>
  <div class="min-h-screen bg-navy-deep">
    <NavBar />
    <main class="pt-14">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import NavBar from './components/NavBar.vue'
</script>
