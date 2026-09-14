<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { message } from "ant-design-vue";
import { CheckCircleOutlined, ReloadOutlined, ThunderboltOutlined } from "@ant-design/icons-vue";

import { getPromptOptimizeStyles } from "@/api/config";
import UserSuggestionDialog from "@/components/feedback/UserSuggestionDialog.vue";
import type { PublicPromptOptimizeStyle } from "@/types";

const props = defineProps<{
  open: boolean;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  confirm: [style: PublicPromptOptimizeStyle];
}>();

const loading = ref(false);
const styles = ref<PublicPromptOptimizeStyle[]>([]);
const stylesLoaded = ref(false);
const selectedStyleId = ref<number | null>(null);
const suggestionDialogOpen = ref(false);

const selectedStyle = computed(() => (
  styles.value.find((item) => item.id === selectedStyleId.value) || null
));

watch(() => props.open, (open) => {
  if (!open) return;
  if (stylesLoaded.value && styles.value.length) {
    applyDefaultSelection(styles.value);
    return;
  }
  void loadStyles();
}, { immediate: true });

function closeDialog() {
  emit("update:open", false);
}

function applyDefaultSelection(items: PublicPromptOptimizeStyle[]) {
  const defaultStyle = items.find((item) => item.is_default) || items[0] || null;
  selectedStyleId.value = defaultStyle?.id ?? null;
}

async function loadStyles() {
  loading.value = true;
  try {
    const items = await getPromptOptimizeStyles();
    styles.value = items;
    stylesLoaded.value = true;
    applyDefaultSelection(items);
  } catch (err: any) {
    styles.value = [];
    stylesLoaded.value = false;
    selectedStyleId.value = null;
    message.error(err?.response?.data?.detail || "获取提示词优化风格失败");
  } finally {
    loading.value = false;
  }
}

function handleConfirm() {
  if (!selectedStyle.value) {
    message.warning("请先选择一个提示词优化风格");
    return;
  }
  emit("confirm", selectedStyle.value);
}

function openSuggestionDialog() {
  suggestionDialogOpen.value = true;
}
</script>

<template>
  <a-modal
    :open="open"
    title="选择提示词优化风格"
    :confirm-loading="loading"
    centered
    :width="680"
    @update:open="(value: boolean) => emit('update:open', value)"
    @cancel="closeDialog"
  >
    <div class="style-dialog">
      <div class="style-dialog-intro">
        <ThunderboltOutlined />
        <span>选择一套系统提示词风格后，再对当前输入框中的提示词进行优化。</span>
      </div>

      <div v-if="loading" class="style-loading-wrap">
        <a-spin tip="加载风格中..." />
      </div>

      <div v-else-if="!styles.length" class="style-empty-wrap">
        <a-empty description="当前没有可用的提示词优化风格" />
        <a-button class="warm-secondary-btn" @click="loadStyles">
          <template #icon><ReloadOutlined /></template>
          重新加载
        </a-button>
      </div>

      <div v-else class="style-list">
        <button
          v-for="item in styles"
          :key="item.id"
          type="button"
          class="style-card"
          :class="{ 'style-card-active': selectedStyleId === item.id }"
          @click="selectedStyleId = item.id"
        >
          <div class="style-card-head">
            <div class="style-card-title">
              {{ item.name }}
              <a-tag v-if="item.is_default" class="style-default-tag">默认</a-tag>
            </div>
            <CheckCircleOutlined v-if="selectedStyleId === item.id" class="style-card-check" />
          </div>
          <div class="style-card-desc">{{ item.description || "未填写风格说明" }}</div>
        </button>
      </div>

    </div>

    <template #footer>
      <div class="style-dialog-footer">
        <a-button class="style-add-request-btn" @click="openSuggestionDialog">
          我要加风格
        </a-button>
        <div class="style-dialog-footer-actions">
          <a-button @click="closeDialog">取消</a-button>
          <a-button type="primary" :loading="loading" :disabled="!styles.length" @click="handleConfirm">
            确认优化
          </a-button>
        </div>
      </div>
    </template>
  </a-modal>

  <UserSuggestionDialog v-model:open="suggestionDialogOpen" />
</template>

<style scoped lang="scss">
.style-dialog {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.style-dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.style-dialog-footer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.style-add-request-btn {
  color: var(--theme-accent-text, #8a5a16);
  border-color: var(--theme-panel-border-strong, #e2c28a);
  background: var(--theme-panel-bg-soft, #fff8ee);
}

.style-add-request-btn:hover,
.style-add-request-btn:focus {
  color: var(--theme-accent-text-hover, #6f4610) !important;
  border-color: var(--theme-accent) !important;
  background: var(--theme-control-hover-bg, #fff1d9) !important;
}

.style-dialog-intro {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--theme-muted-text);
  font-size: 13px;
}

.style-loading-wrap,
.style-empty-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 28px 0 16px;
}

.style-loading-wrap :deep(.ant-spin) {
  color: var(--theme-accent);
}

.style-loading-wrap :deep(.ant-spin-dot-item) {
  background-color: var(--theme-accent);
}

.style-loading-wrap :deep(.ant-spin-text) {
  color: var(--theme-muted-text, #8a6a3d);
}

.style-empty-wrap {
  gap: 12px;
}

.style-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.style-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 72px;
  padding: 10px 12px;
  text-align: left;
  border: 1px solid var(--theme-panel-border);
  border-radius: 12px;
  background: var(--theme-panel-bg);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease, background 0.2s ease;
}

.style-card:hover {
  border-color: var(--theme-accent);
  transform: translateY(-1px);
}

.style-card-active {
  border: 2px solid var(--theme-accent);
  padding: 9px 11px;
  background: var(--theme-control-hover-bg);
  box-shadow: none;
}

.style-card-active .style-card-title {
  color: var(--theme-accent-text);
}

.style-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.style-card-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  color: var(--theme-text-primary);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.3;
}

.style-card-check {
  color: var(--theme-icon);
  font-size: 16px;
}

.style-default-tag {
  margin-inline-end: 0;
  color: var(--theme-accent-text) !important;
  background: var(--theme-panel-bg-strong) !important;
  border-color: var(--theme-panel-border-strong) !important;
}

.style-card-desc {
  display: -webkit-box;
  overflow: hidden;
  color: var(--theme-muted-text);
  font-size: 12px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

@media (max-width: 720px) {
  .style-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 480px) {
  .style-list {
    grid-template-columns: 1fr;
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
