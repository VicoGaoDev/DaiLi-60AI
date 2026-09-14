<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { message } from "ant-design-vue";
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";
import { BarChartOutlined } from "@ant-design/icons-vue";
import {
  getAdminVideoAnalyticsBreakdown,
  getAdminVideoAnalyticsSummary,
  getAdminVideoAnalyticsTimeseries,
  getAdminVideoTasks,
  listUserOptions,
} from "@/api/admin";
import { getVideoTaskScenes } from "@/api/videoConfig";
import AdminUserInfoDialog from "@/components/admin/AdminUserInfoDialog.vue";
import { VChart } from "@/components/admin/charting";
import VideoTaskDetailDialog from "@/components/video/VideoTaskDetailDialog.vue";
import { getAvatarImageSrc } from "@/api/images";
import { getSuccessRateColor } from "@/lib/analyticsMetric";
import { isSessionExpiredError } from "@/lib/authError";
import type {
  AdminAnalyticsBreakdown,
  AdminAnalyticsGranularity,
  AdminAnalyticsSummary,
  AdminAnalyticsTimeseries,
  AdminUser,
  AdminVideoTaskResult,
  TaskSource,
  VideoAnalyticsQuery,
  VideoTaskModeFilter,
  VideoTaskSceneConfig,
} from "@/types";

const analyticsLoading = ref(false);
const tasksLoading = ref(false);
const summary = ref<AdminAnalyticsSummary | null>(null);
const timeseries = ref<AdminAnalyticsTimeseries | null>(null);
const breakdown = ref<AdminAnalyticsBreakdown | null>(null);
const users = ref<AdminUser[]>([]);
const usersLoading = ref(false);
const taskScenes = ref<VideoTaskSceneConfig[]>([]);
const tasks = ref<AdminVideoTaskResult[]>([]);
const taskTotal = ref(0);
const page = ref(1);
const granularity = ref<AdminAnalyticsGranularity>("3hour");
const preset = ref("today");
const ready = ref(false);
const detailOpen = ref(false);
const detailItem = ref<AdminVideoTaskResult | null>(null);
const userInfoDialogOpen = ref(false);
const selectedUserInfo = ref<AdminUser | null>(null);
const TASK_PAGE_SIZE = 20;
const TASK_TABLE_SCROLL_X = 1320;

type PeriodCardItem = {
  key: string;
  label: string;
  color: string;
  current: number;
  previous?: number;
  delta?: number;
  delta_pct?: number | null;
  suffix?: string;
  chipText?: string;
  deltaText?: string;
};

const filters = reactive<{
  status: string | undefined;
  user_id: string | undefined;
  source: TaskSource | undefined;
  model: string | undefined;
  mode: VideoTaskModeFilter | undefined;
  include_unsafe_tasks: boolean;
  dateRange: [Dayjs, Dayjs] | null;
}>({
  status: undefined,
  user_id: undefined,
  source: undefined,
  model: undefined,
  mode: undefined,
  include_unsafe_tasks: true,
  dateRange: null,
});

const columns = [
  { title: "用户", dataIndex: "username", width: 172 },
  { title: "模型", dataIndex: "model", width: 180 },
  { title: "提示词", dataIndex: "prompt", width: 280, ellipsis: true },
  { title: "状态", dataIndex: "status", width: 128 },
  { title: "来源", dataIndex: "source", width: 80 },
  { title: "类型", dataIndex: "mode", width: 90 },
  { title: "视频时长", dataIndex: "duration_seconds", width: 96 },
  { title: "消耗积分", dataIndex: "credit_cost", width: 96 },
  { title: "时间", dataIndex: "created_at", width: 148 },
  { title: "操作", key: "actions", width: 72, fixed: "right" as const },
];

const modelOptions = computed(() => (
  taskScenes.value.map((scene) => ({
    value: scene.scene_key,
    label: scene.display_name || scene.scene_label || scene.scene_key,
  }))
));

const processingTaskCount = computed(() => (
  breakdown.value?.status_breakdown.find((item) => item.name === "processing")?.count ?? 0
));

const periodCards = computed<PeriodCardItem[]>(() => {
  if (!summary.value) return [];
  const successRateCurrent = summary.value.tasks_created.current
    ? Number(((summary.value.success_tasks.current / summary.value.tasks_created.current) * 100).toFixed(1))
    : 0;
  const successRatePrevious = summary.value.tasks_created.previous
    ? Number(((summary.value.success_tasks.previous / summary.value.tasks_created.previous) * 100).toFixed(1))
    : 0;
  const successRateDelta = Number((successRateCurrent - successRatePrevious).toFixed(1));
  return [
    { key: "tasks_created", label: "周期任务数", color: "#1890ff", current: summary.value.tasks_created.current, previous: summary.value.tasks_created.previous, delta: summary.value.tasks_created.delta, delta_pct: summary.value.tasks_created.delta_pct },
    { key: "success_tasks", label: "周期成功数", color: "#52c41a", current: summary.value.success_tasks.current, previous: summary.value.success_tasks.previous, delta: summary.value.success_tasks.delta, delta_pct: summary.value.success_tasks.delta_pct },
    { key: "failed_tasks", label: "周期失败数", color: "#ff4d4f", current: summary.value.failed_tasks.current, previous: summary.value.failed_tasks.previous, delta: summary.value.failed_tasks.delta, delta_pct: summary.value.failed_tasks.delta_pct },
    { key: "processing_tasks", label: "周期进行中数", color: "#2f54eb", current: processingTaskCount.value, chipText: "当前周期", deltaText: "来自任务状态占比" },
    { key: "credits_consumed", label: "周期积分消耗", color: "#fa8c16", current: summary.value.credits_consumed.current, previous: summary.value.credits_consumed.previous, delta: summary.value.credits_consumed.delta, delta_pct: summary.value.credits_consumed.delta_pct },
    { key: "active_users", label: "周期活跃用户", color: "#13c2c2", current: summary.value.active_users.current, previous: summary.value.active_users.previous, delta: summary.value.active_users.delta, delta_pct: summary.value.active_users.delta_pct },
    { key: "success_rate", label: "周期成功率", color: getSuccessRateColor(successRateCurrent), current: successRateCurrent, previous: successRatePrevious, delta: successRateDelta, delta_pct: successRatePrevious === 0 ? null : Number(((successRateDelta / successRatePrevious) * 100).toFixed(1)), suffix: "%" },
  ];
});

const activeFilterSummary = computed(() => {
  const chips: string[] = [];
  if (filters.user_id) {
    const user = users.value.find((item) => item.id === filters.user_id);
    if (user) chips.push(`用户：${user.username}`);
  }
  if (filters.source) chips.push(`来源：${sourceLabel(filters.source)}`);
  if (filters.mode) chips.push(`类型：${videoModeLabel(filters.mode)}`);
  if (filters.model) chips.push(`模型：${modelLabel(filters.model)}`);
  if (filters.status) chips.push(`状态：${statusLabel(filters.status)}`);
  if (!filters.include_unsafe_tasks) chips.push("错误任务：不含不合规");
  if (filters.dateRange) {
    chips.push(`${filters.dateRange[0].format("YYYY-MM-DD")} ~ ${filters.dateRange[1].format("YYYY-MM-DD")}`);
  }
  if (!chips.length && summary.value) chips.push(`统计范围：${summary.value.current_range_label}`);
  return chips;
});

const filterSignature = computed(() => JSON.stringify({
  granularity: granularity.value,
  preset: preset.value,
  status: filters.status || null,
  user_id: filters.user_id || null,
  source: filters.source || null,
  model: filters.model || null,
  mode: filters.mode || null,
  include_unsafe_tasks: filters.include_unsafe_tasks,
  start: filters.dateRange?.[0]?.valueOf() || null,
  end: filters.dateRange?.[1]?.valueOf() || null,
}));

const trendLabels = computed(() => timeseries.value?.current.map((item) => item.label) || []);
const hasTrendData = computed(() => {
  if (!timeseries.value) return false;
  return [...timeseries.value.current, ...timeseries.value.previous].some((item) => (
    item.tasks_created > 0
    || item.success_tasks > 0
    || item.failed_tasks > 0
    || item.credits_consumed > 0
    || item.active_users > 0
  ));
});

const hasBreakdownData = computed(() => {
  if (!breakdown.value) return false;
  return [
    ...breakdown.value.status_breakdown,
    ...breakdown.value.source_breakdown,
    ...breakdown.value.mode_breakdown,
    ...breakdown.value.model_breakdown,
    ...breakdown.value.top_users_by_tasks,
    ...breakdown.value.top_users_by_credit,
  ].some((item) => item.count > 0 || item.credit_cost > 0);
});

const tasksTrendOption = computed(() => ({
  color: ["#1890ff", "#91caff"],
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
  },
  legend: { top: 0 },
  grid: { left: 40, right: 20, top: 44, bottom: 28 },
  xAxis: { type: "category", data: trendLabels.value },
  yAxis: { type: "value" },
  series: [
    {
      name: "当前周期任务数",
      type: "line",
      smooth: true,
      symbolSize: 8,
      areaStyle: { color: "rgba(24, 144, 255, 0.12)" },
      lineStyle: { width: 3 },
      data: timeseries.value?.current.map((item) => item.tasks_created) || [],
    },
    {
      name: "上一周期任务数",
      type: "line",
      smooth: true,
      symbolSize: 7,
      lineStyle: { type: "dashed" },
      data: timeseries.value?.previous.map((item) => item.tasks_created) || [],
    },
  ],
}));

const creditTrendOption = computed(() => ({
  color: ["#fa8c16", "#ffd591", "#13c2c2"],
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
  },
  legend: { top: 0 },
  grid: { left: 40, right: 20, top: 44, bottom: 28 },
  xAxis: { type: "category", data: trendLabels.value },
  yAxis: [
    { type: "value", name: "积分" },
    { type: "value", name: "人数" },
  ],
  series: [
    {
      name: "当前周期积分",
      type: "bar",
      data: timeseries.value?.current.map((item) => item.credits_consumed) || [],
      itemStyle: { color: "#fa8c16", borderRadius: [8, 8, 0, 0] },
    },
    {
      name: "上一周期积分",
      type: "bar",
      data: timeseries.value?.previous.map((item) => item.credits_consumed) || [],
      itemStyle: { color: "#ffd591", borderRadius: [8, 8, 0, 0] },
    },
    {
      name: "当前活跃用户",
      type: "line",
      yAxisIndex: 1,
      smooth: true,
      symbolSize: 8,
      lineStyle: { width: 3 },
      data: timeseries.value?.current.map((item) => item.active_users) || [],
      itemStyle: { color: "#13c2c2" },
    },
  ],
}));

const statusTrendOption = computed(() => ({
  color: ["#52c41a", "#ff4d4f", "#b7eb8f", "#ffa39e"],
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
  },
  legend: { top: 0 },
  grid: { left: 40, right: 20, top: 44, bottom: 28 },
  xAxis: { type: "category", data: trendLabels.value },
  yAxis: { type: "value" },
  series: [
    {
      name: "当前成功",
      type: "bar",
      data: timeseries.value?.current.map((item) => item.success_tasks) || [],
      itemStyle: { color: "#52c41a", borderRadius: [8, 8, 0, 0] },
    },
    {
      name: "当前失败",
      type: "bar",
      data: timeseries.value?.current.map((item) => item.failed_tasks) || [],
      itemStyle: { color: "#ff4d4f", borderRadius: [8, 8, 0, 0] },
    },
    {
      name: "上期成功",
      type: "bar",
      data: timeseries.value?.previous.map((item) => item.success_tasks) || [],
      itemStyle: { color: "#b7eb8f", borderRadius: [8, 8, 0, 0] },
    },
    {
      name: "上期失败",
      type: "bar",
      data: timeseries.value?.previous.map((item) => item.failed_tasks) || [],
      itemStyle: { color: "#ffa39e", borderRadius: [8, 8, 0, 0] },
    },
  ],
}));

const statusPieOption = computed(() => ({
  color: ["#52c41a", "#ff4d4f", "#fa8c16", "#91caff", "#d3adf7"],
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
      data: (breakdown.value?.status_breakdown || []).map((item) => ({
        name: statusLabel(item.name),
        value: item.count,
        rawValue: item.name,
      })),
    },
  ],
}));

const sourcePieOption = computed(() => ({
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
      data: (breakdown.value?.source_breakdown || []).map((item) => ({
        name: sourceLabel(item.name),
        value: item.count,
        rawValue: item.name,
      })),
    },
  ],
}));

const modePieOption = computed(() => ({
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
      data: (breakdown.value?.mode_breakdown || []).map((item) => ({
        name: videoModeLabel(item.name),
        value: item.count,
        rawValue: item.name,
      })),
    },
  ],
}));

const modelBarOption = computed(() => ({
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(76, 52, 26, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#fffdf8" },
  },
  grid: { left: 40, right: 20, top: 20, bottom: 48 },
  xAxis: {
    type: "category",
    data: (breakdown.value?.model_breakdown || []).map((item) => modelLabel(item.name)),
    axisLabel: { interval: 0, rotate: 18 },
  },
  yAxis: { type: "value" },
  series: [
    {
      type: "bar",
      data: (breakdown.value?.model_breakdown || []).map((item) => item.count),
      itemStyle: { color: "#1890ff", borderRadius: [8, 8, 0, 0] },
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
  xAxis: {
    type: "category",
    data: (breakdown.value?.top_users_by_tasks || []).map((item) => item.name),
    axisLabel: { interval: 0, rotate: 18 },
  },
  yAxis: { type: "value" },
  series: [
    {
      type: "bar",
      data: (breakdown.value?.top_users_by_tasks || []).map((item) => item.count),
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
  xAxis: {
    type: "category",
    data: (breakdown.value?.top_users_by_credit || []).map((item) => item.name),
    axisLabel: { interval: 0, rotate: 18 },
  },
  yAxis: { type: "value" },
  series: [
    {
      type: "bar",
      data: (breakdown.value?.top_users_by_credit || []).map((item) => item.credit_cost),
      itemStyle: { color: "#fa8c16", borderRadius: [8, 8, 0, 0] },
    },
  ],
}));

function defaultPresetByGranularity(value: AdminAnalyticsGranularity) {
  if (value === "3hour") return "today";
  if (value === "week") return "8w";
  if (value === "month") return "6m";
  return "today";
}

function applyPresetRange(value: string) {
  const now = dayjs();
  if (value === "today") {
    filters.dateRange = [now.startOf("day"), now.endOf("day")];
    return;
  }
  if (value === "3d") {
    filters.dateRange = [now.subtract(2, "day").startOf("day"), now.endOf("day")];
    return;
  }
  if (value === "7d") {
    filters.dateRange = [now.subtract(6, "day").startOf("day"), now.endOf("day")];
    return;
  }
  if (value === "30d") {
    filters.dateRange = [now.subtract(29, "day").startOf("day"), now.endOf("day")];
    return;
  }
  if (value === "8w") {
    filters.dateRange = [now.subtract(7, "week").startOf("day"), now.endOf("day")];
    return;
  }
  if (value === "12w") {
    filters.dateRange = [now.subtract(11, "week").startOf("day"), now.endOf("day")];
    return;
  }
  if (value === "6m") {
    filters.dateRange = [now.subtract(5, "month").startOf("day"), now.endOf("day")];
    return;
  }
  if (value === "12m") {
    filters.dateRange = [now.subtract(11, "month").startOf("day"), now.endOf("day")];
    return;
  }
  filters.dateRange = [now.subtract(6, "day").startOf("day"), now.endOf("day")];
}

function formatQueryDate(value?: Dayjs) {
  return value ? value.format("YYYY-MM-DDTHH:mm:ss") : undefined;
}

function buildAnalyticsQuery(): VideoAnalyticsQuery {
  const useBucketRange = granularity.value === "3hour" && preset.value === "custom";
  return {
    granularity: granularity.value,
    status: filters.status,
    user_id: filters.user_id,
    source: filters.source,
    model: filters.model,
    mode: filters.mode,
    include_unsafe_tasks: filters.include_unsafe_tasks,
    start_date: formatQueryDate(useBucketRange ? filters.dateRange?.[0] : filters.dateRange?.[0].startOf("day")),
    end_date: formatQueryDate(useBucketRange ? filters.dateRange?.[1] : filters.dateRange?.[1].endOf("day")),
  };
}

function buildTaskFilters() {
  const query = buildAnalyticsQuery();
  return {
    source: query.source,
    model: query.model,
    mode: query.mode,
    status: query.status as "pending" | "queued" | "processing" | "success" | "failed" | undefined,
    user_id: query.user_id,
    include_unsafe_tasks: query.include_unsafe_tasks,
    start_date: query.start_date,
    end_date: query.end_date,
  };
}

async function loadModels() {
  try {
    taskScenes.value = await getVideoTaskScenes();
  } catch {
    taskScenes.value = [];
  }
}

async function loadUsers() {
  if (users.value.length || usersLoading.value) return;
  usersLoading.value = true;
  try {
    users.value = (await listUserOptions()).filter((item) => !item.is_whitelisted);
  } catch {
    users.value = [];
  } finally {
    usersLoading.value = false;
  }
}

function handleUserDropdownVisible(open: boolean) {
  if (open) void loadUsers();
}

async function loadAnalytics() {
  analyticsLoading.value = true;
  try {
    const query = buildAnalyticsQuery();
    const [summaryRes, timeseriesRes, breakdownRes] = await Promise.all([
      getAdminVideoAnalyticsSummary(query),
      getAdminVideoAnalyticsTimeseries(query),
      getAdminVideoAnalyticsBreakdown(query),
    ]);
    summary.value = summaryRes;
    timeseries.value = timeseriesRes;
    breakdown.value = breakdownRes;
  } catch (err: any) {
    if (isSessionExpiredError(err)) return;
    message.error("获取视频统计分析失败");
  } finally {
    analyticsLoading.value = false;
  }
}

async function loadTasks() {
  tasksLoading.value = true;
  try {
    const res = await getAdminVideoTasks(page.value, TASK_PAGE_SIZE, buildTaskFilters());
    tasks.value = res.items;
    taskTotal.value = res.total;
  } catch (err: any) {
    if (isSessionExpiredError(err)) return;
    message.error("获取视频任务明细失败");
  } finally {
    tasksLoading.value = false;
  }
}

async function loadPageData() {
  await Promise.all([loadAnalytics(), loadTasks()]);
}

async function handleRefresh() {
  await loadPageData();
}

function handleReset() {
  filters.status = undefined;
  filters.user_id = undefined;
  filters.source = undefined;
  filters.model = undefined;
  filters.mode = undefined;
  filters.include_unsafe_tasks = true;
  preset.value = defaultPresetByGranularity(granularity.value);
  applyPresetRange(preset.value);
}

function handleGranularityChange(value: AdminAnalyticsGranularity) {
  granularity.value = value;
  preset.value = defaultPresetByGranularity(value);
  applyPresetRange(preset.value);
}

function handlePresetChange(value: string) {
  preset.value = value;
  applyPresetRange(value);
}

function handlePageChange(nextPage: number) {
  page.value = nextPage;
  void loadTasks();
}

function openTaskDetail(record: AdminVideoTaskResult) {
  detailItem.value = record;
  detailOpen.value = true;
}

function findAdminUser(userId?: string | null) {
  if (!userId) return null;
  return users.value.find((item) => item.id === userId) || null;
}

function openUserInfoDialog(record: AdminVideoTaskResult) {
  if (!record.user_id) return;
  const matchedUser = findAdminUser(record.user_id);
  selectedUserInfo.value = matchedUser || {
    id: record.user_id,
    username: record.username || "未知用户",
    email: "",
    avatar_url: record.avatar_url || "",
    role: "user",
    status: "active",
    is_whitelisted: false,
    credits: 0,
    consumed_credits: 0,
    created_at: "",
  };
  userInfoDialogOpen.value = true;
}

function filterBySelectedUser(user: AdminUser) {
  filters.user_id = user.id;
  userInfoDialogOpen.value = false;
}

const detailItemIndex = computed(() => {
  if (!detailOpen.value || !detailItem.value) return -1;
  return tasks.value.findIndex((item) => item.id === detailItem.value?.id);
});

const hasDetailPrev = computed(() => detailItemIndex.value > 0);
const hasDetailNext = computed(() => (
  detailItemIndex.value >= 0
  && detailItemIndex.value < tasks.value.length - 1
));

function navigateTaskDetail(delta: -1 | 1) {
  const nextIndex = detailItemIndex.value + delta;
  const nextItem = tasks.value[nextIndex];
  if (!nextItem) return;
  openTaskDetail(nextItem);
}

function handleBucketClick(params: { dataIndex?: number }) {
  const point = timeseries.value?.current[params.dataIndex || 0];
  if (!point?.bucket_start || !point?.bucket_end) return;
  filters.dateRange = [dayjs(point.bucket_start), dayjs(point.bucket_end)];
  preset.value = "custom";
}

function getRawValue(data: unknown) {
  if (!data || typeof data !== "object") return "";
  return "rawValue" in data && typeof data.rawValue === "string" ? data.rawValue : "";
}

function handleStatusClick(params: { data?: unknown }) {
  const rawValue = getRawValue(params.data);
  if (rawValue) filters.status = rawValue;
}

function handleSourceClick(params: { data?: unknown }) {
  const rawValue = getRawValue(params.data);
  if (rawValue) filters.source = rawValue as TaskSource;
}

function handleModeClick(params: { data?: unknown }) {
  const rawValue = getRawValue(params.data);
  if (rawValue) filters.mode = rawValue as VideoTaskModeFilter;
}

function handleModelClick(params: { dataIndex?: number }) {
  const item = breakdown.value?.model_breakdown[params.dataIndex || 0];
  if (item) filters.model = item.name;
}

function handleUserTaskClick(params: { dataIndex?: number }) {
  const item = breakdown.value?.top_users_by_tasks[params.dataIndex || 0];
  if (!item) return;
  const matchedUser = users.value.find((user) => user.username === item.name);
  if (matchedUser) filters.user_id = matchedUser.id;
}

function handleUserCreditClick(params: { dataIndex?: number }) {
  const item = breakdown.value?.top_users_by_credit[params.dataIndex || 0];
  if (!item) return;
  const matchedUser = users.value.find((user) => user.username === item.name);
  if (matchedUser) filters.user_id = matchedUser.id;
}

function fmtTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function modelLabel(value: string) {
  if (!value) return "-";
  return modelOptions.value.find((item) => item.value === value)?.label || value;
}

function sourceLabel(value: string) {
  if (value === "app") return "App";
  if (value === "api") return "API";
  return "Web";
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

function statusColor(value: string) {
  if (value === "success") return "green";
  if (value === "failed") return "red";
  if (value === "processing" || value === "queued") return "orange";
  return "default";
}

function videoModeLabel(value: string) {
  if (value === "first_last_frame") return "首尾帧";
  if (value === "image_to_video") return "图生视频";
  if (value === "text_to_video") return "文生视频";
  return value;
}

function formatDelta(current: number, previous: number, delta: number, deltaPct?: number | null, suffix = "") {
  const sign = delta > 0 ? "+" : "";
  if (deltaPct == null) return `较上期 ${sign}${delta}${suffix}`;
  return `较上期 ${sign}${delta}${suffix} (${sign}${deltaPct}%)`;
}

onMounted(async () => {
  preset.value = defaultPresetByGranularity(granularity.value);
  applyPresetRange(preset.value);
  await loadModels();
  await loadPageData();
  ready.value = true;
});

watch(filterSignature, async () => {
  if (!ready.value) return;
  page.value = 1;
  await loadPageData();
});
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <BarChartOutlined />
        </div>
        <div>
          <div class="warm-page-title">视频数据</div>
          <div class="warm-page-desc">单独查看视频任务的数量、成功率、积分消耗、来源和用户分布，不混入生图数据。</div>
        </div>
      </div>
      <div v-if="summary" class="page-period-meta">
        <span class="page-period-chip">当前周期：{{ summary.current_range_label }}</span>
        <span class="page-period-chip">对比周期：{{ summary.previous_range_label }}</span>
      </div>
    </div>

    <div class="analytics-filter warm-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <div class="analytics-filter-row">
        <div class="analytics-filter-panel-compact">
          <a-radio-group
            :value="granularity"
            class="analytics-segmented-group analytics-granularity-group"
            button-style="solid"
            @update:value="handleGranularityChange"
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
            @update:value="handlePresetChange"
          >
            <a-radio-button v-if="granularity === '3hour' || granularity === 'day'" value="today">今日</a-radio-button>
            <a-radio-button v-if="granularity === '3hour' || granularity === 'day'" value="3d">近3天</a-radio-button>
            <a-radio-button v-if="granularity === '3hour' || granularity === 'day'" value="7d">近7天</a-radio-button>
            <a-radio-button v-if="granularity === '3hour' || granularity === 'day'" value="30d">近30天</a-radio-button>
            <a-radio-button v-if="granularity === 'week'" value="8w">近8周</a-radio-button>
            <a-radio-button v-if="granularity === 'week'" value="12w">近12周</a-radio-button>
            <a-radio-button v-if="granularity === 'month'" value="6m">近6月</a-radio-button>
            <a-radio-button v-if="granularity === 'month'" value="12m">近12月</a-radio-button>
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
          @dropdownVisibleChange="handleUserDropdownVisible"
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

        <a-select v-model:value="filters.status" placeholder="全部状态" allow-clear class="analytics-filter-select">
          <a-select-option value="pending">等待中</a-select-option>
          <a-select-option value="queued">排队中</a-select-option>
          <a-select-option value="processing">处理中</a-select-option>
          <a-select-option value="success">成功</a-select-option>
          <a-select-option value="failed">失败</a-select-option>
        </a-select>

        <a-select v-model:value="filters.source" placeholder="全部来源" allow-clear class="analytics-filter-select">
          <a-select-option value="web">Web</a-select-option>
          <a-select-option value="app">App</a-select-option>
          <a-select-option value="api">API</a-select-option>
        </a-select>

        <a-select v-model:value="filters.mode" placeholder="全部类型" allow-clear class="analytics-filter-select">
          <a-select-option value="text_to_video">文生视频</a-select-option>
          <a-select-option value="image_to_video">图生视频</a-select-option>
          <a-select-option value="first_last_frame">首尾帧</a-select-option>
        </a-select>

        <a-select v-model:value="filters.model" placeholder="全部模型" allow-clear class="analytics-filter-select analytics-filter-model">
          <a-select-option v-for="option in modelOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </a-select-option>
        </a-select>

        <a-select v-model:value="filters.include_unsafe_tasks" class="analytics-filter-select analytics-filter-unsafe">
          <a-select-option :value="true">包含不合规错误</a-select-option>
          <a-select-option :value="false">不含不合规错误</a-select-option>
        </a-select>

        <a-range-picker v-model:value="filters.dateRange" class="analytics-filter-date" />
        <a-button class="analytics-action-btn analytics-action-btn-secondary" :loading="analyticsLoading || tasksLoading" @click="handleReset">
          重置
        </a-button>
        <a-button class="analytics-action-btn analytics-action-btn-secondary" :loading="analyticsLoading || tasksLoading" @click="handleRefresh">
          刷新
        </a-button>
      </div>
    </div>

    <section class="dashboard-section">
      <div class="section-title-row">
        <h3 class="section-title">核心指标</h3>
        <span class="section-kicker">Video KPI</span>
      </div>
      <a-spin :spinning="analyticsLoading">
        <div class="kpi-grid">
          <div
            v-for="(card, index) in periodCards"
            :key="card.key"
            class="kpi-card warm-card motion-card-lift motion-fade-up"
            :style="{ '--motion-delay': `${180 + Math.min(index, 5) * 45}ms` }"
          >
            <div class="kpi-head">
              <div class="kpi-label-wrap">
                <span class="kpi-dot" :style="{ background: card.color }" />
                <div class="kpi-label">{{ card.label }}</div>
              </div>
              <div class="kpi-chip">{{ card.chipText || "周期对比" }}</div>
            </div>
            <div class="kpi-value" :style="{ color: card.color }">{{ card.current }}{{ card.suffix || "" }}</div>
            <div v-if="card.previous !== undefined" class="kpi-meta">
              <span class="kpi-meta-label">上期</span>
              <span class="kpi-meta-value">{{ card.previous }}{{ card.suffix || "" }}</span>
            </div>
            <div class="kpi-delta" :class="{ positive: (card.delta || 0) > 0, negative: (card.delta || 0) < 0 }">
              {{ card.deltaText || formatDelta(card.current, card.previous || 0, card.delta || 0, card.delta_pct, card.suffix) }}
            </div>
          </div>
        </div>
      </a-spin>
    </section>

    <section class="dashboard-section">
      <div class="section-title-row">
        <h3 class="section-title">趋势分析</h3>
        <span class="section-tip">点击图表任意时间点可直接下钻到该时间范围视频任务明细。</span>
      </div>
      <div class="section-filter-chips">
        <span v-for="item in activeFilterSummary" :key="item" class="section-filter-chip">{{ item }}</span>
      </div>
      <a-spin :spinning="analyticsLoading">
        <div v-if="hasTrendData" class="trend-grid">
          <div class="trend-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 220ms">
            <div class="trend-card-head">
              <div>
                <div class="trend-card-title">视频任务趋势对比</div>
                <div class="trend-card-desc">对比当前周期与上一周期的视频任务波动。</div>
              </div>
              <div class="trend-card-badge">折线图</div>
            </div>
            <VChart class="trend-chart" :option="tasksTrendOption" autoresize @click="handleBucketClick" />
          </div>
          <div class="trend-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 260ms">
            <div class="trend-card-head">
              <div>
                <div class="trend-card-title">积分与活跃用户</div>
                <div class="trend-card-desc">同时观察视频任务投入和使用活跃度的变化。</div>
              </div>
              <div class="trend-card-badge">混合图</div>
            </div>
            <VChart class="trend-chart" :option="creditTrendOption" autoresize @click="handleBucketClick" />
          </div>
          <div class="trend-card warm-card trend-card-wide motion-card-lift motion-fade-up" style="--motion-delay: 300ms">
            <div class="trend-card-head">
              <div>
                <div class="trend-card-title">成功失败趋势对比</div>
                <div class="trend-card-desc">快速识别失败峰值和异常时间段。</div>
              </div>
              <div class="trend-card-badge">柱状图</div>
            </div>
            <VChart class="trend-chart" :option="statusTrendOption" autoresize @click="handleBucketClick" />
          </div>
        </div>
        <div v-else class="trend-empty warm-card motion-fade-up" style="--motion-delay: 220ms">
          <a-empty class="warm-empty" description="当前筛选条件下暂无趋势数据">
            <template #description>
              <div class="empty-title">当前筛选条件下暂无趋势数据</div>
              <div class="empty-desc">调整时间范围、用户或状态后，可查看视频任务趋势图和周期对比。</div>
            </template>
          </a-empty>
        </div>
      </a-spin>
    </section>

    <section class="dashboard-section">
      <div class="section-title-row">
        <h3 class="section-title">结构分布</h3>
        <span class="section-tip">点击占比或排行图可自动带筛选查看视频任务记录。</span>
      </div>
      <div class="section-filter-chips">
        <span v-for="item in activeFilterSummary" :key="item" class="section-filter-chip">{{ item }}</span>
      </div>
      <a-spin :spinning="analyticsLoading">
        <div v-if="hasBreakdownData" class="breakdown-grid">
          <div class="breakdown-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 220ms">
            <div class="breakdown-head">
              <div>
                <div class="breakdown-title">任务状态占比</div>
                <div class="breakdown-desc">查看视频任务整体结果健康度。</div>
              </div>
              <div class="breakdown-badge">饼图</div>
            </div>
            <VChart class="breakdown-chart" :option="statusPieOption" autoresize @click="handleStatusClick" />
          </div>
          <div class="breakdown-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 260ms">
            <div class="breakdown-head">
              <div>
                <div class="breakdown-title">来源分布</div>
                <div class="breakdown-desc">区分 Web、App、API 的视频任务占比。</div>
              </div>
              <div class="breakdown-badge">饼图</div>
            </div>
            <VChart class="breakdown-chart" :option="sourcePieOption" autoresize @click="handleSourceClick" />
          </div>
          <div class="breakdown-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 300ms">
            <div class="breakdown-head">
              <div>
                <div class="breakdown-title">任务类型占比</div>
                <div class="breakdown-desc">区分文生视频与图生视频的使用比例。</div>
              </div>
              <div class="breakdown-badge">饼图</div>
            </div>
            <VChart class="breakdown-chart" :option="modePieOption" autoresize @click="handleModeClick" />
          </div>
          <div class="breakdown-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 340ms">
            <div class="breakdown-head">
              <div>
                <div class="breakdown-title">模型使用 Top</div>
                <div class="breakdown-desc">了解当前最常被使用的视频模型。</div>
              </div>
              <div class="breakdown-badge">排行</div>
            </div>
            <VChart class="breakdown-chart" :option="modelBarOption" autoresize @click="handleModelClick" />
          </div>
          <div class="breakdown-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 380ms">
            <div class="breakdown-head">
              <div>
                <div class="breakdown-title">用户提交次数 Top</div>
                <div class="breakdown-desc">定位高频使用视频功能的用户。</div>
              </div>
              <div class="breakdown-badge">排行</div>
            </div>
            <VChart class="breakdown-chart" :option="userTaskOption" autoresize @click="handleUserTaskClick" />
          </div>
          <div class="breakdown-card warm-card breakdown-card-wide motion-card-lift motion-fade-up" style="--motion-delay: 420ms">
            <div class="breakdown-head">
              <div>
                <div class="breakdown-title">用户视频积分消耗 Top</div>
                <div class="breakdown-desc">从视频消耗角度观察重点用户。</div>
              </div>
              <div class="breakdown-badge">排行</div>
            </div>
            <VChart class="breakdown-chart" :option="userCreditOption" autoresize @click="handleUserCreditClick" />
          </div>
        </div>
        <div v-else class="breakdown-empty warm-card motion-fade-up" style="--motion-delay: 220ms">
          <a-empty class="warm-empty" description="当前筛选条件下暂无分布数据">
            <template #description>
              <div class="empty-title">当前筛选条件下暂无分布数据</div>
              <div class="empty-desc">当有视频任务、积分或用户数据时，这里会自动展示占比和排行图。</div>
            </template>
          </a-empty>
        </div>
      </a-spin>
    </section>

    <section class="dashboard-section">
      <div class="warm-card warm-table-card motion-card-lift motion-fade-up" style="--motion-delay: 320ms">
        <div class="table-card-head">
          <div>
            <div class="table-card-title-row">
              <h3 class="section-title">视频任务明细</h3>
              <span class="section-kicker">Details</span>
            </div>
            <div class="table-card-desc">当前图表与筛选条件对应的视频任务明细列表。</div>
          </div>
          <div class="history-summary">
            <span class="history-summary-chip">筛选结果 {{ taskTotal }} 条</span>
          </div>
        </div>

        <a-table
          :columns="columns"
          :data-source="tasks"
          :loading="tasksLoading"
          :row-key="(record: AdminVideoTaskResult) => record.id"
          :pagination="false"
          :scroll="{ x: TASK_TABLE_SCROLL_X }"
          class="admin-mobile-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.dataIndex === 'username'">
              <div class="table-user-cell">
                <button
                  type="button"
                  class="table-user-avatar-btn"
                  title="查看用户信息"
                  @click="openUserInfoDialog(record)"
                >
                  <a-avatar :size="30" :src="getAvatarImageSrc(record.avatar_url) || undefined" class="table-user-avatar">
                    {{ record.username?.charAt(0)?.toUpperCase() }}
                  </a-avatar>
                </button>
                <span>{{ record.username || "-" }}</span>
              </div>
            </template>
            <template v-else-if="column.dataIndex === 'mode'">
              {{ videoModeLabel(record.generation_mode || (record.reference_images?.length ? 'image_to_video' : 'text_to_video')) }}
            </template>
            <template v-else-if="column.dataIndex === 'source'">
              {{ sourceLabel(record.source) }}
            </template>
            <template v-else-if="column.dataIndex === 'prompt'">
              <a-tooltip v-if="record.prompt" placement="topLeft">
                <template #title>
                  <div class="prompt-tooltip-content">{{ record.prompt }}</div>
                </template>
                <div class="prompt-cell-text">{{ record.prompt }}</div>
              </a-tooltip>
              <span v-else>-</span>
            </template>
            <template v-else-if="column.dataIndex === 'model'">
              <span class="table-single-line" :title="modelLabel(record.model)">
                {{ modelLabel(record.model) }}
              </span>
            </template>
            <template v-else-if="column.dataIndex === 'status'">
              <a-space size="small" wrap>
                <a-tag :color="statusColor(record.status)">
                  {{ statusLabel(record.status) }}
                </a-tag>
                <a-tag v-if="record.task_is_deleted" color="red">已软删</a-tag>
              </a-space>
            </template>
            <template v-else-if="column.dataIndex === 'duration_seconds'">
              {{ record.duration_seconds ? `${record.duration_seconds}秒` : "-" }}
            </template>
            <template v-else-if="column.dataIndex === 'created_at'">
              {{ fmtTime(record.created_at) }}
            </template>
            <template v-else-if="column.key === 'actions'">
              <a-button type="link" size="small" class="table-detail-btn" @click="openTaskDetail(record)">
                详情
              </a-button>
            </template>
          </template>
        </a-table>
      </div>

      <div v-if="taskTotal > TASK_PAGE_SIZE" class="warm-pagination">
        <a-pagination
          :current="page"
          :total="taskTotal"
          :page-size="TASK_PAGE_SIZE"
          show-less-items
          @change="handlePageChange"
        />
      </div>
    </section>

    <VideoTaskDetailDialog
      :open="detailOpen"
      :item="detailItem"
      :model-options="modelOptions"
      :show-reedit="false"
      :has-prev="hasDetailPrev"
      :has-next="hasDetailNext"
      @update:open="detailOpen = $event"
      @navigate-prev="navigateTaskDetail(-1)"
      @navigate-next="navigateTaskDetail(1)"
    />
    <AdminUserInfoDialog
      v-model:open="userInfoDialogOpen"
      :user="selectedUserInfo"
      show-view-data
      @view-data="filterBySelectedUser"
    />
  </div>
</template>

<style scoped lang="scss">
.dashboard-section + .dashboard-section {
  margin-top: 18px;
}

.dashboard-section {
  padding-top: 2px;
}

.analytics-filter-select {
  width: 138px;
}

.analytics-filter-model {
  width: 180px;
}

.analytics-filter-unsafe {
  width: 168px;
}

.overview-grid,
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}

.overview-card,
.kpi-card {
  min-height: 116px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  justify-content: space-between;
}

.overview-card-head,
.kpi-head,
.trend-card-head,
.breakdown-head,
.section-title-row,
.table-card-head,
.table-card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.overview-card-label,
.kpi-label {
  color: #8c7458;
  font-size: 13px;
  font-weight: 700;
}

.overview-card-dot,
.kpi-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  box-shadow: 0 0 0 4px rgba(255, 193, 90, 0.14);
}

.overview-card-value,
.kpi-value {
  font-size: 30px;
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.overview-card-desc,
.trend-card-desc,
.breakdown-desc,
.table-card-desc,
.empty-desc {
  color: #9a805b;
  font-size: 12px;
  line-height: 1.5;
}

.kpi-card {
  min-height: 126px;
  position: relative;
  overflow: hidden;

  &::after {
    content: "";
    position: absolute;
    inset: 0 auto auto 0;
    width: 100%;
    height: 1px;
    background: linear-gradient(90deg, rgba(255, 193, 90, 0.85), rgba(255, 193, 90, 0));
  }
}

.kpi-label-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kpi-chip,
.trend-card-badge,
.breakdown-badge,
.section-kicker {
  flex-shrink: 0;
  padding: 4px 8px;
  border-radius: 999px;
  background: var(--theme-panel-bg-strong);
  color: var(--theme-accent-text);
  font-size: 11px;
  font-weight: 700;
}

.kpi-meta {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.kpi-meta-label {
  color: #ad8a58;
  font-size: 11px;
  font-weight: 700;
}

.kpi-meta-value {
  color: #7b6342;
  font-size: 14px;
  font-weight: 700;
}

.kpi-delta {
  font-size: 12px;
  color: #8c7458;
  line-height: 1.5;
  padding: 8px 10px 0;
  border-top: 1px dashed rgba(232, 213, 192, 0.9);

  &.positive { color: #389e0d; }
  &.negative { color: #cf1322; }
}

.section-title-row {
  margin-bottom: 10px;
  flex-wrap: wrap;
  padding: 0 2px;
}

.section-title {
  font-size: 16px;
  font-weight: 700;
  color: #5d4526;
  margin: 0;
  position: relative;
  padding-left: 14px;

  &::before {
    content: "";
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 6px;
    height: 18px;
    border-radius: 999px;
    background: var(--theme-accent);
    box-shadow: 0 6px 12px var(--theme-shadow-strong);
  }
}

.section-tip,
.page-period-meta,
.history-summary {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 13px;
  color: #8c7458;
}

.section-filter-chips {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin: -2px 2px 12px;
}

.section-filter-chip,
.page-period-chip,
.history-summary-chip {
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(255, 253, 248, 0.92);
  border: 1px solid rgba(240, 223, 190, 0.95);
}

.trend-grid,
.breakdown-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.trend-card,
.breakdown-card {
  min-height: 320px;
  padding: 18px 20px 14px;
  overflow: hidden;
}

.trend-card-wide,
.breakdown-card-wide {
  grid-column: span 2;
}

.trend-card-title,
.breakdown-title,
.empty-title {
  color: #5d4526;
  font-size: 14px;
  font-weight: 700;
}

.trend-chart,
.breakdown-chart {
  height: 260px;
}

.trend-empty,
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

.table-card-head {
  align-items: flex-start;
  padding: 18px 20px 14px;
  border-bottom: 1px solid rgba(240, 223, 190, 0.9);
  background: linear-gradient(180deg, rgba(255, 250, 240, 0.88), rgba(255, 255, 255, 0.2));
}

.table-card-title-row {
  flex-wrap: wrap;
}

.table-user-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--theme-title);
  font-weight: 700;
  min-width: 0;
  font-size: 13px;
}

.table-user-avatar {
  background: linear-gradient(180deg, var(--theme-brand-bg-start), var(--theme-brand-bg-end));
  color: var(--theme-accent-contrast);
  font-weight: 700;
}

.table-user-avatar-btn {
  appearance: none;
  border: 0;
  padding: 0;
  margin: 0;
  background: transparent;
  line-height: 0;
  cursor: pointer;
  border-radius: 999px;

  &:focus-visible {
    outline: 2px solid rgba(255, 171, 37, 0.8);
    outline-offset: 2px;
  }
}

.table-detail-btn {
  padding-inline: 0;
  font-weight: 600;
  font-size: 12px;
}

.prompt-cell-text {
  display: block;
  overflow: hidden;
  color: var(--theme-text);
  font-size: 13px;
  line-height: 1.45;
  white-space: nowrap;
  text-overflow: ellipsis;
  cursor: help;
}

.table-single-line {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  line-height: 1.4;
}

.prompt-tooltip-content {
  max-width: min(560px, 70vw);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}

:deep(.admin-mobile-table .ant-table-header) {
  position: sticky;
  top: 0;
  z-index: 2;
}

:deep(.admin-mobile-table .ant-table-thead > tr > th) {
  background: var(--theme-table-head-bg);
  color: var(--theme-title);
  font-weight: 700;
  border-bottom: 1px solid var(--theme-border);
  padding: 9px 10px;
  font-size: 13px;
  white-space: nowrap;
}

:deep(.admin-mobile-table .ant-table-tbody > tr > td) {
  padding: 8px 10px;
}

:deep(.admin-mobile-table .ant-tag) {
  margin-inline-end: 0;
  padding-inline: 6px;
  font-size: 11px;
  line-height: 18px;
  border-radius: 999px;
}

:deep(.admin-mobile-table .ant-table-content) {
  overflow-x: auto !important;
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

@media (max-width: 900px) {
  .trend-grid,
  .breakdown-grid {
    grid-template-columns: 1fr;
  }

  .trend-card-wide,
  .breakdown-card-wide {
    grid-column: span 1;
  }

  .trend-card,
  .breakdown-card {
    padding: 16px;
  }

  .trend-card-head,
  .breakdown-head,
  .table-card-head {
    flex-direction: column;
  }
}

@media (max-width: 768px) {
  .analytics-filter-select,
  .analytics-filter-model,
  .analytics-filter-unsafe,
  .analytics-filter-date {
    width: 100%;
  }

  :deep(.analytics-granularity-group .ant-radio-button-wrapper) {
    padding-inline: 12px;
  }

  .page-period-meta {
    justify-content: flex-start;
  }

  .table-card-head {
    padding: 16px;
  }
}
</style>
