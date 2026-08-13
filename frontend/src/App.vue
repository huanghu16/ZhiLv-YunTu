<script setup lang="ts">
import { useTripStore } from "./stores/trip";

import Home from "./views/Home.vue";
import Result from "./views/Result.vue";
import History from "./views/History.vue";

const store = useTripStore();
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="app-header__title" @click="store.goHome">
        <span class="app-header__icon">🗺️</span>
        <span>智旅云图</span>
      </div>
      <nav class="app-header__nav">
        <button
          :class="['nav-btn', { 'nav-btn--active': store.currentPage === 'home' }]"
          @click="store.goHome"
        >
          规划
        </button>
        <button
          :class="['nav-btn', { 'nav-btn--active': store.currentPage === 'plan', 'nav-btn--disabled': !store.hasItinerary }]"
          :disabled="!store.hasItinerary"
          @click="store.goPlan"
        >
          行程计划
        </button>
        <button
          :class="['nav-btn', { 'nav-btn--active': store.currentPage === 'history' }]"
          @click="store.goHistory"
        >
          历史
        </button>
      </nav>
    </header>

    <main class="app-body">
      <Home v-if="store.currentPage === 'home'" />
      <Result v-else-if="store.currentPage === 'plan'" />
      <History v-else-if="store.currentPage === 'history'" />
    </main>
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background:
    linear-gradient(135deg, #eef2ff 0%, #f0fdfa 50%, #fefce8 100%);
  min-height: 100vh;
}

.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 32px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(98, 116, 164, 0.08);
  position: sticky;
  top: 0;
  z-index: 100;
}

.app-header__title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 20px;
  font-weight: 800;
  color: #394867;
  cursor: pointer;
}

.app-header__icon {
  font-size: 24px;
}

.app-header__nav {
  display: flex;
  gap: 8px;
}

.nav-btn {
  border: none;
  border-radius: 999px;
  padding: 8px 20px;
  background: transparent;
  color: #667085;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.nav-btn:hover {
  background: rgba(109, 130, 222, 0.08);
}

.nav-btn--active {
  background: linear-gradient(135deg, #6d82de 0%, #8a67cf 100%);
  color: #ffffff;
}

.nav-btn--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.nav-btn--disabled:hover {
  background: transparent;
}

.app-body {
  flex: 1;
  padding: 24px 32px;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
}

@media (max-width: 768px) {
  .app-header {
    padding: 12px 16px;
  }

  .app-body {
    padding: 16px;
  }
}
</style>
