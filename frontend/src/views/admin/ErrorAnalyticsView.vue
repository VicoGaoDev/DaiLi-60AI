<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { message } from "ant-design-vue";
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";
import { BugOutlined } from "@ant-design/icons-vue";
import { getAdminErrorAnalytics, getAdminErrorCategoryTimeseries, getAdminErrorTasks, getAdminHistoryDetail, getAdminVideoTaskDetail } from "@/api/admin";
import { getGenerationModels, getTaskScenes } from "@/api/config";
import { getVideoTaskScenes } from "@/api/videoConfig";
import { isSessionExpiredError } from "@/lib/authError";
import { VChart } from "@/components/admin/charting";
import HistoryDetailDialog from "@/components/history/HistoryDetailDialog.vue";
import VideoTaskDetailDialog from "@/components/video/VideoTaskDetailDialog.vue";
import type {
  AdminErrorAnalytics,
  AdminErrorCategoryTimeseries,
  AdminErrorTaskKind,
  AdminErrorTaskItem,
  ErrorTrendGranularity,
  GenerationModelOption,
  TaskSource,
  TaskSceneConfig,
  UserHistoryCard,
  VideoTaskResult,
  VideoTaskSceneConfig,
} from "@/types";

type DatePreset = "today" | "3d" | "7d" | "30d";
type FallbackFilterValue = "all" | "used" | "unused";

const loading = ref(false);
const preset = ref<DatePreset | undefined>("today");
const dateRange = ref<[Dayjs, Dayjs] | null>(null);
const analytics = ref<AdminErrorAnalytics | null>(null);
const errorTrend = ref<AdminErrorCategoryTimeseries | null>(null);
const taskKindFilter = ref<AdminErrorTaskKind>("image");
const sourceFilter = ref<TaskSource | undefined>(undefined);
const modelFilter = ref<string | undefined>(undefined);
const fallbackFilter = ref<FallbackFilterValue>("all");
const includeUnsafeTasks = ref(true);
const fallbackOnly = computed(() => fallbackFilter.value === "used");
const trendGranularity = ref<ErrorTrendGranularity>("3hour");
const selectedErrorCategory = ref<string | undefined>(undefined);
const selectedTaskErrorCategory = ref<string | undefined>(undefined);
const selectedBucketLabel = ref<string | undefined>(undefined);
const drilledDateRange = ref<[Dayjs, Dayjs] | null>(null);
const taskTableLoading = ref(false);
const taskTableItems = ref<AdminErrorTaskItem[]>([]);
const taskTableTotal = ref(0);
const taskTablePage = ref(1);
const generationModels = ref<GenerationModelOption[]>([]);
const taskScenes = ref<TaskSceneConfig[]>([]);
const videoTaskScenes = ref<VideoTaskSceneConfig[]>([]);
const imageDetailOpen = ref(false);
const imageDetailLoading = ref(false);
const imageDetailItem = ref<UserHistoryCard | null>(null);
const videoDetailOpen = ref(false);
const videoDetailLoading = ref(false);
const videoDetailItem = ref<VideoTaskResult | null>(null);
let activeDetailRequestKey = "";

const TASK_TABLE_PAGE_SIZE = 10;

const fallbackTriggerGroups = [
  {
    title: "HTTP 状态",
    desc: "主接口直接返回这些上游临时故障状态码时切换备用接口。",
    items: ["HTTP 502", "HTTP 503", "HTTP 504"],
  },
  {
    title: "临时上游故障关键词",
    desc: "主接口错误文案命中以下关键词时切换备用接口。",
    items: [
      "server is busy",
      "please retry later",
      "retry later",
      "try again later",
      "temporarily unavailable",
      "too many requests",
      "rate limit",
      "timeout",
      "timed out",
      "read timed out",
      "请求超时",
      "响应读取超时",
      "上游请求超时",
      "连接超时",
    ],
  },
  {
    title: "结果解析异常",
    desc: "上游响应成功但缺少配置的结果图字段时，也会尝试备用接口。",
    items: ["缺少配置路径对应的 base64 数据"],
  },
];

const taskColumns = computed(() => {
  const baseColumns = [
    { title: "用户", dataIndex: "username", width: 120 },
    { title: "模型", dataIndex: "model", width: 180 },
    { title: "类型", dataIndex: "task_type", width: 110 },
    { title: "来源", dataIndex: "source", width: 90 },
    { title: "状态", dataIndex: "status", width: 90 },
  ];
  if (fallbackOnly.value) {
    return [
      ...baseColumns,
      { title: "主接口", dataIndex: "primary_api_config_name", width: 150 },
      { title: "主接口 HTTP", dataIndex: "primary_http_status", width: 110 },
      { title: "主接口错误", dataIndex: "error_message", width: 320 },
      { title: "备用接口", dataIndex: "fallback_api_config_name", width: 150 },
      { title: "备用结果", dataIndex: "fallback_status", width: 110 },
      { title: "备用错误", dataIndex: "fallback_error_message", width: 320 },
      { title: "时间", dataIndex: "created_at", width: 168 },
      { title: "操作", key: "actions", width: 80, fixed: "right" as const },
    ];
  }
  return [
    ...baseColumns,
    { title: "备用接口", dataIndex: "used_fallback_api", width: 110 },
    { title: "错误信息", dataIndex: "error_message" },
    { title: "时间", dataIndex: "created_at", width: 168 },
    { title: "操作", key: "actions", width: 80, fixed: "right" as const },
  ];
});

const columns = [
  { title: "错误次数", dataIndex: "count", width: 120 },
  { title: "错误类别", dataIndex: "error_category", width: 200 },
  { title: "错误信息", dataIndex: "error_message", width: 720 },
  { title: "操作", key: "actions", width: 110, fixed: "right" as const },
];

const filteredItems = computed(() => analytics.value?.items || []);
const activeTaskErrorCategory = computed(() => selectedTaskErrorCategory.value || selectedErrorCategory.value);
const showTaskTable = computed(() => fallbackOnly.value || Boolean(activeTaskErrorCategory.value));
const taskKindLabel = computed(() => taskKindFilter.value === "video" ? "视频任务" : "图片任务");

const filteredFailedTaskCount = computed(() => (
  filteredItems.value.reduce((sum, item) => sum + item.count, 0)
));

const summaryCards = computed(() => {
  if (fallbackOnly.value) {
    return [
      {
        key: "total",
        label: selectedErrorCategory.value ? "当前钻取任务数" : "触发备用接口任务数",
        value: analytics.value?.fallback_task_total ?? 0,
        desc: selectedErrorCategory.value
          ? "当前选中错误类别在所选时间桶内触发备用接口的任务数量"
          : "当前时间范围内触发备用接口的任务数量",
        color: "#cf3f36",
      },
      {
        key: "success",
        label: "最终成功数",
        value: analytics.value?.fallback_success_tasks ?? 0,
        desc: selectedErrorCategory.value
          ? "当前选中错误类别对应任务里，最终成功的数量"
          : "当前时间范围内触发备用接口后最终成功的任务数量",
        color: "#389e0d",
      },
      {
        key: "failed",
        label: "最终失败数",
        value: analytics.value?.fallback_failed_tasks ?? 0,
        desc: selectedErrorCategory.value
          ? "当前选中错误类别对应任务里，最终失败的数量"
          : "当前时间范围内触发备用接口后最终失败的任务数量",
        color: "#d48806",
      },
      {
        key: "categories",
        label: selectedErrorCategory.value ? "已选错误类别" : "错误类别数",
        value: selectedErrorCategory.value ? 1 : (analytics.value?.distinct_error_categories ?? 0),
        desc: selectedErrorCategory.value ? "图表联动后当前锁定的错误类别" : "按主接口错误聚合后的不同错误类型数量",
        color: "#1677ff",
      },
      {
        key: "distinct",
        label: selectedErrorCategory.value ? "该类别原始文案数" : "原始错误文案数",
        value: filteredItems.value.length,
        desc: selectedErrorCategory.value ? "当前错误类别下去重后的原始错误文案数量" : "去重后的主接口错误文案数量",
        color: "#7c6cf2",
      },
    ];
  }

  return [
    {
      key: "total",
      label: selectedErrorCategory.value ? "当前钻取失败数" : "失败任务总数",
      value: selectedErrorCategory.value ? filteredFailedTaskCount.value : (analytics.value?.total_failed_tasks ?? 0),
      desc: selectedErrorCategory.value
        ? "当前选中错误类别在所选时间桶内的失败任务数量"
        : "当前时间范围内状态为失败的任务数量",
      color: "#cf3f36",
    },
    {
      key: "categories",
      label: selectedErrorCategory.value ? "已选错误类别" : "错误类别数",
      value: selectedErrorCategory.value ? 1 : (analytics.value?.distinct_error_categories ?? 0),
      desc: selectedErrorCategory.value ? "图表联动后当前锁定的错误类别" : "按错误类别聚合后的不同错误类型数量",
      color: "#d48806",
    },
    {
      key: "distinct",
      label: selectedErrorCategory.value ? "该类别原始文案数" : "原始错误文案数",
      value: filteredItems.value.length,
      desc: selectedErrorCategory.value ? "当前错误类别下去重后的原始错误文案数量" : "去重后的 error_message 原始文案数量",
      color: "#7c6cf2",
    },
  ];
});

const trendGranularityLabel = computed(() => {
  const labelMap: Record<ErrorTrendGranularity, string> = {
    "1hour": "1 小时",
    "3hour": "3 小时",
    "6hour": "6 小时",
  };
  return labelMap[trendGranularity.value];
});

const trendLabels = computed(() => errorTrend.value?.points.map((item) => item.label) || []);
const hasTrendData = computed(() => (
  (errorTrend.value?.series.length || 0) > 0
  && (errorTrend.value?.points.some((point) => point.total_failed_tasks > 0) || false)
));
const trendOption = computed(() => ({
  color: ["#cf3f36", "#d48806", "#7c6cf2", "#1890ff", "#13c2c2", "#52c41a"],
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
  },
  legend: { top: 0 },
  grid: { left: 40, right: 20, top: 48, bottom: 28 },
  xAxis: { type: "category", data: trendLabels.value },
  yAxis: { type: "value", minInterval: 1 },
  series: (errorTrend.value?.series || []).map((seriesItem, index) => ({
    name: `${seriesItem.error_category} (${seriesItem.total_count})`,
    type: "line",
    smooth: true,
    symbolSize: 7,
    lineStyle: {
      width: selectedErrorCategory.value === seriesItem.error_category || (!selectedErrorCategory.value && index === 0) ? 3 : 2,
      opacity: selectedErrorCategory.value && selectedErrorCategory.value !== seriesItem.error_category ? 0.35 : 1,
    },
    areaStyle: selectedErrorCategory.value === seriesItem.error_category || (!selectedErrorCategory.value && index === 0)
      ? { color: index === 0 ? "rgba(207, 63, 54, 0.12)" : "rgba(24, 144, 255, 0.10)" }
      : undefined,
    emphasis: { focus: "series" },
    data: errorTrend.value?.points.map((point) => point.categories[seriesItem.error_category] || 0) || [],
  })),
}));

const modelOptions = computed(() => {
  if (taskKindFilter.value === "video") {
    return videoTaskScenes.value.map((item) => ({
      value: item.scene_key,
      label: item.display_name || item.scene_label || item.scene_key,
    }));
  }
  const optionMap = new Map<string, string>();
  generationModels.value.forEach((item) => {
    optionMap.set(item.model_key, item.model_label);
  });
  taskScenes.value
    .filter((item) => item.scene_type === "image_edit")
    .forEach((item) => {
      optionMap.set(item.scene_key, item.display_name || item.scene_label);
    });
  optionMap.set("inpaint", "局部重绘");
  optionMap.set("smart_cutout", "智能抠图");
  return Array.from(optionMap.entries()).map(([value, label]) => ({ value, label }));
});

const imageModelOptions = computed(() => {
  const optionMap = new Map<string, string>();
  generationModels.value.forEach((item) => {
    optionMap.set(item.model_key, item.model_label);
  });
  taskScenes.value
    .filter((item) => item.scene_type === "image_edit")
    .forEach((item) => {
      optionMap.set(item.scene_key, item.display_name || item.scene_label);
    });
    optionMap.set("inpaint", "局部重绘");
    optionMap.set("smart_cutout", "智能抠图");
  return Array.from(optionMap.entries()).map(([value, label]) => ({ value, label }));
});

const videoModelOptions = computed(() => (
  videoTaskScenes.value.map((item) => ({
    value: item.scene_key,
    label: item.display_name || item.scene_label || item.scene_key,
  }))
));

function formatQueryDate(value?: Dayjs) {
  return value ? value.format("YYYY-MM-DDTHH:mm:ss") : undefined;
}

function getEffectiveQueryRange() {
  const effectiveRange = drilledDateRange.value || dateRange.value;
  if (!effectiveRange?.[0] || !effectiveRange?.[1]) return null;
  if (drilledDateRange.value) {
    return {
      start_date: formatQueryDate(effectiveRange[0]),
      end_date: formatQueryDate(effectiveRange[1]),
    };
  }
  return {
    start_date: formatQueryDate(effectiveRange[0].startOf("day")),
    end_date: formatQueryDate(effectiveRange[1].endOf("day")),
  };
}

function applyPreset(nextPreset: DatePreset) {
  const now = dayjs();
  preset.value = nextPreset;
  if (nextPreset === "today") {
    dateRange.value = [now.startOf("day"), now.endOf("day")];
    return;
  }
  if (nextPreset === "3d") {
    dateRange.value = [now.subtract(2, "day").startOf("day"), now.endOf("day")];
    return;
  }
  if (nextPreset === "7d") {
    dateRange.value = [now.subtract(6, "day").startOf("day"), now.endOf("day")];
    return;
  }
  dateRange.value = [now.subtract(29, "day").startOf("day"), now.endOf("day")];
}

function handlePresetChange(value: DatePreset) {
  applyPreset(value);
  load();
}

function handleDateRangeChange() {
  preset.value = undefined;
  selectedErrorCategory.value = undefined;
  selectedTaskErrorCategory.value = undefined;
  selectedBucketLabel.value = undefined;
  drilledDateRange.value = null;
  if (dateRange.value?.[0] && dateRange.value?.[1]) {
    load();
  }
}

function handleReset() {
  applyPreset("today");
  taskKindFilter.value = "image";
  sourceFilter.value = undefined;
  modelFilter.value = undefined;
  fallbackFilter.value = "all";
  includeUnsafeTasks.value = true;
  trendGranularity.value = "3hour";
  selectedErrorCategory.value = undefined;
  selectedTaskErrorCategory.value = undefined;
  selectedBucketLabel.value = undefined;
  drilledDateRange.value = null;
  load();
}

function handleTrendGranularityChange(value: ErrorTrendGranularity) {
  trendGranularity.value = value;
  selectedErrorCategory.value = undefined;
  selectedTaskErrorCategory.value = undefined;
  selectedBucketLabel.value = undefined;
  drilledDateRange.value = null;
  load();
}

function handleFallbackFilterChange() {
  selectedErrorCategory.value = undefined;
  selectedTaskErrorCategory.value = undefined;
  selectedBucketLabel.value = undefined;
  drilledDateRange.value = null;
  load();
}

function handleTaskKindChange() {
  modelFilter.value = undefined;
  selectedErrorCategory.value = undefined;
  selectedTaskErrorCategory.value = undefined;
  selectedBucketLabel.value = undefined;
  drilledDateRange.value = null;
  taskTableItems.value = [];
  taskTableTotal.value = 0;
  taskTablePage.value = 1;
  load();
}

async function loadModelOptions() {
  try {
    const [models, scenes, videoScenes] = await Promise.all([getGenerationModels(), getTaskScenes(), getVideoTaskScenes()]);
    generationModels.value = models;
    taskScenes.value = scenes;
    videoTaskScenes.value = videoScenes;
  } catch {
    generationModels.value = [];
    taskScenes.value = [];
    videoTaskScenes.value = [];
  }
}

async function load() {
  if (!dateRange.value?.[0] || !dateRange.value?.[1]) return;
  loading.value = true;
  try {
    const queryRange = getEffectiveQueryRange();
    const [analyticsResult, trendResult] = await Promise.all([
      getAdminErrorAnalytics({
        task_kind: taskKindFilter.value,
        start_date: queryRange?.start_date,
        end_date: queryRange?.end_date,
        source: sourceFilter.value,
        model: modelFilter.value,
        error_category: selectedErrorCategory.value,
        used_fallback_api: fallbackFilter.value === "all" ? undefined : fallbackFilter.value === "used",
        include_unsafe_tasks: includeUnsafeTasks.value,
      }),
      getAdminErrorCategoryTimeseries({
        task_kind: taskKindFilter.value,
        granularity: trendGranularity.value,
        start_date: formatQueryDate(dateRange.value[0].startOf("day")),
        end_date: formatQueryDate(dateRange.value[1].endOf("day")),
        source: sourceFilter.value,
        model: modelFilter.value,
        used_fallback_api: fallbackFilter.value === "all" ? undefined : fallbackFilter.value === "used",
        include_unsafe_tasks: includeUnsafeTasks.value,
        limit: 6,
      }),
    ]);
    analytics.value = analyticsResult;
    errorTrend.value = trendResult;
    taskTablePage.value = 1;
    await loadTaskTable(1);
  } catch (err: unknown) {
    if (isSessionExpiredError(err)) return;
    message.error("获取错误统计失败");
  } finally {
    loading.value = false;
  }
}

async function loadTaskTable(page = taskTablePage.value) {
  if (!dateRange.value?.[0] || !dateRange.value?.[1] || (!fallbackOnly.value && !activeTaskErrorCategory.value)) {
    taskTableItems.value = [];
    taskTableTotal.value = 0;
    taskTablePage.value = 1;
    return;
  }
  taskTableLoading.value = true;
  try {
    const queryRange = getEffectiveQueryRange();
    const res = await getAdminErrorTasks({
      task_kind: taskKindFilter.value,
      page,
      page_size: TASK_TABLE_PAGE_SIZE,
      start_date: queryRange?.start_date,
      end_date: queryRange?.end_date,
      source: sourceFilter.value,
      model: modelFilter.value,
      error_category: activeTaskErrorCategory.value,
      used_fallback_api: fallbackFilter.value === "all" ? undefined : fallbackFilter.value === "used",
      include_unsafe_tasks: includeUnsafeTasks.value,
    });
    taskTableItems.value = res.items;
    taskTableTotal.value = res.total;
    taskTablePage.value = page;
  } catch (err: unknown) {
    if (isSessionExpiredError(err)) return;
    message.error("获取错误任务明细失败");
  } finally {
    taskTableLoading.value = false;
  }
}

function getErrorRowKey(record: AdminErrorAnalytics["items"][number]) {
  return `${record.error_category}-${record.error_message}`;
}

function handleTrendChartClick(params: { seriesName?: string; dataIndex?: number }) {
  const rawName = (params.seriesName || "").trim();
  const category = rawName.replace(/\s*\(\d+\)\s*$/, "").trim();
  if (!category) return;
  const point = typeof params.dataIndex === "number" ? errorTrend.value?.points[params.dataIndex] : null;
  if (
    selectedErrorCategory.value === category
    && selectedBucketLabel.value
    && point?.label === selectedBucketLabel.value
  ) {
    clearErrorCategoryFilter();
    return;
  }
  selectedErrorCategory.value = category;
  selectedTaskErrorCategory.value = undefined;
  selectedBucketLabel.value = point?.label;
  if (point?.bucket_start && point?.bucket_end) {
    drilledDateRange.value = [dayjs(point.bucket_start), dayjs(point.bucket_end)];
  } else {
    drilledDateRange.value = null;
  }
  load();
}

function clearErrorCategoryFilter() {
  selectedErrorCategory.value = undefined;
  selectedTaskErrorCategory.value = undefined;
  selectedBucketLabel.value = undefined;
  drilledDateRange.value = null;
  load();
}

function openErrorTaskList(record: AdminErrorAnalytics["items"][number]) {
  selectedTaskErrorCategory.value = record.error_category;
  void loadTaskTable(1);
}

function clearTaskCategoryFilter() {
  selectedTaskErrorCategory.value = undefined;
  void loadTaskTable(1);
}

function fmtTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function modeLabel(value: string) {
  if (value === "text_generate") return "文生图";
  if (value === "image_edit") return "图编辑";
  if (value === "inpaint") return "局部重绘";
  if (value === "smart_cutout") return "智能抠图";
  if (value === "promptReverse") return "提示词反推";
  if (value === "promptOptimize") return "提示词优化";
  if (value === "text_to_video") return "文生视频";
  if (value === "image_to_video") return "图生视频";
  return value;
}

function sourceLabel(value: string) {
  if (value === "app") return "App";
  if (value === "api") return "API";
  return "Web";
}

function modelLabel(value: string) {
  if (!value) return "-";
  return modelOptions.value.find((item) => item.value === value)?.label || value;
}

function statusLabel(value: string) {
  const map: Record<string, string> = {
    pending: "等待中",
    queued: "排队中",
    processing: "处理中",
    success: "成功",
    failed: "失败",
  };
  return map[value] || value;
}

function taskErrorText(record: AdminErrorTaskItem) {
  return record.error_message || "-";
}

function fallbackStatusLabel(value?: AdminErrorTaskItem["fallback_status"]) {
  if (value === "success") return "成功";
  if (value === "failed") return "失败";
  if (value === "partial") return "部分成功";
  return "未调用";
}

function fallbackStatusClass(value?: AdminErrorTaskItem["fallback_status"]) {
  if (value === "success") return "category-badge-success";
  if (value === "failed") return "category-badge-danger";
  if (value === "partial") return "category-badge-warning";
  return "";
}

async function openTaskDetail(record: AdminErrorTaskItem) {
  if (taskKindFilter.value === "video") {
    videoDetailOpen.value = true;
    videoDetailLoading.value = true;
    videoDetailItem.value = null;
  } else {
    imageDetailOpen.value = true;
    imageDetailLoading.value = true;
    imageDetailItem.value = null;
  }
  const requestKey = record.task_id;
  activeDetailRequestKey = requestKey;
  try {
    const detail = taskKindFilter.value === "video"
      ? await getAdminVideoTaskDetail(record.task_id)
      : await getAdminHistoryDetail({
          item_type: "task",
          task_id: record.task_id,
        });
    if (activeDetailRequestKey !== requestKey) return;
    if (taskKindFilter.value === "video") {
      videoDetailItem.value = detail as VideoTaskResult;
    } else {
      imageDetailItem.value = detail as UserHistoryCard;
    }
  } catch {
    if (activeDetailRequestKey !== requestKey) return;
    if (taskKindFilter.value === "video") {
      videoDetailOpen.value = false;
    } else {
      imageDetailOpen.value = false;
    }
    message.error("获取任务详情失败");
  } finally {
    if (activeDetailRequestKey === requestKey) {
      imageDetailLoading.value = false;
      videoDetailLoading.value = false;
    }
  }
}

onMounted(async () => {
  applyPreset("today");
  await loadModelOptions();
  load();
});
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <BugOutlined />
        </div>
        <div>
          <div class="warm-page-title">错误统计</div>
          <div class="warm-page-desc">查看失败任务分布，并按错误类别聚合分析趋势与明细；使用备用接口时可直接查看主接口报错和备用结果。</div>
        </div>
      </div>
      <div v-if="analytics" class="page-period-chip">
        {{ analytics.range_label }}
      </div>
    </div>

    <div class="analytics-filter warm-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <div class="analytics-filter-row">
        <a-range-picker
          v-model:value="dateRange"
          :placeholder="['开始日期', '结束日期']"
          class="analytics-filter-date"
          @change="handleDateRangeChange"
        />
        <a-select
          v-model:value="taskKindFilter"
          class="analytics-filter-select analytics-task-kind-select"
          @change="handleTaskKindChange"
        >
          <a-select-option value="image">图片任务</a-select-option>
          <a-select-option value="video">视频任务</a-select-option>
        </a-select>
        <a-select
          v-model:value="sourceFilter"
          allow-clear
          class="analytics-filter-select analytics-filter-source"
          placeholder="全部来源"
          @change="load"
        >
          <a-select-option value="web">Web</a-select-option>
          <a-select-option value="api">API</a-select-option>
        </a-select>
        <a-select
          v-model:value="modelFilter"
          allow-clear
          show-search
          class="analytics-filter-select"
          placeholder="全部模型"
          :options="modelOptions"
          option-filter-prop="label"
          @change="load"
        />
        <a-select
          v-model:value="fallbackFilter"
          class="analytics-filter-select analytics-fallback-select"
          @change="handleFallbackFilterChange"
        >
          <a-select-option value="all">备用接口：全部</a-select-option>
          <a-select-option value="used">备用接口：有</a-select-option>
          <a-select-option value="unused">备用接口：无</a-select-option>
        </a-select>
        <a-select
          v-model:value="includeUnsafeTasks"
          class="analytics-filter-select analytics-unsafe-select"
          @change="load"
        >
          <a-select-option :value="true">包含不合规错误</a-select-option>
          <a-select-option :value="false">不含不合规错误</a-select-option>
        </a-select>
        <div class="analytics-filter-panel-compact">
          <a-radio-group
            :value="preset"
            class="analytics-segmented-group analytics-segmented-group-secondary"
            button-style="solid"
            @update:value="handlePresetChange"
          >
            <a-radio-button value="today">今日</a-radio-button>
            <a-radio-button value="3d">近 3 天</a-radio-button>
            <a-radio-button value="7d">近 7 天</a-radio-button>
            <a-radio-button value="30d">近 30 天</a-radio-button>
          </a-radio-group>
        </div>
        <a-button type="primary" class="analytics-action-btn" :loading="loading" @click="load">查询</a-button>
        <a-button class="analytics-action-btn analytics-action-btn-secondary" @click="handleReset">重置</a-button>
      </div>
    </div>

    <div class="fallback-trigger-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 150ms">
      <div class="fallback-trigger-head">
        <div>
          <div class="table-card-title">备用接口触发条件</div>
          <div class="table-card-desc">以下规则为静态记录，和图片生成 worker 的备用接口判断保持一致；命中后会尝试调用绑定的备用接口。</div>
        </div>
        <span class="fallback-trigger-note">图片任务</span>
      </div>
      <div class="fallback-trigger-grid">
        <div v-for="group in fallbackTriggerGroups" :key="group.title" class="fallback-trigger-group">
          <div class="fallback-trigger-group-title">{{ group.title }}</div>
          <div class="fallback-trigger-group-desc">{{ group.desc }}</div>
          <div class="fallback-trigger-tags">
            <span v-for="item in group.items" :key="item" class="fallback-trigger-tag">{{ item }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="summary-grid">
      <div
        v-for="(item, index) in summaryCards"
        :key="item.key"
        class="summary-card warm-card motion-card-lift motion-fade-up"
        :style="{ '--motion-delay': `${160 + index * 40}ms` }"
      >
        <div class="summary-card-head">
          <span class="summary-card-label">{{ item.label }}</span>
          <span class="summary-card-dot" :style="{ background: item.color }" />
        </div>
        <div class="summary-card-value" :style="{ color: item.color }">{{ item.value }}</div>
        <div class="summary-card-desc">{{ item.desc }}</div>
      </div>
    </div>

    <div class="warm-card trend-card motion-card-lift motion-fade-up" style="--motion-delay: 220ms">
      <div class="table-card-head">
        <div>
          <div class="table-card-title">错误类别趋势</div>
          <div class="table-card-desc">
            {{
              fallbackOnly
                ? `按 ${trendGranularityLabel} 展示触发备用接口的${taskKindLabel}主接口失败 Top 6 趋势。`
                : `按 ${trendGranularityLabel} 展示当前范围内 ${taskKindLabel} Top 6 错误类别变化趋势。`
            }}
          </div>
        </div>
        <div class="trend-card-actions">
          <a-radio-group
            :value="trendGranularity"
            class="analytics-segmented-group analytics-segmented-group-secondary trend-granularity-group"
            button-style="solid"
            @update:value="handleTrendGranularityChange"
          >
            <a-radio-button value="1hour">1 小时</a-radio-button>
            <a-radio-button value="3hour">3 小时</a-radio-button>
            <a-radio-button value="6hour">6 小时</a-radio-button>
          </a-radio-group>
          <div v-if="selectedErrorCategory" class="linked-filter-chip-wrap">
            <span class="linked-filter-chip">已筛选：{{ selectedErrorCategory }}</span>
            <span v-if="selectedBucketLabel" class="linked-filter-chip linked-filter-chip-secondary">时间桶：{{ selectedBucketLabel }}</span>
            <a-button type="link" size="small" class="clear-filter-btn" @click="clearErrorCategoryFilter">清除</a-button>
          </div>
        </div>
      </div>
      <div v-if="hasTrendData" class="trend-chart-wrap">
        <VChart class="trend-chart" :option="trendOption" autoresize @click="handleTrendChartClick" />
      </div>
      <div v-else class="trend-empty">
        <a-empty description="当前时间范围内暂无错误趋势数据" />
      </div>
    </div>

    <div class="warm-card warm-table-card motion-card-lift motion-fade-up" style="--motion-delay: 260ms">
      <div class="table-card-head">
        <div>
          <div class="table-card-title">错误明细</div>
          <div class="table-card-desc">
            {{
              selectedErrorCategory
                ? `当前仅展示“${selectedErrorCategory}”在${selectedBucketLabel || "当前范围"}内的${taskKindLabel}明细。`
                : fallbackOnly
                  ? `按主接口失败类别聚合展示使用过备用接口的${taskKindLabel}，并保留每类的示例错误文案。`
                  : `按错误类别聚合展示${taskKindLabel}，并保留每类的示例错误文案。`
            }}
          </div>
        </div>
      </div>
      <a-table
        :columns="columns"
        :data-source="filteredItems"
        :loading="loading"
        :pagination="false"
        :row-key="getErrorRowKey"
        :scroll="{ x: 1160 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'count'">
            <span class="count-badge">{{ record.count }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'error_message'">
            <div class="error-message-cell">{{ record.error_message }}</div>
          </template>
          <template v-else-if="column.dataIndex === 'error_category'">
            <span class="category-badge">{{ record.error_category }}</span>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-button type="link" size="small" class="table-detail-btn" @click="openErrorTaskList(record)">
              错误任务
            </a-button>
          </template>
        </template>
        <template #emptyText>
          <a-empty :description="`当前时间范围内暂无${taskKindLabel}错误记录`" />
        </template>
      </a-table>
    </div>

    <div v-if="showTaskTable" class="warm-card warm-table-card motion-card-lift motion-fade-up" style="--motion-delay: 300ms">
      <div class="table-card-head">
        <div>
          <div class="table-card-title">{{ fallbackOnly ? "备用接口任务情况" : "错误任务列表" }}</div>
          <div class="table-card-desc">
            {{
              fallbackOnly
                ? (
                  activeTaskErrorCategory
                    ? (selectedBucketLabel ? `查看“${activeTaskErrorCategory}”在 ${selectedBucketLabel} 触发备用接口的${taskKindLabel}。` : `查看“${activeTaskErrorCategory}”对应的备用接口${taskKindLabel}。`)
                    : `当前直接展示所选时间范围内所有使用过备用接口的${taskKindLabel}。`
                )
                : (selectedBucketLabel ? `查看“${activeTaskErrorCategory}”在 ${selectedBucketLabel} 的${taskKindLabel}失败明细。` : `查看“${activeTaskErrorCategory}”对应的${taskKindLabel}失败明细。`)
            }}
          </div>
        </div>
        <div class="history-summary">
          <span v-if="activeTaskErrorCategory" class="history-summary-chip">
            错误类别：{{ activeTaskErrorCategory }}
          </span>
          <span class="history-summary-chip">
            {{ fallbackOnly ? `触发备用接口 ${analytics?.fallback_task_total ?? 0} 条` : `筛选结果 ${taskTableTotal} 条` }}
          </span>
          <span v-if="fallbackOnly" class="history-summary-chip history-summary-chip-success">
            成功 {{ analytics?.fallback_success_tasks ?? 0 }}
          </span>
          <span v-if="fallbackOnly" class="history-summary-chip history-summary-chip-danger">
            失败 {{ analytics?.fallback_failed_tasks ?? 0 }}
          </span>
          <a-button
            v-if="selectedTaskErrorCategory"
            type="link"
            size="small"
            class="clear-filter-btn"
            @click="clearTaskCategoryFilter"
          >
            清除任务筛选
          </a-button>
        </div>
      </div>
      <a-table
        :columns="taskColumns"
        :data-source="taskTableItems"
        :loading="taskTableLoading"
        :pagination="false"
        :row-key="(record: AdminErrorTaskItem) => record.task_id"
        :scroll="{ x: fallbackOnly ? 1700 : 1180 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'model'">
            <span class="table-single-line" :title="modelLabel(record.model)">{{ modelLabel(record.model) }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'task_type'">
            {{ modeLabel(record.task_type) }}
          </template>
          <template v-else-if="column.dataIndex === 'source'">
            {{ sourceLabel(record.source) }}
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <span class="category-badge" :class="record.status === 'failed' ? 'category-badge-danger' : ''">{{ statusLabel(record.status) }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'used_fallback_api'">
            <span v-if="record.used_fallback_api" class="category-badge">已调用</span>
            <span v-else class="table-muted">未调用</span>
          </template>
          <template v-else-if="column.dataIndex === 'primary_api_config_name'">
            <span class="table-single-line" :title="record.primary_api_config_name || '-'">{{ record.primary_api_config_name || "-" }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'primary_http_status'">
            {{ typeof record.primary_http_status === "number" ? record.primary_http_status : "-" }}
          </template>
          <template v-else-if="column.dataIndex === 'error_message'">
            <div class="error-message-cell">{{ taskErrorText(record) }}</div>
          </template>
          <template v-else-if="column.dataIndex === 'fallback_api_config_name'">
            <span class="table-single-line" :title="record.fallback_api_config_name || '-'">{{ record.fallback_api_config_name || "-" }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'fallback_status'">
            <span class="category-badge" :class="fallbackStatusClass(record.fallback_status)">{{ fallbackStatusLabel(record.fallback_status) }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'fallback_error_message'">
            <div class="error-message-cell">{{ record.fallback_error_message || "-" }}</div>
          </template>
          <template v-else-if="column.dataIndex === 'created_at'">
            {{ fmtTime(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-button type="link" size="small" class="table-detail-btn" @click="openTaskDetail(record)">详情</a-button>
          </template>
        </template>
        <template #emptyText>
          <a-empty :description="`当前筛选条件下暂无${taskKindLabel}失败明细`" />
        </template>
      </a-table>
      <div v-if="taskTableTotal > TASK_TABLE_PAGE_SIZE" class="warm-pagination">
        <a-pagination
          :current="taskTablePage"
          :total="taskTableTotal"
          :page-size="TASK_TABLE_PAGE_SIZE"
          show-less-items
          @change="loadTaskTable"
        />
      </div>
    </div>
  </div>
  <HistoryDetailDialog
    :open="imageDetailOpen"
    :item="imageDetailItem"
    :loading="imageDetailLoading"
    :model-options="imageModelOptions"
    show-error-message
    show-attempt-response-preview
    @update:open="imageDetailOpen = $event"
  />
  <VideoTaskDetailDialog
    :open="videoDetailOpen"
    :item="videoDetailItem"
    :loading="videoDetailLoading"
    :model-options="videoModelOptions"
    @update:open="videoDetailOpen = $event"
  />
</template>

<style scoped lang="scss">
.analytics-filter {
  margin-bottom: 16px;
}

.page-period-chip {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 253, 248, 0.92);
  border: 1px solid rgba(240, 223, 190, 0.95);
  color: #8c7458;
  font-size: 13px;
}

.fallback-trigger-card {
  margin-bottom: 16px;
  overflow: hidden;
}

.fallback-trigger-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid rgba(240, 223, 190, 0.9);
  background: linear-gradient(180deg, rgba(255, 250, 240, 0.88), rgba(255, 255, 255, 0.2));
}

.fallback-trigger-note {
  flex: 0 0 auto;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(22, 119, 255, 0.08);
  border: 1px solid rgba(22, 119, 255, 0.18);
  color: #1677ff;
  font-size: 12px;
  font-weight: 700;
}

.fallback-trigger-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
  padding: 16px 20px 18px;
}

.fallback-trigger-group {
  padding: 14px;
  border-radius: 16px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
}

.fallback-trigger-group-title {
  color: var(--theme-title);
  font-size: 14px;
  font-weight: 800;
}

.fallback-trigger-group-desc {
  margin-top: 6px;
  color: #9a805b;
  font-size: 12px;
  line-height: 1.5;
}

.fallback-trigger-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.fallback-trigger-tag {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(255, 243, 218, 0.82);
  border: 1px solid rgba(229, 187, 112, 0.38);
  color: #7c5b2e;
  font-size: 12px;
  line-height: 1.2;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.summary-card {
  min-height: 116px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  justify-content: space-between;
}

.summary-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.summary-card-label {
  color: #8c7458;
  font-size: 13px;
  font-weight: 700;
}

.summary-card-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  box-shadow: 0 0 0 4px rgba(255, 193, 90, 0.14);
}

.summary-card-value {
  font-size: 30px;
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.summary-card-desc {
  color: #9a805b;
  font-size: 12px;
  line-height: 1.5;
}

.trend-card {
  margin-bottom: 16px;
  overflow: hidden;
}

.table-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid rgba(240, 223, 190, 0.9);
  background: linear-gradient(180deg, rgba(255, 250, 240, 0.88), rgba(255, 255, 255, 0.2));
}

.trend-card-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
}

.trend-granularity-group {
  flex-wrap: nowrap;
}

.table-card-title {
  color: #5d4526;
  font-size: 16px;
  font-weight: 700;
}

.table-card-desc {
  margin-top: 8px;
  color: #9a805b;
  font-size: 12px;
  line-height: 1.5;
}

.linked-filter-chip-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.linked-filter-chip {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(255, 242, 239, 0.96);
  color: #cf3f36;
  font-weight: 700;
  line-height: 1.4;
}

.linked-filter-chip-secondary {
  background: rgba(255, 248, 226, 0.96);
  color: #9c6b00;
}

.category-badge-danger {
  background: rgba(255, 242, 239, 0.96);
  color: #cf3f36;
}

.category-badge-success {
  background: rgba(240, 255, 244, 0.96);
  color: #389e0d;
}

.category-badge-warning {
  background: rgba(255, 247, 230, 0.96);
  color: var(--theme-accent-text);
}

.clear-filter-btn {
  padding-inline: 0;
}

.count-badge {
  display: inline-flex;
  min-width: 34px;
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(255, 242, 239, 0.96);
  color: #cf3f36;
  font-weight: 700;
  justify-content: center;
}

.category-badge {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255, 248, 226, 0.96);
  color: #9c6b00;
  font-weight: 700;
  line-height: 1.4;
}

.trend-chart-wrap {
  height: 360px;
  padding: 14px 16px 8px;
}

.trend-chart {
  height: 100%;
}

.trend-empty {
  min-height: 260px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 20px;
}

.error-message-cell {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
  color: var(--theme-text);
}

.history-summary {
  display: flex;
  align-items: center;
  gap: 8px;
}

.history-summary-chip {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 248, 226, 0.9);
  color: #9a6b17;
  font-size: 12px;
  font-weight: 700;
}

.history-summary-chip-success {
  background: rgba(240, 255, 244, 0.96);
  color: #389e0d;
}

.history-summary-chip-danger {
  background: rgba(255, 242, 239, 0.96);
  color: #cf3f36;
}

.table-single-line {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.table-muted {
  color: #a58a68;
}

.warm-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 14px 20px 18px;
}

.analytics-filter-select {
  width: 336px;
}

.analytics-filter-source {
  width: 140px;
}

.analytics-task-kind-select {
  width: 132px;
}

.analytics-fallback-select {
  width: 170px;
}

.analytics-unsafe-select {
  width: 178px;
}

@media (max-width: 768px) {
  .analytics-filter-row {
    align-items: stretch;
  }

  .table-card-head {
    flex-direction: column;
    align-items: stretch;
  }

  .trend-card-actions {
    align-items: stretch;
  }

  .analytics-filter-select,
  .analytics-filter-date,
  .analytics-action-btn {
    width: 100%;
  }
}
</style>
