/**
 * trip.ts — 全局行程状态管理（基于 Vue 3 reactive，零依赖）
 *
 * 职责：
 * 1. 用 reactive 维护全局状态（currentItinerary + currentPage）
 * 2. 初始化时从 localStorage 恢复，修改时自动持久化
 * 3. 对组件暴露统一接口，替代 ref + emit 的跨组件通信
 *
 * 为什么不用 Pinia？
 * → Pinia 需要额外安装依赖。这里用 Vue 3 内置的 reactive + computed
 *   即可实现同等效果，代码量极小，且无外部依赖。
 */
import { computed, reactive, watch } from "vue";

import type { Itinerary } from "../types";

type Page = "home" | "plan" | "history";

// ═══════════════════════════════════════════════════════════
// 持久化工具
// ═══════════════════════════════════════════════════════════

const STORAGE_KEY = "zhilv-yuntu-store";

interface PersistedState {
  currentItinerary: Itinerary | null;
  currentPage: Page;
}

function loadFromStorage(): Partial<PersistedState> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      return JSON.parse(raw) as PersistedState;
    }
  } catch {
    // 解析失败静默处理
  }
  return {};
}

function saveToStorage(state: PersistedState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // 存储失败静默处理（如隐私模式）
  }
}

// ═══════════════════════════════════════════════════════════
// Store 定义
// ═══════════════════════════════════════════════════════════

const saved = loadFromStorage();

const state = reactive<PersistedState>({
  currentItinerary: saved.currentItinerary ?? null,
  currentPage: saved.currentPage ?? "home",
});

// 自动持久化：任何状态变化都写入 localStorage
watch(
  () => ({ currentItinerary: state.currentItinerary, currentPage: state.currentPage }),
  (next) => saveToStorage(next),
  { deep: true }
);

// 对外暴露只读状态 + 操作方法
export const useTripStore = () => {
  const hasItinerary = computed(() => state.currentItinerary !== null);

  function setItinerary(itinerary: Itinerary) {
    state.currentItinerary = itinerary;
  }

  function updateItinerary(itinerary: Itinerary) {
    state.currentItinerary = itinerary;
  }

  function setPage(page: Page) {
    state.currentPage = page;
  }

  function clearItinerary() {
    state.currentItinerary = null;
    state.currentPage = "home";
  }

  function goHome() {
    state.currentPage = "home";
  }

  function goPlan() {
    if (state.currentItinerary) {
      state.currentPage = "plan";
    }
  }

  function goHistory() {
    state.currentPage = "history";
  }

  return reactive({
    // 状态（只读，防止组件直接修改）
    currentItinerary: computed(() => state.currentItinerary),
    currentPage: computed(() => state.currentPage),
    hasItinerary,

    // 操作
    setItinerary,
    updateItinerary,
    setPage,
    clearItinerary,
    goHome,
    goPlan,
    goHistory,
  });
};
