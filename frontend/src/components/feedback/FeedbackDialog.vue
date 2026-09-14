<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { message } from "ant-design-vue";
import { createFeedback } from "@/api/feedback";
import type { FeedbackDetail, FeedbackType } from "@/types";

const props = withDefaults(defineProps<{
  open: boolean;
  taskId?: string | null;
  model?: string;
  prompt?: string;
  createdAt?: string | null;
  title?: string;
  contextTitle?: string;
  requireTask?: boolean;
  appendContent?: string;
  feedbackType?: FeedbackType;
}>(), {
  taskId: "",
  model: "",
  prompt: "",
  createdAt: null,
  title: "提交反馈",
  contextTitle: "任务提示词",
  requireTask: true,
  appendContent: "",
  feedbackType: "image_task",
});

const emit = defineEmits<{
  "update:open": [value: boolean];
  submitted: [detail: FeedbackDetail];
}>();

const content = ref("");
const submitting = ref(false);

const promptPreview = computed(() => {
  const normalized = (props.prompt || "").trim();
  if (!normalized) return "-";
  return normalized.length > 140 ? `${normalized.slice(0, 140)}...` : normalized;
});

watch(
  () => props.open,
  (value) => {
    if (!value) {
      content.value = "";
      submitting.value = false;
    }
  },
);

function closeDialog() {
  emit("update:open", false);
}

function handleOpenChange(value: boolean) {
  emit("update:open", value);
}

async function handleSubmit() {
  const taskId = (props.taskId || "").trim();
  const normalized = content.value.trim();
  if (props.requireTask && !taskId) {
    message.warning("当前任务暂不支持反馈");
    return;
  }
  if (!normalized) {
    message.warning("请输入反馈内容");
    return;
  }

  submitting.value = true;
  try {
    const extra = (props.appendContent || "").trim();
    const contentToSubmit = extra ? `${normalized}\n\n${extra}` : normalized;
    const detail = await createFeedback(taskId || null, contentToSubmit, {
      feedback_type: props.feedbackType,
    });
    message.success("反馈已提交");
    emit("submitted", detail);
    closeDialog();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "提交反馈失败");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <a-modal
    :open="open"
    :title="title"
    ok-text="提交"
    cancel-text="取消"
    :confirm-loading="submitting"
    :width="560"
    centered
    @update:open="handleOpenChange"
    @ok="handleSubmit"
    @cancel="closeDialog"
  >
    <div class="feedback-dialog">
      <div class="feedback-prompt-preview">
        <div class="feedback-section-title">{{ contextTitle }}</div>
        <div class="feedback-prompt-text">{{ promptPreview }}</div>
      </div>
      <a-form layout="vertical">
        <a-form-item label="反馈内容" style="margin-bottom: 0">
          <a-textarea
            v-model:value="content"
            :rows="5"
            :maxlength="5000"
            show-count
            placeholder="请描述问题现象、预期效果或改进建议"
          />
        </a-form-item>
      </a-form>
    </div>
  </a-modal>
</template>

<style scoped lang="scss">
.feedback-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-top: 6px;
}

.feedback-section-title {
  margin-bottom: 8px;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 700;
}

.feedback-prompt-preview {
  padding: 12px 14px;
  border-radius: 16px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
}

.feedback-prompt-text {
  color: var(--theme-title);
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
