<script setup lang="ts">
import { onMounted, ref, shallowRef, type Component, type ShallowRef } from "vue";
import WorkbenchPageSkeleton from "./WorkbenchPageSkeleton.vue";
import { registerExtendedAntdComponents } from "@/lib/antd";

const props = defineProps<{
  load: () => Promise<{ default: Component }>;
  tabs: string[];
  actionLabel: string;
  cacheKey: string;
}>();

const pageCache = new Map<string, Component>();
const page: ShallowRef<Component | null> = shallowRef(null);
const loadError = ref(false);
page.value = pageCache.get(props.cacheKey) ?? null;

async function loadPage() {
  loadError.value = false;
  if (page.value) return;

  try {
    const [, mod] = await Promise.all([
      registerExtendedAntdComponents(),
      props.load(),
    ]);
    const nextPage = mod.default;
    pageCache.set(props.cacheKey, nextPage);
    page.value = nextPage;
  } catch (error) {
    loadError.value = true;
    console.error("Failed to load workbench page", error);
  }
}

onMounted(() => {
  void loadPage();
});
</script>

<template>
  <component :is="page" v-if="page" />
  <div v-else-if="loadError" class="workbench-load-error">
    <p>页面加载失败，请重试</p>
    <button type="button" class="workbench-load-error-btn" @click="loadPage">重新加载</button>
  </div>
  <WorkbenchPageSkeleton v-else :tabs="tabs" :action-label="actionLabel" />
</template>

<style scoped>
.workbench-load-error {
  display: flex;
  min-height: calc(100vh - 112px);
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: var(--theme-nav-text);
  font-size: 14px;
}

.workbench-load-error-btn {
  height: 36px;
  padding: 0 16px;
  border: 0;
  border-radius: 999px;
  background: linear-gradient(180deg, var(--theme-brand-start, #ffd06d), var(--theme-brand-end, #ffaf29));
  color: var(--theme-brand-text, #523713);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}
</style>
