<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeftOutlined, CopyOutlined, MessageOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import dayjs from "dayjs";
import FeedbackTaskResultGrid from "@/components/feedback/FeedbackTaskResultGrid.vue";
import HistoryDetailDialog from "@/components/history/HistoryDetailDialog.vue";
import { getGenerationModels } from "@/api/config";
import { getMyFeedbackDetail } from "@/api/feedback";
import { getPreviewImageSrc } from "@/api/images";
import { getTask } from "@/api/tasks";
import { copyText as copyToClipboard } from "@/lib/clipboard";
import type { FeedbackDetail, FeedbackStatus, GenerationModelOption, TaskResult, UserHistoryCard } from "@/types";

const route = useRoute();
const router = useRouter();
const loading = ref(false);
const detail = ref<FeedbackDetail | null>(null);
const previewVisible = ref(false);
const previewSrc = ref("");
const generationModels = ref<GenerationModelOption[]>([]);
const taskDetailOpen = ref(false);
const taskDetailLoading = ref(false);
const taskDetailItem = ref<UserHistoryCard | null>(null);
let activeTaskDetailRequestKey = "";

const feedbackId = computed(() => String(route.params.feedbackId || ""));
const taskReferenceImages = computed(() => detail.value?.task.reference_images || []);
const taskReferenceThumbs = computed(() => detail.value?.task.reference_image_thumbs || []);
const detailModelOptions = computed(() => (
  generationModels.value.map((item) => ({
    label: item.model_label || item.display_name || item.model_key,
    value: item.model_key,
  }))
));

function statusLabel(status: FeedbackStatus) {
  return {
    pending: "待处理",
    processing: "处理中",
    completed: "已完成",
  }[status];
}

function statusColor(status: FeedbackStatus) {
  return {
    pending: "gold",
    processing: "blue",
    completed: "green",
  }[status];
}

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function formatShortId(value?: string | null) {
  const normalized = (value || "").trim();
  if (!normalized) return "-";
  if (normalized.length <= 14) return normalized;
  return `${normalized.slice(0, 8)}...${normalized.slice(-4)}`;
}

async function copyText(value?: string | null, label = "内容") {
  const normalized = (value || "").trim();
  if (!normalized) {
    message.warning(`暂无可复制的${label}`);
    return;
  }
  try {
    await copyToClipboard(normalized);
    message.success(`${label}已复制`);
  } catch {
    message.error("复制失败，请重试");
  }
}

function getModelLabel(model?: string) {
  if (!model) return "未设置";
  const matched = generationModels.value.find((item) => item.model_key === model);
  return matched?.model_label || matched?.display_name || model;
}

function getReferenceThumbSrc(url: string, index: number) {
  return taskReferenceThumbs.value[index] || url;
}

function getReferencePreviewSrc(url: string) {
  return getPreviewImageSrc(url);
}

function openPreview(url: string) {
  if (!url) return;
  previewSrc.value = url;
  previewVisible.value = true;
}

function convertTaskToHistoryCard(task: TaskResult): UserHistoryCard {
  const primaryImage = task.images.find((image) => image.status === "success") || task.images[0];
  return {
    item_type: "task",
    task_id: task.id,
    display_id: task.id,
    image_id: typeof primaryImage?.id === "number" && primaryImage.id > 0 ? primaryImage.id : null,
    is_pinned: false,
    image_url: primaryImage?.image_url || "",
    preview_url: primaryImage?.preview_url,
    thumb_url: primaryImage?.thumb_url,
    status: task.status,
    image_format: primaryImage?.image_format,
    image_size_bytes: primaryImage?.image_size_bytes,
    task_type: detail.value?.task.task_type || (task.reference_images?.length ? "image_edit" : "text_generate"),
    model: task.model,
    source: task.source,
    mode: task.mode,
    prompt: task.prompt,
    reference_images: task.reference_images || [],
    reference_image_thumbs: task.reference_image_thumbs || [],
    source_image: task.source_image || "",
    source_image_thumb: task.source_image_thumb || "",
    mask_image: task.mask_image || "",
    mask_image_thumb: task.mask_image_thumb || "",
    num_images: task.num_images,
    size: task.size || "",
    resolution: task.resolution || "",
    custom_size: task.custom_size || "",
    credit_cost: task.credit_cost || 0,
    credit_refunded: Boolean(task.credit_refunded),
    created_at: task.created_at,
    request_started_at: task.request_started_at,
    request_finished_at: task.request_finished_at,
    error_message: task.error_message || "",
    images: task.images || [],
  };
}

async function openTaskDetail() {
  const taskId = detail.value?.task_id;
  if (!taskId) {
    message.warning("当前反馈没有关联任务");
    return;
  }
  taskDetailOpen.value = true;
  taskDetailLoading.value = true;
  taskDetailItem.value = null;
  activeTaskDetailRequestKey = taskId;
  try {
    const task = await getTask(taskId);
    if (activeTaskDetailRequestKey !== taskId) return;
    taskDetailItem.value = convertTaskToHistoryCard(task);
  } catch {
    if (activeTaskDetailRequestKey !== taskId) return;
    taskDetailOpen.value = false;
    message.error("获取任务详情失败");
  } finally {
    if (activeTaskDetailRequestKey === taskId) {
      taskDetailLoading.value = false;
    }
  }
}

async function load() {
  if (!feedbackId.value) return;
  loading.value = true;
  try {
    detail.value = await getMyFeedbackDetail(feedbackId.value);
  } catch {
    message.error("获取反馈详情失败");
  } finally {
    loading.value = false;
  }
}

async function loadGenerationModels() {
  try {
    generationModels.value = await getGenerationModels();
  } catch {
    generationModels.value = [];
  }
}

watch(feedbackId, () => {
  void load();
});

onMounted(() => {
  void load();
  void loadGenerationModels();
});
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <MessageOutlined />
        </div>
        <div>
          <div class="warm-page-title">反馈详情</div>
          <div class="warm-page-desc">查看反馈原文、当前处理进度和最终结果。</div>
        </div>
      </div>
      <a-button class="back-btn" @click="router.push('/feedbacks')">
        <template #icon><ArrowLeftOutlined /></template>
        返回列表
      </a-button>
    </div>

    <a-spin :spinning="loading">
      <template v-if="detail">
        <div class="detail-grid">
          <div class="warm-card detail-main motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
            <div class="section-title-row">
              <h3>反馈信息</h3>
              <a-tag class="warm-tag" :color="statusColor(detail.status)">{{ statusLabel(detail.status) }}</a-tag>
            </div>
            <div class="meta-grid">
              <div>
                <span>反馈编号</span>
                <strong class="copyable-id">
                  <span :title="detail.feedback_id">{{ formatShortId(detail.feedback_id) }}</span>
                  <a-button type="text" size="small" class="copy-id-btn" @click="copyText(detail.feedback_id, '反馈编号')">
                    <template #icon><CopyOutlined /></template>
                  </a-button>
                </strong>
              </div>
              <div>
                <span>任务 ID</span>
                <strong class="copyable-id">
                  <span :title="detail.task_id">{{ formatShortId(detail.task_id) }}</span>
                  <a-button type="text" size="small" class="copy-id-btn" @click="copyText(detail.task_id, '任务 ID')">
                    <template #icon><CopyOutlined /></template>
                  </a-button>
                </strong>
              </div>
              <div><span>提交时间</span><strong>{{ formatTime(detail.created_at) }}</strong></div>
              <div><span>更新时间</span><strong>{{ formatTime(detail.updated_at) }}</strong></div>
              <div><span>处理人</span><strong>{{ detail.handler_name || "-" }}</strong></div>
              <div><span>处理时间</span><strong>{{ formatTime(detail.handled_at) }}</strong></div>
            </div>

            <div class="detail-block">
              <div class="detail-label">反馈内容</div>
              <div class="detail-text detail-text-emphasis">{{ detail.content || "-" }}</div>
            </div>

            <div class="note-grid">
              <div class="detail-block note-card">
                <div class="detail-label">处理进度</div>
                <div class="detail-text">{{ detail.process_note || "暂未更新处理进度" }}</div>
              </div>

              <div class="detail-block note-card">
                <div class="detail-label">处理结果</div>
                <div class="detail-text detail-text-result">{{ detail.result_note || "暂未填写处理结果" }}</div>
              </div>
            </div>
          </div>

          <div class="warm-card detail-side motion-fade-up motion-card-lift" style="--motion-delay: 180ms">
            <div class="section-title-row">
              <h3>关联任务</h3>
              <a-button
                v-if="detail.task_id"
                type="primary"
                size="small"
                class="warm-primary-btn"
                :loading="taskDetailLoading"
                @click="openTaskDetail"
              >
                查看任务详情
              </a-button>
            </div>
            <div class="task-meta-list">
              <div><span>模型</span><strong>{{ getModelLabel(detail.task.model) }}</strong></div>
              <div><span>类型</span><strong>{{ detail.task.mode || "-" }}</strong></div>
              <div><span>来源</span><strong>{{ detail.task.source || "-" }}</strong></div>
              <div><span>任务状态</span><strong>{{ detail.task.status || "-" }}</strong></div>
              <div><span>任务时间</span><strong>{{ formatTime(detail.task.created_at) }}</strong></div>
            </div>
            <div class="detail-block" style="margin-top: 18px">
              <div class="detail-label">任务提示词</div>
              <div class="detail-text">{{ detail.task.prompt || "-" }}</div>
            </div>

            <div v-if="taskReferenceImages.length" class="detail-block task-result-block">
              <div class="detail-label detail-label-inline">
                <span>任务参考图</span>
                <small>点击缩略图可放大</small>
              </div>
              <div class="task-result-grid task-reference-grid">
                <button
                  v-for="(url, index) in taskReferenceImages"
                  :key="url + index"
                  type="button"
                  class="task-result-thumb task-reference-thumb clickable"
                  @click="openPreview(getReferencePreviewSrc(url))"
                >
                  <img :src="getReferenceThumbSrc(url, index)" :alt="`任务参考图 ${index + 1}`" loading="lazy" />
                </button>
              </div>
            </div>

            <FeedbackTaskResultGrid v-if="detail" :task="detail.task" @preview="openPreview" />
          </div>
        </div>
      </template>
    </a-spin>

    <div v-if="previewVisible" style="display: none">
      <a-image
        :src="previewSrc"
        :preview="{ visible: previewVisible, onVisibleChange: (v: boolean) => (previewVisible = v) }"
      />
    </div>

    <HistoryDetailDialog
      v-model:open="taskDetailOpen"
      :item="taskDetailItem"
      :loading="taskDetailLoading"
      :model-options="detailModelOptions"
    />
  </div>
</template>

<style scoped lang="scss">
.back-btn {
  border-radius: 12px;
  border-color: var(--theme-panel-border-strong);
  background: var(--theme-panel-bg-strong);
  color: var(--theme-accent-text);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.detail-main,
.detail-side {
  padding: 20px;
}

.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;

  h3 {
    margin: 0;
    color: var(--theme-title);
    font-size: 18px;
  }
}

.meta-grid,
.task-meta-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;

  > div {
    padding: 12px 14px;
    border-radius: 14px;
    background: var(--theme-panel-bg-soft);
    border: 1px solid var(--theme-panel-border);
  }

  span {
    display: block;
    margin-bottom: 6px;
    color: var(--text-secondary);
    font-size: 12px;
  }

  strong {
    color: var(--theme-title);
    word-break: break-word;
  }
}

.copyable-id {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;

  > span {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.copy-id-btn {
  flex: 0 0 auto;
  width: 24px;
  height: 24px;
  color: var(--theme-accent-text);
}

.detail-block {
  margin-top: 18px;
}

.note-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 18px;
}

.note-card {
  margin-top: 0;
}

.detail-label {
  margin-bottom: 8px;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 700;
}

.detail-label-inline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;

  small {
    color: var(--theme-text-secondary);
    font-size: 12px;
    font-weight: 500;
  }
}

.detail-text {
  padding: 14px 16px;
  border-radius: 16px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
  color: var(--theme-title);
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-text-emphasis {
  background: linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-panel-bg-strong));
}

.detail-text-result {
  background: linear-gradient(180deg, rgba(255, 245, 222, 0.88), rgba(255, 239, 199, 0.94));
  border-color: rgba(219, 176, 81, 0.22);
}

.warm-tag {
  border-radius: 999px;
  font-weight: 600;
}

.task-result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.task-reference-grid {
  grid-template-columns: repeat(auto-fill, minmax(72px, 72px));
  gap: 8px;
}

.task-result-thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 96px;
  padding: 0;
  border: 1px solid var(--theme-panel-border);
  border-radius: 14px;
  background: var(--theme-panel-bg-soft);
  overflow: hidden;
  transition:
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft);

  &.clickable {
    cursor: zoom-in;
  }

  &.clickable:hover {
    transform: translateY(-2px);
    border-color: var(--theme-panel-border-strong);
  }

  img {
    width: 100%;
    aspect-ratio: 1 / 1;
    object-fit: cover;
    border-radius: 0;
    background: var(--theme-empty-bg);
  }
}

.task-reference-thumb {
  min-height: 72px;

  img {
    aspect-ratio: 1 / 1;
  }
}

@media (max-width: 900px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }

  .meta-grid,
  .task-meta-list,
  .note-grid {
    grid-template-columns: 1fr;
  }

}
</style>
