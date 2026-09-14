<script setup lang="ts">
defineProps<{
  tabs: string[];
  actionLabel: string;
}>();
</script>

<template>
  <div class="workbench-skeleton" aria-busy="true" aria-live="polite">
    <div class="workbench-skeleton-grid">
      <section class="workbench-skeleton-config">
        <div class="workbench-skeleton-tabs">
          <span
            v-for="(tab, index) in tabs"
            :key="tab"
            class="workbench-skeleton-tab"
            :class="{ active: index === 0 }"
          >
            {{ tab }}
          </span>
        </div>
        <div class="workbench-skeleton-card">
          <div class="workbench-skeleton-label" />
          <div class="workbench-skeleton-prompt" />
          <div class="workbench-skeleton-row">
            <div class="workbench-skeleton-field" />
            <div class="workbench-skeleton-field" />
          </div>
          <div class="workbench-skeleton-action">{{ actionLabel }}</div>
        </div>
      </section>
      <section class="workbench-skeleton-result">
        <div class="workbench-skeleton-result-head" />
        <div class="workbench-skeleton-result-body">
          <div class="workbench-skeleton-pulse" />
          <p>页面加载中...</p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.workbench-skeleton {
  min-height: calc(100vh - 112px);
  height: calc(100vh - 112px);
  background: var(--theme-page-base);
}

:global(.app-layout-desktop-side-nav) .workbench-skeleton {
  min-height: calc(100dvh - 66px);
  height: calc(100dvh - 66px);
}

.workbench-skeleton-grid {
  display: grid;
  grid-template-columns: minmax(320px, 31vw) minmax(0, 1fr);
  gap: 20px;
  width: 100%;
  min-width: 0;
  height: 100%;
}

.workbench-skeleton-config,
.workbench-skeleton-result {
  min-width: 0;
  min-height: 0;
}

.workbench-skeleton-tabs {
  display: flex;
  gap: 12px;
  margin-bottom: 14px;
}

.workbench-skeleton-tab {
  display: inline-flex;
  align-items: center;
  height: 36px;
  padding: 0 14px;
  border-radius: 16px;
  color: var(--theme-nav-text);
  font-size: 14px;
  font-weight: 700;
}

.workbench-skeleton-tab.active {
  background: var(--theme-control-bg, rgba(255, 255, 255, 0.72));
  color: var(--theme-title);
  box-shadow: 0 8px 18px var(--theme-shadow-soft);
}

.workbench-skeleton-card,
.workbench-skeleton-result {
  border: 1px solid var(--theme-panel-border);
  border-radius: 24px;
  background: var(--theme-page-base);
  box-shadow: 0 18px 36px var(--theme-shadow-soft);
}

.workbench-skeleton-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: calc(100% - 50px);
  padding: 16px;
}

.workbench-skeleton-label,
.workbench-skeleton-prompt,
.workbench-skeleton-field,
.workbench-skeleton-result-head,
.workbench-skeleton-pulse {
  border-radius: 14px;
  background: color-mix(in srgb, var(--theme-title) 8%, transparent);
  animation: workbench-skeleton-shimmer 1.2s ease-in-out infinite;
}

.workbench-skeleton-label,
.workbench-skeleton-result-head {
  width: 72px;
  height: 16px;
}

.workbench-skeleton-prompt {
  flex: 1;
  min-height: 160px;
}

.workbench-skeleton-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.workbench-skeleton-field {
  height: 40px;
}

.workbench-skeleton-action {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 44px;
  border-radius: 16px;
  background: linear-gradient(180deg, var(--theme-brand-start, #ffd06d), var(--theme-brand-end, #ffaf29));
  color: var(--theme-brand-text, #523713);
  font-size: 15px;
  font-weight: 800;
}

.workbench-skeleton-result {
  display: flex;
  flex-direction: column;
  padding: 16px 18px 18px;
  background: var(--theme-panel-bg);
}

.workbench-skeleton-result-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: var(--theme-nav-text);
  font-size: 14px;
}

.workbench-skeleton-pulse {
  width: 42px;
  height: 42px;
  border-radius: 999px;
}

@keyframes workbench-skeleton-shimmer {
  0%,
  100% {
    opacity: 0.55;
  }
  50% {
    opacity: 0.95;
  }
}

@media (max-width: 900px) {
  .workbench-skeleton,
  :global(.app-layout-desktop-side-nav) .workbench-skeleton {
    height: auto;
    min-height: calc(100dvh - 72px);
  }

  .workbench-skeleton-grid {
    grid-template-columns: 1fr;
  }

  .workbench-skeleton-card {
    height: auto;
  }

  .workbench-skeleton-result {
    min-height: 280px;
  }
}
</style>
