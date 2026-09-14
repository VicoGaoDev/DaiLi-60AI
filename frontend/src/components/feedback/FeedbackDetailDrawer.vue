<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import {
  CloseCircleOutlined,
  CloseOutlined,
  EyeOutlined,
  InboxOutlined,
  PaperClipOutlined,
  SendOutlined,
} from "@ant-design/icons-vue";
import { message, Modal } from "ant-design-vue";
import dayjs from "dayjs";
import {
  getMyFeedbackDetail,
  listMyFeedbackMessages,
  markMyFeedbackAsRead,
  sendMyFeedbackMessage,
} from "@/api/feedback";
import {
  closeAdminFeedback,
  getAdminFeedbackDetail,
  getAdminHistoryDetail,
  listAdminFeedbackMessages,
  markAdminFeedbackAsRead,
  sendAdminFeedbackMessage,
} from "@/api/admin";
import { getGenerationModels } from "@/api/config";
import { getPreviewImageSrc } from "@/api/images";
import { getTask } from "@/api/tasks";
import {
  isImageUploadTooLarge,
  MAX_IMAGE_UPLOAD_SIZE_TEXT,
  uploadReferenceImage,
} from "@/api/upload";
import HistoryDetailDialog from "@/components/history/HistoryDetailDialog.vue";
import type {
  FeedbackDetail,
  FeedbackMessage,
  FeedbackStatus,
  FeedbackType,
  GenerationModelOption,
  TaskResult,
  UserHistoryCard,
} from "@/types";

const props = defineProps<{
  open: boolean;
  feedbackId: string | null;
  mode: "user" | "admin";
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  changed: [];
}>();

const loading = ref(false);
const detail = ref<FeedbackDetail | null>(null);
const messages = ref<FeedbackMessage[]>([]);
const content = ref("");
const attachment = ref<string | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);
const messageListRef = ref<HTMLElement | null>(null);
const sending = ref(false);
const uploading = ref(false);
const closing = ref(false);
const dragActive = ref(false);
const previewVisible = ref(false);
const previewSrc = ref("");
const generationModels = ref<GenerationModelOption[]>([]);
const taskDetailOpen = ref(false);
const taskDetailLoading = ref(false);
const taskDetailItem = ref<UserHistoryCard | null>(null);
const pendingOpenTaskDetail = ref(false);
const reopenDrawerAfterTaskDetail = ref(false);
let activeTaskDetailRequestKey = "";

const isClosed = computed(() => detail.value?.status === "completed");
const canClose = computed(() => props.mode === "admin" && !!detail.value && !isClosed.value);
const canSend = computed(() => !isClosed.value && !sending.value && !uploading.value);
const hasLinkedTask = computed(() => Boolean(detail.value?.task_id));
const detailModelOptions = computed(() => (
  generationModels.value.map((item) => ({
    label: item.model_label || item.display_name || item.model_key,
    value: item.model_key,
  }))
));

function statusLabel(status?: FeedbackStatus) {
  return {
    pending: "待处理",
    processing: "处理中",
    completed: "已关闭",
  }[status || "pending"];
}

function statusColor(status?: FeedbackStatus) {
  return {
    pending: "gold",
    processing: "blue",
    completed: "green",
  }[status || "pending"];
}

function feedbackTypeLabel(feedbackType?: FeedbackType) {
  return {
    general: "通用反馈",
    image_task: "图片任务反馈",
    video_task: "视频任务反馈",
    canvas: "Canvas反馈",
    purchase: "购买积分反馈",
    feature_request: "加新功能",
    bug_report: "我要提BUG",
    optimization: "优化建议",
  }[feedbackType || "general"];
}

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "-";
}

function formatMessageTime(value?: string | null) {
  if (!value) return "";
  const time = dayjs(value);
  if (!time.isValid()) return "";
  return time.isSame(dayjs(), "day") ? time.format("HH:mm") : time.format("YYYY-MM-DD HH:mm");
}

function messageRoleLabel(item: FeedbackMessage) {
  if (item.sender_role === "admin") return "客服";
  if (item.sender_role === "system") return "系统";
  return "我";
}

function isOwnMessage(item: FeedbackMessage) {
  if (props.mode === "admin") return item.sender_role === "admin";
  return item.sender_role === "user";
}

function closeDrawer() {
  emit("update:open", false);
}

function handleDrawerAfterOpenChange(nextOpen: boolean) {
  if (!nextOpen && pendingOpenTaskDetail.value) {
    pendingOpenTaskDetail.value = false;
    taskDetailOpen.value = true;
  }
}

function openPreview(url: string) {
  const previewUrl = getPreviewImageSrc(url);
  if (!previewUrl) return;
  previewSrc.value = previewUrl;
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

async function ensureGenerationModels() {
  if (generationModels.value.length) return;
  try {
    generationModels.value = await getGenerationModels();
  } catch {
    generationModels.value = [];
  }
}

async function openTaskDetail() {
  const taskId = detail.value?.task_id;
  if (!taskId) {
    message.warning("当前反馈没有关联任务");
    return;
  }

  taskDetailLoading.value = true;
  taskDetailItem.value = null;
  pendingOpenTaskDetail.value = false;
  reopenDrawerAfterTaskDetail.value = false;
  activeTaskDetailRequestKey = taskId;
  await ensureGenerationModels();

  try {
    if (props.mode === "admin") {
      const taskDetail = await getAdminHistoryDetail({
        item_type: "task",
        task_id: taskId,
      });
      if (activeTaskDetailRequestKey !== taskId) return;
      taskDetailItem.value = taskDetail;
    } else {
      const task = await getTask(taskId);
      if (activeTaskDetailRequestKey !== taskId) return;
      taskDetailItem.value = convertTaskToHistoryCard(task);
    }
    if (activeTaskDetailRequestKey !== taskId) return;
    pendingOpenTaskDetail.value = true;
    reopenDrawerAfterTaskDetail.value = true;
    emit("update:open", false);
  } catch {
    if (activeTaskDetailRequestKey !== taskId) return;
    pendingOpenTaskDetail.value = false;
    message.error("获取任务详情失败");
  } finally {
    if (activeTaskDetailRequestKey === taskId) {
      taskDetailLoading.value = false;
    }
  }
}

async function scrollToBottom() {
  await nextTick();
  const el = messageListRef.value;
  if (el) el.scrollTop = el.scrollHeight;
}

async function markRead() {
  if (!props.feedbackId) return;
  if (props.mode === "admin") {
    await markAdminFeedbackAsRead(props.feedbackId);
  } else {
    const updated = await markMyFeedbackAsRead(props.feedbackId);
    detail.value = updated;
  }
}

async function load() {
  if (!props.open || !props.feedbackId) return;
  loading.value = true;
  try {
    const [detailRes, messageRes] = await Promise.all([
      props.mode === "admin" ? getAdminFeedbackDetail(props.feedbackId) : getMyFeedbackDetail(props.feedbackId),
      props.mode === "admin" ? listAdminFeedbackMessages(props.feedbackId) : listMyFeedbackMessages(props.feedbackId),
    ]);
    detail.value = detailRes;
    messages.value = messageRes.items;
    // Only notify parents when user unread state actually flips; opening alone
    // must not force list reloads (e.g. admin /feedback page=1).
    const shouldNotifyReadChange = props.mode === "user" && !detailRes.is_read;
    await markRead();
    if (shouldNotifyReadChange) {
      emit("changed");
    }
    await scrollToBottom();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取反馈详情失败");
  } finally {
    loading.value = false;
  }
}

function resetComposer() {
  content.value = "";
  attachment.value = null;
  dragActive.value = false;
  if (fileInputRef.value) fileInputRef.value.value = "";
}

function warnAttachmentLimit() {
  message.warning("每条消息最多上传 1 张图片，请先删除后再重新上传");
}

function openFilePicker() {
  if (!canSend.value) return;
  if (attachment.value) {
    warnAttachmentLimit();
    return;
  }
  fileInputRef.value?.click();
}

async function uploadFile(file: File) {
  if (!file.type.startsWith("image/")) {
    message.warning("仅支持上传图片");
    return;
  }
  if (attachment.value) {
    warnAttachmentLimit();
    return;
  }
  if (isImageUploadTooLarge(file)) {
    message.warning(`图片不能超过 ${MAX_IMAGE_UPLOAD_SIZE_TEXT}`);
    return;
  }

  uploading.value = true;
  try {
    const res = await uploadReferenceImage(file, "user_suggestion");
    attachment.value = res.url;
    message.success("图片已上传");
  } catch {
    message.error("图片上传失败，请重试");
  } finally {
    uploading.value = false;
  }
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement | null;
  const file = input?.files?.[0];
  if (file) await uploadFile(file);
  if (input) input.value = "";
}

async function handlePaste(event: ClipboardEvent) {
  const file = Array.from(event.clipboardData?.files || []).find((item) => item.type.startsWith("image/"));
  if (!file) return;
  event.preventDefault();
  await uploadFile(file);
}

async function handleDrop(event: DragEvent) {
  event.preventDefault();
  dragActive.value = false;
  const file = Array.from(event.dataTransfer?.files || []).find((item) => item.type.startsWith("image/"));
  if (file) await uploadFile(file);
}

async function handleSend() {
  const normalized = content.value.trim();
  const attachments = attachment.value ? [attachment.value] : [];
  if (!normalized && !attachments.length) {
    message.warning("请输入回复内容或上传图片");
    return;
  }
  if (!props.feedbackId) return;

  sending.value = true;
  try {
    const payload = { content: normalized, attachments };
    const created = props.mode === "admin"
      ? await sendAdminFeedbackMessage(props.feedbackId, payload)
      : await sendMyFeedbackMessage(props.feedbackId, payload);
    messages.value.push(created);
    resetComposer();
    const latest = props.mode === "admin"
      ? await getAdminFeedbackDetail(props.feedbackId)
      : await getMyFeedbackDetail(props.feedbackId);
    detail.value = latest;
    emit("changed");
    await scrollToBottom();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "发送失败");
  } finally {
    sending.value = false;
  }
}

function handleCloseFeedback() {
  if (!props.feedbackId) return;
  Modal.confirm({
    title: "关闭反馈",
    content: "关闭后双方都不能继续发送消息，确认关闭吗？",
    okText: "关闭反馈",
    cancelText: "取消",
    okButtonProps: { danger: true },
    async onOk() {
      closing.value = true;
      try {
        detail.value = await closeAdminFeedback(props.feedbackId as string);
        emit("changed");
        message.success("反馈已关闭");
      } catch (err: any) {
        message.error(err.response?.data?.detail || "关闭反馈失败");
      } finally {
        closing.value = false;
      }
    },
  });
}

watch(taskDetailOpen, (nextOpen, prevOpen) => {
  if (!nextOpen && prevOpen && reopenDrawerAfterTaskDetail.value) {
    reopenDrawerAfterTaskDetail.value = false;
    emit("update:open", true);
  }
});

watch(
  () => [props.open, props.feedbackId, props.mode] as const,
  () => {
    if (props.open) {
      void load();
    } else {
      if (!pendingOpenTaskDetail.value && !taskDetailOpen.value) {
        detail.value = null;
        messages.value = [];
        resetComposer();
        taskDetailLoading.value = false;
        taskDetailItem.value = null;
        activeTaskDetailRequestKey = "";
      }
    }
  },
  { immediate: true },
);
</script>

<template>
  <a-drawer
    :open="open"
    :width="720"
    root-class-name="feedback-detail-drawer"
    class="feedback-detail-drawer"
    :body-style="{ padding: 0 }"
    @after-open-change="handleDrawerAfterOpenChange"
    @update:open="(value: boolean) => emit('update:open', value)"
    @close="closeDrawer"
  >
    <template #title>
      <div class="drawer-title">
        <span>反馈详情</span>
        <a-tag v-if="detail" class="warm-tag" :color="statusColor(detail.status)">{{ statusLabel(detail.status) }}</a-tag>
      </div>
    </template>
    <template #extra>
      <div class="drawer-extra-actions">
        <a-button
          v-if="hasLinkedTask"
          type="primary"
          class="warm-primary-btn drawer-action-btn"
          :loading="taskDetailLoading"
          @click="openTaskDetail"
        >
          <template #icon><EyeOutlined /></template>
          查看任务详情
        </a-button>
        <a-button
          v-if="canClose"
          danger
          class="warm-danger-btn drawer-close-btn"
          :style="hasLinkedTask ? { marginLeft: '16px' } : undefined"
          :loading="closing"
          @click="handleCloseFeedback"
        >
          关闭反馈
        </a-button>
      </div>
    </template>

    <a-spin :spinning="loading">
      <div v-if="detail" class="drawer-shell">
        <div ref="messageListRef" class="drawer-content-scroll">
          <section class="ticket-summary">
            <div class="ticket-summary-top">
              <a-tag class="warm-tag" color="geekblue">{{ feedbackTypeLabel(detail.feedback_type) }}</a-tag>
              <div class="ticket-meta">
                <span v-if="mode === 'admin'">用户：{{ detail.username || "-" }}</span>
                <span>创建：{{ formatTime(detail.created_at) }}</span>
                <span>更新：{{ formatTime(detail.last_message_at || detail.updated_at) }}</span>
              </div>
            </div>
            <div class="ticket-content">{{ detail.content }}</div>
            <div v-if="detail.attachments?.length" class="initial-attachments">
              <button
                v-for="url in detail.attachments"
                :key="url"
                type="button"
                class="attachment-thumb"
                title="点击预览"
                @click="openPreview(url)"
              >
                <img :src="getPreviewImageSrc(url)" alt="反馈附件" loading="lazy" />
              </button>
            </div>
          </section>

          <section class="message-list">
            <div
              v-for="item in messages"
              :key="item.message_id"
              class="message-row"
              :class="{ own: isOwnMessage(item), system: item.sender_role === 'system' }"
            >
              <div class="message-stack">
                <div class="message-meta">
                  <span>{{ messageRoleLabel(item) }}</span>
                  <span>{{ formatMessageTime(item.created_at) }}</span>
                </div>
                <div class="message-bubble">
                  <div v-if="item.content" class="message-content">{{ item.content }}</div>
                  <div v-if="item.attachments.length" class="message-attachments">
                    <button
                      v-for="url in item.attachments"
                      :key="url"
                      type="button"
                      class="message-image"
                      title="点击预览"
                      @click="openPreview(url)"
                    >
                      <img :src="getPreviewImageSrc(url)" :alt="item.content || '消息图片'" loading="lazy" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>

        <section class="composer" :class="{ disabled: isClosed }" @paste="handlePaste">
          <div v-if="isClosed" class="closed-tip">
            <CloseCircleOutlined />
            该反馈已关闭，不能继续发送消息
          </div>
          <template v-else>
            <div
              class="drop-zone"
              :class="{ active: dragActive }"
              @dragenter.prevent="dragActive = true"
              @dragover.prevent="dragActive = true"
              @dragleave.prevent="dragActive = false"
              @drop="handleDrop"
            >
              <div v-if="attachment" class="composer-attachment">
                <img :src="getPreviewImageSrc(attachment)" alt="待发送图片" />
                <button
                  type="button"
                  class="composer-attachment-remove"
                  title="删除图片"
                  @click="attachment = null"
                >
                  <CloseOutlined />
                </button>
              </div>
              <div v-else class="drop-hint">
                <InboxOutlined />
                <span>可拖拽或粘贴图片，最多 1 张</span>
              </div>
              <a-textarea
                v-model:value="content"
                :maxlength="1500"
                :rows="4"
                show-count
                placeholder="输入回复内容..."
                class="warm-textarea composer-input"
                @keydown.ctrl.enter.prevent="handleSend"
                @keydown.meta.enter.prevent="handleSend"
              />
            </div>
            <div class="composer-actions">
              <div class="composer-upload-tip">
                {{ attachment ? "已上传 1 张，删除后可更换" : "支持拖拽/粘贴/选择，最多 1 张" }}
              </div>
              <input
                ref="fileInputRef"
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                style="display: none"
                @change="handleFileChange"
              />
              <a-button
                class="warm-secondary-btn drawer-action-btn"
                :disabled="!canSend || !!attachment"
                :loading="uploading"
                @click="openFilePicker"
              >
                <template #icon><PaperClipOutlined /></template>
                上传图片
              </a-button>
              <a-button
                type="primary"
                class="warm-primary-btn drawer-action-btn"
                :loading="sending"
                :disabled="!canSend"
                @click="handleSend"
              >
                <template #icon><SendOutlined /></template>
                发送
              </a-button>
            </div>
          </template>
        </section>
      </div>
    </a-spin>

    <div style="display: none">
      <a-image
        :src="previewSrc"
        :preview="{
          visible: previewVisible,
          onVisibleChange: (value: boolean) => (previewVisible = value),
        }"
      />
    </div>
  </a-drawer>

  <HistoryDetailDialog
    v-model:open="taskDetailOpen"
    :item="taskDetailItem"
    :loading="taskDetailLoading"
    :model-options="detailModelOptions"
    :show-error-message="mode === 'admin'"
    :show-attempt-response-preview="mode === 'admin'"
  />
</template>

<style lang="scss">
/* Drawer is teleported; keep theme overrides outside scoped CSS. */
.feedback-detail-drawer.ant-drawer .ant-drawer-content,
.feedback-detail-drawer .ant-drawer-content,
.feedback-detail-drawer .ant-drawer-content-wrapper {
  border-radius: 0 !important;
  height: 100%;
}

.feedback-detail-drawer .ant-drawer-content {
  display: flex;
  flex-direction: column;
  overflow: hidden !important;
}

.feedback-detail-drawer .ant-drawer-header {
  flex-shrink: 0;
  background: var(--theme-modal-header-bg) !important;
  border-bottom: 1px solid var(--theme-border) !important;
}

.feedback-detail-drawer .ant-drawer-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden !important;
  padding: 0 !important;
}

.feedback-detail-drawer .ant-spin-nested-loading,
.feedback-detail-drawer .ant-spin-container {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.feedback-detail-drawer .ant-drawer-title {
  color: var(--theme-title) !important;
  font-weight: 700;
}

.feedback-detail-drawer .ant-drawer-close {
  color: var(--theme-accent-text) !important;
  border-radius: 10px;
}

.feedback-detail-drawer .ant-drawer-close:hover {
  color: var(--theme-accent-text-hover) !important;
  background: var(--theme-control-hover-bg) !important;
}

.feedback-detail-drawer .ant-drawer-extra .drawer-extra-actions,
.feedback-detail-drawer .drawer-extra-actions {
  display: inline-flex !important;
  align-items: center !important;
  flex-wrap: nowrap !important;
  gap: 16px !important;
}

.feedback-detail-drawer .drawer-extra-actions .drawer-close-btn.ant-btn {
  margin-left: 16px !important;
}

.feedback-detail-drawer .drawer-close-btn.ant-btn,
.feedback-detail-drawer .drawer-action-btn.ant-btn {
  height: 36px !important;
  padding-inline: 14px !important;
  border-radius: 12px !important;
  font-size: 14px !important;
  font-weight: 700 !important;
}

.feedback-detail-drawer .warm-primary-btn.ant-btn-primary {
  border: none !important;
  background: var(--theme-accent) !important;
  color: var(--theme-accent-contrast) !important;
  box-shadow: 0 10px 18px var(--theme-shadow-strong) !important;
}

.feedback-detail-drawer .warm-primary-btn.ant-btn-primary:hover,
.feedback-detail-drawer .warm-primary-btn.ant-btn-primary:focus {
  background: var(--theme-accent) !important;
  color: var(--theme-accent-contrast) !important;
  filter: brightness(1.02);
}

.feedback-detail-drawer .warm-secondary-btn.ant-btn {
  border: 1px solid var(--theme-panel-border-strong) !important;
  background: var(--theme-panel-bg-strong) !important;
  color: var(--theme-accent-text) !important;
  box-shadow: none !important;
}

.feedback-detail-drawer .warm-secondary-btn.ant-btn:hover,
.feedback-detail-drawer .warm-secondary-btn.ant-btn:focus {
  border-color: var(--theme-border-strong) !important;
  background: var(--theme-control-hover-bg) !important;
  color: var(--theme-accent-text-hover) !important;
}

.feedback-detail-drawer .warm-danger-btn.ant-btn {
  border: 1px solid #f4c7bf !important;
  background: linear-gradient(180deg, #fff4f1, #ffe8e2) !important;
  color: #c85043 !important;
  box-shadow: 0 8px 16px rgba(216, 92, 74, 0.12) !important;
}

.feedback-detail-drawer .warm-danger-btn.ant-btn:hover,
.feedback-detail-drawer .warm-danger-btn.ant-btn:focus {
  border-color: #eea89d !important;
  background: linear-gradient(180deg, #ffece7, #ffdcd4) !important;
  color: #b84034 !important;
}

.feedback-detail-drawer .warm-textarea.ant-input {
  border-radius: 14px !important;
  border-color: var(--theme-control-border-strong) !important;
  background: var(--theme-control-bg) !important;
  color: var(--theme-title) !important;
  box-shadow: none !important;
}

.feedback-detail-drawer .warm-textarea.ant-input:hover {
  border-color: var(--theme-border-strong) !important;
}

.feedback-detail-drawer .warm-textarea.ant-input:focus {
  border-color: var(--theme-accent) !important;
  box-shadow: 0 0 0 2px var(--theme-focus-ring) !important;
}

.feedback-detail-drawer .warm-tag {
  border-radius: 999px !important;
  font-weight: 600;
}
</style>

<style scoped lang="scss">
.drawer-title {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--theme-title);
  font-weight: 700;
}

.drawer-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--theme-page-bg);
}

.drawer-content-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.ticket-summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg);
}

.ticket-summary-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.ticket-content {
  color: var(--theme-title);
  font-size: 15px;
  font-weight: 600;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.ticket-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 14px;
  color: var(--theme-text-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.initial-attachments,
.message-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.attachment-thumb,
.message-image {
  appearance: none;
  display: inline-flex;
  width: 72px;
  height: 72px;
  padding: 0;
  margin: 0;
  border: 1px solid var(--theme-panel-border);
  border-radius: 10px;
  overflow: hidden;
  cursor: zoom-in;
  background: var(--theme-control-bg);
  line-height: 0;

  img {
    width: 72px;
    height: 72px;
    object-fit: cover;
  }

  &:hover {
    border-color: var(--theme-border-strong);
  }

  &:focus-visible {
    outline: 2px solid var(--theme-accent);
    outline-offset: 2px;
  }
}

.message-list {
  padding: 20px;
}

.message-row {
  display: flex;
  margin-bottom: 16px;

  &.own {
    justify-content: flex-end;

    .message-stack {
      align-items: flex-end;
    }

    .message-meta {
      justify-content: flex-end;
    }

    .message-bubble {
      border-radius: 16px 16px 4px 16px;
      background: linear-gradient(135deg, var(--theme-brand-bg-start), var(--theme-brand-bg-end));
      color: var(--theme-accent-contrast);
    }
  }

  &.system {
    justify-content: center;

    .message-stack {
      align-items: center;
    }

    .message-meta {
      justify-content: center;
    }

    .message-bubble {
      border-radius: 16px;
      background: var(--theme-panel-bg-strong);
      color: var(--theme-text-secondary);
      text-align: center;
    }
  }

  &:not(.own):not(.system) {
    .message-bubble {
      border-radius: 16px 16px 16px 4px;
    }
  }
}

.message-stack {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  max-width: min(520px, 82%);
}

.message-bubble {
  width: fit-content;
  max-width: 100%;
  padding: 10px 12px;
  border-radius: 16px;
  background: var(--theme-panel-bg-strong);
  color: var(--theme-title);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--theme-text-secondary);
  font-size: 12px;
  line-height: 1.2;
}

.message-content {
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.composer {
  flex-shrink: 0;
  position: sticky;
  bottom: 0;
  z-index: 3;
  padding: 14px 20px 18px;
  border-top: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg);
}

.closed-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px;
  color: var(--theme-text-secondary);
}

.drop-zone {
  border: 1px dashed var(--theme-panel-border-strong);
  border-radius: 16px;
  padding: 12px;
  background: var(--theme-control-bg);
  transition:
    border-color var(--motion-duration-base) var(--motion-ease-soft),
    background var(--motion-duration-base) var(--motion-ease-soft);

  &.active {
    border-color: var(--theme-accent);
    background: var(--theme-panel-bg-strong);
    box-shadow: 0 0 0 2px var(--theme-focus-ring);
  }
}

.drop-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  color: var(--theme-text-secondary);
  font-size: 12px;
}

.composer-input {
  border-radius: 14px !important;
}

.composer-attachment {
  position: relative;
  display: inline-flex;
  width: 72px;
  height: 72px;
  margin-bottom: 10px;
  overflow: hidden;
  border-radius: 10px;
  border: 1px solid var(--theme-panel-border);

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  &:hover .composer-attachment-remove {
    opacity: 1;
  }
}

.composer-attachment-remove {
  position: absolute;
  top: 4px;
  right: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: rgb(0 0 0 / 58%);
  color: #fff;
  font-size: 10px;
  cursor: pointer;
  opacity: 0;
  transition: opacity var(--motion-duration-fast, 160ms) var(--motion-ease-soft, ease);
}

.composer-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.composer-upload-tip {
  margin-right: auto;
  color: var(--theme-text-secondary);
  font-size: 12px;
  line-height: 1.4;
}

@media (max-width: 768px) {
  .ticket-summary-top {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
