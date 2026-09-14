<script setup lang="ts">
import { computed, ref } from "vue";
import { DownOutlined } from "@ant-design/icons-vue";
import type { SceneOptionItem } from "@/types";

const props = withDefaults(defineProps<{
  modelValue: string;
  options: SceneOptionItem[];
  panelTitle: string;
  placeholder?: string;
  showPreview?: boolean;
  columns?: number;
}>(), {
  placeholder: "请选择",
  showPreview: false,
  columns: 3,
});

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

const open = ref(false);

const selectedOption = computed(
  () => props.options.find((item) => item.value === props.modelValue) || props.options[0] || null,
);

function parseRatioParts(value?: string) {
  if (!value) return null;
  const normalized = value.trim();
  const ratioMatch = normalized.match(/^(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)$/);
  if (ratioMatch) {
    return { width: Number(ratioMatch[1]), height: Number(ratioMatch[2]) };
  }
  const sizeMatch = normalized.match(/^(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)$/);
  if (sizeMatch) {
    return { width: Number(sizeMatch[1]), height: Number(sizeMatch[2]) };
  }
  return null;
}

function formatOptionLabel(option: SceneOptionItem) {
  const parts = parseRatioParts(option.value);
  if (parts) {
    if (option.value.includes(":")) {
      return `${parts.width}:${parts.height}`;
    }
    return `${parts.width} x ${parts.height}`;
  }
  return option.label.trim() || option.value;
}

function getPreviewStyle(value: string, maxSize = 22) {
  const parts = parseRatioParts(value);
  if (!parts || parts.width <= 0 || parts.height <= 0) {
    return { width: `${maxSize}px`, height: `${maxSize}px` };
  }
  if (parts.width >= parts.height) {
    return {
      width: `${maxSize}px`,
      height: `${Math.max(12, Math.round((maxSize * parts.height) / parts.width))}px`,
    };
  }
  return {
    height: `${maxSize}px`,
    width: `${Math.max(12, Math.round((maxSize * parts.width) / parts.height))}px`,
  };
}

function shouldShowPreview(value: string) {
  return props.showPreview && !!parseRatioParts(value);
}

function selectOption(value: string) {
  emit("update:modelValue", value);
  open.value = false;
}
</script>

<template>
  <a-popover
    v-model:open="open"
    trigger="click"
    placement="topLeft"
    overlay-class-name="option-grid-popover"
    class="option-grid-picker"
  >
    <template #content>
      <div class="option-grid-panel">
        <div class="option-grid-panel-title">{{ panelTitle }}</div>
        <div class="option-grid" :class="{ 'is-single-col': columns <= 1 }" :style="{ gridTemplateColumns: `repeat(${Math.max(1, columns)}, minmax(0, 1fr))` }">
          <button
            v-for="option in options"
            :key="option.value"
            type="button"
            class="option-grid-item"
            :class="{ active: modelValue === option.value }"
            @click="selectOption(option.value)"
          >
            <span v-if="shouldShowPreview(option.value)" class="option-grid-preview-shell">
              <span class="option-grid-preview" :style="getPreviewStyle(option.value, 20)" />
            </span>
            <span
              v-else
              class="option-grid-badge"
              :class="{ 'option-grid-badge-compact': formatOptionLabel(option).length > 6 }"
            >
              {{ formatOptionLabel(option) }}
            </span>
            <span v-if="shouldShowPreview(option.value)" class="option-grid-label">
              {{ formatOptionLabel(option) }}
            </span>
          </button>
        </div>
      </div>
    </template>

    <button type="button" class="option-grid-trigger" :class="{ open }">
      <span v-if="selectedOption" class="option-grid-trigger-main">
        <span v-if="shouldShowPreview(selectedOption.value)" class="option-grid-preview-shell option-grid-preview-shell-compact">
          <span class="option-grid-preview" :style="getPreviewStyle(selectedOption.value, 18)" />
        </span>
        <span class="option-grid-trigger-label">{{ formatOptionLabel(selectedOption) }}</span>
      </span>
      <span v-else class="option-grid-trigger-placeholder">{{ placeholder }}</span>
      <DownOutlined class="option-grid-trigger-arrow" />
    </button>
  </a-popover>
</template>

<style scoped lang="scss">
.option-grid-picker {
  display: inline-flex;
  width: auto;
  max-width: 100%;
  cursor: pointer;
}

.option-grid-trigger {
  appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: auto;
  min-width: 108px;
  max-width: 100%;
  min-height: 40px;
  padding: 0 12px;
  border: 1px solid var(--theme-control-border-strong);
  border-radius: 16px;
  background: var(--theme-field-bg, var(--theme-control-bg));
  color: var(--theme-title);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  cursor: pointer;
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 10px 22px var(--theme-shadow-soft);
  transition:
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover,
  &.open {
    border-color: var(--theme-border-strong);
    background: var(--theme-field-hover-bg, var(--theme-control-hover-bg));
    transform: translateY(-1px);
    box-shadow:
      inset 0 1px 0 var(--theme-panel-inset),
      0 12px 22px var(--theme-shadow-medium);
  }

  &.open {
    border-color: var(--theme-border-accent);
    box-shadow:
      inset 0 1px 0 var(--theme-panel-inset),
      0 0 0 3px var(--theme-focus-ring),
      0 12px 22px var(--theme-shadow-medium);
  }
}

.option-grid-trigger-main {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.option-grid-trigger-label {
  white-space: nowrap;
}

.option-grid-trigger-placeholder {
  color: var(--text-muted);
}

.option-grid-trigger-arrow {
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 11px;
  transition: transform var(--motion-duration-fast) var(--motion-ease-soft);
}

.option-grid-trigger.open .option-grid-trigger-arrow {
  transform: rotate(180deg);
}

.option-grid-preview-shell {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
}

.option-grid-preview-shell-compact {
  width: 22px;
  height: 22px;
}

.option-grid-preview {
  display: block;
  border: 1.5px solid currentColor;
  border-radius: 3px;
  background: color-mix(in srgb, currentColor 12%, transparent);
}

.option-grid-panel-title {
  margin-bottom: 8px;
  color: var(--theme-title);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
}

.option-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  width: min(228px, calc(100vw - 72px));
}

.option-grid.is-single-col {
  width: min(260px, calc(100vw - 72px));
  max-height: min(280px, 46vh);
  overflow-y: auto;
  padding-right: 2px;
}

.option-grid.is-single-col .option-grid-item {
  flex-direction: row;
  justify-content: flex-start;
  min-height: 36px;
  padding: 8px 10px;
}

.option-grid.is-single-col .option-grid-badge {
  min-width: 0;
  min-height: 0;
  padding: 0;
  background: transparent;
  font-size: 13px;
  justify-content: flex-start;
  text-align: left;
}

.option-grid-item {
  appearance: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 58px;
  padding: 7px 5px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 11px;
  background: linear-gradient(180deg, var(--theme-control-bg), var(--theme-panel-bg-soft));
  color: var(--theme-title);
  font-weight: 400;
  cursor: pointer;
  transition:
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover {
    border-color: var(--theme-border-strong);
    transform: translateY(-1px);
    box-shadow: 0 6px 14px var(--theme-shadow-soft);
  }

  &.active {
    border-color: var(--theme-border-accent);
    background: color-mix(in srgb, var(--theme-accent) 10%, var(--theme-control-bg));
    color: var(--theme-accent-text);
    box-shadow:
      inset 0 1px 0 var(--theme-panel-inset),
      0 0 0 1px color-mix(in srgb, var(--theme-accent) 24%, transparent);
  }
}

.option-grid-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  min-height: 26px;
  padding: 0 6px;
  border-radius: 8px;
  background: color-mix(in srgb, currentColor 10%, transparent);
  font-size: 13px;
  font-weight: 400;
  line-height: 1;
}

.option-grid-badge-compact {
  min-width: 0;
  padding: 0 4px;
  font-size: 10px;
  line-height: 1.2;
  text-align: center;
}

.option-grid-label {
  font-size: 11px;
  font-weight: 400;
  line-height: 1.2;
  text-align: center;
  word-break: break-word;
}
</style>

<style lang="scss">
.option-grid-popover {
  z-index: 1400;

  .ant-popover-inner {
    padding: 10px;
    border-radius: 16px;
    background: var(--theme-dropdown-bg);
    border: 1px solid var(--theme-panel-border);
    box-shadow: 0 18px 32px var(--theme-shadow-medium);
  }

  .ant-popover-inner-content {
    padding: 0;
  }

  .ant-popover-arrow::before {
    background: var(--theme-dropdown-bg);
  }
}
</style>
