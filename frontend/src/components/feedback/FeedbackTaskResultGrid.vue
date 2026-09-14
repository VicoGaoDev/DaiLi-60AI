<script setup lang="ts">
import { computed } from "vue";
import { getDisplayImageUrl, getPreviewImageUrl } from "@/api/images";
import { withBaseUrl } from "@/lib/assets";
import { formatGenerationErrorMessage } from "@/lib/generationErrors";
import type { FeedbackTaskSummary, ImageResult } from "@/types";

const props = defineProps<{
  task: FeedbackTaskSummary;
}>();

const emit = defineEmits<{
  preview: [url: string];
}>();

const failedResultAsset = withBaseUrl("failed-result.svg");
const images = computed(() => {
  const items = props.task.images || [];
  if (items.length || props.task.status !== "failed") return items;
  return [
    {
      id: -1,
      image_url: "",
      status: "failed",
      error_message: props.task.error_message || "",
    } as ImageResult,
  ];
});

const hasPreviewableImages = computed(() =>
  images.value.some((image) => !isImageFailed(image) && !!getPreviewImageUrl(image))
);

function isImageFailed(image: ImageResult) {
  return image.status === "failed" || props.task.status === "failed";
}

function getDisplaySrc(image: ImageResult) {
  if (isImageFailed(image)) return "";
  return getDisplayImageUrl(image);
}

function getPreviewSrc(image: ImageResult) {
  if (isImageFailed(image)) return "";
  return getPreviewImageUrl(image);
}

function getFailureMessage(image: ImageResult) {
  const message = (props.task.error_message || image.error_message || "").trim();
  return formatGenerationErrorMessage(message, "生成失败");
}
</script>

<template>
  <div class="detail-block task-result-block">
    <div class="detail-label detail-label-inline">
      <span>任务结果图</span>
      <small v-if="hasPreviewableImages">点击缩略图可放大</small>
    </div>
    <div v-if="images.length" class="task-result-grid task-result-grid-compact">
      <button
        v-for="(image, index) in images"
        :key="image.id"
        type="button"
        class="task-result-thumb"
        :class="{
          clickable: !!getPreviewSrc(image),
          pending: !isImageFailed(image) && !getDisplaySrc(image),
          failed: isImageFailed(image),
        }"
        :disabled="isImageFailed(image)"
        @click="getPreviewSrc(image) && emit('preview', getPreviewSrc(image))"
      >
        <template v-if="isImageFailed(image)">
          <img :src="failedResultAsset" class="task-failed-image" :alt="`任务结果图 ${index + 1}`" />
          <div class="task-result-failed-message">{{ getFailureMessage(image) }}</div>
        </template>
        <img
          v-else-if="getDisplaySrc(image)"
          :src="getDisplaySrc(image)"
          :alt="`任务结果图 ${index + 1}`"
          loading="lazy"
        />
        <div v-else class="task-result-state compact">
          <a-spin size="small" />
        </div>
      </button>
    </div>
    <a-empty v-else description="任务结果图暂未生成或已不可用" />
  </div>
</template>

<style scoped lang="scss">
.detail-block {
  margin-top: 18px;
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

.task-result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.task-result-grid-compact {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.task-result-thumb {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
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

  &.failed {
    cursor: default;
  }

  > img:not(.task-failed-image) {
    width: 100%;
    aspect-ratio: 1 / 1;
    object-fit: cover;
    border-radius: 0;
    background: var(--theme-empty-bg);
  }
}

.task-failed-image {
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: contain;
  padding: 16px;
  background: linear-gradient(180deg, #fff2ef, #ffdcd5);
}

.task-result-failed-message {
  flex: 1 1 auto;
  padding: 8px 10px 10px;
  color: #b85d47;
  font-size: 11px;
  line-height: 1.5;
  text-align: center;
  word-break: break-word;
  background: rgba(255, 242, 239, 0.96);
  border-top: 1px solid rgba(184, 93, 71, 0.12);
}

.task-result-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 96px;
  width: 100%;
  padding: 12px;
  border-radius: 0;
  background: var(--theme-empty-bg);
  color: var(--theme-text-secondary);
  text-align: center;
  line-height: 1.6;
}

.task-result-state.compact {
  min-height: 96px;
  padding: 8px;
}

@media (max-width: 900px) {
  .task-result-grid-compact {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .task-result-grid-compact {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) {
  .task-failed-image,
  .task-result-failed-message {
    background: var(--theme-panel-bg-soft);
  }

  .task-result-failed-message {
    color: #e8a498;
    border-top-color: rgba(232, 164, 152, 0.18);
  }
}
</style>
