<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import { createFeedback } from "@/api/feedback";
import {
  isImageUploadTooLarge,
  MAX_IMAGE_UPLOAD_SIZE_TEXT,
  uploadReferenceImage,
} from "@/api/upload";
import type { FeedbackDetail, FeedbackType } from "@/types";

const props = defineProps<{
  open: boolean;
}>();
const router = useRouter();

const emit = defineEmits<{
  "update:open": [value: boolean];
  submitted: [detail: FeedbackDetail];
}>();

const MAX_ATTACHMENTS = 5;

const feedbackType = ref<FeedbackType>("feature_request");
const content = ref("");
const attachments = ref<string[]>([]);
const uploadInputRef = ref<HTMLInputElement | null>(null);
const submitting = ref(false);
const uploading = ref(false);
const previewVisible = ref(false);
const previewSrc = ref("");

const attachmentSlotsLeft = computed(() => Math.max(0, MAX_ATTACHMENTS - attachments.value.length));

function closeDialog() {
  emit("update:open", false);
}

function goMyFeedbacks() {
  closeDialog();
  router.push("/feedbacks");
}

function resetForm() {
  feedbackType.value = "feature_request";
  content.value = "";
  attachments.value = [];
  submitting.value = false;
  uploading.value = false;
  previewVisible.value = false;
  previewSrc.value = "";
  if (uploadInputRef.value) {
    uploadInputRef.value.value = "";
  }
}

watch(
  () => props.open,
  (value) => {
    if (!value) {
      resetForm();
    }
  },
);

function openFilePicker() {
  if (uploading.value) return;
  if (attachmentSlotsLeft.value <= 0) {
    message.warning(`最多上传 ${MAX_ATTACHMENTS} 张图片`);
    return;
  }
  uploadInputRef.value?.click();
}

function removeAttachment(index: number) {
  attachments.value.splice(index, 1);
}

function openPreview(url: string) {
  previewSrc.value = url;
  previewVisible.value = true;
}

async function handleUploadChange(event: Event) {
  const input = event.target as HTMLInputElement | null;
  const fileList = Array.from(input?.files || []);
  if (!fileList.length) return;

  const availableSlots = attachmentSlotsLeft.value;
  const files = fileList.slice(0, availableSlots);
  if (fileList.length > availableSlots) {
    message.warning(`最多上传 ${MAX_ATTACHMENTS} 张图片，已截取前 ${availableSlots} 张`);
  }

  let uploadedCount = 0;
  let oversizedCount = 0;
  let failedCount = 0;
  uploading.value = true;
  try {
    for (const file of files) {
      if (isImageUploadTooLarge(file)) {
        oversizedCount += 1;
        continue;
      }
      try {
        const res = await uploadReferenceImage(file, "user_suggestion");
        attachments.value.push(res.url);
        uploadedCount += 1;
      } catch {
        failedCount += 1;
      }
    }
  } finally {
    uploading.value = false;
    if (input) input.value = "";
  }

  if (uploadedCount > 0) {
    message.success(`已上传 ${uploadedCount} 张图片`);
  }
  if (oversizedCount > 0) {
    message.warning(`${oversizedCount} 张图片超过 ${MAX_IMAGE_UPLOAD_SIZE_TEXT}，已跳过`);
  }
  if (failedCount > 0) {
    message.warning(`${failedCount} 张图片上传失败，请稍后重试`);
  }
}

async function handleSubmit() {
  const normalized = content.value.trim();
  if (!normalized) {
    message.warning("请输入建议内容");
    return;
  }

  if (attachments.value.length > MAX_ATTACHMENTS) {
    message.warning(`最多上传 ${MAX_ATTACHMENTS} 张图片`);
    return;
  }

  submitting.value = true;
  try {
    const detail = await createFeedback(null, normalized, {
      feedback_type: feedbackType.value,
      attachments: attachments.value,
    });
    message.success("建议已提交");
    emit("submitted", detail);
    closeDialog();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "提交建议失败");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <a-modal
    :open="open"
    ok-text="提交"
    cancel-text="取消"
    :confirm-loading="submitting"
    :ok-button-props="{ disabled: uploading }"
    :width="640"
    centered
    @update:open="(value: boolean) => emit('update:open', value)"
    @ok="handleSubmit"
    @cancel="closeDialog"
  >
    <template #title>
      <div class="suggestion-title-row">
        <span>提交建议</span>
        <button type="button" class="suggestion-title-link" @click.stop="goMyFeedbacks">
          我的反馈
        </button>
      </div>
    </template>

    <div class="suggestion-dialog">
      <a-form layout="vertical">
        <a-form-item label="建议类型">
          <a-radio-group v-model:value="feedbackType" class="suggestion-type-group">
            <a-radio value="feature_request">加新功能</a-radio>
            <a-radio value="bug_report">我要提BUG</a-radio>
            <a-radio value="optimization">其他优化建议</a-radio>
          </a-radio-group>
        </a-form-item>

        <a-form-item label="建议内容">
          <a-textarea
            v-model:value="content"
            :rows="6"
            :maxlength="5000"
            show-count
            placeholder="请尽量描述清楚问题现象、使用场景、期望效果，便于我们更快处理"
          />
        </a-form-item>

        <a-form-item style="margin-bottom: 0">
          <template #label>
            <div class="upload-label-row">
              <span>图片附件</span>
              <small>最多 5 张，单张不超过 {{ MAX_IMAGE_UPLOAD_SIZE_TEXT }}</small>
            </div>
          </template>

          <input
            ref="uploadInputRef"
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            style="display: none"
            @change="handleUploadChange"
          />

          <div class="suggestion-upload-grid">
            <div
              v-for="(url, index) in attachments"
              :key="url + index"
              class="upload-preview-card"
              @click="openPreview(url)"
            >
              <img :src="url" :alt="`建议附件 ${index + 1}`" loading="lazy" />
              <button
                type="button"
                class="upload-remove-btn"
                title="删除图片"
                @click.stop="removeAttachment(index)"
              >
                <DeleteOutlined />
              </button>
            </div>

            <button
              v-if="attachmentSlotsLeft > 0"
              type="button"
              class="upload-picker-card"
              :disabled="uploading"
              @click="openFilePicker"
            >
              <PlusOutlined />
              <span>{{ uploading ? "上传中..." : "上传图片" }}</span>
            </button>
          </div>
        </a-form-item>
      </a-form>
    </div>

    <div v-if="previewVisible" style="display: none">
      <a-image
        :src="previewSrc"
        :preview="{ visible: previewVisible, onVisibleChange: (v: boolean) => (previewVisible = v) }"
      />
    </div>
  </a-modal>
</template>

<style scoped lang="scss">
.suggestion-dialog {
  padding-top: 6px;
}

.suggestion-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.suggestion-title-link {
  border: none;
  background: transparent;
  color: var(--theme-link);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.suggestion-type-group {
  display: flex;
  flex-wrap: wrap;
  gap: 16px 24px;

  :deep(.ant-radio-inner) {
    border-color: var(--theme-border-strong);
    background-color: var(--theme-control-bg);
  }

  :deep(.ant-radio-wrapper:hover .ant-radio-inner),
  :deep(.ant-radio-checked .ant-radio-inner) {
    border-color: var(--theme-control-active);
  }

  :deep(.ant-radio-checked .ant-radio-inner) {
    background-color: var(--theme-control-active);
  }

  :deep(.ant-radio-inner::after) {
    background-color: #ffffff;
  }
}

.upload-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;

  small {
    color: var(--theme-text-secondary);
    font-size: 12px;
    font-weight: 500;
  }
}

.suggestion-upload-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(108px, 108px));
  gap: 12px;
}

.upload-preview-card,
.upload-picker-card {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 108px;
  height: 108px;
  border-radius: 16px;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
  overflow: hidden;
}

.upload-preview-card {
  padding: 0;
  cursor: zoom-in;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    background: var(--theme-empty-bg);
  }
}

.upload-picker-card {
  flex-direction: column;
  gap: 8px;
  color: var(--theme-accent);
  border-color: var(--theme-panel-border-strong);
  font-weight: 600;
  transition:
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover:not(:disabled) {
    transform: translateY(-2px);
    color: var(--theme-accent-text);
    border-color: var(--theme-control-active);
  }

  &:disabled {
    cursor: wait;
    opacity: 0.7;
  }

  :deep(.anticon) {
    font-size: 18px;
  }
}

.upload-remove-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 999px;
  background: rgb(0 0 0 / 58%);
  color: #fff;
  cursor: pointer;
}

@media (max-width: 640px) {
  .upload-label-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .suggestion-upload-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .upload-preview-card,
  .upload-picker-card {
    width: 100%;
    height: 96px;
  }
}
</style>
