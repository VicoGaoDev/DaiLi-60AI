<script setup lang="ts">
import { onMounted, ref } from "vue";
import { message } from "ant-design-vue";
import { BgColorsOutlined, SettingOutlined } from "@ant-design/icons-vue";
import { appThemes, getAppThemeGroups, type AppThemeName } from "@/config/theme";
import { getCurrentTheme, setAppTheme } from "@/lib/theme";

const currentTheme = ref<AppThemeName>(getCurrentTheme());
const themeGroups = getAppThemeGroups();

onMounted(() => {
  currentTheme.value = getCurrentTheme();
});

function applyThemeSelection() {
  setAppTheme(currentTheme.value);
  message.success(`已切换为${appThemes[currentTheme.value].label}`);
}
</script>

<template>
  <div class="settings-page warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <SettingOutlined />
        </div>
        <div>
          <div class="warm-page-title">设置</div>
          <div class="warm-page-desc">在这里调整当前浏览器主题。主题仅保存在本地浏览器中。</div>
        </div>
      </div>
    </div>

    <div class="theme-card warm-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <div class="theme-section theme-section-standalone">
        <div class="theme-section-head">
          <div>
            <div class="settings-label">前端主题风格</div>
            <div class="theme-tip">仅作用于当前浏览器，本地保存。刷新或重新打开后会继续使用所选主题。</div>
          </div>
          <BgColorsOutlined class="theme-section-icon" />
        </div>

        <div
          v-for="group in themeGroups"
          :key="group.key"
          class="theme-group"
        >
          <div class="theme-group-label">{{ group.label }}</div>
          <div
            class="theme-option-grid"
            :class="{ 'theme-option-grid-dark': group.key === 'dark' }"
          >
            <button
              v-for="option in group.themes"
              :key="option.key"
              type="button"
              class="theme-option-card"
              :class="{ 'is-active': currentTheme === option.key }"
              @click="currentTheme = option.key"
            >
              <div class="theme-option-name">{{ option.label }}</div>
              <div class="theme-option-swatches">
                <div
                  v-for="swatch in option.palette"
                  :key="swatch.label"
                  class="theme-swatch"
                >
                  <span
                    class="theme-swatch-chip"
                    :style="{ background: swatch.color }"
                    :title="swatch.label"
                  />
                  <span class="theme-swatch-label">{{ swatch.label }}</span>
                </div>
              </div>
            </button>
          </div>
        </div>

        <div class="theme-actions">
          <a-button type="primary" class="warm-primary-btn" @click="applyThemeSelection">
            应用主题
          </a-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.settings-page {
  max-width: 920px;
}

.theme-card {
  padding: 32px;
}

.settings-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--theme-subtitle);
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.theme-section {
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding: 22px 24px;
  border-radius: 22px;
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-soft));
  border: 1px solid var(--theme-panel-border);
}

.theme-section-standalone {
  margin-top: 0;
}

.theme-section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.theme-section-icon {
  font-size: 22px;
  color: var(--theme-accent-text);
}

.theme-tip {
  color: var(--text-secondary);
  line-height: 1.6;
  font-size: 13px;
}

.theme-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.theme-group-label {
  color: var(--theme-title);
  font-size: 13px;
  font-weight: 700;
}

.theme-option-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.theme-option-grid-dark {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.theme-option-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px 14px 12px;
  text-align: left;
  border: 1px solid var(--theme-panel-border);
  border-radius: 16px;
  background: var(--theme-panel-bg);
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease, background 0.2s ease;
}

.theme-option-card:hover {
  border-color: var(--theme-accent);
  background: var(--theme-control-hover-bg);
  transform: translateY(-1px);
}

.theme-option-card.is-active {
  border: 2px solid var(--theme-accent);
  padding: 13px 13px 11px;
  background: var(--theme-control-hover-bg);
  box-shadow: 0 8px 20px var(--theme-shadow-soft);
}

.theme-option-name {
  color: var(--theme-title);
  font-size: 14px;
  font-weight: 700;
}

.theme-option-card.is-active .theme-option-name {
  color: var(--theme-accent-text);
}

.theme-option-swatches {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.theme-swatch {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.theme-swatch-chip {
  display: block;
  width: 100%;
  height: 28px;
  border: 1px solid var(--theme-panel-border-strong);
  border-radius: 8px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.24);
}

.theme-swatch-label {
  overflow: hidden;
  max-width: 100%;
  color: var(--theme-text-muted);
  font-size: 11px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.theme-actions {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 720px) {
  .theme-option-grid,
  .theme-option-grid-dark {
    grid-template-columns: 1fr;
  }
}
</style>
