<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { DownOutlined, RightOutlined } from "@ant-design/icons-vue";

export interface ModelCategorySelectOption {
  value: string;
  label: string;
  description?: string;
  sortOrder?: number;
  categoryId?: number | null;
  categoryName?: string | null;
  categorySortOrder?: number | null;
}

const props = withDefaults(defineProps<{
  modelValue: string;
  options: ModelCategorySelectOption[];
  placeholder?: string;
  disabled?: boolean;
  loading?: boolean;
  variant?: "flat" | "default";
  popupClassName?: string;
}>(), {
  placeholder: "请选择模型",
  disabled: false,
  loading: false,
  variant: "default",
  popupClassName: "",
});

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

const MOBILE_QUERY = "(max-width: 768px)";

const open = ref(false);
const isMobile = ref(false);
const hoveredCategoryId = ref<number | null>(null);
const expandedCategoryIds = ref<number[]>([]);
const rootRef = ref<HTMLElement | null>(null);
const dropdownRef = ref<HTMLElement | null>(null);
const submenuRef = ref<HTMLElement | null>(null);
const dropdownStyle = ref<Record<string, string>>({});
const submenuStyle = ref<Record<string, string>>({});
let hoverClearTimer: number | null = null;
let mobileQuery: MediaQueryList | null = null;

const selectedOption = computed(() => (
  props.options.find((item) => item.value === props.modelValue) || null
));

const modelCount = computed(() => props.options.length);

const groupedCategories = computed(() => {
  const groups = new Map<number, {
    id: number;
    name: string;
    sortOrder: number;
    options: ModelCategorySelectOption[];
  }>();
  props.options.forEach((item) => {
    if (item.categoryId == null || !item.categoryName) return;
    const existing = groups.get(item.categoryId);
    if (existing) {
      existing.options.push(item);
      return;
    }
    groups.set(item.categoryId, {
      id: item.categoryId,
      name: item.categoryName,
      sortOrder: item.categorySortOrder ?? 0,
      options: [item],
    });
  });
  return Array.from(groups.values())
    .filter((item) => item.options.length > 0)
    .sort((a, b) => a.sortOrder - b.sortOrder || a.id - b.id)
    .map((item) => ({
      ...item,
      options: [...item.options].sort((a, b) => (a.sortOrder ?? 0) - (b.sortOrder ?? 0)),
    }));
});

const uncategorizedOptions = computed(() => (
  props.options
    .filter((item) => item.categoryId == null || !item.categoryName)
    .sort((a, b) => (a.sortOrder ?? 0) - (b.sortOrder ?? 0))
));

const hoveredCategory = computed(() => (
  isMobile.value ? null : groupedCategories.value.find((item) => item.id === hoveredCategoryId.value) || null
));

function expandAllCategories() {
  expandedCategoryIds.value = groupedCategories.value.map((item) => item.id);
}

function isCategoryExpanded(categoryId: number) {
  return expandedCategoryIds.value.includes(categoryId);
}

function toggleCategory(categoryId: number) {
  if (!isMobile.value) {
    hoverCategory(categoryId);
    return;
  }
  expandedCategoryIds.value = isCategoryExpanded(categoryId)
    ? expandedCategoryIds.value.filter((id) => id !== categoryId)
    : [...expandedCategoryIds.value, categoryId];
  void nextTick().then(() => updateDropdownPosition());
}

function syncMobileQuery() {
  isMobile.value = Boolean(mobileQuery?.matches);
  if (isMobile.value) {
    cancelHoverClear();
    hoveredCategoryId.value = null;
    if (open.value) expandAllCategories();
    return;
  }
  expandedCategoryIds.value = [];
}

function cancelHoverClear() {
  if (hoverClearTimer != null) {
    window.clearTimeout(hoverClearTimer);
    hoverClearTimer = null;
  }
}

function closeMenu() {
  cancelHoverClear();
  open.value = false;
  hoveredCategoryId.value = null;
}

function toggleOpen() {
  if (props.disabled) return;
  if (open.value) {
    closeMenu();
    return;
  }
  if (isMobile.value) expandAllCategories();
  updateDropdownPosition();
  open.value = true;
}

const PANEL_GAP = 6;
const VIEWPORT_PAD = 8;
const PANEL_MAX_HEIGHT = 360;
const ITEM_ESTIMATE = 48;

function selectOption(value: string) {
  emit("update:modelValue", value);
  closeMenu();
}

function estimatePanelHeight(count: number) {
  return Math.min(PANEL_MAX_HEIGHT, 12 + Math.max(1, count) * ITEM_ESTIMATE);
}

function clampPanelHeight(available: number) {
  return Math.max(120, Math.min(PANEL_MAX_HEIGHT, available));
}

const isOpenUp = computed(() => (
  Boolean(dropdownStyle.value.bottom) && dropdownStyle.value.bottom !== "auto"
));

function updateDropdownPosition() {
  const trigger = rootRef.value?.querySelector(".model-category-select-trigger") as HTMLElement | null;
  if (!trigger) return;
  const rect = trigger.getBoundingClientRect();
  const spaceBelow = window.innerHeight - rect.bottom - PANEL_GAP - VIEWPORT_PAD;
  const spaceAbove = rect.top - PANEL_GAP - VIEWPORT_PAD;
  const itemCount = isMobile.value
    ? groupedCategories.value.reduce((count, category) => (
      count + 1 + (isCategoryExpanded(category.id) ? category.options.length : 0)
    ), uncategorizedOptions.value.length)
    : groupedCategories.value.length + uncategorizedOptions.value.length;
  const needed = Math.min(
    PANEL_MAX_HEIGHT,
    dropdownRef.value?.scrollHeight || estimatePanelHeight(itemCount),
  );
  const openUp = spaceBelow < needed && spaceAbove > spaceBelow;
  const maxHeight = clampPanelHeight(openUp ? spaceAbove : spaceBelow);
  dropdownStyle.value = openUp
    ? {
        top: "auto",
        bottom: `${window.innerHeight - rect.top + PANEL_GAP}px`,
        left: `${rect.left}px`,
        width: `${rect.width}px`,
        maxHeight: `${maxHeight}px`,
      }
    : {
        top: `${rect.bottom + PANEL_GAP}px`,
        bottom: "auto",
        left: `${rect.left}px`,
        width: `${rect.width}px`,
        maxHeight: `${maxHeight}px`,
      };
  if (hoveredCategory.value) {
    updateSubmenuPosition();
  }
}

function updateSubmenuPosition() {
  const dropdown = dropdownRef.value;
  const submenu = submenuRef.value;
  const active = dropdown?.querySelector(".is-category.is-active") as HTMLElement | null;
  if (!dropdown || !active) return;
  const dropdownRect = dropdown.getBoundingClientRect();
  const itemRect = active.getBoundingClientRect();
  const width = Math.max(240, Math.min(dropdownRect.width, 320));
  const openRight = dropdownRect.right + 8 + width <= window.innerWidth - 8;
  const estimatedHeight = Math.min(
    PANEL_MAX_HEIGHT,
    submenu?.scrollHeight || estimatePanelHeight(hoveredCategory.value?.options.length || 1),
  );
  let top = itemRect.top;
  if (top + estimatedHeight > window.innerHeight - VIEWPORT_PAD) {
    top = Math.max(VIEWPORT_PAD, window.innerHeight - VIEWPORT_PAD - estimatedHeight);
  }
  if (top < VIEWPORT_PAD) top = VIEWPORT_PAD;
  const maxHeight = clampPanelHeight(window.innerHeight - VIEWPORT_PAD - top);
  submenuStyle.value = {
    top: `${top}px`,
    left: openRight ? `${dropdownRect.right + 4}px` : `${Math.max(VIEWPORT_PAD, dropdownRect.left - width - 4)}px`,
    width: `${width}px`,
    maxHeight: `${maxHeight}px`,
  };
}

function handleDocumentPointerDown(event: PointerEvent) {
  const target = event.target as Node | null;
  if (!target) return;
  if (rootRef.value?.contains(target) || dropdownRef.value?.contains(target) || submenuRef.value?.contains(target)) {
    return;
  }
  closeMenu();
}

function handleEscape(event: KeyboardEvent) {
  if (event.key === "Escape") closeMenu();
}

function hoverCategory(categoryId: number) {
  if (isMobile.value) return;
  cancelHoverClear();
  hoveredCategoryId.value = categoryId;
}

function scheduleClearHoveredCategory() {
  if (isMobile.value) return;
  cancelHoverClear();
  hoverClearTimer = window.setTimeout(() => {
    hoveredCategoryId.value = null;
    hoverClearTimer = null;
  }, 120);
}

watch(open, async (visible) => {
  if (!visible) {
    hoveredCategoryId.value = null;
    window.removeEventListener("resize", updateDropdownPosition);
    window.removeEventListener("scroll", updateDropdownPosition, true);
    return;
  }
  hoveredCategoryId.value = null;
  if (isMobile.value) expandAllCategories();
  updateDropdownPosition();
  window.addEventListener("resize", updateDropdownPosition);
  window.addEventListener("scroll", updateDropdownPosition, true);
  await nextTick();
  updateDropdownPosition();
});

watch(hoveredCategoryId, async () => {
  if (!open.value || !hoveredCategory.value) return;
  await nextTick();
  updateSubmenuPosition();
  await nextTick();
  updateSubmenuPosition();
});

if (typeof document !== "undefined") {
  document.addEventListener("pointerdown", handleDocumentPointerDown);
  document.addEventListener("keydown", handleEscape);
}

onMounted(() => {
  if (typeof window === "undefined") return;
  mobileQuery = window.matchMedia(MOBILE_QUERY);
  syncMobileQuery();
  mobileQuery.addEventListener("change", syncMobileQuery);
});

onBeforeUnmount(() => {
  cancelHoverClear();
  mobileQuery?.removeEventListener("change", syncMobileQuery);
  document.removeEventListener("pointerdown", handleDocumentPointerDown);
  document.removeEventListener("keydown", handleEscape);
  window.removeEventListener("resize", updateDropdownPosition);
  window.removeEventListener("scroll", updateDropdownPosition, true);
});
</script>

<template>
  <div
    ref="rootRef"
    class="model-category-select"
    :class="[`is-${variant}`, { 'is-open': open, 'is-disabled': disabled, 'is-mobile': isMobile }]"
  >
    <button
      type="button"
      class="model-category-select-trigger"
      :disabled="disabled"
      @click="toggleOpen"
    >
      <span v-if="selectedOption" class="model-category-select-value">
        <span class="model-category-select-label">{{ selectedOption.label }}</span>
      </span>
      <span v-else class="model-category-select-placeholder">{{ loading ? "加载中..." : placeholder }}</span>
      <span v-if="modelCount > 0" class="model-category-select-count">共 {{ modelCount }} 个模型</span>
      <DownOutlined class="model-category-select-arrow" />
    </button>

    <Teleport to="body">
      <Transition name="model-category-select-slide">
      <div
        v-if="open"
        ref="dropdownRef"
        class="model-category-select-panel"
        :class="[popupClassName, { 'is-mobile-accordion': isMobile, 'is-open-up': isOpenUp }]"
        :style="dropdownStyle"
        @mouseleave="scheduleClearHoveredCategory"
      >
        <div
          v-for="category in groupedCategories"
          :key="`category-${category.id}`"
          class="model-category-select-group"
        >
          <button
            type="button"
            class="model-category-select-item is-category"
            :class="{
              'is-active': !isMobile && hoveredCategoryId === category.id,
              'is-expanded': isMobile && isCategoryExpanded(category.id),
              'is-selected': !isMobile && category.options.some((item) => item.value === modelValue),
            }"
            @mouseenter="hoverCategory(category.id)"
            @focus="hoverCategory(category.id)"
            @click.stop="toggleCategory(category.id)"
          >
            <span class="model-category-select-item-main">
              <span class="model-category-select-item-label">{{ category.name }}</span>
            </span>
            <DownOutlined
              v-if="isMobile"
              class="model-category-select-item-arrow is-toggle"
              :class="{ 'is-expanded': isCategoryExpanded(category.id) }"
            />
            <RightOutlined v-else class="model-category-select-item-arrow" />
          </button>

          <Transition name="model-category-select-accordion">
          <div v-if="isMobile && isCategoryExpanded(category.id)" class="model-category-select-children">
            <button
              v-for="option in category.options"
              :key="option.value"
              type="button"
              class="model-category-select-item is-child"
              :class="{ 'is-selected': option.value === modelValue }"
              @click="selectOption(option.value)"
            >
              <span class="model-category-select-item-main">
                <span class="model-category-select-item-label">{{ option.label }}</span>
                <span v-if="option.description" class="model-category-select-item-desc">{{ option.description }}</span>
              </span>
            </button>
          </div>
          </Transition>
        </div>

        <button
          v-for="option in uncategorizedOptions"
          :key="option.value"
          type="button"
          class="model-category-select-item"
          :class="{ 'is-selected': option.value === modelValue }"
          @mouseenter="hoveredCategoryId = null"
          @click="selectOption(option.value)"
        >
          <span class="model-category-select-item-main">
            <span class="model-category-select-item-label">{{ option.label }}</span>
            <span v-if="option.description" class="model-category-select-item-desc">{{ option.description }}</span>
          </span>
        </button>
      </div>
      </Transition>

      <Transition name="model-category-select-slide">
      <div
        v-if="open && !isMobile && hoveredCategory"
        ref="submenuRef"
        class="model-category-select-panel is-submenu"
        :class="popupClassName"
        :style="submenuStyle"
        @mouseenter="hoverCategory(hoveredCategory.id)"
        @mouseleave="scheduleClearHoveredCategory"
      >
        <button
          v-for="option in hoveredCategory.options"
          :key="option.value"
          type="button"
          class="model-category-select-item"
          :class="{ 'is-selected': option.value === modelValue }"
          @click="selectOption(option.value)"
        >
          <span class="model-category-select-item-main">
            <span class="model-category-select-item-label">{{ option.label }}</span>
            <span v-if="option.description" class="model-category-select-item-desc">{{ option.description }}</span>
          </span>
        </button>
      </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped lang="scss">
.model-category-select {
  position: relative;
  width: 100%;
}

.model-category-select-trigger {
  appearance: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  min-height: 40px;
  padding: 0 12px;
  border: 1px solid var(--theme-control-border, #d9d9d9);
  border-radius: 10px;
  background: var(--theme-control-bg, #fff);
  color: var(--theme-title, #1f1f1f);
  font-family: inherit;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;

  &:disabled {
    cursor: not-allowed;
    opacity: 0.65;
  }
}

.model-category-select-value,
.model-category-select-placeholder {
  min-width: 0;
  flex: 1;
}

.model-category-select-value {
  display: flex;
  align-items: center;
}

.model-category-select-label,
.model-category-select-placeholder {
  overflow: hidden;
  font-size: 14px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-category-select-placeholder {
  color: var(--text-muted, #8c8c8c);
  font-weight: 400;
}

.model-category-select-count {
  flex-shrink: 0;
  margin-left: auto;
  color: var(--text-secondary, #8c7458);
  font-size: 12px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
}

.model-category-select-arrow {
  flex-shrink: 0;
  color: var(--text-muted, #8c8c8c);
  font-size: 12px;
  transition: transform 0.16s ease;
}

.is-open .model-category-select-arrow {
  transform: rotate(180deg);
}

.model-category-select-panel {
  position: fixed;
  z-index: 1400;
  max-height: 360px;
  padding: 6px;
  overflow: auto;
  border: 1px solid var(--theme-panel-border);
  border-radius: 14px;
  background: var(--theme-dropdown-bg);
  box-shadow: 0 18px 32px var(--theme-shadow-medium);
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

.model-category-select-panel.is-submenu {
  z-index: 1410;
}

.model-category-select-item {
  appearance: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  min-height: 48px;
  padding: 8px 12px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--theme-title);
  font: inherit;
  font-size: 14px;
  text-align: left;
  cursor: pointer;

  &:hover,
  &.is-active {
    background: var(--theme-dropdown-hover-bg);
  }

  &.is-selected {
    background: var(--theme-dropdown-selected-bg);
    color: var(--theme-dropdown-selected-text);

    .model-category-select-item-label,
    .model-category-select-item-desc,
    .model-category-select-item-arrow {
      color: var(--theme-dropdown-selected-text);
    }

    .model-category-select-item-desc {
      opacity: 0.78;
    }
  }
}

.model-category-select-item-main {
  min-width: 0;
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
}

.model-category-select-item-label {
  overflow: hidden;
  color: var(--theme-title);
  font-family: inherit;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-category-select-item-desc {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-category-select-item-arrow {
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 10px;
}

.model-category-select-item-arrow.is-toggle {
  font-size: 12px;
  transition: transform 0.16s ease;
}

.model-category-select-item-arrow.is-toggle.is-expanded {
  transform: rotate(180deg);
}

.model-category-select-group {
  display: flex;
  flex-direction: column;
}

.model-category-select-children {
  display: flex;
  flex-direction: column;
}

.model-category-select-item.is-child {
  min-height: 44px;
  padding-left: calc(12px + 2em);
}

.model-category-select-panel.is-mobile-accordion {
  max-height: min(360px, calc(100vh - 24px));
}

.is-flat .model-category-select-trigger {
  min-height: 48px;
  padding: 0 15px;
  border: 1px solid var(--theme-control-border-strong);
  border-radius: 16px;
  background: var(--theme-field-bg, var(--theme-control-bg));
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 8px 18px var(--theme-card-shadow);
  transition: border-color var(--motion-duration-fast, 0.16s) var(--motion-ease-soft, ease),
    box-shadow var(--motion-duration-fast, 0.16s) var(--motion-ease-soft, ease),
    transform var(--motion-duration-fast, 0.16s) var(--motion-ease-soft, ease),
    background var(--motion-duration-fast, 0.16s) var(--motion-ease-soft, ease);

  &:hover {
    border-color: var(--theme-border-strong);
    background: var(--theme-field-hover-bg, var(--theme-control-hover-bg));
    transform: translateY(-1px);
    box-shadow:
      inset 0 1px 0 var(--theme-panel-inset),
      0 12px 22px var(--theme-card-shadow-strong);
  }
}

.is-flat.is-open .model-category-select-trigger {
  border-color: var(--theme-border-accent);
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 0 0 3px var(--theme-focus-ring),
    0 12px 22px var(--theme-card-shadow-strong);
}

.is-flat .model-category-select-label {
  font-size: 14px;
  font-weight: 700;
  color: var(--theme-title);
}

.is-flat .model-category-select-count {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.model-category-select-slide-enter-active,
.model-category-select-slide-leave-active {
  transform-origin: 50% 0;
  transition:
    opacity var(--motion-duration-reveal-fast, 0.36s) var(--motion-ease-enter, cubic-bezier(0.24, 0.72, 0.32, 1)),
    transform var(--motion-duration-reveal-fast, 0.36s) var(--motion-ease-enter, cubic-bezier(0.24, 0.72, 0.32, 1));
}

.model-category-select-slide-enter-active.is-open-up,
.model-category-select-slide-leave-active.is-open-up {
  transform-origin: 50% 100%;
}

.model-category-select-slide-enter-from,
.model-category-select-slide-leave-to {
  opacity: 0;
  transform: translate3d(0, -8px, 0) scaleY(0.92);
}

.model-category-select-slide-enter-from.is-open-up,
.model-category-select-slide-leave-to.is-open-up {
  transform: translate3d(0, 8px, 0) scaleY(0.92);
}

.model-category-select-accordion-enter-active,
.model-category-select-accordion-leave-active {
  overflow: hidden;
  transition:
    opacity var(--motion-duration-fast, 0.2s) var(--motion-ease-enter, cubic-bezier(0.24, 0.72, 0.32, 1)),
    transform var(--motion-duration-fast, 0.2s) var(--motion-ease-enter, cubic-bezier(0.24, 0.72, 0.32, 1));
}

.model-category-select-accordion-enter-from,
.model-category-select-accordion-leave-to {
  opacity: 0;
  transform: translate3d(0, -6px, 0);
}
</style>
