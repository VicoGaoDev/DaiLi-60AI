<script setup lang="ts">
import { computed } from "vue";
import type { PropType } from "vue";
import type { AdminAnalyticsSummary, AdminAnalyticsMetric } from "@/types";
import { getSuccessRateColor } from "@/lib/analyticsMetric";

type CardItem = {
  key: string;
  label: string;
  color: string;
  metric?: AdminAnalyticsMetric;
  plainValue?: number;
  clickable?: boolean;
  suffix?: string;
  chipText?: string;
  deltaText?: string;
};

function buildSuccessRateMetric(
  tasksCreated: AdminAnalyticsMetric,
  successTasks: AdminAnalyticsMetric,
): AdminAnalyticsMetric {
  const current = tasksCreated.current
    ? Number(((successTasks.current / tasksCreated.current) * 100).toFixed(1))
    : 0;
  const previous = tasksCreated.previous
    ? Number(((successTasks.previous / tasksCreated.previous) * 100).toFixed(1))
    : 0;
  const delta = Number((current - previous).toFixed(1));
  const delta_pct = previous === 0 ? null : Number(((delta / previous) * 100).toFixed(1));
  return { current, previous, delta, delta_pct };
}

const props = defineProps({
  summary: {
    type: Object as PropType<AdminAnalyticsSummary | null>,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  processingTasks: {
    type: Number,
    default: 0,
  },
});

const emit = defineEmits<{
  "card-click": [key: string];
}>();

const cards = computed<CardItem[]>(() => {
  if (!props.summary) return [];
  const successRateMetric = buildSuccessRateMetric(props.summary.tasks_created, props.summary.success_tasks);
  return [
    { key: "tasks_created", label: "任务总数", color: "#1890ff", metric: props.summary.tasks_created },
    { key: "success_tasks", label: "成功任务数", color: "#52c41a", metric: props.summary.success_tasks },
    { key: "failed_tasks", label: "失败任务数", color: "#ff4d4f", metric: props.summary.failed_tasks, clickable: true },
    { key: "processing_tasks", label: "进行中任务数", color: "#2f54eb", plainValue: props.processingTasks, chipText: "当前周期", deltaText: "来自任务状态占比" },
    { key: "credits_consumed", label: "消耗积分", color: "#fa8c16", metric: props.summary.credits_consumed },
    {
      key: "success_rate",
      label: "周期成功率",
      color: getSuccessRateColor(successRateMetric.current),
      metric: successRateMetric,
      suffix: "%",
    },
    { key: "active_users", label: "活跃用户数", color: "#13c2c2", metric: props.summary.active_users },
    { key: "new_users", label: "新增用户数", color: "#722ed1", metric: props.summary.new_users, clickable: true },
  ];
});

function formatDelta(metric?: AdminAnalyticsMetric, suffix = "") {
  if (!metric) return "";
  const sign = metric.delta > 0 ? "+" : "";
  if (metric.delta_pct == null) return `较上期 ${sign}${metric.delta}${suffix}`;
  return `较上期 ${sign}${metric.delta}${suffix} (${sign}${metric.delta_pct}%)`;
}

function handleCardClick(card: CardItem) {
  if (!card.clickable) return;
  emit("card-click", card.key);
}
</script>

<template>
  <a-spin :spinning="loading">
    <div class="kpi-grid">
      <div
        v-for="(card, index) in cards"
        :key="card.key"
        class="kpi-card warm-card motion-card-lift motion-fade-up"
        :class="{ 'kpi-card-clickable': card.clickable }"
        :style="{ '--motion-delay': `${180 + Math.min(index, 5) * 45}ms` }"
        @click="handleCardClick(card)"
      >
        <div class="kpi-head">
          <div class="kpi-label-wrap">
            <span class="kpi-dot" :style="{ background: card.color }" />
            <div class="kpi-label">{{ card.label }}</div>
          </div>
          <div class="kpi-chip">{{ card.chipText || (card.metric ? "周期对比" : "累计") }}</div>
        </div>
        <div class="kpi-value" :style="{ color: card.color }">
          {{ card.metric ? card.metric.current : (card.plainValue ?? 0) }}{{ card.suffix || "" }}
        </div>
        <div v-if="card.metric" class="kpi-meta">
          <span class="kpi-meta-label">上期</span>
          <span class="kpi-meta-value">{{ card.metric.previous }}{{ card.suffix || "" }}</span>
        </div>
        <div
          class="kpi-delta"
          :class="{ positive: (card.metric?.delta || 0) > 0, negative: (card.metric?.delta || 0) < 0 }"
        >
          {{ card.deltaText || (card.metric ? formatDelta(card.metric, card.suffix) : "当前总量") }}
        </div>
      </div>
    </div>
  </a-spin>
</template>

<style scoped lang="scss">
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}

.kpi-card {
  min-height: 126px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 18px 20px;
  gap: 10px;
  position: relative;
  overflow: hidden;
  transition: transform var(--motion-duration-swift) var(--motion-ease-soft), box-shadow var(--motion-duration-swift) var(--motion-ease-soft), border-color var(--motion-duration-swift) var(--motion-ease-soft);

  &::after {
    content: "";
    position: absolute;
    inset: 0 auto auto 0;
    width: 100%;
    height: 1px;
    background: linear-gradient(90deg, rgba(255, 193, 90, 0.85), rgba(255, 193, 90, 0));
  }

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 24px 42px rgba(236, 185, 88, 0.16);
    border-color: rgba(241, 210, 154, 0.92);
  }
}

.kpi-card-clickable {
  cursor: pointer;
}

.kpi-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.kpi-label-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kpi-dot {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  box-shadow: 0 0 0 4px rgba(255, 193, 90, 0.14);
}

.kpi-label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 600;
}

.kpi-chip {
  flex-shrink: 0;
  padding: 4px 8px;
  border-radius: 999px;
  background: var(--theme-panel-bg-strong);
  color: var(--theme-accent-text);
  font-size: 11px;
  font-weight: 700;
}

.kpi-value {
  font-size: 32px;
  line-height: 1.1;
  font-weight: 700;
  color: var(--theme-title);
  letter-spacing: -0.02em;
}

.kpi-meta {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-top: -2px;
}

.kpi-meta-label {
  color: var(--theme-subtitle);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.kpi-meta-value {
  color: var(--theme-title);
  font-size: 14px;
  font-weight: 700;
}

.kpi-delta {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  padding: 8px 10px 0;
  border-top: 1px dashed rgba(232, 213, 192, 0.9);
  margin: 0 -2px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.4);

  &.positive {
    color: #389e0d;
  }

  &.negative {
    color: #cf1322;
  }
}

@media (max-width: 700px) {
  .kpi-grid {
    grid-template-columns: 1fr;
  }
}
</style>
