<script setup lang="ts">
import { computed } from "vue";
import type { PropType } from "vue";
import type { AdminAnalyticsTimeseries } from "@/types";
import { getCurrentTheme } from "@/lib/theme";
import { VChart } from "./charting";

function chartLabelColor() {
  return getCurrentTheme() === "midnight" ? "#d8d8d8" : "#8c7458";
}

const props = defineProps({
  data: {
    type: Object as PropType<AdminAnalyticsTimeseries | null>,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits<{
  (e: "bucket-click", payload: { start?: string | null; end?: string | null }): void;
}>();

const labels = computed(() => props.data?.current.map((item) => item.label) || []);
const hasTrendData = computed(() => {
  if (!props.data) return false;
  return [...props.data.current, ...props.data.previous].some((item) => (
    item.tasks_created > 0
    || item.success_tasks > 0
    || item.failed_tasks > 0
    || item.credits_consumed > 0
    || item.new_users > 0
    || item.active_users > 0
  ));
});

const tasksOption = computed(() => ({
  color: ["#1890ff", "#91caff"],
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
  },
  legend: { top: 0 },
  grid: { left: 40, right: 20, top: 44, bottom: 28 },
  xAxis: { type: "category", data: labels.value },
  yAxis: { type: "value" },
  series: [
    {
      name: "当前周期任务数",
      type: "line",
      smooth: true,
      symbolSize: 8,
      areaStyle: { color: "rgba(24, 144, 255, 0.12)" },
      lineStyle: { width: 3 },
      data: props.data?.current.map((item) => item.tasks_created) || [],
    },
    {
      name: "上一周期任务数",
      type: "line",
      smooth: true,
      symbolSize: 7,
      lineStyle: { type: "dashed" },
      data: props.data?.previous.map((item) => item.tasks_created) || [],
    },
  ],
}));

const creditOption = computed(() => ({
  color: ["#fa8c16", "#ffd591", "#722ed1"],
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
  },
  legend: { top: 0 },
  grid: { left: 40, right: 20, top: 44, bottom: 28 },
  xAxis: { type: "category", data: labels.value },
  yAxis: [
    { type: "value", name: "积分" },
    { type: "value", name: "人数" },
  ],
  series: [
    {
      name: "当前周期积分",
      type: "bar",
      data: props.data?.current.map((item) => item.credits_consumed) || [],
      itemStyle: { color: "#fa8c16", borderRadius: [8, 8, 0, 0] },
    },
    {
      name: "上一周期积分",
      type: "bar",
      data: props.data?.previous.map((item) => item.credits_consumed) || [],
      itemStyle: { color: "#ffd591", borderRadius: [8, 8, 0, 0] },
    },
    {
      name: "新增用户",
      type: "line",
      yAxisIndex: 1,
      smooth: true,
      symbolSize: 8,
      lineStyle: { width: 3 },
      data: props.data?.current.map((item) => item.new_users) || [],
      itemStyle: { color: "#722ed1" },
    },
  ],
}));

function periodTotal(point?: { success_tasks?: number; failed_tasks?: number } | null) {
  if (!point) return 0;
  return Number(point.success_tasks || 0) + Number(point.failed_tasks || 0);
}

function topStatusKey(point?: { success_tasks?: number; failed_tasks?: number } | null) {
  if (!point) return null;
  if (Number(point.failed_tasks || 0) > 0) return "failed";
  if (Number(point.success_tasks || 0) > 0) return "success";
  return null;
}

function buildStatusStackData(
  points: Array<{ success_tasks?: number; failed_tasks?: number }> | undefined,
  key: "success_tasks" | "failed_tasks",
  color: string,
) {
  return (points || []).map((item) => {
    const value = Number(item[key] || 0);
    const isTop = topStatusKey(item) === (key === "failed_tasks" ? "failed" : "success");
    return {
      value: value || null,
      itemStyle: {
        color,
        borderRadius: isTop ? [8, 8, 0, 0] : 0,
      },
      label: {
        show: isTop && periodTotal(item) !== 0,
        position: "top",
        color: chartLabelColor(),
        fontSize: 10,
        fontWeight: 600,
        formatter: String(periodTotal(item)),
      },
    };
  });
}

const statusOption = computed(() => ({
  color: ["#52c41a", "#ff4d4f", "#b7eb8f", "#ffa39e"],
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
    formatter: (params: Array<{ dataIndex?: number; axisValue?: string; marker?: string; seriesName?: string }>) => {
      const index = params[0]?.dataIndex || 0;
      const current = props.data?.current[index];
      const previous = props.data?.previous[index];
      const marker = (name: string) => params.find((item) => item.seriesName === name)?.marker || "";
      return [
        params[0]?.axisValue || "",
        `${marker("当前成功")}当前成功：${Number(current?.success_tasks || 0)}`,
        `${marker("当前失败")}当前失败：${Number(current?.failed_tasks || 0)}`,
        `当前合计：${periodTotal(current)}`,
        `${marker("上一周期成功")}上一周期成功：${Number(previous?.success_tasks || 0)}`,
        `${marker("上一周期失败")}上一周期失败：${Number(previous?.failed_tasks || 0)}`,
        `上一周期合计：${periodTotal(previous)}`,
      ].join("<br/>");
    },
  },
  legend: { top: 0 },
  grid: { left: 40, right: 20, top: 56, bottom: 28 },
  xAxis: { type: "category", data: labels.value },
  yAxis: { type: "value" },
  series: [
    {
      name: "当前成功",
      type: "bar",
      stack: "current",
      data: buildStatusStackData(props.data?.current, "success_tasks", "#52c41a"),
    },
    {
      name: "当前失败",
      type: "bar",
      stack: "current",
      data: buildStatusStackData(props.data?.current, "failed_tasks", "#ff4d4f"),
    },
    {
      name: "上一周期成功",
      type: "bar",
      stack: "previous",
      data: buildStatusStackData(props.data?.previous, "success_tasks", "#b7eb8f"),
    },
    {
      name: "上一周期失败",
      type: "bar",
      stack: "previous",
      data: buildStatusStackData(props.data?.previous, "failed_tasks", "#ffa39e"),
    },
  ],
}));

function successRate(point?: { success_tasks?: number; tasks_created?: number } | null) {
  const total = Number(point?.tasks_created || 0);
  if (!total) return null;
  return Number(((Number(point?.success_tasks || 0) / total) * 100).toFixed(1));
}

const successRateOption = computed(() => ({
  color: ["#52c41a", "#b7eb8f"],
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
    formatter: (params: Array<{ dataIndex?: number; axisValue?: string; marker?: string; seriesName?: string }>) => {
      const index = params[0]?.dataIndex || 0;
      const current = props.data?.current[index];
      const previous = props.data?.previous[index];
      const currentRate = successRate(current);
      const previousRate = successRate(previous);
      const marker = (name: string) => params.find((item) => item.seriesName === name)?.marker || "";
      return [
        params[0]?.axisValue || "",
        `${marker("当前周期成功率")}当前周期成功率：${currentRate == null ? "-" : `${currentRate}%`}`,
        `当前成功 / 任务：${Number(current?.success_tasks || 0)} / ${Number(current?.tasks_created || 0)}`,
        `${marker("上一周期成功率")}上一周期成功率：${previousRate == null ? "-" : `${previousRate}%`}`,
        `上一周期成功 / 任务：${Number(previous?.success_tasks || 0)} / ${Number(previous?.tasks_created || 0)}`,
      ].join("<br/>");
    },
  },
  legend: { top: 0 },
  grid: { left: 48, right: 20, top: 44, bottom: 28 },
  xAxis: { type: "category", data: labels.value },
  yAxis: {
    type: "value",
    min: 0,
    max: 100,
    axisLabel: { formatter: "{value}%" },
  },
  series: [
    {
      name: "当前周期成功率",
      type: "line",
      smooth: true,
      symbolSize: 8,
      areaStyle: { color: "rgba(82, 196, 26, 0.12)" },
      lineStyle: { width: 3 },
      data: props.data?.current.map((item) => successRate(item)) || [],
    },
    {
      name: "上一周期成功率",
      type: "line",
      smooth: true,
      symbolSize: 7,
      lineStyle: { type: "dashed" },
      data: props.data?.previous.map((item) => successRate(item)) || [],
    },
  ],
}));

function handlePointClick(params: { dataIndex?: number }) {
  const point = props.data?.current[params.dataIndex || 0];
  if (!point) return;
  emit("bucket-click", { start: point.bucket_start, end: point.bucket_end });
}
</script>

<template>
  <a-spin :spinning="loading">
    <div v-if="hasTrendData" class="trend-grid">
      <div class="trend-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 220ms">
        <div class="trend-card-head">
          <div>
            <div class="trend-card-title">任务趋势对比</div>
            <div class="trend-card-desc">对比当前周期与上一周期的任务波动。</div>
          </div>
          <div class="trend-card-badge">折线图</div>
        </div>
        <VChart class="trend-chart" :option="tasksOption" autoresize @click="handlePointClick" />
      </div>
      <div class="trend-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 260ms">
        <div class="trend-card-head">
          <div>
            <div class="trend-card-title">积分与新增用户</div>
            <div class="trend-card-desc">同时观察投入和用户增长的节奏。</div>
          </div>
          <div class="trend-card-badge">混合图</div>
        </div>
        <VChart class="trend-chart" :option="creditOption" autoresize @click="handlePointClick" />
      </div>
      <div class="trend-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 300ms">
        <div class="trend-card-head">
          <div>
            <div class="trend-card-title">成功失败趋势对比</div>
            <div class="trend-card-desc">快速识别异常高峰和失败集中的时间段。</div>
          </div>
          <div class="trend-card-badge">柱状图</div>
        </div>
        <VChart class="trend-chart" :option="statusOption" autoresize @click="handlePointClick" />
      </div>
      <div class="trend-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 340ms">
        <div class="trend-card-head">
          <div>
            <div class="trend-card-title">成功率趋势对比</div>
            <div class="trend-card-desc">对照任务量变化，判断失败是量增还是质量下滑。</div>
          </div>
          <div class="trend-card-badge">折线图</div>
        </div>
        <VChart class="trend-chart" :option="successRateOption" autoresize @click="handlePointClick" />
      </div>
    </div>
    <div v-else class="trend-empty warm-card motion-fade-up" style="--motion-delay: 220ms">
      <a-empty class="warm-empty" description="当前筛选条件下暂无趋势数据">
        <template #description>
          <div class="empty-title">当前筛选条件下暂无趋势数据</div>
          <div class="empty-desc">调整时间范围、用户或状态后，可查看趋势图和周期对比。</div>
        </template>
      </a-empty>
    </div>
  </a-spin>
</template>

<style scoped lang="scss">
.trend-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.trend-empty {
  min-height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 28px 20px;
  background:
    radial-gradient(circle at top right, var(--theme-page-glow), transparent 34%),
    var(--theme-modal-bg);
}

.trend-card {
  min-height: 340px;
  padding: 18px 20px 14px;
  overflow: hidden;
  transition: transform var(--motion-duration-swift) var(--motion-ease-soft), box-shadow var(--motion-duration-swift) var(--motion-ease-soft), border-color var(--motion-duration-swift) var(--motion-ease-soft);

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 24px 42px rgba(236, 185, 88, 0.16);
    border-color: rgba(241, 210, 154, 0.92);
  }
}

.trend-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}

.trend-card-title {
  font-size: 14px;
  font-weight: 700;
  color: #5d4526;
}

.trend-card-desc {
  margin-top: 4px;
  color: #9a805b;
  font-size: 12px;
  line-height: 1.5;
}

.trend-card-badge {
  flex-shrink: 0;
  padding: 5px 10px;
  border-radius: 999px;
  background: var(--theme-panel-bg-strong);
  color: #a07d49;
  font-size: 11px;
  font-weight: 700;
}

.trend-chart {
  height: 280px;
}

.empty-title {
  color: #5d4526;
  font-size: 15px;
  font-weight: 700;
}

.empty-desc {
  margin-top: 6px;
  color: #9a805b;
  font-size: 12px;
}

@media (max-width: 900px) {
  .trend-grid {
    grid-template-columns: 1fr;
  }

  .trend-card {
    padding: 16px;
  }

  .trend-card-head {
    flex-direction: column;
  }
}
</style>
