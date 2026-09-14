<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { message } from "ant-design-vue";
import dayjs from "dayjs";
import { useRouter } from "vue-router";
import {
  ClockCircleOutlined,
  DownloadOutlined,
  EyeOutlined,
  LoadingOutlined,
  VideoCameraOutlined,
} from "@ant-design/icons-vue";
import { getAdminVideoTasks, listUserOptions } from "@/api/admin";
import { getVideoTaskScenes } from "@/api/videoConfig";
import AdminUserInfoDialog from "@/components/admin/AdminUserInfoDialog.vue";
import VideoTaskDetailDialog from "@/components/video/VideoTaskDetailDialog.vue";
import { getAvatarImageSrc } from "@/api/images";
import { withApiBaseUrl } from "@/lib/assets";
import { triggerDirectDownload } from "@/lib/directDownload";
import { readStoredGridColumnCount, writeStoredGridColumnCount } from "@/lib/gridColumnPreference";
import { saveVideoGenerateDraft } from "@/lib/videoGenerateDraft";
import type { AdminUser, AdminVideoTaskResult, TaskSource, VideoTaskResult, VideoTaskSceneConfig } from "@/types";

const VIDEO_GRID_COLUMN_OPTIONS = [3, 4, 5] as const;
type VideoGridColumnOption = typeof VIDEO_GRID_COLUMN_OPTIONS[number];
const DEFAULT_VIDEO_GRID_COLUMN_COUNT: VideoGridColumnOption = 4;
const VIDEO_GRID_COLUMN_COUNT_KEY = "adminVideoGridColumnCount";
const VIDEO_POLL_INTERVAL_MS = 10000;

const items = ref<AdminVideoTaskResult[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const loading = ref(false);
const loadingMore = ref(false);
const gridColumnCount = ref<VideoGridColumnOption>(
  readStoredGridColumnCount(
    VIDEO_GRID_COLUMN_COUNT_KEY,
    VIDEO_GRID_COLUMN_OPTIONS,
    DEFAULT_VIDEO_GRID_COLUMN_COUNT,
  ),
);
const sourceFilter = ref<TaskSource | undefined>(undefined);
const modelFilter = ref<string | undefined>(undefined);
const statusFilter = ref<"pending" | "queued" | "processing" | "success" | "failed" | undefined>(undefined);
const fallbackFilter = ref<"used" | undefined>(undefined);
const includeUnsafeTasks = ref(true);
const userFilter = ref<string | undefined>(undefined);
const promptFilter = ref("");
const dateRangeFilter = ref<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
const users = ref<AdminUser[]>([]);
const usersLoading = ref(false);
const taskScenes = ref<VideoTaskSceneConfig[]>([]);
const detailOpen = ref(false);
const detailItem = ref<AdminVideoTaskResult | null>(null);
const userInfoDialogOpen = ref(false);
const selectedUserInfo = ref<AdminUser | null>(null);
const loadMoreAnchor = ref<HTMLElement | null>(null);
const playingVideoTaskIds = ref<Set<string>>(new Set());
const videoPlayerRefs = new Map<string, HTMLVideoElement>();
const router = useRouter();

let loadMoreObserver: IntersectionObserver | null = null;
let filterDebounceTimer: number | null = null;
let videoPollTimer: number | null = null;

const detailModelOptions = computed(() => (
  taskScenes.value.map((scene) => ({
    label: scene.display_name || scene.scene_label || scene.scene_key,
    value: scene.scene_key,
  }))
));
const modelLabelMap = computed(() => new Map(detailModelOptions.value.map((item) => [item.value, item.label])));
const activeFilterCount = computed(() => {
  let count = 0;
  if (sourceFilter.value) count += 1;
  if (modelFilter.value) count += 1;
  if (statusFilter.value) count += 1;
  if (fallbackFilter.value) count += 1;
  if (!includeUnsafeTasks.value) count += 1;
  if (userFilter.value) count += 1;
  if (promptFilter.value.trim()) count += 1;
  if (dateRangeFilter.value) count += 1;
  return count;
});
const hasMoreVideoTasks = computed(() => items.value.length < total.value);
const gridStyle = computed(() => ({
  "--history-grid-columns": String(gridColumnCount.value),
}));

watch(gridColumnCount, (count) => {
  writeStoredGridColumnCount(VIDEO_GRID_COLUMN_COUNT_KEY, count);
});

function hasRunningTasks(list: AdminVideoTaskResult[]) {
  return list.some((item) => ["pending", "queued", "processing"].includes(item.status));
}

function stopVideoPolling() {
  if (videoPollTimer) {
    clearInterval(videoPollTimer);
    videoPollTimer = null;
  }
}

function syncVideoPolling() {
  if (!hasRunningTasks(items.value)) {
    stopVideoPolling();
    return;
  }
  if (videoPollTimer) return;
  videoPollTimer = window.setInterval(() => {
    if (loading.value || loadingMore.value) return;
    void loadVideoTasks(true);
  }, VIDEO_POLL_INTERVAL_MS);
}

function getQuery() {
  return {
    source: sourceFilter.value,
    model: modelFilter.value,
    prompt: promptFilter.value,
    status: statusFilter.value,
    user_id: userFilter.value,
    used_fallback_api: fallbackFilter.value === "used" ? true : undefined,
    include_unsafe_tasks: includeUnsafeTasks.value,
    start_date: dateRangeFilter.value?.[0].startOf("day").toISOString(),
    end_date: dateRangeFilter.value?.[1].endOf("day").toISOString(),
  };
}

async function fetchVideoTaskPage(targetPage: number) {
  return getAdminVideoTasks(targetPage, pageSize.value, getQuery());
}

function syncDetail(list: AdminVideoTaskResult[]) {
  if (!detailItem.value) return;
  const refreshedDetail = list.find((item) => item.id === detailItem.value?.id);
  if (!refreshedDetail) return;
  if (detailItem.value.status === "success" && refreshedDetail.status === "success") return;
  detailItem.value = refreshedDetail;
}

async function loadVideoTasks(silent = false) {
  if (!silent) loading.value = true;
  try {
    const targetPages = Math.max(1, page.value);
    const results = await Promise.all(
      Array.from({ length: targetPages }, (_, index) => fetchVideoTaskPage(index + 1)),
    );
    const mergedItems = results.flatMap((result) => result.items);
    items.value = mergedItems;
    total.value = results[0]?.total || 0;
    syncDetail(mergedItems);
    syncVideoPolling();
  } catch {
    if (!silent) message.error("获取用户视频失败");
  } finally {
    if (!silent) loading.value = false;
  }
}

async function loadNextPage() {
  if (loading.value || loadingMore.value || !hasMoreVideoTasks.value) return;
  loadingMore.value = true;
  try {
    const nextPage = page.value + 1;
    const res = await fetchVideoTaskPage(nextPage);
    items.value = [...items.value, ...res.items];
    total.value = res.total;
    page.value = nextPage;
    syncVideoPolling();
  } catch {
    message.error("加载更多用户视频失败");
  } finally {
    loadingMore.value = false;
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

function handleUserFilterDropdownVisible(open: boolean) {
  if (open) void loadUsers();
}

function setupLoadMoreObserver(target: HTMLElement | null) {
  loadMoreObserver?.disconnect();
  loadMoreObserver = null;
  if (!target) return;
  loadMoreObserver = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) void loadNextPage();
    },
    { root: null, rootMargin: "0px 0px 260px 0px", threshold: 0.01 },
  );
  loadMoreObserver.observe(target);
}

async function loadTaskScenes() {
  try {
    taskScenes.value = await getVideoTaskScenes();
  } catch {
    taskScenes.value = [];
  }
}

function resetFilters() {
  sourceFilter.value = undefined;
  modelFilter.value = undefined;
  statusFilter.value = undefined;
  fallbackFilter.value = undefined;
  includeUnsafeTasks.value = true;
  userFilter.value = undefined;
  promptFilter.value = "";
  dateRangeFilter.value = null;
}

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function formatRunTime(task: AdminVideoTaskResult) {
  if (!task.request_started_at || !task.request_finished_at) return "";
  const durationSeconds = dayjs(task.request_finished_at).diff(dayjs(task.request_started_at), "second");
  if (durationSeconds <= 0) return "0秒";
  const minutes = Math.floor(durationSeconds / 60);
  const remainSeconds = durationSeconds % 60;
  if (minutes <= 0) return `${remainSeconds}秒`;
  return `${minutes}分${remainSeconds}秒`;
}

function getRunTimeTitle(task: AdminVideoTaskResult) {
  const runTime = formatRunTime(task);
  if (!runTime) return "";
  return `接口调用耗时 ${runTime}（${formatTime(task.request_started_at)} - ${formatTime(task.request_finished_at)}）`;
}

function statusLabel(status: AdminVideoTaskResult["status"]) {
  const mapping: Record<string, string> = {
    pending: "等待中",
    queued: "排队中",
    processing: "处理中",
    success: "成功",
    failed: "失败",
  };
  return mapping[status] || status;
}

function sourceLabel(source: TaskSource) {
  if (source === "app") return "App";
  if (source === "api") return "API";
  return "Web";
}

function modeLabel(task: AdminVideoTaskResult) {
  if (task.generation_mode === "first_last_frame") return "首尾帧";
  if (task.generation_mode === "image_to_video") return "图生视频";
  if (task.generation_mode === "text_to_video") return "文生视频";
  return task.reference_images?.length ? "图生视频" : "文生视频";
}

function getModelLabel(model?: string) {
  if (!model) return "";
  return modelLabelMap.value.get(model) || model;
}

function getSpecLabel(task: AdminVideoTaskResult) {
  return [
    modeLabel(task),
    task.duration_seconds ? `${task.duration_seconds}秒` : "",
    task.resolution || "",
    sourceLabel(task.source),
  ].filter(Boolean).join(" / ");
}

function getVideoPoster(task: AdminVideoTaskResult) {
  const coverUrl = withApiBaseUrl(task.videos[0]?.cover_url || "");
  if (coverUrl) return coverUrl;
  const referenceUrl = withApiBaseUrl(task.reference_images?.[0] || "");
  if (referenceUrl) return referenceUrl;
  return "";
}

function getVideoSourceUrl(task: Pick<VideoTaskResult, "videos">) {
  return withApiBaseUrl(task.videos[0]?.video_url || "");
}

function hasVideoStarted(taskId: string) {
  return playingVideoTaskIds.value.has(taskId);
}

function setVideoPlayerRef(taskId: string, el: unknown) {
  if (el instanceof HTMLVideoElement) {
    videoPlayerRefs.set(taskId, el);
    return;
  }
  videoPlayerRefs.delete(taskId);
}

function markVideoStarted(taskId: string) {
  if (playingVideoTaskIds.value.has(taskId)) return;
  const next = new Set(playingVideoTaskIds.value);
  next.add(taskId);
  playingVideoTaskIds.value = next;
}

async function handlePlayVideo(taskId: string) {
  const video = videoPlayerRefs.get(taskId);
  if (!video) return;
  markVideoStarted(taskId);
  try {
    await video.play();
  } catch {
    message.warning("视频暂时无法播放，请稍后重试");
  }
}

function openDetail(task: AdminVideoTaskResult) {
  detailItem.value = task;
  detailOpen.value = true;
}

const detailItemIndex = computed(() => {
  if (!detailOpen.value || !detailItem.value) return -1;
  return items.value.findIndex((item) => item.id === detailItem.value?.id);
});

const hasDetailPrev = computed(() => detailItemIndex.value > 0);
const hasDetailNext = computed(() => (
  detailItemIndex.value >= 0
  && detailItemIndex.value < items.value.length - 1
));

function navigateDetail(delta: -1 | 1) {
  const nextIndex = detailItemIndex.value + delta;
  const nextItem = items.value[nextIndex];
  if (!nextItem) return;
  openDetail(nextItem);
}

function findAdminUser(userId?: string) {
  if (!userId) return null;
  return users.value.find((user) => user.id === userId) || null;
}

function openUserInfoDialog(task: AdminVideoTaskResult) {
  if (!task.user_id) return;
  const matchedUser = findAdminUser(task.user_id);
  selectedUserInfo.value = matchedUser || {
    id: task.user_id,
    username: task.username || "未知用户",
    avatar_url: task.avatar_url || "",
    role: "user",
    status: "",
    is_whitelisted: false,
    credits: 0,
    consumed_credits: 0,
    created_at: "",
  };
  userInfoDialogOpen.value = true;
}

function filterBySelectedUser(user = selectedUserInfo.value) {
  if (!user?.id) return;
  userFilter.value = user.id;
  page.value = 1;
  userInfoDialogOpen.value = false;
  void loadVideoTasks(true);
}

function handleDownloadVideo(task: Pick<VideoTaskResult, "id" | "videos">) {
  if (!task.videos[0]?.video_url) {
    message.warning("当前没有可下载的原视频");
    return;
  }
  try {
    triggerDirectDownload(task.videos[0]?.video_url || "", `${task.id}.${task.videos[0]?.video_format || "mp4"}`);
  } catch {
    message.error("原视频下载失败");
  }
}

function handleDetailReedit(task: VideoTaskResult) {
  const mode = task.generation_mode === "first_last_frame"
    ? "firstLastFrame"
    : (task.generation_mode === "image_to_video" || task.reference_images?.length ? "imageToVideo" : "textGenerate");
  const saved = saveVideoGenerateDraft({
    mode,
    prompt: task.prompt || "",
    reference_images: (task.reference_images || []).map((item) => withApiBaseUrl(item)),
    model: task.model || "",
    aspect_ratio: task.aspect_ratio || "",
    duration_seconds: task.duration_seconds || undefined,
    resolution: task.resolution || "",
  });
  if (!saved) {
    message.warning("当前任务暂不支持回填参数");
    return;
  }
  detailOpen.value = false;
  router.push("/video-generate");
}

watch(loadMoreAnchor, (target) => {
  setupLoadMoreObserver(target);
});

watch(
  [
    sourceFilter,
    modelFilter,
    statusFilter,
    fallbackFilter,
    includeUnsafeTasks,
    userFilter,
    promptFilter,
    dateRangeFilter,
  ],
  () => {
    if (filterDebounceTimer) clearTimeout(filterDebounceTimer);
    filterDebounceTimer = window.setTimeout(() => {
      page.value = 1;
      void loadVideoTasks(true);
    }, 250);
  },
);

watch(items, (tasks) => {
  if (!detailOpen.value || !detailItem.value) return;
  const latest = tasks.find((item) => item.id === detailItem.value?.id);
  if (latest) detailItem.value = latest;
});

onMounted(() => {
  void loadVideoTasks();
  void loadTaskScenes();
});

onBeforeUnmount(() => {
  stopVideoPolling();
  if (filterDebounceTimer) {
    clearTimeout(filterDebounceTimer);
    filterDebounceTimer = null;
  }
  loadMoreObserver?.disconnect();
  loadMoreObserver = null;
  videoPlayerRefs.clear();
  playingVideoTaskIds.value = new Set();
});
</script>

<template>
  <div class="warm-page history-page">
    <div class="history-topbar">
      <div class="warm-page-heading">
        <div class="warm-page-icon history-topbar-icon">
          <ClockCircleOutlined />
        </div>
        <div>
          <div class="warm-page-title history-topbar-title">用户视频</div>
          <div class="warm-page-desc">管理员可查看所有用户的视频生成任务，并按用户、状态、模型和时间筛选。</div>
        </div>
      </div>
      <div class="history-topbar-meta">
        <span>共 {{ total }} 条结果</span>
        <span>已展示 {{ items.length }} 条</span>
      </div>
    </div>

    <div class="history-filter-bar">
      <a-select v-model:value="sourceFilter" placeholder="全部来源" class="history-filter-control history-filter-select history-filter-select-sm" allow-clear>
        <a-select-option value="web">Web</a-select-option>
        <a-select-option value="app">App</a-select-option>
        <a-select-option value="api">API</a-select-option>
      </a-select>
      <a-select v-model:value="modelFilter" placeholder="全部模型" class="history-filter-control history-filter-select history-filter-select-lg" allow-clear>
        <a-select-option v-for="option in detailModelOptions" :key="option.value" :value="option.value">
          {{ option.label }}
        </a-select-option>
      </a-select>
      <a-select v-model:value="statusFilter" placeholder="全部状态" class="history-filter-control history-filter-select" allow-clear>
        <a-select-option value="pending">等待中</a-select-option>
        <a-select-option value="queued">排队中</a-select-option>
        <a-select-option value="processing">处理中</a-select-option>
        <a-select-option value="success">成功</a-select-option>
        <a-select-option value="failed">失败</a-select-option>
      </a-select>
      <a-select
        v-model:value="fallbackFilter"
        placeholder="备用接口"
        class="history-filter-control history-filter-select"
        allow-clear
      >
        <a-select-option value="used">使用了备用接口</a-select-option>
      </a-select>
      <a-select
        v-model:value="includeUnsafeTasks"
        class="history-filter-control history-filter-select"
      >
        <a-select-option :value="true">包含不合规错误</a-select-option>
        <a-select-option :value="false">不含不合规错误</a-select-option>
      </a-select>
      <a-select
        v-model:value="userFilter"
        placeholder="全部用户"
        class="history-filter-control history-filter-select history-filter-select-user"
        allow-clear
        show-search
        option-filter-prop="label"
        :loading="usersLoading"
        @dropdownVisibleChange="handleUserFilterDropdownVisible"
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
      <a-input
        v-model:value="promptFilter"
        placeholder="按提示词筛选"
        class="history-filter-control history-filter-prompt"
        allow-clear
      />
      <a-range-picker
        v-model:value="dateRangeFilter"
        :placeholder="['开始日期', '结束日期']"
        class="history-filter-control history-filter-date"
      />
      <a-select v-model:value="gridColumnCount" placeholder="每行列数" class="history-filter-control history-filter-columns">
        <a-select-option :value="3">3 列</a-select-option>
        <a-select-option :value="4">4 列</a-select-option>
        <a-select-option :value="5">5 列</a-select-option>
      </a-select>
      <a-button class="history-filter-btn history-filter-btn-secondary" @click="resetFilters">重置</a-button>
    </div>

    <a-spin :spinning="loading">
      <div v-if="!items.length && !loading" class="empty-state warm-card">
        <a-empty :description="activeFilterCount ? '没有符合条件的视频任务' : '暂无用户视频任务'" />
      </div>

      <TransitionGroup v-else name="history-card" tag="div" class="history-grid" :style="gridStyle">
        <div
          v-for="(item, index) in items"
          :key="item.id"
          class="result-card warm-card"
          :style="{ '--history-card-delay': `${Math.min(index, 9) * 45}ms` }"
          @click="openDetail(item)"
        >
          <div
            class="result-card-media"
            :class="{
              'result-card-media-failed': item.status === 'failed',
              'result-card-media-pending': ['pending', 'queued', 'processing'].includes(item.status),
            }"
          >
            <button
              type="button"
              class="result-card-user"
              @click.stop="openUserInfoDialog(item)"
            >
              <a-avatar :size="22" :src="getAvatarImageSrc(item.avatar_url) || undefined" class="result-card-user-avatar">
                {{ item.username?.charAt(0)?.toUpperCase() }}
              </a-avatar>
              <span class="result-card-user-name">{{ item.username || "未知用户" }}</span>
            </button>

            <div
              v-if="item.status === 'success' && getVideoSourceUrl(item)"
              class="result-card-video-shell"
              :class="{ 'is-started': hasVideoStarted(item.id) }"
            >
              <video
                :ref="(el) => setVideoPlayerRef(item.id, el)"
                class="result-card-video-player"
                :poster="getVideoPoster(item) || undefined"
                :src="getVideoSourceUrl(item)"
                :controls="hasVideoStarted(item.id)"
                playsinline
                preload="metadata"
                @play="markVideoStarted(item.id)"
                @click.stop
              />
              <button
                v-if="!hasVideoStarted(item.id)"
                type="button"
                class="result-card-video-play-btn"
                aria-label="播放视频"
                @click.stop="handlePlayVideo(item.id)"
              >
                <svg class="result-card-video-play-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M7.2 6.4c0-.9 1-1.45 1.75-1l8.1 4.7c.8.45.8 1.55 0 2l-8.1 4.7c-.75.45-1.75-.1-1.75-1V6.4Z" />
                </svg>
              </button>
            </div>
            <div
              v-else-if="item.status === 'failed'"
              class="result-card-placeholder result-card-placeholder-failed"
            >
              <div class="result-card-failed-copy">
                <strong>视频生成失败</strong>
                <span>{{ item.error_message || item.videos[0]?.error_message || "任务执行失败，请查看详情" }}</span>
              </div>
            </div>
            <img
              v-else-if="getVideoPoster(item)"
              :src="getVideoPoster(item)"
              alt="视频封面"
              loading="lazy"
            />
            <div v-else class="result-card-placeholder">
              <template v-if="['pending', 'queued', 'processing'].includes(item.status)">
                <a-spin
                  :indicator="h(LoadingOutlined, { style: { fontSize: '28px', color: '#7c8db5' } })"
                />
              </template>
              <VideoCameraOutlined v-else />
            </div>

            <div v-if="getModelLabel(item.model)" class="result-card-model-badge" :title="getModelLabel(item.model)">
              {{ getModelLabel(item.model) }}
            </div>
            <div v-if="formatRunTime(item)" class="result-card-run-time" :title="getRunTimeTitle(item)">
              {{ formatRunTime(item) }}
            </div>
            <div v-if="getSpecLabel(item)" class="result-card-spec-badge" :title="getSpecLabel(item)">
              {{ getSpecLabel(item) }}
            </div>
            <div v-if="item.used_fallback_api" class="result-card-fallback-badge">
              备用接口
            </div>
            <div
              v-if="item.task_is_deleted"
              class="result-card-soft-deleted-badge"
              :class="{ 'result-card-soft-deleted-badge-stacked': !!getModelLabel(item.model) }"
            >
              已软删
            </div>

            <div class="history-overlay-actions history-overlay-actions-top">
              <a-tooltip title="查看详情">
                <a-button shape="circle" type="text" class="history-overlay-btn" @click.stop="openDetail(item)">
                  <template #icon><EyeOutlined /></template>
                </a-button>
              </a-tooltip>
            </div>

            <div class="history-overlay-actions history-overlay-actions-bottom">
              <a-tooltip v-if="item.videos[0]?.video_url" title="下载原视频">
                <a-button shape="circle" type="text" class="history-overlay-btn" @click.stop="handleDownloadVideo(item)">
                  <template #icon><DownloadOutlined /></template>
                </a-button>
              </a-tooltip>
            </div>
          </div>
        </div>
      </TransitionGroup>
    </a-spin>

    <div v-if="loadingMore" class="history-load-more-tip">
      <a-spin size="small" />
      <span>正在加载更多用户视频...</span>
    </div>
    <div v-else-if="items.length && !hasMoreVideoTasks" class="history-load-more-tip history-load-more-tip-finished">
      已加载全部用户视频
    </div>
    <div
      v-if="items.length && hasMoreVideoTasks"
      ref="loadMoreAnchor"
      class="history-load-more-anchor"
      aria-hidden="true"
    />

    <VideoTaskDetailDialog
      :open="detailOpen"
      :item="detailItem"
      :model-options="detailModelOptions"
      :has-prev="hasDetailPrev"
      :has-next="hasDetailNext"
      @update:open="detailOpen = $event"
      @reedit="handleDetailReedit"
      @download="handleDownloadVideo"
      @navigate-prev="navigateDetail(-1)"
      @navigate-next="navigateDetail(1)"
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
.history-page {
  gap: 10px;
  animation: history-page-enter var(--motion-duration-reveal) ease both;
}

@keyframes history-page-enter {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes history-fade-up {
  from {
    opacity: 0;
    transform: translate3d(0, 16px, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

.history-topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 3px;
  animation: history-fade-up var(--motion-duration-reveal) var(--motion-ease-enter) 0.04s both;
}

.history-topbar-icon {
  width: 38px;
  height: 38px;
  border-radius: 13px;
  font-size: 17px;
}

.history-topbar-title {
  font-size: 19px;
  line-height: 1.3;
}

.history-topbar .warm-page-desc {
  font-size: 13px;
  line-height: 1.6;
}

.history-topbar-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 13px;
  color: var(--theme-text-secondary);
  padding-top: 3px;
}

.history-filter-bar {
  display: flex;
  gap: 10px;
  row-gap: 5px;
  flex-wrap: nowrap;
  align-items: center;
  margin-bottom: 9px;
  animation: history-fade-up var(--motion-duration-reveal-soft) var(--motion-ease-enter) 0.12s both;

  :deep(.ant-select-single:not(.ant-select-customize-input) .ant-select-selector) {
    height: 30px !important;
    min-height: 30px !important;
  }

  :deep(.ant-select-selection-item),
  :deep(.ant-select-selection-placeholder) {
    line-height: 28px !important;
  }

  :deep(.ant-select-selection-search-input) {
    height: 28px !important;
  }

  :deep(.ant-input),
  :deep(.ant-input-affix-wrapper) {
    height: 30px !important;
    min-height: 30px !important;
    padding-block: 0 !important;
  }

  :deep(.ant-input-affix-wrapper .ant-input) {
    height: 28px !important;
    line-height: 28px !important;
  }

  :deep(.ant-picker) {
    height: 30px !important;
    min-height: 30px !important;
    padding-block: 0 !important;
  }
}

.history-filter-control {
  flex: 0 1 auto;
  min-width: 0;
}

.history-filter-select {
  width: clamp(112px, 8.2vw, 160px);
}

.history-filter-select-sm {
  width: clamp(104px, 7.2vw, 140px);
}

.history-filter-select-lg {
  width: clamp(180px, 13.2vw, 255px);
}

.history-filter-select-user {
  width: clamp(132px, 9.8vw, 190px);
}

.history-filter-prompt {
  flex: 1 1 150px;
  width: clamp(140px, 11vw, 220px);
}

.history-filter-date {
  width: clamp(210px, 14vw, 250px);
}

.history-filter-columns {
  width: 70px;
}

.history-filter-btn {
  height: 30px;
  border-radius: 11px;
  font-size: 13px;
  font-weight: 600;
  box-shadow: none;
}

.history-filter-btn-secondary {
  border-color: var(--theme-panel-border-strong) !important;
  background: var(--theme-panel-bg-strong) !important;
  color: var(--theme-accent-text) !important;

  &:hover,
  &:focus {
    border-color: var(--theme-border-strong) !important;
    background: var(--theme-control-hover-bg) !important;
    color: var(--theme-accent-text-hover) !important;
  }
}

.empty-state {
  padding: 72px 0;
  text-align: center;
  animation: history-fade-up var(--motion-duration-reveal) var(--motion-ease-enter) 0.2s both;
}

.history-grid {
  display: grid;
  grid-template-columns: repeat(var(--history-grid-columns, 4), minmax(0, 1fr));
  gap: 12px;
}

.history-grid .result-card.warm-card {
  border: none;
  background: transparent;
  box-shadow: none;
}

.result-card {
  position: relative;
  padding: 0;
  overflow: visible;
  cursor: pointer;
  transition:
    transform var(--motion-duration-hover) var(--motion-ease-enter),
    box-shadow var(--motion-duration-hover) var(--motion-ease-soft);

  &:hover {
    transform: translateY(-6px);
    box-shadow: none;
  }

  &:hover .result-card-media {
    box-shadow: 0 16px 28px var(--theme-shadow-medium);
    border-color: var(--theme-border-strong);
  }

  &:hover .result-card-media img {
    transform: scale(1.02);
  }

  &:hover .result-card-video-player {
    transform: scale(1.02);
  }

  &:hover .result-card-model-badge,
  &:hover .result-card-run-time,
  &:hover .result-card-spec-badge,
  &:hover .result-card-fallback-badge,
  &:hover .result-card-soft-deleted-badge {
    opacity: 0;
    transform: translateY(6px);
  }
}

.result-card-user {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: 7px;
  max-width: calc(100% - 24px);
  min-width: 0;
  padding: 5px 8px 5px 5px;
  border: 1px solid rgba(255, 240, 214, 0.18);
  border-radius: 999px;
  background: rgba(76, 52, 26, 0.58);
  color: #fff7ea;
  box-shadow: 0 10px 20px rgba(34, 22, 10, 0.22);
  backdrop-filter: blur(10px);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.result-card-user-avatar {
  flex: 0 0 auto;
  background: var(--theme-accent);
  color: var(--theme-accent-contrast);
}

.result-card-user-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-card-model-badge,
.result-card-status-badge,
.result-card-run-time,
.result-card-spec-badge,
.result-card-fallback-badge,
.result-card-soft-deleted-badge {
  position: absolute;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  max-width: calc(100% - 24px);
  min-height: 24px;
  padding: 0 8px;
  border: 1px solid rgba(255, 240, 214, 0.18);
  border-radius: 999px;
  background: rgba(76, 52, 26, 0.58);
  color: #fff7ea;
  box-shadow: 0 10px 20px rgba(34, 22, 10, 0.22);
  backdrop-filter: blur(10px);
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  pointer-events: none;
  transition:
    opacity var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft);
}

.result-card-model-badge {
  left: 12px;
  bottom: 12px;
}

.result-card-status-badge {
  top: 12px;
  right: 12px;
}

.result-card-status-badge.is-success {
  background: rgba(27, 110, 74, 0.72);
}

.result-card-status-badge.is-failed {
  background: rgba(166, 60, 47, 0.72);
}

.result-card-run-time {
  top: 12px;
  right: 12px;
}

.result-card-spec-badge {
  right: 12px;
  bottom: 12px;
}

.result-card-fallback-badge {
  right: 12px;
  bottom: 42px;
  background: rgba(143, 94, 30, 0.82);
  color: #fff4d8;
}

.result-card-soft-deleted-badge {
  left: 12px;
  bottom: 12px;
  color: #fff3ef;
  background: rgba(166, 60, 47, 0.72);
  border-color: rgba(255, 224, 220, 0.22);
  box-shadow: 0 10px 20px rgba(96, 31, 22, 0.22);
}

.result-card-soft-deleted-badge-stacked {
  bottom: 42px;
}

.result-card-media {
  --media-radius: 16px;
  width: 100%;
  aspect-ratio: 1 / 1;
  box-sizing: border-box;
  border-radius: var(--media-radius);
  overflow: hidden;
  border: 1px dashed var(--theme-panel-border);
  background:
    radial-gradient(circle at 50% 45%, rgba(var(--theme-surface-strong-rgb), 0.98) 0%, rgba(var(--theme-page-base-rgb), 0.98) 58%, rgba(var(--theme-page-base-rgb), 0.96) 100%),
    linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-strong));
  box-shadow: 0 12px 24px var(--theme-shadow-soft);
  position: relative;
  transition:
    box-shadow var(--motion-duration-hover) var(--motion-ease-soft),
    border-color var(--motion-duration-hover) var(--motion-ease-soft);

  img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    object-position: center;
    display: block;
    border-radius: calc(var(--media-radius) - 1px);
    background:
      linear-gradient(180deg, rgba(20, 20, 20, 0.92), rgba(34, 34, 34, 0.96));
    transition: transform var(--motion-duration-emphasis) var(--motion-ease-enter);
  }

  &.result-card-media-failed {
    border-color: rgba(201, 73, 60, 0.72);
    background: linear-gradient(180deg, #fff0ed, #ffe1db);
  }

  &.result-card-media-pending {
    background:
      linear-gradient(180deg, rgba(255, 252, 246, 0.24), rgba(255, 248, 238, 0.34)),
      linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-panel-bg));
  }
}

.result-card-placeholder {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  color: var(--text-secondary);
  text-align: center;
  font-size: 28px;
}

.result-card-placeholder-failed {
  padding: 20px;
  background: linear-gradient(180deg, #fff1ee, #ffe1db);
}

.result-card-failed-copy {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  justify-content: center;
  max-width: 100%;
  color: #b85d47;
  text-align: center;

  strong {
    font-size: 16px;
    font-weight: 800;
    line-height: 1.4;
  }

  span {
    font-size: 12px;
    line-height: 1.7;
    word-break: break-word;
    white-space: pre-wrap;
  }
}

.result-card-video-shell {
  position: relative;
  width: 100%;
  height: 100%;
  background: #000;
}

.result-card-video-player {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
  object-position: center;
  background: linear-gradient(180deg, rgba(20, 20, 20, 0.92), rgba(34, 34, 34, 0.96));
  border-radius: calc(var(--media-radius) - 1px);
  transition: transform var(--motion-duration-emphasis) var(--motion-ease-enter);
}

.result-card-video-play-btn {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: rgba(48, 48, 48, 0.58);
  transform: translate(-50%, -50%);
  cursor: pointer;
  transition:
    background var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-press) var(--motion-ease-soft);

  &:hover {
    background: rgba(36, 36, 36, 0.72);
  }

  &:active {
    transform: translate(-50%, -50%) scale(0.96);
  }
}

.result-card-video-play-icon {
  width: 34px;
  height: 34px;
  margin: 0;
  fill: #fff;
}

.history-overlay-actions {
  position: absolute;
  display: flex;
  gap: 8px;
  z-index: 2;
  opacity: 0;
  transform: translateY(6px);
  pointer-events: none;
  transition:
    opacity var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft);
}

.history-overlay-actions-top {
  top: 12px;
  right: 12px;
}

.history-overlay-actions-bottom {
  right: 12px;
  bottom: 12px;
}

.result-card:hover .history-overlay-actions,
.result-card:focus-within .history-overlay-actions {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

.history-overlay-btn {
  width: 32px !important;
  height: 32px !important;
  min-width: 32px !important;
  padding: 0 !important;
  border-radius: 50% !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  border: 1px solid rgba(255, 240, 214, 0.18) !important;
  background: rgba(76, 52, 26, 0.58) !important;
  color: #fff7ea !important;
  box-shadow: 0 10px 20px rgba(34, 22, 10, 0.22);
  backdrop-filter: blur(10px);
}

.history-load-more-tip {
  margin-top: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

.history-load-more-tip-finished {
  color: var(--text-muted);
}

.history-load-more-anchor {
  width: 100%;
  height: 1px;
  margin-top: 1px;
}

.history-card-enter-active,
.history-card-leave-active {
  transition:
    opacity var(--motion-duration-emphasis) var(--motion-ease-soft),
    transform var(--motion-duration-emphasis-plus) var(--motion-ease-enter);
  transition-delay: var(--history-card-delay, 0ms);
}

.history-card-enter-from,
.history-card-leave-to {
  opacity: 0;
  transform: translate3d(0, 22px, 0) scale(0.985);
}

.history-card-move {
  transition: transform var(--motion-duration-reveal-fast) var(--motion-ease-enter);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .history-page .result-card-user,
html:is([data-theme="dark"], [data-theme="midnight"]) .history-page .result-card-model-badge,
html:is([data-theme="dark"], [data-theme="midnight"]) .history-page .result-card-status-badge,
html:is([data-theme="dark"], [data-theme="midnight"]) .history-page .result-card-run-time,
html:is([data-theme="dark"], [data-theme="midnight"]) .history-page .result-card-spec-badge,
html:is([data-theme="dark"], [data-theme="midnight"]) .history-page .result-card-fallback-badge,
html:is([data-theme="dark"], [data-theme="midnight"]) .history-page .result-card-soft-deleted-badge,
html:is([data-theme="dark"], [data-theme="midnight"]) .history-page .history-overlay-btn {
  border-color: var(--theme-panel-border) !important;
  background: rgba(var(--theme-surface-strong-rgb), 0.9) !important;
  color: var(--theme-accent-text) !important;
  box-shadow: 0 10px 20px var(--theme-shadow-soft);
}

@media (max-width: 900px) {
  .history-topbar {
    flex-direction: column;
    align-items: stretch;
  }

  .history-filter-bar {
    flex-wrap: wrap;
  }

  .history-filter-select,
  .history-filter-select-sm,
  .history-filter-select-lg,
  .history-filter-select-user,
  .history-filter-prompt,
  .history-filter-date {
    flex: 1 1 160px;
    width: auto;
  }

  .history-grid {
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  }
}
</style>
