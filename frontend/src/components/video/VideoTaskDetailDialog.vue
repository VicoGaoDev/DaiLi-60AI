<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { message } from "ant-design-vue";
import {
  CloseOutlined,
  CopyOutlined,
  DownloadOutlined,
  LeftOutlined,
  LoadingOutlined,
  PictureOutlined,
  ReloadOutlined,
  RightOutlined,
} from "@ant-design/icons-vue";
import dayjs from "dayjs";
import type { VideoTaskApiAttempt, VideoTaskResult } from "@/types";

const SIDE_NAV_WIDTH = 76;
const SIDE_NAV_BREAKPOINT = 960;

const props = withDefaults(defineProps<{
  open: boolean;
  item: VideoTaskResult | null;
  loading?: boolean;
  modelOptions?: Array<{ label: string; value: string }>;
  title?: string;
  compact?: boolean;
  showReedit?: boolean;
  hasPrev?: boolean;
  hasNext?: boolean;
}>(), {
  loading: false,
  modelOptions: () => [],
  title: "视频任务详情",
  compact: false,
  showReedit: true,
  hasPrev: false,
  hasNext: false,
});

const emit = defineEmits<{
  "update:open": [value: boolean];
  reedit: [item: VideoTaskResult];
  download: [item: VideoTaskResult];
  "navigate-prev": [];
  "navigate-next": [];
}>();

const previewVisible = ref(false);
const previewSrc = ref("");
const videoStarted = ref(false);
const videoPlayerRef = ref<HTMLVideoElement | null>(null);
const viewportWidth = ref(typeof window === "undefined" ? 1280 : window.innerWidth);
const mediaLoadedKeys = ref<Set<string>>(new Set());
const mainVideoLoadFailed = ref(false);

const modelLabelMap = computed(() => new Map(props.modelOptions.map((item) => [item.value, item.label])));
const reserveSideNav = computed(() => {
  if (typeof document === "undefined") return false;
  if (viewportWidth.value <= SIDE_NAV_BREAKPOINT) return false;
  return !!document.querySelector(".app-layout-desktop-side-nav .canvas-side-nav");
});
const panelStyle = computed(() => (
  reserveSideNav.value
    ? { left: `${SIDE_NAV_WIDTH}px` }
    : { left: "0px" }
));

function updateViewportWidth() {
  if (typeof window === "undefined") return;
  viewportWidth.value = window.innerWidth;
}

function closeDialog() {
  emit("update:open", false);
}

function navigatePrev() {
  if (!props.hasPrev) return;
  emit("navigate-prev");
}

function navigateNext() {
  if (!props.hasNext) return;
  emit("navigate-next");
}

function handleKeydown(event: KeyboardEvent) {
  if (!props.open) return;
  if (event.key === "Escape") {
    closeDialog();
    return;
  }
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    navigatePrev();
    return;
  }
  if (event.key === "ArrowRight") {
    event.preventDefault();
    navigateNext();
  }
}

watch(
  () => [props.open, props.item?.id] as const,
  ([open]) => {
    videoStarted.value = false;
    previewVisible.value = false;
    previewSrc.value = "";
    mediaLoadedKeys.value = new Set();
    mainVideoLoadFailed.value = false;
    if (typeof document === "undefined") return;
    document.body.style.overflow = open ? "hidden" : "";
  },
);

onMounted(() => {
  updateViewportWidth();
  if (typeof window !== "undefined") {
    window.addEventListener("resize", updateViewportWidth);
    window.addEventListener("keydown", handleKeydown);
  }
});

onBeforeUnmount(() => {
  if (typeof window !== "undefined") {
    window.removeEventListener("resize", updateViewportWidth);
    window.removeEventListener("keydown", handleKeydown);
  }
  if (typeof document !== "undefined") {
    document.body.style.overflow = "";
  }
});

function formatTime(t?: string | null) {
  return t ? dayjs(t).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function statusLabel(status: VideoTaskResult["status"]) {
  const mapping: Record<string, string> = {
    pending: "等待中",
    queued: "排队中",
    processing: "处理中",
    success: "成功",
    failed: "失败",
  };
  return mapping[status] || status;
}

function sourceLabel(source: VideoTaskResult["source"]) {
  if (source === "app") return "App";
  if (source === "api") return "API";
  return "Web";
}

function modeLabel(item: VideoTaskResult) {
  if (item.generation_mode === "first_last_frame") return "首尾帧";
  if (item.generation_mode === "image_to_video") return "图生视频";
  if (item.generation_mode === "text_to_video") return "文生视频";
  return item.reference_images?.length ? "图生视频" : "文生视频";
}

function getModelLabel(model?: string) {
  if (!model) return "-";
  return modelLabelMap.value.get(model) || model;
}

function formatVideoSize(size?: number) {
  const bytes = Number(size || 0);
  if (!bytes) return "-";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDuration(durationMs?: number | null) {
  if (typeof durationMs !== "number" || Number.isNaN(durationMs)) return "-";
  if (durationMs < 1000) return `${durationMs} ms`;
  return `${(durationMs / 1000).toFixed(2)} s`;
}

function detailMetaList(item: VideoTaskResult) {
  const video = item.videos[0];
  return [
    `状态：${statusLabel(item.status)}`,
    item.task_is_deleted ? "任务状态：已软删除" : "",
    `来源：${sourceLabel(item.source)}`,
    `类型：${modeLabel(item)}`,
    `模型：${getModelLabel(item.model)}`,
    item.aspect_ratio ? `宽高比：${item.aspect_ratio}` : "",
    item.duration_seconds ? `秒数：${item.duration_seconds} 秒` : "",
    item.resolution ? `分辨率：${item.resolution}` : "",
    video?.video_format ? `格式：${video.video_format}` : "",
    video?.video_size_bytes ? `大小：${formatVideoSize(video.video_size_bytes)}` : "",
    `消耗积分：${item.credit_cost || 0}${item.credit_refunded ? "（已返还）" : ""}`,
    !props.compact && item.api_attempts?.length
      ? `备用接口：${item.used_fallback_api ? "已调用" : "未调用"}`
      : "",
    !props.compact && item.request_started_at ? `开始时间：${formatTime(item.request_started_at)}` : "",
    item.request_finished_at ? `完成时间：${formatTime(item.request_finished_at)}` : "",
    !props.compact ? `创建时间：${formatTime(item.created_at)}` : "",
  ].filter(Boolean);
}

function attemptStatusLabel(status: string) {
  return status === "success" ? "成功" : "失败";
}

function attemptRoleLabel(attempt: VideoTaskApiAttempt) {
  return attempt.is_fallback ? "备用接口" : "主接口";
}

function openPreview(url?: string) {
  if (!url) return;
  previewSrc.value = url;
  previewVisible.value = true;
}

function getMediaKey(prefix: string, value: string | number | null | undefined) {
  return `${prefix}:${String(value ?? "")}`;
}

function isMediaLoaded(key: string) {
  return mediaLoadedKeys.value.has(key);
}

function markMediaLoaded(key: string) {
  if (mediaLoadedKeys.value.has(key)) return;
  const next = new Set(mediaLoadedKeys.value);
  next.add(key);
  mediaLoadedKeys.value = next;
}

function handleMainVideoLoaded() {
  markMediaLoaded(getMediaKey("main-video", props.item?.id));
  mainVideoLoadFailed.value = false;
}

function handleMainVideoError() {
  markMediaLoaded(getMediaKey("main-video", props.item?.id));
  mainVideoLoadFailed.value = true;
}

async function copyPrompt(text?: string) {
  if (!text?.trim()) return;
  try {
    await navigator.clipboard.writeText(text);
    message.success("已复制提示词");
  } catch {
    message.error("复制失败，请重试");
  }
}

async function copyBusinessId(text?: string) {
  if (!text?.trim()) return;
  try {
    await navigator.clipboard.writeText(text);
    message.success("已复制 ID");
  } catch {
    message.error("复制失败，请重试");
  }
}

async function handlePlayVideo() {
  const video = videoPlayerRef.value;
  if (!video) return;
  videoStarted.value = true;
  try {
    await video.play();
  } catch {
    message.warning("视频暂时无法播放，请稍后重试");
  }
}

function handleReedit(item: VideoTaskResult) {
  emit("reedit", item);
}

function handleDownload(item: VideoTaskResult) {
  emit("download", item);
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="video-task-detail-overlay"
      :class="{ 'is-side-nav-offset': reserveSideNav }"
      :style="panelStyle"
    >
      <div class="video-task-detail-panel">
        <div class="video-task-detail-header">
          <div class="video-task-detail-title">{{ title }}</div>
          <button type="button" class="video-task-detail-close" aria-label="关闭" @click="closeDialog">
            <CloseOutlined />
          </button>
        </div>

        <div class="video-task-detail-body">
          <div v-if="loading" class="detail-loading">
            <a-spin
              :indicator="h(LoadingOutlined, { style: { fontSize: '28px', color: '#7c8db5' } })"
            />
            <span>正在加载视频任务详情...</span>
          </div>
          <template v-else-if="item">
            <div :key="item.id" class="detail-layout">
              <div class="detail-left">
                <button
                  v-if="hasPrev"
                  type="button"
                  class="detail-nav-btn detail-nav-prev"
                  aria-label="上一个任务"
                  @click="navigatePrev"
                >
                  <LeftOutlined />
                </button>
                <button
                  v-if="hasNext"
                  type="button"
                  class="detail-nav-btn detail-nav-next"
                  aria-label="下一个任务"
                  @click="navigateNext"
                >
                  <RightOutlined />
                </button>
                <div class="detail-section">
                  <div class="detail-result-card">
                    <template v-if="['pending', 'queued', 'processing'].includes(item.status)">
                      <div class="detail-result-placeholder">
                        <a-spin
                          :indicator="h(LoadingOutlined, { style: { fontSize: '28px', color: '#7c8db5' } })"
                        />
                        <span>视频生成中，请稍候...</span>
                      </div>
                    </template>
                    <template v-else-if="item.status === 'success' && item.videos[0]?.video_url">
                      <div class="detail-video-shell" :class="{ 'is-started': videoStarted }">
                        <div
                          v-if="!isMediaLoaded(getMediaKey('main-video', item.id))"
                          class="detail-media-loading detail-media-loading-dark"
                        >
                          <a-spin :indicator="h(LoadingOutlined, { style: { fontSize: '28px', color: '#ffffff' } })" />
                        </div>
                        <video
                          ref="videoPlayerRef"
                          class="detail-video-player"
                          :class="{ 'detail-media-hidden': !isMediaLoaded(getMediaKey('main-video', item.id)) && !mainVideoLoadFailed }"
                          :poster="item.videos[0].cover_url || undefined"
                          :src="item.videos[0].video_url"
                          :controls="videoStarted"
                          playsinline
                          preload="metadata"
                          @play="videoStarted = true"
                          @loadeddata="handleMainVideoLoaded"
                          @error="handleMainVideoError"
                        />
                        <button
                          v-if="!videoStarted && isMediaLoaded(getMediaKey('main-video', item.id)) && !mainVideoLoadFailed"
                          type="button"
                          class="detail-video-play-btn"
                          aria-label="播放视频"
                          @click="handlePlayVideo"
                        >
                          <svg class="detail-video-play-icon" viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M7.2 6.4c0-.9 1-1.45 1.75-1l8.1 4.7c.8.45.8 1.55 0 2l-8.1 4.7c-.75.45-1.75-.1-1.75-1V6.4Z" />
                          </svg>
                        </button>
                      </div>
                    </template>
                    <template v-else>
                      <div class="detail-result-placeholder is-error">
                        {{ item.error_message || item.videos[0]?.error_message || "生成视频失败，请反馈给我们处理" }}
                      </div>
                    </template>
                  </div>
                </div>
              </div>

              <div class="detail-right">
                <div class="detail-section">
                  <div class="detail-meta">
                    <span v-if="item.id" class="detail-meta-business-id">
                      ID：{{ item.id }}
                      <button
                        type="button"
                        class="detail-meta-copy"
                        aria-label="复制 ID"
                        @click="copyBusinessId(item.id)"
                      >
                        <CopyOutlined />
                      </button>
                    </span>
                    <span v-for="meta in detailMetaList(item)" :key="meta">{{ meta }}</span>
                  </div>
                </div>

                <div v-if="!compact && item.api_attempts?.length" class="detail-section">
                  <div class="detail-label">接口调用记录</div>
                  <div class="detail-attempt-list">
                    <div
                      v-for="attempt in item.api_attempts"
                      :key="`${attempt.id || 'attempt'}-${attempt.attempt_index}`"
                      class="detail-attempt-card"
                    >
                      <div class="detail-attempt-header">
                        <span class="detail-attempt-title">第 {{ attempt.attempt_index }} 次尝试</span>
                        <a-space size="small">
                          <a-tag class="api-tag" :class="attempt.is_fallback ? 'api-tag-group' : 'api-tag-muted'">
                            {{ attemptRoleLabel(attempt) }}
                          </a-tag>
                          <a-tag class="api-tag" :class="attempt.status === 'success' ? 'api-tag-enabled' : 'api-tag-danger'">
                            {{ attemptStatusLabel(attempt.status) }}
                          </a-tag>
                        </a-space>
                      </div>
                      <div class="detail-attempt-meta">
                        <span>接口：{{ attempt.api_config_name || "-" }}</span>
                        <span>HTTP：{{ typeof attempt.http_status === "number" ? attempt.http_status : "-" }}</span>
                        <span>耗时：{{ formatDuration(attempt.duration_ms) }}</span>
                      </div>
                      <div v-if="attempt.error_message" class="detail-attempt-error">{{ attempt.error_message }}</div>
                    </div>
                  </div>
                </div>

                <div v-if="item.reference_images?.length" class="detail-section">
                  <div class="detail-label">
                    <PictureOutlined />
                    <span>参考图</span>
                  </div>
                  <div class="detail-thumb-row">
                    <div
                      v-for="(ref, index) in item.reference_images"
                      :key="`${ref}-${index}`"
                      class="detail-thumb"
                      @click="openPreview(ref)"
                    >
                      <div
                        v-if="!isMediaLoaded(getMediaKey('reference-image', `${index}-${ref}`))"
                        class="detail-media-loading"
                      >
                        <a-spin :indicator="h(LoadingOutlined, { style: { fontSize: '20px', color: '#7c8db5' } })" />
                      </div>
                      <img
                        :src="ref"
                        alt="参考图"
                        loading="lazy"
                        :class="{ 'detail-media-hidden': !isMediaLoaded(getMediaKey('reference-image', `${index}-${ref}`)) }"
                        @load="markMediaLoaded(getMediaKey('reference-image', `${index}-${ref}`))"
                        @error="markMediaLoaded(getMediaKey('reference-image', `${index}-${ref}`))"
                      />
                    </div>
                  </div>
                </div>

                <div class="detail-section">
                  <div class="detail-label">提示词</div>
                  <div class="detail-prompt-box">
                    <button
                      v-if="item.prompt?.trim()"
                      type="button"
                      class="detail-prompt-copy"
                      aria-label="复制提示词"
                      @click="copyPrompt(item.prompt)"
                    >
                      <CopyOutlined />
                    </button>
                    <div class="detail-prompt">{{ item.prompt || "-" }}</div>
                  </div>
                  <div v-if="item.error_message" class="detail-error-block">
                    <div class="detail-error-label">错误信息</div>
                    <div class="detail-error-message">{{ item.error_message }}</div>
                  </div>
                </div>
              </div>

              <div class="detail-floating-actions">
                <a-tooltip v-if="showReedit" title="回填参数">
                  <a-button type="text" class="ghost-icon-btn detail-action-btn" @click="handleReedit(item)">
                    <template #icon><ReloadOutlined /></template>
                  </a-button>
                </a-tooltip>
                <a-tooltip title="下载原视频">
                  <a-button
                    type="text"
                    class="ghost-icon-btn detail-action-btn"
                    :disabled="!item.videos[0]?.video_url"
                    @click="handleDownload(item)"
                  >
                    <template #icon><DownloadOutlined /></template>
                  </a-button>
                </a-tooltip>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </Teleport>

  <div v-if="previewVisible" style="display: none">
    <a-image
      :src="previewSrc"
      :preview="{ visible: previewVisible, onVisibleChange: (v: boolean) => (previewVisible = v) }"
    />
  </div>
</template>

<style scoped lang="scss">
.video-task-detail-overlay {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  background: var(--theme-panel-bg, #fffaf2);
}

.video-task-detail-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.video-task-detail-header {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--theme-panel-border);
  background: var(--theme-modal-header-bg, #fff8ec);
}

.video-task-detail-title {
  color: var(--theme-title);
  font-size: 16px;
  font-weight: 700;
  line-height: 1.4;
}

.video-task-detail-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition:
    color var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover {
    color: var(--theme-title);
    background: rgba(var(--theme-surface-strong-rgb), 0.72);
  }
}

.video-task-detail-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 20px 24px 24px 0;
  overflow: hidden;
}

.detail-loading {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding-left: 24px;
  color: var(--text-secondary);
}

@keyframes video-detail-slide-in {
  from {
    opacity: 0;
    transform: translate3d(22px, 0, 0) scale(0.985);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0) scale(1);
  }
}

.detail-section + .detail-section {
  margin-top: 18px;
}

.detail-attempt-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.detail-attempt-card {
  border: 1px solid var(--border-color);
  border-radius: 14px;
  padding: 12px 14px;
  background: var(--bg-elevated, rgba(255, 255, 255, 0.64));
}

.detail-attempt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.detail-attempt-title {
  font-weight: 600;
  color: var(--text-primary);
}

.detail-attempt-meta {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  color: var(--text-secondary);
  font-size: 13px;
}

.detail-attempt-error {
  margin-top: 8px;
  color: var(--danger-color, #d84f45);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.api-tag-danger {
  color: #b42318;
  background: rgba(217, 45, 32, 0.12);
}

.api-tag-enabled {
  color: #067647;
  background: rgba(18, 183, 106, 0.12);
}

.api-tag-group {
  color: #b54708;
  background: rgba(247, 144, 9, 0.12);
}

.api-tag-muted {
  color: var(--text-secondary);
  background: rgba(148, 163, 184, 0.14);
}

.detail-layout {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(280px, 0.55fr);
  gap: 0;
  align-items: stretch;
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
  animation: video-detail-slide-in var(--motion-duration-reveal-slower) var(--motion-ease-enter) both;
}

.detail-left,
.detail-right {
  min-width: 0;
  min-height: 0;
}

.detail-left {
  position: relative;
  display: flex;
  flex-direction: column;
  padding-left: 56px;
  padding-right: 56px;
}

.detail-nav-btn {
  position: absolute;
  top: 50%;
  z-index: 4;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  margin: 0;
  padding: 0;
  border: 1px solid var(--theme-panel-border);
  border-radius: 999px;
  background: rgba(var(--theme-surface-strong-rgb), 0.92);
  color: var(--theme-title);
  box-shadow: 0 10px 24px var(--theme-shadow-soft);
  cursor: pointer;
  transform: translateY(-50%);
  transition:
    color var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover {
    color: var(--theme-accent-text);
    border-color: var(--theme-border-strong);
    background: var(--theme-panel-bg);
    box-shadow: 0 14px 28px var(--theme-shadow-soft);
    transform: translateY(calc(-50% - 1px));
  }
}

.detail-nav-prev {
  left: 8px;
}

.detail-nav-next {
  right: 8px;
}

.detail-left > .detail-section {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  margin-top: 0;
}

.detail-right {
  display: flex;
  flex-direction: column;
  max-height: 100%;
  overflow-x: hidden;
  overflow-y: auto;
  padding-left: 20px;
  padding-right: 4px;
  padding-bottom: 44px;
  border-left: 1px solid var(--theme-panel-border);
  scrollbar-width: thin;
}

.detail-action-btn {
  width: 36px;
  height: 36px;
}

.detail-floating-actions {
  position: absolute;
  right: 0;
  bottom: 0;
  display: flex;
  gap: 6px;
  padding: 0 2px 2px 0;
}

.detail-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-secondary);
}

.detail-section > .detail-label {
  margin-bottom: 10px;
}

.detail-prompt-box {
  position: relative;
}

.detail-prompt-copy {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--theme-link);
  cursor: pointer;
}

.detail-prompt-copy:hover {
  background: var(--theme-control-hover-bg);
  color: var(--theme-accent-text-hover);
}

.detail-prompt {
  padding: 12px 40px 12px 14px;
  border-radius: 12px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
  color: var(--theme-title);
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 280px;
  overflow-y: auto;
  scrollbar-width: thin;
}

.detail-error-block {
  margin-top: 12px;
}

.detail-error-label {
  margin-bottom: 8px;
  color: #b85d47;
  font-size: 13px;
  font-weight: 700;
}

.detail-error-message {
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(207, 63, 54, 0.16);
  background: rgba(255, 242, 239, 0.92);
  color: #b85d47;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.detail-meta > span {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(var(--theme-surface-strong-rgb), 0.72);
  border: 1px solid var(--theme-panel-border);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.detail-meta-business-id {
  gap: 4px;
  word-break: break-all;
}

.detail-meta-copy {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--theme-link);
  cursor: pointer;
  flex: 0 0 auto;
}

.detail-meta-copy:hover {
  color: var(--theme-accent);
}

.detail-thumb-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.detail-thumb {
  position: relative;
  width: 84px;
  height: 84px;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
  cursor: pointer;
  transition:
    transform var(--motion-duration-base) var(--motion-ease-soft),
    box-shadow var(--motion-duration-base) var(--motion-ease-soft),
    border-color var(--motion-duration-base) var(--motion-ease-soft);

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  &:hover {
    transform: translateY(-2px);
    border-color: var(--theme-border-strong);
    box-shadow: 0 16px 24px var(--theme-shadow-soft);
  }
}

.detail-result-card {
  flex: 1;
  min-height: 0;
  height: 100%;
  border-radius: 0;
  overflow: hidden;
  border: 0;
  background: #000;
  position: relative;
}

.detail-media-loading {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--theme-page-base) 86%, transparent);
}

.detail-media-loading-dark {
  background: rgba(12, 12, 12, 0.78);
}

.detail-media-hidden {
  opacity: 0;
}

.detail-result-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  color: rgba(255, 255, 255, 0.82);
  text-align: center;
  background: linear-gradient(180deg, #1a1a1a, #0d0d0d);

  &.is-error {
    color: #ffb4a8;
    white-space: pre-wrap;
    word-break: break-word;
  }
}

.detail-video-shell {
  position: relative;
  width: 100%;
  height: 100%;
  background: #000;
}

.detail-video-player {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
  background: #000;
}

.detail-video-play-btn {
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
    background: rgba(36, 36, 36, 0.7);
  }

  &:active {
    transform: translate(-50%, -50%) scale(0.96);
  }
}

.detail-video-play-icon {
  width: 34px;
  height: 34px;
  margin: 0;
  fill: #fff;
}

@media (max-width: 960px) {
  .detail-layout {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(240px, 42vh) minmax(0, 1fr);
    height: 100%;
    overflow: hidden;
  }

  .detail-left {
    padding-left: 48px;
    padding-right: 48px;
    padding-bottom: 16px;
  }

  .detail-nav-prev {
    left: 4px;
  }

  .detail-nav-next {
    right: 4px;
  }

  .detail-right {
    max-height: none;
    overflow: auto;
    padding-left: 0;
    padding-right: 0;
    padding-top: 16px;
    border-left: 0;
    border-top: 1px solid var(--theme-panel-border);
  }

  .detail-floating-actions {
    position: static;
    justify-content: flex-end;
    margin-top: 16px;
  }

  .detail-left > .detail-section,
  .detail-result-card {
    flex: 1;
    min-height: 0;
    height: 100%;
  }

  .detail-result-card,
  .detail-result-placeholder,
  .detail-video-shell {
    min-height: 0;
    height: 100%;
    aspect-ratio: auto;
  }
}
</style>
