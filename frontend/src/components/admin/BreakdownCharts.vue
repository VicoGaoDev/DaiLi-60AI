<script setup lang="ts">
import { computed } from "vue";
import type { PropType } from "vue";
import type { AdminAnalyticsBreakdown } from "@/types";
import { VChart } from "./charting";

const props = defineProps({
  data: {
    type: Object as PropType<AdminAnalyticsBreakdown | null>,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits<{
  (e: "filter-click", payload: { type: "status" | "source" | "mode" | "model" | "user" | "canvas"; value: string }): void;
}>();

const modelCompare = computed(() => props.data?.model_compare || []);
const apiAttemptPerformance = computed(() => props.data?.api_attempt_performance || []);

const hasApiAttemptPerformance = computed(() => (
  apiAttemptPerformance.value.some((item) => item.call_count > 0 || item.task_duration_count > 0 || item.download_count > 0)
));

function formatDurationSeconds(value: number | undefined) {
  const seconds = Number(value || 0);
  if (!Number.isFinite(seconds) || seconds <= 0) return "-";
  const durationMs = seconds * 1000;
  if (durationMs < 1000) return `${Math.round(durationMs)} ms`;
  return `${seconds.toFixed(2)} s`;
}

function formatDurationMs(value: number | undefined) {
  const durationMs = Number(value || 0);
  if (!Number.isFinite(durationMs) || durationMs <= 0) return "-";
  if (durationMs < 1000) return `${Math.round(durationMs)} ms`;
  return `${(durationMs / 1000).toFixed(2)} s`;
}

const hasBreakdownData = computed(() => {
  if (!props.data) return false;
  return hasApiAttemptPerformance.value || [
    ...props.data.status_breakdown,
    ...props.data.source_breakdown,
    ...props.data.mode_breakdown,
    ...(props.data.canvas_breakdown || []),
    ...props.data.model_breakdown,
    ...modelCompare.value,
    ...props.data.top_users_by_tasks,
    ...props.data.top_users_by_credit,
  ].some((item) => item.count > 0 || item.credit_cost > 0);
});

function statusLabel(value: string) {
  const map: Record<string, string> = {
    pending: "等待中",
    processing: "处理中",
    success: "成功",
    failed: "失败",
  };
  return map[value] || value;
}

function modeLabel(value: string) {
  if (value === "text_generate") return "文生图";
  if (value === "image_edit") return "图编辑";
  if (value === "inpaint") return "局部重绘";
  if (value === "smart_cutout") return "智能抠图";
  if (value === "promptReverse") return "提示词反推";
  if (value === "promptOptimize") return "提示词优化";
  return value;
}

function sourceLabel(value: string) {
  if (value === "app") return "App";
  if (value === "api") return "API";
  return "Web";
}

function canvasLabel(value: string) {
  if (value === "canvas") return "Canvas";
  return "普通生图";
}

const statusPieOption = computed(() => ({
  color: ["#52c41a", "#ff4d4f", "#fa8c16", "#91caff"],
  tooltip: {
    trigger: "item",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
  },
  legend: { bottom: 0 },
  series: [
    {
      type: "pie",
      radius: ["42%", "68%"],
      data: (props.data?.status_breakdown || []).map((item) => ({
        name: statusLabel(item.name),
        value: item.count,
        rawValue: item.name,
      })),
    },
  ],
}));

const modePieOption = computed(() => ({
  color: ["#1890ff", "#722ed1", "#13c2c2"],
  tooltip: {
    trigger: "item",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
  },
  legend: { bottom: 0 },
  series: [
    {
      type: "pie",
      radius: ["42%", "68%"],
      data: (props.data?.mode_breakdown || []).map((item) => ({
        name: modeLabel(item.name),
        value: item.count,
        rawValue: item.name,
      })),
    },
  ],
}));

const canvasPieOption = computed(() => ({
  color: ["#722ed1", "#13c2c2"],
  tooltip: {
    trigger: "item",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
  },
  legend: { bottom: 0 },
  series: [
    {
      type: "pie",
      radius: ["42%", "68%"],
      data: (props.data?.canvas_breakdown || []).map((item) => ({
        name: canvasLabel(item.name),
        value: item.count,
        rawValue: item.name,
      })),
    },
  ],
}));

const sourcePieOption = computed(() => ({
  color: ["#1890ff", "#722ed1"],
  tooltip: {
    trigger: "item",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
  },
  legend: { bottom: 0 },
  series: [
    {
      type: "pie",
      radius: ["42%", "68%"],
      data: (props.data?.source_breakdown || []).map((item) => ({
        name: sourceLabel(item.name),
        value: item.count,
        rawValue: item.name,
      })),
    },
  ],
}));

const modelCompareOption = computed(() => ({
  color: ["#1890ff", "#fa8c16", "#52c41a"],
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
    formatter: (params: Array<{ axisValue?: string; dataIndex?: number }>) => {
      const dataIndex = params[0]?.dataIndex ?? 0;
      const item = modelCompare.value[dataIndex];
      const name = item?.name || params[0]?.axisValue || "";
      if (!item) return name;
      return [
        name,
        `用量：${item.count}`,
        `成功 / 失败：${item.success_count} / ${item.failed_count}`,
        `成功率：${item.success_rate}%`,
        `平均耗时：${formatDurationSeconds(item.avg_duration_seconds)}`,
      ].join("<br/>");
    },
  },
  legend: { top: 0 },
  grid: { left: 40, right: 72, top: 44, bottom: 52 },
  xAxis: {
    type: "category",
    data: modelCompare.value.map((item) => item.name),
    axisLabel: { interval: 0, rotate: 18 },
  },
  yAxis: [
    {
      type: "value",
      name: "用量",
    },
    {
      type: "value",
      name: "平均耗时",
      splitLine: { show: false },
      axisLabel: { formatter: "{value}秒" },
    },
    {
      type: "value",
      name: "成功率",
      min: 0,
      max: 100,
      offset: 40,
      splitLine: { show: false },
      axisLabel: { formatter: "{value}%" },
    },
  ],
  series: [
    {
      name: "用量",
      type: "bar",
      yAxisIndex: 0,
      data: modelCompare.value.map((item) => item.count),
      itemStyle: { color: "#1890ff", borderRadius: [8, 8, 0, 0] },
    },
    {
      name: "平均耗时",
      type: "line",
      yAxisIndex: 1,
      smooth: true,
      symbolSize: 8,
      lineStyle: { width: 3 },
      data: modelCompare.value.map((item) => item.avg_duration_seconds ?? 0),
      itemStyle: { color: "#fa8c16" },
    },
    {
      name: "成功率",
      type: "line",
      yAxisIndex: 2,
      smooth: true,
      symbolSize: 8,
      lineStyle: { width: 3 },
      data: modelCompare.value.map((item) => item.success_rate),
      itemStyle: { color: "#52c41a" },
    },
  ],
}));

const apiAttemptPerformanceOption = computed(() => ({
  color: ["#2f54eb", "#fa8c16", "#52c41a"],
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
    formatter: (params: Array<{ axisValue?: string; dataIndex?: number }>) => {
      const dataIndex = params[0]?.dataIndex ?? 0;
      const item = apiAttemptPerformance.value[dataIndex];
      const name = item?.name || params[0]?.axisValue || "";
      if (!item) return name;
      return [
        name,
        `调用次数：${item.call_count}`,
        `平均任务耗时：${formatDurationSeconds(item.avg_task_duration_seconds)}`,
        `平均下载耗时：${formatDurationMs(item.avg_result_download_ms)}`,
        `下载样本数：${item.download_count}`,
      ].join("<br/>");
    },
  },
  legend: { top: 0 },
  grid: { left: 40, right: 72, top: 44, bottom: 56 },
  xAxis: {
    type: "category",
    data: apiAttemptPerformance.value.map((item) => item.name),
    axisLabel: { interval: 0, rotate: 18 },
  },
  yAxis: [
    {
      type: "value",
      name: "调用次数",
    },
    {
      type: "value",
      name: "平均耗时",
      splitLine: { show: false },
      axisLabel: { formatter: "{value}秒" },
    },
  ],
  series: [
    {
      name: "调用次数",
      type: "bar",
      yAxisIndex: 0,
      data: apiAttemptPerformance.value.map((item) => item.call_count),
      itemStyle: { color: "#2f54eb", borderRadius: [8, 8, 0, 0] },
    },
    {
      name: "平均任务耗时",
      type: "line",
      yAxisIndex: 1,
      smooth: true,
      symbolSize: 8,
      lineStyle: { width: 3 },
      data: apiAttemptPerformance.value.map((item) => item.avg_task_duration_seconds ?? 0),
      itemStyle: { color: "#fa8c16" },
    },
    {
      name: "平均下载耗时",
      type: "line",
      yAxisIndex: 1,
      smooth: true,
      symbolSize: 8,
      lineStyle: { width: 3 },
      data: apiAttemptPerformance.value.map((item) => (item.avg_result_download_ms || 0) / 1000),
      itemStyle: { color: "#52c41a" },
    },
  ],
}));

const userTaskOption = computed(() => ({
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
  },
  grid: { left: 48, right: 20, top: 20, bottom: 48 },
  xAxis: { type: "category", data: (props.data?.top_users_by_tasks || []).map((item) => item.name), axisLabel: { interval: 0, rotate: 18 } },
  yAxis: { type: "value" },
  series: [
    {
      type: "bar",
      data: (props.data?.top_users_by_tasks || []).map((item) => item.count),
      itemStyle: { color: "#13c2c2", borderRadius: [8, 8, 0, 0] },
    },
  ],
}));

const userCreditOption = computed(() => ({
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
  },
  grid: { left: 48, right: 20, top: 20, bottom: 48 },
  xAxis: { type: "category", data: (props.data?.top_users_by_credit || []).map((item) => item.name), axisLabel: { interval: 0, rotate: 18 } },
  yAxis: { type: "value" },
  series: [
    {
      type: "bar",
      data: (props.data?.top_users_by_credit || []).map((item) => item.credit_cost),
      itemStyle: { color: "#fa8c16", borderRadius: [8, 8, 0, 0] },
    },
  ],
}));

function getRawValue(data: unknown) {
  if (!data || typeof data !== "object") return "";
  return "rawValue" in data && typeof data.rawValue === "string" ? data.rawValue : "";
}

function handleStatusClick(params: { data?: unknown }) {
  const rawValue = getRawValue(params.data);
  if (rawValue) emit("filter-click", { type: "status", value: rawValue });
}

function handleModeClick(params: { data?: unknown }) {
  const rawValue = getRawValue(params.data);
  if (rawValue) emit("filter-click", { type: "mode", value: rawValue });
}

function handleSourceClick(params: { data?: unknown }) {
  const rawValue = getRawValue(params.data);
  if (rawValue) emit("filter-click", { type: "source", value: rawValue });
}

function handleCanvasClick(params: { data?: unknown }) {
  const rawValue = getRawValue(params.data);
  if (rawValue) emit("filter-click", { type: "canvas", value: rawValue });
}

function handleModelClick(params: { dataIndex?: number }) {
  const item = modelCompare.value[params.dataIndex || 0] || props.data?.model_breakdown[params.dataIndex || 0];
  if (item) emit("filter-click", { type: "model", value: item.name });
}

function handleUserTaskClick(params: { dataIndex?: number }) {
  const item = props.data?.top_users_by_tasks[params.dataIndex || 0];
  if (item) emit("filter-click", { type: "user", value: item.name });
}

function handleUserCreditClick(params: { dataIndex?: number }) {
  const item = props.data?.top_users_by_credit[params.dataIndex || 0];
  if (item) emit("filter-click", { type: "user", value: item.name });
}
</script>

<template>
  <a-spin :spinning="loading">
    <div v-if="hasBreakdownData" class="breakdown-layout">
      <div class="breakdown-pies">
        <div class="breakdown-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 220ms">
          <div class="breakdown-head">
            <div>
              <div class="breakdown-title">任务状态占比</div>
              <div class="breakdown-desc">查看整体结果健康度。</div>
            </div>
            <div class="breakdown-badge">饼图</div>
          </div>
          <VChart class="breakdown-chart" :option="statusPieOption" autoresize @click="handleStatusClick" />
        </div>
        <div class="breakdown-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 260ms">
          <div class="breakdown-head">
            <div>
              <div class="breakdown-title">来源分布（Web/App）</div>
              <div class="breakdown-desc">区分不同端的任务占比和消耗情况。</div>
            </div>
            <div class="breakdown-badge">饼图</div>
          </div>
          <VChart class="breakdown-chart" :option="sourcePieOption" autoresize @click="handleSourceClick" />
        </div>
        <div class="breakdown-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 300ms">
          <div class="breakdown-head">
            <div>
              <div class="breakdown-title">任务类型占比</div>
              <div class="breakdown-desc">区分生图、局部重绘和提示词反推的占用比例。</div>
            </div>
            <div class="breakdown-badge">饼图</div>
          </div>
          <VChart class="breakdown-chart" :option="modePieOption" autoresize @click="handleModeClick" />
        </div>
        <div class="breakdown-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 340ms">
          <div class="breakdown-head">
            <div>
              <div class="breakdown-title">Canvas / 普通生图占比</div>
              <div class="breakdown-desc">看画布任务是否在分流普通生图的用量。</div>
            </div>
            <div class="breakdown-badge">饼图</div>
          </div>
          <VChart class="breakdown-chart" :option="canvasPieOption" autoresize @click="handleCanvasClick" />
        </div>
      </div>
      <div class="breakdown-grid">
      <div class="breakdown-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 340ms">
        <div class="breakdown-head">
          <div>
            <div class="breakdown-title">模型用量 / 成功率 / 平均耗时</div>
            <div class="breakdown-desc">对照高频模型的使用量、成功率和单次平均接口耗时。</div>
          </div>
          <div class="breakdown-badge">对照</div>
        </div>
        <VChart class="breakdown-chart" :option="modelCompareOption" autoresize @click="handleModelClick" />
      </div>
      <div v-if="hasApiAttemptPerformance" class="breakdown-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 360ms">
        <div class="breakdown-head">
          <div>
            <div class="breakdown-title">接口调用次数 / 任务耗时 / 下载耗时</div>
            <div class="breakdown-desc">按实际调用接口统计结果 URL 图片下载速度和任务耗时。</div>
          </div>
          <div class="breakdown-badge">接口</div>
        </div>
        <VChart class="breakdown-chart" :option="apiAttemptPerformanceOption" autoresize />
      </div>
      <div class="breakdown-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 380ms">
        <div class="breakdown-head">
          <div>
            <div class="breakdown-title">用户生成次数 Top</div>
            <div class="breakdown-desc">定位高频使用用户。</div>
          </div>
          <div class="breakdown-badge">排行</div>
        </div>
        <VChart class="breakdown-chart" :option="userTaskOption" autoresize @click="handleUserTaskClick" />
      </div>
      <div class="breakdown-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 420ms">
        <div class="breakdown-head">
          <div>
            <div class="breakdown-title">用户消耗积分 Top</div>
            <div class="breakdown-desc">从消耗角度观察重点用户。</div>
          </div>
          <div class="breakdown-badge">排行</div>
        </div>
        <VChart class="breakdown-chart" :option="userCreditOption" autoresize @click="handleUserCreditClick" />
      </div>
      </div>
    </div>
    <div v-else class="breakdown-empty warm-card motion-fade-up" style="--motion-delay: 220ms">
      <a-empty class="warm-empty" description="当前筛选条件下暂无分布数据">
        <template #description>
          <div class="empty-title">当前筛选条件下暂无分布数据</div>
          <div class="empty-desc">当有任务、积分或用户数据时，这里会自动展示占比和排行图。</div>
        </template>
      </a-empty>
    </div>
  </a-spin>
</template>

<style scoped lang="scss">
.breakdown-layout,
.breakdown-pies,
.breakdown-grid {
  display: grid;
  gap: 14px;
}

.breakdown-pies {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.breakdown-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.breakdown-empty {
  min-height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 28px 20px;
  background:
    radial-gradient(circle at top right, rgba(255, 208, 109, 0.16), transparent 34%),
    var(--theme-modal-bg);
}

.breakdown-card {
  min-height: 320px;
  padding: 18px 20px 14px;
  overflow: hidden;
  transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 24px 42px rgba(236, 185, 88, 0.16);
    border-color: rgba(241, 210, 154, 0.92);
  }
}

.breakdown-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}

.breakdown-title {
  font-size: 14px;
  font-weight: 700;
  color: #5d4526;
}

.breakdown-desc {
  margin-top: 4px;
  color: #9a805b;
  font-size: 12px;
  line-height: 1.5;
}

.breakdown-badge {
  flex-shrink: 0;
  padding: 5px 10px;
  border-radius: 999px;
  background: var(--theme-panel-bg-strong);
  color: #a07d49;
  font-size: 11px;
  font-weight: 700;
}

.breakdown-chart {
  height: 260px;
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

@media (max-width: 1200px) {
  .breakdown-pies {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .breakdown-pies,
  .breakdown-grid {
    grid-template-columns: 1fr;
  }

  .breakdown-card {
    padding: 16px;
  }

  .breakdown-head {
    flex-direction: column;
  }
}
</style>
