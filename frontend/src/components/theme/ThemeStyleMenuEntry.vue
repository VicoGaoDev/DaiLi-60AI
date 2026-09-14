<script setup lang="ts">
import { ref } from "vue";
import { message } from "ant-design-vue";
import { CheckOutlined, RightOutlined } from "@ant-design/icons-vue";
import { appThemes, getAppThemeGroups, type AppThemeName } from "@/config/theme";
import { setAppTheme } from "@/lib/theme";

const props = defineProps<{
  currentTheme: AppThemeName;
}>();

const themeMenuGroups = getAppThemeGroups();
const themeDropdownAlign = ref({
  offset: [0, 0] as [number, number],
  overflow: { adjustX: false, adjustY: false },
});

function applyTheme(theme: AppThemeName) {
  if (theme === props.currentTheme) return;
  setAppTheme(theme);
  message.success(`已切换为${appThemes[theme].label}`);
}

function getThemePopupContainer(trigger: HTMLElement) {
  return trigger.closest(".ant-dropdown") || document.body;
}

function updateThemeDropdownAlign(event: MouseEvent) {
  const trigger = event.currentTarget as HTMLElement;
  const menu = trigger.closest(".ant-dropdown-menu");
  if (!menu) return;
  const extra = Math.round(menu.getBoundingClientRect().right - trigger.getBoundingClientRect().right);
  themeDropdownAlign.value = {
    offset: [Math.max(0, extra), 0],
    overflow: { adjustX: false, adjustY: false },
  };
}
</script>

<template>
  <a-dropdown
    :trigger="['hover']"
    placement="rightBottom"
    :auto-adjust-overflow="false"
    :mouse-enter-delay="0.05"
    :align="themeDropdownAlign"
    :get-popup-container="getThemePopupContainer"
    overlay-class-name="theme-style-overlay"
  >
    <div class="theme-style-entry" @click.stop @mouseenter="updateThemeDropdownAlign">
      <span>主题风格</span>
      <RightOutlined class="theme-style-entry-arrow" />
    </div>
    <template #overlay>
      <div class="theme-style-panel" @click.stop>
        <div
          v-for="group in themeMenuGroups"
          :key="group.key"
          class="theme-style-group"
        >
          <div class="theme-style-group-label">{{ group.label }}</div>
          <button
            v-for="option in group.themes"
            :key="option.key"
            type="button"
            class="theme-style-option"
            :class="{ 'is-active': currentTheme === option.key }"
            @click="applyTheme(option.key)"
          >
            <a-tooltip
              placement="right"
              :mouse-enter-delay="0.05"
              overlay-class-name="theme-swatch-tooltip"
            >
              <template #title>
                <div class="theme-menu-swatches">
                  <div
                    v-for="swatch in option.palette"
                    :key="swatch.label"
                    class="theme-menu-swatch"
                  >
                    <span class="theme-menu-swatch-chip" :style="{ background: swatch.color }" />
                    <span>{{ swatch.label }}</span>
                  </div>
                </div>
              </template>
              <span class="theme-menu-item-title">
                <span>{{ option.label }}</span>
                <CheckOutlined v-if="currentTheme === option.key" class="theme-menu-check" />
              </span>
            </a-tooltip>
          </button>
        </div>
      </div>
    </template>
  </a-dropdown>
</template>

<style scoped lang="scss">
.theme-style-entry {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  width: 100%;
  height: 100%;
  min-width: max-content;
  min-height: 100%;
  padding: 0;
  color: inherit;
  font-weight: inherit;
  line-height: inherit;
  white-space: nowrap;
  cursor: pointer;
}

.theme-style-entry > span {
  flex-shrink: 0;
  white-space: nowrap;
  word-break: keep-all;
}

.theme-style-entry-arrow {
  position: absolute;
  font-size: 12px !important;
}

.theme-style-panel {
  min-width: 176px;
  padding: 10px;
  overflow: visible;
}

.theme-style-group + .theme-style-group {
  margin-top: 6px;
}

.theme-style-group-label {
  padding: 6px 12px 4px;
  color: var(--theme-text-muted);
  font-size: 12px;
  font-weight: 700;
}

.theme-style-option {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 40px;
  padding: 8px 12px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: var(--theme-title);
  font-weight: 700;
  text-align: left;
  cursor: pointer;
}

.theme-style-option:hover,
.theme-style-option.is-active {
  background: var(--theme-control-hover-bg);
  color: var(--theme-accent-text);
}

.theme-menu-item-title {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
}

.theme-menu-check {
  color: var(--theme-accent);
  font-size: 14px;
}
</style>

<style lang="scss">
.theme-style-overlay {
  top: auto !important;
  right: auto !important;
  bottom: 0 !important;
  left: 100% !important;
  z-index: 1400 !important;
  overflow: visible;
}

.theme-style-overlay .theme-style-panel {
  min-width: 176px;
  max-height: none;
  padding: 10px;
  overflow: visible;
  border-radius: 18px;
  border: 1px solid var(--theme-panel-border);
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-soft));
  box-shadow: 0 16px 28px var(--theme-shadow-soft);
}
</style>
