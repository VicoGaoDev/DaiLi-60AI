<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref } from "vue";
import { CheckOutlined, DownOutlined, UpOutlined } from "@ant-design/icons-vue";
import { withBaseUrl } from "@/lib/assets";
import {
  apertureOpeningRadius,
  emptyGenerateCameraSelection,
  formatGenerateCameraPresetMeta,
  formatSelectedGenerateCameraLabel,
  generateCameraCategories,
  generateCameraPresetGroups,
  generateCameraPresets,
  getGenerateCameraCategory,
  hasSelectedGenerateCamera,
  matchGenerateCameraPreset,
  selectionFromCameraPreset,
  type GenerateCameraCategoryId,
  type GenerateCameraItem,
  type GenerateCameraPreset,
  type GenerateCameraSelection,
} from "@/lib/generateCameras";

const props = defineProps<{
  bodyId: string;
  lensId: string;
  focalId: string;
  apertureId: string;
}>();

const emit = defineEmits<{
  "update:bodyId": [value: string];
  "update:lensId": [value: string];
  "update:focalId": [value: string];
  "update:apertureId": [value: string];
}>();

const open = ref(false);
const draft = ref<GenerateCameraSelection>({ ...emptyGenerateCameraSelection });

const selectedLabel = computed(() => (
  formatSelectedGenerateCameraLabel({
    bodyId: props.bodyId,
    lensId: props.lensId,
    focalId: props.focalId,
    apertureId: props.apertureId,
  }) || "未选择"
));
const hasSelection = computed(() => hasSelectedGenerateCamera({
  bodyId: props.bodyId,
  lensId: props.lensId,
  focalId: props.focalId,
  apertureId: props.apertureId,
}));
const triggerTooltip = computed(() => (
  hasSelection.value
    ? `摄像机参数：${selectedLabel.value}`
    : "摄像机参数：可模拟镜头、焦距和光圈效果，增强构图、景别与画面氛围"
));
const activePresetId = computed(() => matchGenerateCameraPreset(draft.value)?.id || "");
const brokenThumbnails = ref<Record<string, boolean>>({});

const WHEEL_SLOT_PX = 72;
const WHEEL_VIEWPORT_PX = 176;
const WHEEL_THRESHOLD = 36;
const WHEEL_STEP_MS = 108;
const WHEEL_EASE = "cubic-bezier(0.16, 1, 0.3, 1)";
const CAMERA_CATEGORY_IDS: GenerateCameraCategoryId[] = ["body", "lens", "focal", "aperture"];

const visualIndex = reactive<Record<GenerateCameraCategoryId, number>>({
  body: 0,
  lens: 0,
  focal: 0,
  aperture: 0,
});
const wheelInstant = reactive<Record<GenerateCameraCategoryId, boolean>>({
  body: false,
  lens: false,
  focal: false,
  aperture: false,
});
const wheelCarry = reactive<Record<GenerateCameraCategoryId, number>>({
  body: 0,
  lens: 0,
  focal: 0,
  aperture: 0,
});
const wheelDuration = reactive<Record<GenerateCameraCategoryId, number>>({
  body: WHEEL_STEP_MS,
  lens: WHEEL_STEP_MS,
  focal: WHEEL_STEP_MS,
  aperture: WHEEL_STEP_MS,
});
const recenterTimers: Record<GenerateCameraCategoryId, number> = {
  body: 0,
  lens: 0,
  focal: 0,
  aperture: 0,
};
const presetRolling = ref(false);
const pendingTimers: number[] = [];

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function wait(ms: number) {
  return new Promise<void>((resolve) => {
    const id = window.setTimeout(resolve, ms);
    pendingTimers.push(id);
  });
}

function currentId(categoryId: GenerateCameraCategoryId) {
  if (categoryId === "body") return draft.value.bodyId;
  if (categoryId === "lens") return draft.value.lensId;
  if (categoryId === "focal") return draft.value.focalId;
  return draft.value.apertureId;
}

function setCurrentId(categoryId: GenerateCameraCategoryId, value: string) {
  if (categoryId === "body") draft.value = { ...draft.value, bodyId: value };
  else if (categoryId === "lens") draft.value = { ...draft.value, lensId: value };
  else if (categoryId === "focal") draft.value = { ...draft.value, focalId: value };
  else draft.value = { ...draft.value, apertureId: value };
}

function categoryItems(categoryId: GenerateCameraCategoryId) {
  return getGenerateCameraCategory(categoryId)?.items || [];
}

function currentIndex(categoryId: GenerateCameraCategoryId) {
  const id = currentId(categoryId);
  if (!id) return -1;
  return categoryItems(categoryId).findIndex((item) => item.id === id);
}

function loopedItems(categoryId: GenerateCameraCategoryId) {
  const items = categoryItems(categoryId);
  return items.length ? [...items, ...items, ...items] : [];
}

function syncVisualIndex(categoryId: GenerateCameraCategoryId) {
  const items = categoryItems(categoryId);
  const count = items.length;
  if (!count) {
    visualIndex[categoryId] = 0;
    return;
  }
  const index = currentIndex(categoryId);
  visualIndex[categoryId] = count + Math.max(0, index);
}

function syncAllVisualIndices() {
  for (const categoryId of CAMERA_CATEGORY_IDS) syncVisualIndex(categoryId);
}

function itemAtVisualIndex(categoryId: GenerateCameraCategoryId, index: number) {
  const items = categoryItems(categoryId);
  if (!items.length) return null;
  return items[((index % items.length) + items.length) % items.length] || null;
}

function recenterVisualIndex(categoryId: GenerateCameraCategoryId) {
  const count = categoryItems(categoryId).length;
  if (!count) return;
  const current = visualIndex[categoryId];
  if (current >= count && current < count * 2) return;
  const middle = count + ((current % count) + count) % count;
  if (current === middle) return;
  wheelInstant[categoryId] = true;
  visualIndex[categoryId] = middle;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      wheelInstant[categoryId] = false;
    });
  });
}

function scheduleRecenter(categoryId: GenerateCameraCategoryId, duration: number) {
  window.clearTimeout(recenterTimers[categoryId]);
  const id = window.setTimeout(() => recenterVisualIndex(categoryId), duration + 40);
  recenterTimers[categoryId] = id;
  pendingTimers.push(id);
}

function applyWheelDelta(categoryId: GenerateCameraCategoryId, steps: number, duration = WHEEL_STEP_MS) {
  const items = categoryItems(categoryId);
  if (!items.length || !steps) return;
  visualIndex[categoryId] += steps;
  const next = itemAtVisualIndex(categoryId, visualIndex[categoryId]);
  if (next) setCurrentId(categoryId, next.id);
  const motion = prefersReducedMotion() ? 0 : duration;
  wheelDuration[categoryId] = motion;
  scheduleRecenter(categoryId, motion);
}

function trackTranslate(categoryId: GenerateCameraCategoryId) {
  return (WHEEL_VIEWPORT_PX / 2) - (visualIndex[categoryId] * WHEEL_SLOT_PX + WHEEL_SLOT_PX / 2);
}

function trackStyle(categoryId: GenerateCameraCategoryId) {
  const style: Record<string, string> = {
    transform: `translateY(${trackTranslate(categoryId)}px)`,
  };
  if (wheelInstant[categoryId] || prefersReducedMotion()) {
    style.transition = "none";
  } else if (wheelDuration[categoryId] !== WHEEL_STEP_MS) {
    style.transition = `transform ${wheelDuration[categoryId]}ms ${WHEEL_EASE}`;
  }
  return style;
}

function step(categoryId: GenerateCameraCategoryId, offset: number) {
  applyWheelDelta(categoryId, offset > 0 ? 1 : offset < 0 ? -1 : 0, WHEEL_STEP_MS);
}

function handleWheelItemClick(categoryId: GenerateCameraCategoryId, index: number) {
  const current = visualIndex[categoryId];
  if (index === current) return;
  applyWheelDelta(categoryId, index - current, WHEEL_STEP_MS);
}

function handleWheel(categoryId: GenerateCameraCategoryId, event: WheelEvent) {
  event.preventDefault();
  if (presetRolling.value) return;
  const delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY;
  wheelCarry[categoryId] += delta;
  let steps = 0;
  while (Math.abs(wheelCarry[categoryId]) >= WHEEL_THRESHOLD) {
    steps += wheelCarry[categoryId] > 0 ? 1 : -1;
    wheelCarry[categoryId] -= Math.sign(wheelCarry[categoryId]) * WHEEL_THRESHOLD;
  }
  if (!steps) return;
  applyWheelDelta(categoryId, steps);
}

async function rollCategoryTo(categoryId: GenerateCameraCategoryId, targetId: string) {
  const items = categoryItems(categoryId);
  const targetIndex = items.findIndex((item) => item.id === targetId);
  if (targetIndex < 0) {
    setCurrentId(categoryId, targetId);
    syncVisualIndex(categoryId);
    return;
  }
  const count = items.length;
  const from = ((visualIndex[categoryId] % count) + count) % count;
  if (from === targetIndex) return;
  const forward = (targetIndex - from + count) % count;
  const backward = (from - targetIndex + count) % count;
  const direction = forward <= backward ? 1 : -1;
  const steps = Math.min(forward, backward);
  const duration = prefersReducedMotion() ? 0 : Math.min(180, 100 + steps * 14);
  applyWheelDelta(categoryId, direction * steps, duration);
  await wait(duration);
}

function firstItemId(categoryId: GenerateCameraCategoryId) {
  return categoryItems(categoryId)[0]?.id || "";
}

function withDefaultFirstItems(selection: GenerateCameraSelection): GenerateCameraSelection {
  return {
    bodyId: selection.bodyId || firstItemId("body"),
    lensId: selection.lensId || firstItemId("lens"),
    focalId: selection.focalId || firstItemId("focal"),
    apertureId: selection.apertureId || firstItemId("aperture"),
  };
}

function defaultDraft(selection: GenerateCameraSelection): GenerateCameraSelection {
  if (hasSelectedGenerateCamera(selection)) {
    return withDefaultFirstItems(selection);
  }
  const firstPreset = generateCameraPresets[0];
  return firstPreset ? selectionFromCameraPreset(firstPreset) : withDefaultFirstItems(selection);
}

async function applyPreset(preset: GenerateCameraPreset) {
  if (presetRolling.value) return;
  const target = selectionFromCameraPreset(preset);
  presetRolling.value = true;
  try {
    await Promise.all([
      rollCategoryTo("body", target.bodyId),
      rollCategoryTo("lens", target.lensId),
      rollCategoryTo("focal", target.focalId),
      rollCategoryTo("aperture", target.apertureId),
    ]);
  } finally {
    presetRolling.value = false;
  }
}

function openDialog() {
  draft.value = defaultDraft({
    bodyId: props.bodyId,
    lensId: props.lensId,
    focalId: props.focalId,
    apertureId: props.apertureId,
  });
  syncAllVisualIndices();
  open.value = true;
}

onBeforeUnmount(() => {
  pendingTimers.forEach((id) => window.clearTimeout(id));
  CAMERA_CATEGORY_IDS.forEach((categoryId) => window.clearTimeout(recenterTimers[categoryId]));
});

function closeDialog() {
  open.value = false;
}

function confirmSelection() {
  emit("update:bodyId", draft.value.bodyId);
  emit("update:lensId", draft.value.lensId);
  emit("update:focalId", draft.value.focalId);
  emit("update:apertureId", draft.value.apertureId);
  open.value = false;
}

function displayName(item: GenerateCameraItem | null, fallback = "未选择") {
  return item?.name || fallback;
}

function thumbnailUrl(item: GenerateCameraItem | null) {
  return item?.thumbnail ? withBaseUrl(item.thumbnail) : "";
}

function presetThumbnailUrl(preset: GenerateCameraPreset) {
  return preset.thumbnail && !brokenThumbnails.value[preset.id] ? withBaseUrl(preset.thumbnail) : "";
}

function markPresetThumbnailBroken(presetId: string) {
  brokenThumbnails.value = { ...brokenThumbnails.value, [presetId]: true };
}
</script>

<template>
  <div class="generate-camera-picker">
    <a-tooltip :title="triggerTooltip">
      <button
        type="button"
        class="generate-camera-trigger"
        :class="{ open: open, active: hasSelection }"
        aria-label="摄像机参数"
        @click="openDialog"
      >
        <svg class="generate-camera-trigger-icon" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="13" r="4.2" />
          <circle cx="12" cy="13" r="1.6" />
          <path d="M4.5 8.2h3.1l1.2-1.8h6.4l1.2 1.8h3.1c.9 0 1.6.7 1.6 1.6v8.1c0 .9-.7 1.6-1.6 1.6H4.5c-.9 0-1.6-.7-1.6-1.6V9.8c0-.9.7-1.6 1.6-1.6Z" />
        </svg>
      </button>
    </a-tooltip>

    <a-modal
      :open="open"
      centered
      :width="920"
      wrap-class-name="generate-camera-modal"
      @update:open="(value: boolean) => { if (!value) closeDialog(); }"
      @cancel="closeDialog"
    >
      <template #title>
        <div class="camera-dialog-title">
          <span class="camera-dialog-title-text">摄像机参数</span>
          <span class="camera-dialog-title-hint">可先调上面四列，或点下方预设一键套用</span>
        </div>
      </template>

      <div class="camera-dialog">
        <div class="camera-wheels" @wheel.prevent>
        <section
          v-for="category in generateCameraCategories"
          :key="category.id"
          class="camera-column"
          @wheel.prevent="handleWheel(category.id, $event)"
        >
          <h4 class="camera-column-title">{{ category.name }}</h4>
          <button type="button" class="camera-nav" aria-label="上一项" @click="step(category.id, -1)">
            <UpOutlined />
          </button>
          <div class="camera-wheel">
            <div class="camera-wheel-highlight" />
            <div class="camera-wheel-track" :style="trackStyle(category.id)">
              <button
                v-for="(item, index) in loopedItems(category.id)"
                :key="`${category.id}-${index}-${item.id}`"
                type="button"
                class="camera-wheel-item"
                :class="{ 'is-current': index === visualIndex[category.id] }"
                @click="handleWheelItemClick(category.id, index)"
              >
                <template v-if="index === visualIndex[category.id]">
                  <span
                    v-if="thumbnailUrl(item)"
                    class="camera-wheel-photo-wrap"
                  >
                    <img
                      :src="thumbnailUrl(item)"
                      :alt="displayName(item)"
                      class="camera-wheel-photo"
                      loading="lazy"
                      decoding="async"
                    />
                  </span>
                  <svg
                    v-else-if="category.id === 'aperture'"
                    class="camera-wheel-iris"
                    viewBox="0 0 64 64"
                    aria-hidden="true"
                  >
                    <circle cx="32" cy="32" r="28" />
                    <circle
                      class="camera-wheel-iris-opening"
                      cx="32"
                      cy="32"
                      :r="apertureOpeningRadius(item.name)"
                    />
                    <path d="M32 6l8 16H24L32 6Zm18 8 2 17-16-7 14-10ZM14 14l16 10-17 7 1-17Zm-2 20 17-6 9 15-26-9Zm34 0L32 49l9-15 15 9Z" />
                  </svg>
                  <svg v-else-if="category.id === 'body'" class="camera-wheel-icon" viewBox="0 0 64 40" aria-hidden="true">
                    <rect x="6" y="12" width="36" height="20" rx="3" />
                    <rect x="12" y="8" width="10" height="5" rx="1" />
                    <circle cx="48" cy="22" r="10" />
                    <circle cx="48" cy="22" r="5" />
                  </svg>
                  <svg v-else-if="category.id === 'lens'" class="camera-wheel-icon" viewBox="0 0 64 40" aria-hidden="true">
                    <rect x="8" y="14" width="22" height="12" rx="2" />
                    <path d="M30 12h18l6 8-6 8H30V12Z" />
                    <circle cx="22" cy="20" r="4" />
                  </svg>
                  <span v-if="category.id === 'focal'" class="camera-wheel-number is-main">
                    {{ item.name.replace('mm', '') }}
                  </span>
                  <span class="camera-wheel-name">
                    {{ category.id === 'focal' ? 'mm' : displayName(item) }}
                  </span>
                </template>
                <template v-else>
                  <span v-if="category.id === 'focal'" class="camera-wheel-number">
                    {{ item.name.replace('mm', '') }}
                  </span>
                  <span v-else class="camera-wheel-ghost">{{ displayName(item) }}</span>
                </template>
              </button>
            </div>
          </div>
          <button type="button" class="camera-nav" aria-label="下一项" @click="step(category.id, 1)">
            <DownOutlined />
          </button>
        </section>
        </div>

        <div v-if="generateCameraPresetGroups.length" class="camera-preset-sections">
          <div class="camera-preset-head">
            <h4
              v-for="group in generateCameraPresetGroups"
              :key="`${group.name}-title`"
              class="camera-preset-title"
            >
              {{ group.name }}
            </h4>
          </div>
          <div class="camera-preset-stack">
            <section
              v-for="group in generateCameraPresetGroups"
              :key="group.name"
              class="camera-preset-panel"
            >
              <div class="camera-preset-grid">
              <button
                v-for="preset in group.presets"
                :key="preset.id"
                type="button"
                class="camera-preset-card"
                :class="{ 'is-active': activePresetId === preset.id, 'is-rolling': presetRolling }"
                :aria-pressed="activePresetId === preset.id"
                :disabled="presetRolling"
                @click="applyPreset(preset)"
              >
                <span class="camera-preset-preview">
                  <img
                    v-if="presetThumbnailUrl(preset)"
                    :src="presetThumbnailUrl(preset)"
                    :alt="preset.name"
                    class="camera-preset-photo"
                    loading="lazy"
                    decoding="async"
                    @error="markPresetThumbnailBroken(preset.id)"
                  />
                  <span v-if="activePresetId === preset.id" class="camera-preset-check" aria-hidden="true">
                    <CheckOutlined />
                  </span>
                </span>
                <span class="camera-preset-name">{{ preset.name }}</span>
                <span class="camera-preset-meta">{{ formatGenerateCameraPresetMeta(preset) }}</span>
              </button>
              </div>
            </section>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="camera-dialog-footer">
          <div class="camera-dialog-footer-actions">
            <a-button @click="closeDialog">取消</a-button>
            <a-button type="primary" @click="confirmSelection">应用</a-button>
          </div>
        </div>
      </template>
    </a-modal>
  </div>
</template>

<style scoped lang="scss">
.generate-camera-picker {
  display: inline-flex;
  flex-shrink: 0;
}

.generate-camera-trigger {
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
  cursor: pointer;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft);

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

.generate-camera-trigger-icon {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.6;
  stroke-linejoin: round;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-camera-trigger {
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

.camera-dialog-title {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px 10px;
  padding-right: 8px;
}

.camera-dialog-title-text {
  color: var(--theme-title);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.3;
}

.camera-dialog-title-hint {
  color: var(--theme-text-secondary, rgba(0, 0, 0, 0.45));
  font-size: 12px;
  font-weight: 400;
  line-height: 1.3;
}

.camera-dialog {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  gap: 8px;
}

.camera-preset-sections {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  padding-top: 12px;
  border-top: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.08));
}

.camera-preset-head {
  position: relative;
  display: grid;
  grid-template-columns: 1fr 1fr;
  flex-shrink: 0;
  gap: 0 24px;
  padding: 0 2px 10px;
}

.camera-preset-head::before {
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

.camera-preset-stack {
  position: relative;
  display: grid;
  grid-template-columns: 1fr 1fr;
  flex: 1 1 auto;
  min-height: 0;
  gap: 16px 24px;
  padding: 0 2px 4px;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.camera-preset-stack::before {
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

.camera-preset-title,
.camera-column-title {
  margin: 0 0 2px;
  color: var(--theme-title);
  font-size: 14px;
  font-weight: 700;
}

.camera-preset-title {
  margin-bottom: 0;
  font-size: 15px;
}

.camera-preset-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.camera-preset-card {
  appearance: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  min-width: 0;
  padding: 4px 4px 8px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: inherit;
  text-align: center;
  cursor: pointer;

  &:hover:not(:disabled) {
    background: var(--theme-control-hover-bg, rgba(0, 0, 0, 0.04));
    border-color: var(--theme-border-strong, rgba(0, 0, 0, 0.16));
  }

  &:disabled {
    cursor: default;
  }

  &.is-active {
    background: color-mix(in srgb, var(--theme-accent) 12%, transparent);
    border-color: var(--theme-border-accent, var(--theme-accent));
    box-shadow: 0 0 0 1px var(--theme-border-accent, var(--theme-accent));

    .camera-preset-name {
      color: var(--theme-accent, var(--theme-title));
      font-weight: 700;
    }
  }
}

.camera-preset-preview {
  position: relative;
  display: block;
  width: 100%;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 8px;
  background: var(--theme-control-hover-bg, rgba(0, 0, 0, 0.04));
}

.camera-preset-photo {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.camera-preset-check {
  position: absolute;
  top: 5px;
  right: 5px;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--theme-accent, #1677ff);
  color: #fff;
  font-size: 9px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.28);
}

.camera-preset-name {
  max-width: 100%;
  overflow: hidden;
  color: var(--theme-title);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.camera-preset-meta {
  color: var(--theme-text-secondary, rgba(0, 0, 0, 0.45));
  font-size: 11px;
  font-weight: 500;
  line-height: 1.2;
}

.camera-wheels {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  flex-shrink: 0;
  gap: 0;
}

.camera-column {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 0;
  padding: 0 10px;
  border-right: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.08));

  &:last-child {
    border-right: none;
  }
}

.camera-nav {
  appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--theme-text-secondary, rgba(0, 0, 0, 0.4));
  cursor: pointer;

  &:hover {
    color: var(--theme-title);
    background: var(--theme-control-hover-bg);
  }
}

.camera-wheel {
  position: relative;
  width: 100%;
  height: 176px;
  overflow: hidden;
  mask-image: linear-gradient(180deg, transparent 0%, #000 12%, #000 88%, transparent 100%);
}

.camera-wheel-highlight {
  position: absolute;
  top: 40px;
  right: 0;
  left: 0;
  z-index: 0;
  height: 96px;
  border-radius: 12px;
  background: var(--theme-control-hover-bg, rgba(0, 0, 0, 0.04));
  box-shadow: inset 0 0 0 1px var(--theme-panel-border, rgba(0, 0, 0, 0.06));
  pointer-events: none;
}

.camera-wheel-track {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  will-change: transform;
  transition: transform 108ms cubic-bezier(0.16, 1, 0.3, 1);
}

.camera-wheel-item {
  appearance: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 0 0 72px;
  width: 100%;
  height: 72px;
  padding: 0 6px;
  border: none;
  border-radius: 12px;
  background: transparent;
  color: inherit;
  opacity: 0.34;
  cursor: pointer;
  transition: opacity 120ms cubic-bezier(0.16, 1, 0.3, 1);

  &.is-current {
    opacity: 1;
    cursor: default;
  }
}

@media (prefers-reduced-motion: reduce) {
  .camera-wheel-track,
  .camera-wheel-item {
    transition: none;
  }
}

.camera-wheel-photo-wrap {
  display: block;
  box-sizing: border-box;
  width: 48px;
  height: 48px;
  margin-bottom: 1px;
  overflow: hidden;
  border-radius: 10px;
}

.camera-wheel-photo {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  pointer-events: none;
}

.camera-wheel-iris {
  width: 32px;
  height: 32px;
  margin-bottom: 1px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linejoin: round;
  color: var(--theme-title);
}

.camera-wheel-iris-opening {
  fill: currentColor;
  stroke: none;
  opacity: 0.18;
}

.camera-wheel-icon {
  width: 40px;
  height: 24px;
  margin-bottom: 1px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linejoin: round;
  color: var(--theme-title);
}

.camera-wheel-number {
  color: var(--theme-text-secondary, rgba(0, 0, 0, 0.45));
  font-size: 13px;
  font-weight: 600;
  line-height: 1;

  &.is-main {
    color: var(--theme-title);
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.04em;
  }
}

.camera-wheel-name,
.camera-wheel-ghost {
  max-width: 100%;
  overflow: hidden;
  color: var(--theme-title);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.3;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.camera-wheel-ghost {
  color: var(--theme-text-secondary, rgba(0, 0, 0, 0.4));
  font-weight: 500;
}

.camera-dialog-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

.camera-dialog-footer-actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 767px) {
  .camera-preset-head,
  .camera-preset-stack,
  .camera-preset-grid {
    grid-template-columns: 1fr 1fr;
  }

  .camera-preset-head::before,
  .camera-preset-stack::before {
    display: none;
  }

  .camera-wheels {
    grid-template-columns: 1fr 1fr;
    gap: 16px 0;
  }

  .camera-column:nth-child(2) {
    border-right: none;
  }

  .camera-dialog-footer {
    flex-direction: column;
    align-items: stretch;
  }

  .camera-dialog-footer-actions {
    justify-content: flex-end;
  }
}
</style>

<style lang="scss">
.generate-camera-modal .ant-modal-content {
  max-height: min(84vh, 820px);
}

.generate-camera-modal .ant-modal-body {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>
