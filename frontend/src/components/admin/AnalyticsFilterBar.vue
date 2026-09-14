<script setup lang="ts">
import { computed } from "vue";
import type { PropType } from "vue";
import type { Dayjs } from "dayjs";
import type { AdminAnalyticsGranularity, AdminUser, TaskSource, TaskType } from "@/types";

type FilterState = {
  status?: string;
  user_id?: string;
  source?: TaskSource;
  model?: string;
  mode?: TaskType;
  canvas_task_filter?: "all" | "canvas" | "non_canvas";
  include_unsafe_tasks: boolean;
  dateRange: [Dayjs, Dayjs] | null;
};

const props = defineProps({
  users: {
    type: Array as PropType<AdminUser[]>,
    default: () => [],
  },
  modelOptions: {
    type: Array as PropType<Array<{ label: string; value: string }>>,
    default: () => [],
  },
  filters: {
    type: Object as PropType<FilterState>,
    required: true,
  },
  granularity: {
    type: String as PropType<AdminAnalyticsGranularity>,
    required: true,
  },
  preset: {
    type: String,
    required: true,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  usersLoading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits<{
  (e: "update:granularity", value: AdminAnalyticsGranularity): void;
  (e: "preset-change", value: string): void;
  (e: "reset"): void;
  (e: "refresh"): void;
  (e: "user-dropdown-visible", open: boolean): void;
}>();

const presetOptions = computed(() => {
  if (props.granularity === "3hour") {
    return [
      { key: "today", label: "今日" },
      { key: "3d", label: "近 3 天" },
      { key: "7d", label: "近 7 天" },
      { key: "30d", label: "近 30 天" },
    ];
  }
  if (props.granularity === "week") {
    return [
      { key: "8w", label: "近 8 周" },
      { key: "12w", label: "近 12 周" },
    ];
  }
  if (props.granularity === "month") {
    return [
      { key: "6m", label: "近 6 月" },
      { key: "12m", label: "近 12 月" },
    ];
  }
  return [
    { key: "today", label: "今日" },
    { key: "3d", label: "近 3 天" },
    { key: "7d", label: "近 7 天" },
    { key: "30d", label: "近 30 天" },
  ];
});
</script>

<template>
  <div class="analytics-filter warm-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
    <div class="analytics-filter-row">
      <div class="analytics-filter-panel-compact">
        <a-radio-group
          :value="granularity"
          class="analytics-segmented-group analytics-granularity-group"
          button-style="solid"
          @update:value="emit('update:granularity', $event)"
        >
          <a-radio-button value="3hour">每3小时</a-radio-button>
          <a-radio-button value="day">按日</a-radio-button>
          <a-radio-button value="week">按周</a-radio-button>
          <a-radio-button value="month">按月</a-radio-button>
        </a-radio-group>
      </div>

      <div class="analytics-filter-panel-compact">
        <a-radio-group
          :value="preset"
          class="analytics-segmented-group analytics-segmented-group-secondary"
          button-style="solid"
          @update:value="emit('preset-change', $event)"
        >
          <a-radio-button
            v-for="item in presetOptions"
            :key="item.key"
            :value="item.key"
          >
            {{ item.label }}
          </a-radio-button>
        </a-radio-group>
      </div>

      <a-select
        v-model:value="filters.user_id"
        placeholder="全部用户"
        allow-clear
        show-search
        option-filter-prop="label"
        class="analytics-filter-select"
        :loading="usersLoading"
        @dropdownVisibleChange="emit('user-dropdown-visible', $event)"
      >
        <a-select-option
          v-for="user in users"
          :key="user.id"
          :value="user.id"
          :label="user.username"
        >
          {{ user.username }}
        </a-select-option>
      </a-select>

      <a-select
        v-model:value="filters.status"
        placeholder="全部状态"
        allow-clear
        class="analytics-filter-select"
      >
        <a-select-option value="pending">等待中</a-select-option>
        <a-select-option value="processing">处理中</a-select-option>
        <a-select-option value="success">成功</a-select-option>
        <a-select-option value="failed">失败</a-select-option>
      </a-select>

      <a-select
        v-model:value="filters.source"
        placeholder="全部来源"
        allow-clear
        class="analytics-filter-select"
      >
        <a-select-option value="web">Web</a-select-option>
        <a-select-option value="app">App</a-select-option>
        <a-select-option value="api">API</a-select-option>
      </a-select>

      <a-select
        v-model:value="filters.mode"
        placeholder="全部类型"
        allow-clear
        class="analytics-filter-select"
      >
        <a-select-option value="text_generate">文生图</a-select-option>
        <a-select-option value="image_edit">图编辑</a-select-option>
        <a-select-option value="inpaint">局部重绘</a-select-option>
        <a-select-option value="smart_cutout">智能抠图</a-select-option>
        <a-select-option value="promptReverse">提示词反推</a-select-option>
      </a-select>

      <a-select
        v-model:value="filters.model"
        placeholder="全部模型"
        allow-clear
        class="analytics-filter-select analytics-filter-model"
      >
        <a-select-option
          v-for="option in modelOptions"
          :key="option.value"
          :value="option.value"
        >
          {{ option.label }}
        </a-select-option>
      </a-select>

      <a-select
        v-model:value="filters.canvas_task_filter"
        class="analytics-filter-select analytics-filter-canvas"
      >
        <a-select-option value="all">全部任务</a-select-option>
        <a-select-option value="canvas">来自 Canvas</a-select-option>
        <a-select-option value="non_canvas">非 Canvas</a-select-option>
      </a-select>

      <a-select
        v-model:value="filters.include_unsafe_tasks"
        class="analytics-filter-select analytics-filter-unsafe"
      >
        <a-select-option :value="true">包含不合规错误</a-select-option>
        <a-select-option :value="false">不含不合规错误</a-select-option>
      </a-select>

      <a-range-picker
        v-model:value="filters.dateRange"
        class="analytics-filter-date"
      />
      <a-button class="analytics-action-btn analytics-action-btn-secondary" :loading="loading" @click="emit('reset')">
        重置
      </a-button>
      <a-button class="analytics-action-btn analytics-action-btn-secondary" :loading="loading" @click="emit('refresh')">
        刷新
      </a-button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.analytics-filter-select {
  width: 138px;
}

.analytics-filter-model {
  width: 168px;
}

.analytics-filter-unsafe {
  width: 168px;
}

.analytics-filter-canvas {
  width: 156px;
}

:deep(.analytics-granularity-group .ant-radio-button-wrapper) {
  padding-inline: 14px;
}

:deep(.analytics-filter-select .ant-select-selector) {
  border-radius: 12px !important;
  border-color: var(--theme-control-border) !important;
  background: var(--theme-control-bg) !important;
  box-shadow: none !important;
}

:deep(.analytics-filter-select.ant-select-focused .ant-select-selector) {
  border-color: var(--theme-border-accent) !important;
  box-shadow: 0 0 0 2px var(--theme-focus-ring) !important;
}

@media (max-width: 768px) {
  .analytics-filter-select,
  .analytics-filter-model,
  .analytics-filter-canvas,
  .analytics-filter-unsafe,
  .analytics-filter-date {
    width: 100%;
  }

  :deep(.analytics-granularity-group .ant-radio-button-wrapper) {
    padding-inline: 12px;
  }
}
</style>
