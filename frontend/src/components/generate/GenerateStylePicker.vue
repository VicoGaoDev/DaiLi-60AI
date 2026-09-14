<script setup lang="ts">
import { computed, ref } from "vue";
import { CheckOutlined } from "@ant-design/icons-vue";
import { withBaseUrl } from "@/lib/assets";
import {
  formatSelectedGenerateStyleLabel,
  generateStyleCategories,
  type GenerateStyleItem,
} from "@/lib/generateStyles";

const props = defineProps<{
  colorStyleId: string;
  lightingStyleId: string;
}>();

const emit = defineEmits<{
  "update:colorStyleId": [value: string];
  "update:lightingStyleId": [value: string];
}>();

const open = ref(false);
const draftColorStyleId = ref(props.colorStyleId);
const draftLightingStyleId = ref(props.lightingStyleId);

const selectedLabel = computed(() => (
  formatSelectedGenerateStyleLabel(props.colorStyleId, props.lightingStyleId) || "未选择"
));
const hasSelection = computed(() => Boolean(props.colorStyleId || props.lightingStyleId));
const triggerTooltip = computed(() => (
  hasSelection.value
    ? `风格设置：${selectedLabel.value}`
    : "风格设置：可补充画风与光线倾向，让生成效果更统一、更有质感"
));
const draftHasSelection = computed(() => Boolean(draftColorStyleId.value || draftLightingStyleId.value));
const brokenThumbnails = ref<Record<string, boolean>>({});

function previewStyle(item: GenerateStyleItem) {
  const via = item.preview.via ? `, ${item.preview.via}` : "";
  return {
    background: `linear-gradient(145deg, ${item.preview.from}${via}, ${item.preview.to})`,
  };
}

function thumbnailUrl(item: GenerateStyleItem) {
  return item.thumbnail ? withBaseUrl(item.thumbnail) : "";
}

function hasThumbnail(item: GenerateStyleItem) {
  return Boolean(thumbnailUrl(item)) && !brokenThumbnails.value[item.id];
}

function markThumbnailBroken(styleId: string) {
  brokenThumbnails.value = { ...brokenThumbnails.value, [styleId]: true };
}

function isSelected(categoryId: string, styleId: string) {
  return categoryId === "color"
    ? draftColorStyleId.value === styleId
    : draftLightingStyleId.value === styleId;
}

function toggleStyle(categoryId: string, styleId: string) {
  if (categoryId === "color") {
    draftColorStyleId.value = draftColorStyleId.value === styleId ? "" : styleId;
    return;
  }
  draftLightingStyleId.value = draftLightingStyleId.value === styleId ? "" : styleId;
}

function openDialog() {
  draftColorStyleId.value = props.colorStyleId;
  draftLightingStyleId.value = props.lightingStyleId;
  open.value = true;
}

function closeDialog() {
  open.value = false;
}

function clearDraft() {
  draftColorStyleId.value = "";
  draftLightingStyleId.value = "";
}

function confirmSelection() {
  emit("update:colorStyleId", draftColorStyleId.value);
  emit("update:lightingStyleId", draftLightingStyleId.value);
  open.value = false;
}
</script>

<template>
  <div class="generate-style-picker">
    <a-tooltip :title="triggerTooltip">
      <button
        type="button"
        class="generate-style-trigger"
        :class="{ open: open, active: hasSelection }"
        aria-label="风格设置"
        @click="openDialog"
      >
        <svg class="generate-style-trigger-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 3.5c-5.1 0-8.5 3.6-8.5 7.4 0 2.6 1.8 4.4 4.2 4.4 1.1 0 1.8-.5 2.1-1.3.2-.5.7-1.7 1.5-1.7.7 0 1 .7 1 1.6 0 2.5-1.5 5.6 1.7 5.6 4.4 0 7.5-3.8 7.5-8.1C21.5 6.7 17.6 3.5 12 3.5Z" />
          <circle cx="8.1" cy="9.1" r="1.15" />
          <circle cx="11.2" cy="7.35" r="1.15" />
          <circle cx="14.7" cy="8.15" r="1.15" />
          <circle cx="16.15" cy="11.35" r="1.15" />
        </svg>
      </button>
    </a-tooltip>

    <a-modal
      :open="open"
      centered
      :width="920"
      wrap-class-name="generate-style-modal"
      @update:open="(value: boolean) => { if (!value) closeDialog(); }"
      @cancel="closeDialog"
    >
      <template #title>
        <div class="style-dialog-title">
          <span class="style-dialog-title-text">风格设置</span>
          <span class="style-dialog-title-hint">选择后，生成图片会带上对应的风格效果</span>
        </div>
      </template>
      <div class="style-dialog">
        <div class="style-category-grid">
          <section v-for="category in generateStyleCategories" :key="category.id" class="style-category">
            <h4 class="style-category-title">{{ category.name }}</h4>
            <div class="style-card-grid">
              <button
                v-for="item in category.items"
                :key="item.id"
                type="button"
                class="style-card"
                :class="{ 'is-active': isSelected(category.id, item.id) }"
                @click="toggleStyle(category.id, item.id)"
              >
                <span
                  class="style-card-preview"
                  :class="!hasThumbnail(item) && item.preview.pattern ? `is-${item.preview.pattern}` : ''"
                  :style="previewStyle(item)"
                >
                  <img
                    v-if="hasThumbnail(item)"
                    :src="thumbnailUrl(item)"
                    :alt="item.name"
                    class="style-card-photo"
                    loading="lazy"
                    decoding="async"
                    @error="markThumbnailBroken(item.id)"
                  />
                  <span v-if="isSelected(category.id, item.id)" class="style-card-check" aria-hidden="true">
                    <CheckOutlined />
                  </span>
                </span>
                <span class="style-card-name">{{ item.name }}</span>
              </button>
            </div>
          </section>
        </div>
      </div>

      <template #footer>
        <div class="style-dialog-footer">
          <a-button :disabled="!draftHasSelection" @click="clearDraft">清除风格</a-button>
          <div class="style-dialog-footer-actions">
            <a-button @click="closeDialog">取消</a-button>
            <a-button type="primary" @click="confirmSelection">完成</a-button>
          </div>
        </div>
      </template>
    </a-modal>
  </div>
</template>

<style scoped lang="scss">
.generate-style-picker {
  display: inline-flex;
  flex-shrink: 0;
}

.generate-style-trigger {
  appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid var(--theme-control-border-strong);
  border-radius: 12px;
  background: var(--theme-control-bg);
  color: var(--theme-title);
  font-size: 13px;
  font-weight: 600;
  line-height: 1;
  cursor: pointer;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover,
  &.open {
    background: var(--theme-control-hover-bg);
    border-color: var(--theme-border-strong);
    transform: translateY(-1px);
  }

  &:active {
    transform: scale(0.97);
  }

  &.active {
    color: var(--theme-accent-text, var(--theme-title));
    background: color-mix(in srgb, var(--theme-accent) 28%, var(--theme-control-bg));
    border-color: var(--theme-border-accent, var(--theme-accent));
  }

  &.active:hover,
  &.active.open {
    background: color-mix(in srgb, var(--theme-accent) 38%, var(--theme-control-bg));
    border-color: var(--theme-border-accent, var(--theme-accent));
  }
}

.generate-style-trigger-icon {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.6;
  stroke-linejoin: round;
}

.generate-style-trigger-icon circle {
  fill: currentColor;
  stroke: none;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-style-trigger {
  color: var(--text-secondary);
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);

  &:hover,
  &.open {
    color: var(--theme-title);
    background: var(--theme-control-hover-bg);
    border-color: var(--theme-border-strong);
  }

  &.active {
    color: var(--theme-title);
    background: color-mix(in srgb, var(--theme-accent) 34%, var(--theme-panel-bg-soft));
    border-color: var(--theme-border-accent, var(--theme-accent));
  }

  &.active:hover,
  &.active.open {
    background: color-mix(in srgb, var(--theme-accent) 44%, var(--theme-panel-bg-soft));
  }
}

.style-dialog-title {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px 10px;
  padding-right: 8px;
}

.style-dialog-title-text {
  color: var(--theme-title);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.3;
}

.style-dialog-title-hint {
  color: var(--theme-text-secondary, rgba(0, 0, 0, 0.45));
  font-size: 12px;
  font-weight: 400;
  line-height: 1.3;
}

.style-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.style-category-grid {
  position: relative;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px 32px;
}

.style-category-grid::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 1px;
  background: var(--theme-panel-border, rgba(0, 0, 0, 0.1));
  transform: translateX(-50%);
  pointer-events: none;
}

.style-category-title {
  margin: 0 0 12px;
  color: var(--theme-title);
  font-size: 15px;
  font-weight: 700;
}

.style-card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.style-card {
  appearance: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;

  &.is-active {
    .style-card-preview {
      box-shadow: 0 0 0 2px var(--theme-border-accent, #1677ff);
    }

    .style-card-name {
      color: var(--theme-accent, #1677ff);
      font-weight: 700;
    }
  }
}

.style-card-check {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--theme-accent, #1677ff);
  color: #fff;
  font-size: 10px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.28);
}

.style-card-photo {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.style-card-preview {
  position: relative;
  display: block;
  width: 100%;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 10px;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.08);

  &::after {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
  }

  &.is-blinds::after {
    background: repeating-linear-gradient(
      180deg,
      rgba(0, 0, 0, 0.38) 0 8px,
      transparent 8px 16px
    );
  }

  &.is-rim::after {
    background: radial-gradient(circle at 50% 50%, transparent 42%, rgba(0, 0, 0, 0.55) 72%);
  }

  &.is-silhouette::after {
    background: radial-gradient(circle at 50% 52%, rgba(36, 32, 28, 0.42) 20%, rgba(20, 18, 16, 0.22) 38%, transparent 54%);
  }

  &.is-top::after {
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.28), transparent 38%, rgba(0, 0, 0, 0.45));
  }

  &.is-bottom::after {
    background: linear-gradient(0deg, rgba(255, 220, 140, 0.45), transparent 42%, rgba(0, 0, 0, 0.5));
  }

  &.is-hard::after {
    background: linear-gradient(90deg, rgba(0, 0, 0, 0.55) 46%, transparent 54%);
  }
}

.style-card-name {
  display: block;
  min-height: 1.4em;
  padding: 0 2px 4px;
  overflow: hidden;
  color: var(--theme-title);
  font-size: 12px;
  line-height: 1.4;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.style-dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.style-dialog-footer-actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 767px) {
  .style-category-grid,
  .style-card-grid {
    grid-template-columns: 1fr 1fr;
  }

  .style-category-grid::before {
    display: none;
  }

  .style-dialog-footer {
    flex-direction: column;
    align-items: stretch;
  }

  .style-dialog-footer-actions {
    justify-content: flex-end;
  }
}
</style>

<style lang="scss">
.generate-style-modal .ant-modal-body {
  max-height: min(72vh, 720px);
  overflow: auto;
}
</style>
