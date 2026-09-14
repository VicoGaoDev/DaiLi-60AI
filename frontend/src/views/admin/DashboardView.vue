<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { message, notification } from "ant-design-vue";
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";
import { BarChartOutlined } from "@ant-design/icons-vue";
import { useRouter } from "vue-router";
import { getGenerationModels, getTaskScenes } from "@/api/config";
import {
  getAdminUnresolvedFeedbackCount,
  getAdminAnalyticsBreakdown,
  getAdminAnalyticsSummary,
  getAdminAnalyticsTimeseries,
  getAdminHistoryDetail,
  getAdminHistory,
  listUserOptions,
} from "@/api/admin";
import { setStoredAdminUnresolvedFeedbackCount } from "@/lib/adminFeedbackNotice";
import { getAvatarImageSrc } from "@/api/images";
import { isSessionExpiredError } from "@/lib/authError";
import AdminUserInfoDialog from "@/components/admin/AdminUserInfoDialog.vue";
import AnalyticsFilterBar from "@/components/admin/AnalyticsFilterBar.vue";
import BreakdownCharts from "@/components/admin/BreakdownCharts.vue";
import HistoryDetailDialog from "@/components/history/HistoryDetailDialog.vue";
import KpiCards from "@/components/admin/KpiCards.vue";
import TrendCharts from "@/components/admin/TrendCharts.vue";
import type {
  AdminAnalyticsBreakdown,
  AdminAnalyticsGranularity,
  AdminAnalyticsQuery,
  AdminAnalyticsSummary,
  AdminAnalyticsTimeseries,
  AdminUser,
  GenerationModelOption,
  HistoryFilter,
  HistoryItem,
  TaskSceneConfig,
  TaskSource,
  TaskType,
  UserHistoryCard,
} from "@/types";

type FallbackCardItem = {
  key: string;
  label: string;
  value: number | string;
  desc: string;
  color: string;
};

const router = useRouter();
const analyticsLoading = ref(false);
const historyLoading = ref(false);
const historyRefreshing = ref(false);
const summary = ref<AdminAnalyticsSummary | null>(null);
const timeseries = ref<AdminAnalyticsTimeseries | null>(null);
const breakdown = ref<AdminAnalyticsBreakdown | null>(null);
const users = ref<AdminUser[]>([]);
const usersLoading = ref(false);
const generationModels = ref<GenerationModelOption[]>([]);
const taskScenes = ref<TaskSceneConfig[]>([]);
const history = ref<HistoryItem[]>([]);
const historyTotal = ref(0);
const historyCreditTotal = ref(0);
const page = ref(1);
const granularity = ref<AdminAnalyticsGranularity>("3hour");
const preset = ref("today");
const ready = ref(false);
const detailOpen = ref(false);
const detailRequestPreviewLoading = ref(false);
const detailItem = ref<UserHistoryCard | null>(null);
const userInfoDialogOpen = ref(false);
const selectedUserInfo = ref<AdminUser | null>(null);
let activeDetailRequestKey = "";
const HISTORY_PAGE_SIZE = 20;
const HISTORY_TABLE_SCROLL_X = 1400;
const UNRESOLVED_FEEDBACK_NOTIFICATION_KEY = "admin-unresolved-feedback";

const filters = reactive<{
  status: string | undefined;
  user_id: string | undefined;
  source: TaskSource | undefined;
  model: string | undefined;
  mode: TaskType | undefined;
  canvas_task_filter: "all" | "canvas" | "non_canvas";
  include_unsafe_tasks: boolean;
  dateRange: [Dayjs, Dayjs] | null;
}>({
  status: undefined,
  user_id: undefined,
  source: undefined,
  model: undefined,
  mode: undefined,
  canvas_task_filter: "all",
  include_unsafe_tasks: true,
  dateRange: null,
});

const columns = [
  { title: "用户", dataIndex: "username", width: 172 },
  { title: "模型", dataIndex: "model", width: 165 },
  { title: "提示词", dataIndex: "prompt", width: 240, ellipsis: true },
  { title: "状态", dataIndex: "status", width: 128 },
  { title: "来源", dataIndex: "source", width: 68 },
  { title: "类型", dataIndex: "mode", width: 80 },
  { title: "消耗积分", dataIndex: "credit_cost", width: 84 },
  { title: "时间", dataIndex: "created_at", width: 148 },
  { title: "操作", key: "actions", width: 72, fixed: "right" as const },
];

const modelOptions = computed(() => {
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
  optionMap.set("提示词反推", "提示词反推");
  return Array.from(optionMap.entries()).map(([value, label]) => ({ value, label }));
});

const activeFilterSummary = computed(() => {
  const chips: string[] = [];
  if (filters.user_id) {
    const user = users.value.find((item) => item.id === filters.user_id);
    if (user) chips.push(`用户：${user.username}`);
  }
  if (filters.source) chips.push(`来源：${sourceLabel(filters.source)}`);
  if (filters.mode) chips.push(`类型：${modeLabel(filters.mode)}`);
  if (filters.model) chips.push(`模型：${modelLabel(filters.model)}`);
  if (filters.status) chips.push(`状态：${statusLabel(filters.status)}`);
  if (filters.canvas_task_filter === "canvas") chips.push("任务来源：Canvas");
  if (filters.canvas_task_filter === "non_canvas") chips.push("任务来源：非 Canvas");
  if (!filters.include_unsafe_tasks) chips.push("错误任务：不含不合规");
  if (filters.dateRange) {
    chips.push(
      `${filters.dateRange[0].format("YYYY-MM-DD")} ~ ${filters.dateRange[1].format("YYYY-MM-DD")}`,
    );
  }
  if (!chips.length && summary.value) chips.push(`统计范围：${summary.value.current_range_label}`);
  return chips;
});

const fallbackSummaryCards = computed<FallbackCardItem[]>(() => {
  if (!summary.value) return [];
  const fallbackTaskTotal = summary.value.fallback_task_total ?? 0;
  const fallbackSuccessTasks = summary.value.fallback_success_tasks ?? 0;
  const fallbackFailedTasks = summary.value.fallback_failed_tasks ?? 0;
  const resolvedFallbackTasks = fallbackSuccessTasks + fallbackFailedTasks;
  const fallbackSuccessRate = resolvedFallbackTasks
    ? `${((fallbackSuccessTasks / resolvedFallbackTasks) * 100).toFixed(1)}%`
    : "0%";
  return [
    {
      key: "fallback_total",
      label: "触发备用接口任务数",
      value: fallbackTaskTotal,
      desc: "当前时间范围内触发备用接口的任务数量",
      color: "#1890ff",
    },
    {
      key: "fallback_success",
      label: "最终成功数",
      value: fallbackSuccessTasks,
      desc: "当前时间范围内触发备用接口后最终成功的任务数量",
      color: "#38a816",
    },
    {
      key: "fallback_failed",
      label: "最终失败数",
      value: fallbackFailedTasks,
      desc: "当前时间范围内触发备用接口后最终失败的任务数量",
      color: "#ff4d4f",
    },
    {
      key: "fallback_success_rate",
      label: "最终成功率",
      value: fallbackSuccessRate,
      desc: "当前时间范围内已结束的备用接口任务中最终成功的占比",
      color: "#1677ff",
    },
  ];
});

const processingTaskCount = computed(() => (
  breakdown.value?.status_breakdown.find((item) => item.name === "processing")?.count ?? 0
));

const filterSignature = computed(() => JSON.stringify({
  granularity: granularity.value,
  preset: preset.value,
  status: filters.status || null,
  user_id: filters.user_id || null,
  source: filters.source || null,
  model: filters.model || null,
  mode: filters.mode || null,
  canvas_task_filter: filters.canvas_task_filter,
  include_unsafe_tasks: filters.include_unsafe_tasks,
  start: filters.dateRange?.[0]?.valueOf() || null,
  end: filters.dateRange?.[1]?.valueOf() || null,
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

function buildAnalyticsQuery(): AdminAnalyticsQuery {
  const useBucketRange = granularity.value === "3hour" && preset.value === "custom";
  return {
    granularity: granularity.value,
    status: filters.status,
    user_id: filters.user_id,
    source: filters.source,
    model: filters.model,
    mode: filters.mode,
    include_unsafe_tasks: filters.include_unsafe_tasks,
    canvas_task_filter: filters.canvas_task_filter,
    start_date: formatQueryDate(useBucketRange ? filters.dateRange?.[0] : filters.dateRange?.[0].startOf("day")),
    end_date: formatQueryDate(useBucketRange ? filters.dateRange?.[1] : filters.dateRange?.[1].endOf("day")),
  };
}

function buildHistoryFilter(): HistoryFilter {
  const useBucketRange = granularity.value === "3hour" && preset.value === "custom";
  return {
    status: filters.status,
    user_id: filters.user_id,
    source: filters.source,
    model: filters.model,
    mode: filters.mode,
    canvas_task_filter: filters.canvas_task_filter,
    include_unsafe_tasks: filters.include_unsafe_tasks,
    start_date: formatQueryDate(useBucketRange ? filters.dateRange?.[0] : filters.dateRange?.[0].startOf("day")),
    end_date: formatQueryDate(useBucketRange ? filters.dateRange?.[1] : filters.dateRange?.[1].endOf("day")),
  };
}

function formatQueryDate(value?: Dayjs) {
  return value ? value.format("YYYY-MM-DDTHH:mm:ss") : undefined;
}

async function loadModels() {
  try {
    const [models, scenes] = await Promise.all([getGenerationModels(), getTaskScenes()]);
    generationModels.value = models;
    taskScenes.value = scenes;
  } catch {
    generationModels.value = [];
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
      getAdminAnalyticsSummary(query),
      getAdminAnalyticsTimeseries(query),
      getAdminAnalyticsBreakdown(query),
    ]);
    summary.value = summaryRes;
    timeseries.value = timeseriesRes;
    breakdown.value = breakdownRes;
  } catch (err: any) {
    if (isSessionExpiredError(err)) return;
    message.error("获取统计分析失败");
  } finally {
    analyticsLoading.value = false;
  }
}

async function checkUnresolvedFeedbacks() {
  try {
    const { count } = await getAdminUnresolvedFeedbackCount();
    const normalizedCount = setStoredAdminUnresolvedFeedbackCount(count);
    if (normalizedCount > 0) {
      notification.warning({
        key: UNRESOLVED_FEEDBACK_NOTIFICATION_KEY,
        message: "有用户反馈未处理",
        description: `当前有 ${normalizedCount} 条未完成的用户反馈，点击前往处理。`,
        placement: "topRight",
        duration: 5,
        style: { cursor: "pointer" },
        onClick: () => {
          notification.close(UNRESOLVED_FEEDBACK_NOTIFICATION_KEY);
          router.push("/admin/feedbacks");
        },
      });
      return;
    }
    notification.close(UNRESOLVED_FEEDBACK_NOTIFICATION_KEY);
  } catch {
    // Do not block dashboard rendering if the reminder check fails.
  }
}

async function loadHistory() {
  const showFullSpinner = history.value.length === 0;
  if (showFullSpinner) historyLoading.value = true;
  historyRefreshing.value = true;
  try {
    const res = await getAdminHistory(page.value, HISTORY_PAGE_SIZE, buildHistoryFilter());
    history.value = res.items;
    historyTotal.value = res.total;
    historyCreditTotal.value = res.total_credit_cost;
  } catch (err: any) {
    if (isSessionExpiredError(err)) return;
    message.error("获取任务记录失败");
  } finally {
    historyLoading.value = false;
    historyRefreshing.value = false;
  }
}

async function loadPageData() {
  await Promise.all([loadAnalytics(), loadHistory()]);
}

async function handleRefresh() {
  await Promise.all([loadPageData(), checkUnresolvedFeedbacks()]);
}

function handleKpiCardClick(key: string) {
  if (key === "failed_tasks") {
    router.push("/admin/error-analytics");
    return;
  }
  if (key === "new_users") {
    router.push("/admin/users");
  }
}

function handleReset() {
  filters.status = undefined;
  filters.user_id = undefined;
  filters.source = undefined;
  filters.model = undefined;
  filters.mode = undefined;
  filters.canvas_task_filter = "all";
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
  loadHistory();
}

function historyRecordToDetailItem(record: HistoryItem): UserHistoryCard {
  const primaryImage = record.images?.[0];
  return {
    history_id: record.history_id,
    item_type: record.item_type,
    display_id: record.display_id,
    task_id: record.task_id,
    canvas_id: record.canvas_id,
    canvas_project_id: record.canvas_project_id,
    image_id: primaryImage?.id ?? null,
    user_id: record.user_id,
    username: record.username,
    avatar_url: record.avatar_url,
    is_pinned: false,
    image_url: primaryImage?.image_url || "",
    preview_url: primaryImage?.preview_url || "",
    thumb_url: primaryImage?.thumb_url || "",
    status: record.status as UserHistoryCard["status"],
    image_format: primaryImage?.image_format || "",
    image_size_bytes: primaryImage?.image_size_bytes || 0,
    task_is_deleted: record.task_is_deleted,
    is_soft_deleted: record.is_soft_deleted,
    task_type: record.task_type,
    model: record.model,
    source: record.source,
    mode: record.mode,
    prompt: record.prompt,
    reference_images: record.reference_images || [],
    reference_image_thumbs: [],
    source_image: "",
    source_image_thumb: "",
    mask_image: "",
    mask_image_thumb: "",
    num_images: record.num_images,
    size: record.size,
    resolution: record.resolution,
    custom_size: record.custom_size,
    credit_cost: record.credit_cost,
    credit_refunded: record.credit_refunded,
    used_fallback_api: record.used_fallback_api,
    created_at: record.created_at,
    error_message: record.error_message,
    provider_error_message: record.provider_error_message,
    images: record.images || [],
    api_attempts: record.api_attempts || [],
  };
}

async function openHistoryDetail(record: HistoryItem) {
  detailOpen.value = true;
  detailItem.value = historyRecordToDetailItem(record);
  const requestKey = `${record.item_type}:${record.task_id || record.history_id || record.display_id || record.created_at}`;
  activeDetailRequestKey = requestKey;
  detailRequestPreviewLoading.value = true;
  try {
    const detail = await getAdminHistoryDetail({
      item_type: record.item_type,
      task_id: record.task_id,
      history_id: record.history_id,
    });
    if (activeDetailRequestKey !== requestKey) return;
    detailItem.value = detail;
  } catch {
    if (activeDetailRequestKey !== requestKey) return;
    message.error("获取任务详情失败");
  } finally {
    if (activeDetailRequestKey === requestKey) {
      detailRequestPreviewLoading.value = false;
    }
  }
}

function handleBucketClick(payload: { start?: string | null; end?: string | null }) {
  if (!payload.start || !payload.end) return;
  filters.dateRange = [dayjs(payload.start), dayjs(payload.end)];
  preset.value = "custom";
}

function handleBreakdownFilter(payload: { type: "status" | "source" | "mode" | "model" | "user" | "canvas"; value: string }) {
  if (payload.type === "status") filters.status = payload.value;
  if (payload.type === "source") filters.source = payload.value as TaskSource;
  if (payload.type === "mode") filters.mode = payload.value as TaskType;
  if (payload.type === "model") filters.model = payload.value;
  if (payload.type === "canvas" && (payload.value === "canvas" || payload.value === "non_canvas")) {
    filters.canvas_task_filter = payload.value;
  }
  if (payload.type === "user") {
    const matchedUser = users.value.find((item) => item.username === payload.value);
    if (matchedUser) filters.user_id = matchedUser.id;
  }
}

function findHistoryUser(record: HistoryItem) {
  if (record.user_id) {
    const matchedById = users.value.find((item) => item.id === record.user_id);
    if (matchedById) return matchedById;
  }
  return users.value.find((item) => item.username === record.username) || null;
}

function openUserInfoDialog(record: HistoryItem) {
  if (!record.user_id) {
    message.warning("未找到该用户信息");
    return;
  }
  const matchedUser = findHistoryUser(record);
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

function viewUserData(user: AdminUser) {
  filters.user_id = user.id;
  userInfoDialogOpen.value = false;
}

function fmtTime(value: string) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
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

function modelLabel(value: string) {
  if (!value) return "-";
  return modelOptions.value.find((item) => item.value === value)?.label || value;
}

function statusLabel(value: string) {
  const map: Record<string, string> = {
    pending: "等待中",
    processing: "处理中",
    success: "成功",
    failed: "失败",
  };
  return map[value] || value;
}

function statusColor(value: string) {
  if (value === "success") return "green";
  if (value === "failed") return "red";
  if (value === "processing") return "orange";
  return "default";
}

function historyStatusSummary(record: HistoryItem) {
  const tags = [
    { key: "status", text: statusLabel(record.status), color: statusColor(record.status) },
  ];
  if (record.task_is_deleted) {
    tags.push({ key: "taskDeleted", text: "任务已软删", color: "red" });
  }
  if (record.is_soft_deleted) {
    tags.push({
      key: "imageDeleted",
      text: `图片软删 ${record.soft_deleted_count || 0}`,
      color: "orange",
    });
  }
  return tags;
}

onMounted(async () => {
  preset.value = defaultPresetByGranularity(granularity.value);
  applyPresetRange(preset.value);
  await Promise.all([loadModels(), loadPageData(), checkUnresolvedFeedbacks()]);
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
          <div class="warm-page-title">图片数据</div>
          <div class="warm-page-desc">单独查看图片任务的趋势、用户、来源和积分消耗，不混入视频数据。</div>
        </div>
      </div>
      <div v-if="summary" class="page-period-meta">
        <span class="page-period-chip">当前周期：{{ summary.current_range_label }}</span>
        <span class="page-period-chip">对比周期：{{ summary.previous_range_label }}</span>
      </div>
    </div>

    <AnalyticsFilterBar
      :users="users"
      :model-options="modelOptions"
      :filters="filters"
      :granularity="granularity"
      :preset="preset"
      :loading="analyticsLoading || historyLoading"
      :users-loading="usersLoading"
      @update:granularity="handleGranularityChange"
      @preset-change="handlePresetChange"
      @reset="handleReset"
      @refresh="handleRefresh"
      @user-dropdown-visible="handleUserDropdownVisible"
    />

    <section class="dashboard-section">
      <div class="section-title-row">
        <h3 class="section-title">核心指标</h3>
        <span class="section-kicker">Overview</span>
      </div>
      <KpiCards
        :summary="summary"
        :loading="analyticsLoading"
        :processing-tasks="processingTaskCount"
        @card-click="handleKpiCardClick"
      />
    </section>

    <section class="dashboard-section">
      <div class="section-title-row">
        <h3 class="section-title">备用接口任务</h3>
        <span class="section-kicker">Fallback</span>
      </div>
      <div class="overview-grid">
        <div
          v-for="(item, index) in fallbackSummaryCards"
          :key="item.key"
          class="overview-card warm-card motion-card-lift motion-fade-up"
          :style="{ '--motion-delay': `${220 + index * 40}ms` }"
        >
          <div class="overview-card-head">
            <span class="overview-card-label">{{ item.label }}</span>
            <span class="overview-card-dot" :style="{ background: item.color }" />
          </div>
          <div class="overview-card-value" :style="{ color: item.color }">{{ item.value }}</div>
          <div class="overview-card-desc">{{ item.desc }}</div>
        </div>
      </div>
    </section>

    <section class="dashboard-section">
      <div class="section-title-row">
        <h3 class="section-title">趋势分析</h3>
        <span class="section-tip">点击图表任意时间点可直接下钻到该时间范围明细。</span>
      </div>
      <div class="section-filter-chips">
        <span v-for="item in activeFilterSummary" :key="item" class="section-filter-chip">{{ item }}</span>
      </div>
      <TrendCharts :data="timeseries" :loading="analyticsLoading" @bucket-click="handleBucketClick" />
    </section>

    <section class="dashboard-section">
      <div class="section-title-row">
        <h3 class="section-title">结构分布</h3>
        <span class="section-tip">点击占比或排行图可自动带筛选查看记录。</span>
      </div>
      <div class="section-filter-chips">
        <span v-for="item in activeFilterSummary" :key="item" class="section-filter-chip">{{ item }}</span>
      </div>
      <BreakdownCharts :data="breakdown" :loading="analyticsLoading" @filter-click="handleBreakdownFilter" />
    </section>

    <section class="dashboard-section">
      <div class="warm-card warm-table-card motion-card-lift motion-fade-up" style="--motion-delay: 320ms">
        <div class="table-card-head">
          <div>
            <div class="table-card-title-row">
              <h3 class="section-title">全部任务记录</h3>
              <span class="section-kicker">Details</span>
            </div>
            <div class="table-card-desc">当前图表与筛选条件对应的任务与提示词反推明细。</div>
          </div>
          <div class="history-summary">
            <span v-if="historyRefreshing && history.length" class="history-summary-chip">更新中</span>
            <span class="history-summary-chip">筛选结果 {{ historyTotal }} 条</span>
            <span class="history-summary-chip">总消耗积分 {{ historyCreditTotal }}</span>
          </div>
        </div>

        <a-table
          :columns="columns"
          :data-source="history"
          :loading="historyLoading && !history.length"
          :row-key="(record: HistoryItem) => record.display_id || record.task_id"
          :pagination="false"
          :scroll="{ x: HISTORY_TABLE_SCROLL_X }"
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
              {{ modeLabel(record.task_type) }}
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
              <div class="history-status-tags">
                <a-tag
                  v-for="tag in historyStatusSummary(record)"
                  :key="tag.key"
                  :color="tag.color"
                >
                  {{ tag.text }}
                </a-tag>
              </div>
            </template>
            <template v-else-if="column.dataIndex === 'created_at'">
              {{ fmtTime(record.created_at) }}
            </template>
            <template v-else-if="column.key === 'actions'">
              <a-button type="link" size="small" class="table-detail-btn" @click="openHistoryDetail(record)">
                详情
              </a-button>
            </template>
          </template>
        </a-table>
      </div>

      <div v-if="historyTotal > HISTORY_PAGE_SIZE" class="warm-pagination">
        <a-pagination
          :current="page"
          :total="historyTotal"
          :page-size="HISTORY_PAGE_SIZE"
          show-less-items
          @change="handlePageChange"
        />
      </div>
    </section>
    <HistoryDetailDialog
      :open="detailOpen"
      :item="detailItem"
      :request-preview-loading="detailRequestPreviewLoading"
      :model-options="modelOptions"
      show-error-message
      show-attempt-response-preview
      @update:open="detailOpen = $event"
    />
    <AdminUserInfoDialog
      v-model:open="userInfoDialogOpen"
      :user="selectedUserInfo"
      show-view-data
      @view-data="viewUserData"
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

.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}

.overview-card {
  min-height: 116px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  justify-content: space-between;
}

.overview-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.overview-card-label {
  color: #8c7458;
  font-size: 13px;
  font-weight: 700;
}

.overview-card-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  box-shadow: 0 0 0 4px rgba(255, 193, 90, 0.14);
}

.overview-card-value {
  font-size: 30px;
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.overview-card-desc {
  color: #9a805b;
  font-size: 12px;
  line-height: 1.5;
}

.section-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
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

.section-kicker {
  flex-shrink: 0;
  padding: 5px 10px;
  border-radius: 999px;
  background: var(--theme-pill-bg);
  color: var(--theme-pill-text);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
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

.history-status-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.section-filter-chips {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin: -2px 2px 12px;
}

.section-filter-chip {
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  color: #8c7458;
  background: rgba(255, 253, 248, 0.92);
  border: 1px solid rgba(240, 223, 190, 0.95);
}

.page-period-meta {
  justify-content: flex-end;
}

.page-period-chip,
.history-summary-chip {
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(255, 253, 248, 0.92);
  border: 1px solid rgba(240, 223, 190, 0.95);
  box-shadow: 0 10px 18px rgba(236, 185, 88, 0.08);
}

.table-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid rgba(240, 223, 190, 0.9);
  background: linear-gradient(180deg, rgba(255, 250, 240, 0.88), rgba(255, 255, 255, 0.2));
}

.table-card-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.table-card-desc {
  margin-top: 8px;
  color: #9a805b;
  font-size: 12px;
  line-height: 1.5;
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

:deep(.admin-mobile-table .ant-table-tbody > tr > td) {
  padding: 8px 10px;
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
  vertical-align: bottom;
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

:deep(.admin-mobile-table .ant-tag) {
  margin-inline-end: 0;
  padding-inline: 6px;
  font-size: 11px;
  line-height: 18px;
  border-radius: 999px;
}

:deep(.admin-mobile-table .ant-table-body) {
  scrollbar-width: thin;
}

:deep(.admin-mobile-table .ant-table-content) {
  overflow-x: auto !important;
}

:deep(.admin-mobile-table .ant-table-cell-fix-right) {
  background: var(--theme-panel-bg);
}

@media (max-width: 768px) {
  :deep(.admin-mobile-table .ant-table-content) {
    overflow-x: auto !important;
  }

  .page-period-meta {
    justify-content: flex-start;
  }

  .table-card-head {
    flex-direction: column;
    padding: 16px;
  }
}
</style>
