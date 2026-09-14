<script setup lang="ts">
import { computed, ref } from "vue";
import dayjs from "dayjs";
import { message } from "ant-design-vue";
import { CopyOutlined, PictureOutlined, ThunderboltOutlined } from "@ant-design/icons-vue";
import { getPreviewImageSrc } from "@/api/images";
import type { CreativeTemplate, GenerationModelOption } from "@/types";

const props = withDefaults(defineProps<{
  open: boolean;
  loading?: boolean;
  detail: CreativeTemplate | null;
  generationModels?: GenerationModelOption[];
  title?: string;
}>(), {
  loading: false,
  generationModels: () => [],
  title: "模版详情",
});

const emit = defineEmits<{
  "update:open": [value: boolean];
  "use-template": [];
}>();

const previewVisible = ref(false);
const previewSrc = ref("");

function closeDialog() {
  emit("update:open", false);
}

function openPreview(src?: string) {
  if (!src) return;
  previewSrc.value = src;
  previewVisible.value = true;
}

async function copyPrompt(prompt: string) {
  try {
    await navigator.clipboard.writeText(prompt || "");
    message.success("提示词已复制");
  } catch {
    message.error("复制失败，请重试");
  }
}

function formatTime(t?: string) {
  return t ? dayjs(t).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function getModelLabel(model?: string) {
  if (!model) return "-";
  return props.generationModels.find((item) => item.model_key === model)?.model_label || model;
}

const detailMetaList = computed(() => {
  if (!props.detail) return [];
  return [
    props.detail.model ? `模型：${getModelLabel(props.detail.model)}` : "",
    `宽高比：${props.detail.size || "-"}`,
    props.detail.resolution ? `分辨率：${props.detail.resolution}` : "",
    props.detail.custom_size ? `自定义分辨率：${props.detail.custom_size}` : "",
    props.detail.tags.length ? `标签：${props.detail.tags.map((tag) => tag.name).join(" / ")}` : "",
    `时间：${formatTime(props.detail.created_at)}`,
  ].filter(Boolean);
});
</script>

<template>
  <a-modal
    :open="open"
    :title="title"
    :footer="null"
    :width="1040"
    centered
    @update:open="emit('update:open', $event)"
    @cancel="closeDialog"
  >
    <a-spin :spinning="loading">
      <div v-if="detail" :key="detail.id" class="detail-layout">
        <div class="detail-left">
          <div class="detail-section">
            <div class="detail-result-grid">
              <div
                class="detail-result-card single"
                :class="{ empty: !detail.result_image }"
                @click="detail.result_image && openPreview(getPreviewImageSrc(detail.result_image))"
              >
                <img v-if="detail.result_image" :src="getPreviewImageSrc(detail.result_image)" alt="模版结果图" />
                <div v-else class="detail-result-empty">暂无结果图</div>
              </div>
            </div>
          </div>
        </div>

        <div class="detail-right">
          <div class="detail-section">
            <div class="detail-meta">
              <span v-for="meta in detailMetaList" :key="meta">{{ meta }}</span>
            </div>
          </div>

          <div v-if="detail.reference_images.length" class="detail-section">
            <div class="detail-label">
              <PictureOutlined />
              <span>参考图</span>
            </div>
            <div class="detail-thumb-row">
              <div
                v-for="(url, idx) in detail.reference_images"
                :key="url + idx"
                class="detail-thumb"
                @click="openPreview(getPreviewImageSrc(url))"
              >
                <img
                  :src="getPreviewImageSrc(detail.reference_image_thumbs?.[idx] || url)"
                  alt="参考图"
                  loading="lazy"
                />
              </div>
            </div>
          </div>

          <div class="detail-section">
            <div class="detail-label-row">
              <div class="detail-label">提示词</div>
              <a-button type="text" class="detail-copy-btn" @click="copyPrompt(detail.prompt)">
                <template #icon><CopyOutlined /></template>
                复制提示词
              </a-button>
            </div>
            <div class="detail-prompt">{{ detail.prompt || "-" }}</div>
          </div>
        </div>

        <div class="detail-floating-actions">
          <a-button type="primary" class="warm-primary-btn detail-primary-action" @click="emit('use-template')">
            <template #icon><ThunderboltOutlined /></template>
            使用此模版
          </a-button>
        </div>
      </div>
    </a-spin>
  </a-modal>

  <div v-if="previewVisible" style="display: none">
    <a-image
      :src="previewSrc"
      :preview="{ visible: previewVisible, onVisibleChange: (v: boolean) => (previewVisible = v) }"
    />
  </div>
</template>

<style scoped lang="scss">
.detail-section + .detail-section {
  margin-top: 18px;
}

.detail-layout {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 20px;
  align-items: start;
  animation: template-detail-slide-in var(--motion-duration-reveal-slower) var(--motion-ease-enter) both;
}

.detail-left,
.detail-right {
  min-width: 0;
}

.detail-right {
  display: flex;
  flex-direction: column;
}

.detail-floating-actions {
  position: absolute;
  right: 0;
  bottom: 0;
  display: flex;
  gap: 8px;
  padding: 0 2px 2px 0;
}

.detail-primary-action {
  height: 40px;
  padding-inline: 16px;
  border-radius: 14px;
  box-shadow: 0 14px 28px var(--theme-shadow-medium);
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

.detail-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.detail-copy-btn {
  height: 30px;
  padding-inline: 10px;
  border-radius: 10px;
  color: var(--theme-link) !important;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover {
    background: var(--theme-panel-bg-strong) !important;
    color: var(--theme-link-hover) !important;
    transform: translateY(-1px);
    box-shadow: 0 10px 20px var(--theme-shadow-soft);
  }

  &:active {
    transform: scale(0.96);
  }
}

.detail-prompt {
  padding: 12px 14px;
  border-radius: 14px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
  color: var(--theme-title);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 210px;
  overflow-y: auto;
  scrollbar-width: thin;
}

.detail-thumb-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.detail-thumb {
  width: 84px;
  height: 84px;
  border-radius: 14px;
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
    box-shadow: 0 16px 26px var(--theme-shadow-medium);
  }
}

.detail-result-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
}

.detail-result-card {
  height: clamp(220px, 36vh, 340px);
  border-radius: 18px;
  overflow: hidden;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
  cursor: zoom-in;
  transition:
    transform var(--motion-duration-base) var(--motion-ease-soft),
    box-shadow var(--motion-duration-base) var(--motion-ease-soft),
    border-color var(--motion-duration-base) var(--motion-ease-soft);

  img,
  .detail-result-empty {
    width: 100%;
    height: 100%;
  }

  img {
    object-fit: contain;
    display: block;
    background: var(--theme-panel-bg);
    transition: transform var(--motion-duration-hover) var(--motion-ease-soft);
  }

  &:not(.empty):hover {
    transform: translateY(-3px);
    border-color: var(--theme-border-strong);
    box-shadow: 0 18px 30px var(--theme-shadow-medium);
  }

  &:not(.empty):hover img {
    transform: scale(1.015);
  }

  &.single {
    height: clamp(440px, 72vh, 680px);
  }

  &.empty {
    cursor: default;
  }
}

.detail-result-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
  padding: 12px 14px;
  border-radius: 14px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.8;

  span:not(:last-child)::after {
    content: "｜";
    margin: 0 8px;
    color: var(--theme-panel-border-strong);
  }
}

@keyframes template-detail-slide-in {
  from {
    opacity: 0;
    transform: translate3d(20px, 0, 0) scale(0.985);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0) scale(1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .detail-layout {
    animation: none !important;
  }

  .detail-copy-btn,
  .detail-thumb,
  .detail-result-card,
  .detail-result-card img {
    transition: none !important;
  }
}

@media (max-width: 900px) {
  .detail-layout {
    grid-template-columns: 1fr;
  }

  .detail-floating-actions {
    position: static;
    justify-content: flex-end;
    margin-top: 14px;
    padding: 0;
  }

  .detail-result-card.single {
    height: clamp(360px, 60vh, 520px);
  }
}

@media (max-width: 640px) {
  .detail-result-card.single {
    height: clamp(280px, 56vh, 420px);
  }
}
</style>
