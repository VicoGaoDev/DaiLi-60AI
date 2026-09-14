<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { CheckSquareOutlined, CopyOutlined, DeleteOutlined, EditOutlined, FolderAddOutlined, FolderOpenOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons-vue";
import { Modal, message } from "ant-design-vue";

import { useUserPrompts, type UserPromptCategoryFilter } from "@/composables/useUserPrompts";
import type { UserPrompt } from "@/types";

const props = withDefaults(defineProps<{
  open: boolean;
  title?: string;
}>(), {
  title: "我的提示词",
});

const emit = defineEmits<{
  "update:open": [value: boolean];
  "select-prompt": [prompt: UserPrompt];
}>();

const {
  categories,
  uncategorizedCount,
  prompts,
  loading,
  saving,
  refresh,
  createCategory,
  renameCategory,
  removeCategory,
  createPrompt,
  editPrompt,
  removePrompt,
  removePrompts,
  movePrompts,
} = useUserPrompts();

const keyword = ref("");
const activeCategory = ref<UserPromptCategoryFilter>("all");
const promptDialogOpen = ref(false);
const promptDialogMode = ref<"create" | "edit">("create");
const promptDialogSaving = ref(false);
const editingPrompt = ref<UserPrompt | null>(null);
const promptTitle = ref("");
const promptContent = ref("");
const promptCategoryValue = ref<number | "uncategorized">("uncategorized");
const categoryDialogOpen = ref(false);
const categoryDialogMode = ref<"create" | "rename">("create");
const categoryDialogSaving = ref(false);
const categoryDialogValue = ref("");
const moveCategoryDialogOpen = ref(false);
const moveCategoryDialogSaving = ref(false);
const moveCategoryDialogValue = ref<number | "uncategorized">("uncategorized");
const batchMode = ref(false);
const batchDeleting = ref(false);
const selectedPromptIds = ref<number[]>([]);

const libraryTotal = computed(() => (
  uncategorizedCount.value
  + categories.value.reduce((sum, item) => sum + Number(item.prompt_count || 0), 0)
));

const categoryTabs = computed(() => [
  { key: "all" as const, label: "全部", count: libraryTotal.value },
  { key: "uncategorized" as const, label: "未分类", count: uncategorizedCount.value },
  ...categories.value.map((item) => ({
    key: item.id as UserPromptCategoryFilter,
    label: item.name,
    count: item.prompt_count,
  })),
]);

const allVisiblePromptIds = computed(() => prompts.value.map((item) => item.id));
const selectedCount = computed(() => selectedPromptIds.value.length);
const allVisibleSelected = computed(() => (
  allVisiblePromptIds.value.length > 0
  && allVisiblePromptIds.value.every((id) => selectedPromptIds.value.includes(id))
));

watch(() => props.open, (open) => {
  if (!open) return;
  void refreshCurrent().catch((err: any) => {
    message.error(err?.response?.data?.detail || "获取我的提示词失败");
  });
}, { immediate: true });

watch(() => props.open, (open) => {
  if (open) return;
  batchMode.value = false;
  selectedPromptIds.value = [];
});

watch(prompts, (nextPrompts) => {
  const visibleIds = new Set(nextPrompts.map((item) => item.id));
  selectedPromptIds.value = selectedPromptIds.value.filter((id) => visibleIds.has(id));
  if (!nextPrompts.length) {
    batchMode.value = false;
  }
});

function getBodyPopupContainer() {
  return document.body;
}

function closeDialog() {
  emit("update:open", false);
}

async function refreshCurrent() {
  await refresh({
    category: activeCategory.value,
    keyword: keyword.value,
    limit: 120,
  });
}

async function changeCategory(category: UserPromptCategoryFilter) {
  activeCategory.value = category;
  await refreshCurrent();
}

async function handleSearch() {
  await refreshCurrent();
}

function toggleBatchMode() {
  batchMode.value = !batchMode.value;
  if (!batchMode.value) {
    selectedPromptIds.value = [];
  }
}

function handleSelectPromptChange(promptId: number, checked: boolean) {
  if (checked) {
    if (!selectedPromptIds.value.includes(promptId)) {
      selectedPromptIds.value = [...selectedPromptIds.value, promptId];
    }
    return;
  }
  selectedPromptIds.value = selectedPromptIds.value.filter((id) => id !== promptId);
}

function toggleSelectAllPrompts() {
  if (allVisibleSelected.value) {
    selectedPromptIds.value = [];
    return;
  }
  selectedPromptIds.value = [...allVisiblePromptIds.value];
}

function clearPromptSelection() {
  selectedPromptIds.value = [];
}

function togglePromptSelection(promptId: number) {
  handleSelectPromptChange(promptId, !selectedPromptIds.value.includes(promptId));
}

function handlePromptCardClick(promptId: number) {
  if (!batchMode.value) return;
  togglePromptSelection(promptId);
}

function openCreatePromptDialog() {
  editingPrompt.value = null;
  promptDialogMode.value = "create";
  promptTitle.value = "";
  promptContent.value = "";
  promptCategoryValue.value = typeof activeCategory.value === "number" ? activeCategory.value : "uncategorized";
  promptDialogOpen.value = true;
}

function openEditPromptDialog(prompt: UserPrompt) {
  editingPrompt.value = prompt;
  promptDialogMode.value = "edit";
  promptTitle.value = prompt.title || "";
  promptContent.value = prompt.content || "";
  promptCategoryValue.value = typeof prompt.category_id === "number" ? prompt.category_id : "uncategorized";
  promptDialogOpen.value = true;
}

async function submitPromptDialog() {
  const title = promptTitle.value.trim();
  const content = promptContent.value.trim();
  if (!title) {
    message.warning("请输入标题");
    return;
  }
  if (!content) {
    message.warning("请输入提示词内容");
    return;
  }
  promptDialogSaving.value = true;
  try {
    const payload = {
      categoryId: promptCategoryValue.value === "uncategorized" ? null : promptCategoryValue.value,
      title,
      content,
    };
    if (promptDialogMode.value === "create") {
      await createPrompt(payload, {
        category: activeCategory.value,
        keyword: keyword.value,
        limit: 120,
      });
      message.success("提示词已创建");
    } else if (editingPrompt.value) {
      await editPrompt(editingPrompt.value.id, payload, {
        category: activeCategory.value,
        keyword: keyword.value,
        limit: 120,
      });
      message.success("提示词已更新");
    }
    promptDialogOpen.value = false;
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "保存提示词失败");
  } finally {
    promptDialogSaving.value = false;
  }
}

function handleDeletePrompt(prompt: UserPrompt) {
  Modal.confirm({
    title: "删除提示词",
    content: "删除后不可恢复。",
    okText: "删除",
    cancelText: "取消",
    async onOk() {
      try {
        await removePrompt(prompt.id, {
          category: activeCategory.value,
          keyword: keyword.value,
          limit: 120,
        });
        message.success("提示词已删除");
      } catch (err: any) {
        message.error(err?.response?.data?.detail || "删除提示词失败");
      }
    },
  });
}

function handleBatchDeletePrompts() {
  if (!selectedPromptIds.value.length) {
    message.warning("请先选择要删除的提示词");
    return;
  }
  const ids = [...selectedPromptIds.value];
  Modal.confirm({
    title: "批量删除提示词",
    content: `确定删除已选中的 ${ids.length} 条提示词吗？删除后不可恢复。`,
    okText: "删除",
    cancelText: "取消",
    async onOk() {
      batchDeleting.value = true;
      try {
        await removePrompts(ids, {
          category: activeCategory.value,
          keyword: keyword.value,
          limit: 120,
        });
        selectedPromptIds.value = [];
        message.success(`已删除 ${ids.length} 条提示词`);
      } catch (err: any) {
        message.error(err?.response?.data?.detail || "批量删除提示词失败");
      } finally {
        batchDeleting.value = false;
      }
    },
  });
}

function openBatchMoveCategoryDialog() {
  if (!selectedPromptIds.value.length) {
    message.warning("请先选择要修改分类的提示词");
    return;
  }
  moveCategoryDialogValue.value = typeof activeCategory.value === "number" ? activeCategory.value : "uncategorized";
  moveCategoryDialogOpen.value = true;
}

async function submitBatchMoveCategoryDialog() {
  const ids = [...selectedPromptIds.value];
  if (!ids.length) return;
  const nextCategoryId = moveCategoryDialogValue.value === "uncategorized" ? null : moveCategoryDialogValue.value;
  moveCategoryDialogSaving.value = true;
  try {
    await movePrompts(ids, nextCategoryId, {
      category: activeCategory.value,
      keyword: keyword.value,
      limit: 120,
    });
    moveCategoryDialogOpen.value = false;
    selectedPromptIds.value = [];
    message.success(`已更新 ${ids.length} 条提示词的分类`);
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "批量修改分类失败");
  } finally {
    moveCategoryDialogSaving.value = false;
  }
}

function handleUsePrompt(prompt: UserPrompt) {
  emit("select-prompt", prompt);
  emit("update:open", false);
}

async function copyPromptContent(prompt: UserPrompt) {
  const content = (prompt.content || "").trim();
  if (!content) {
    message.warning("该提示词内容为空");
    return;
  }
  try {
    await navigator.clipboard.writeText(content);
    message.success("提示词已复制");
  } catch {
    message.error("复制失败，请手动复制");
  }
}

function openCreateCategoryDialog() {
  categoryDialogMode.value = "create";
  categoryDialogValue.value = "";
  categoryDialogOpen.value = true;
}

function openRenameCategoryDialog() {
  if (typeof activeCategory.value !== "number") return;
  const current = categories.value.find((item) => item.id === activeCategory.value);
  categoryDialogMode.value = "rename";
  categoryDialogValue.value = current?.name || "";
  categoryDialogOpen.value = true;
}

async function submitCategoryDialog() {
  const name = categoryDialogValue.value.trim();
  if (!name) {
    message.warning("请输入分类名称");
    return;
  }
  categoryDialogSaving.value = true;
  try {
    if (categoryDialogMode.value === "create") {
      await createCategory(name);
      message.success("分类已创建");
    } else if (typeof activeCategory.value === "number") {
      await renameCategory(activeCategory.value, name);
      message.success("分类已更新");
    }
    categoryDialogOpen.value = false;
    await refreshCurrent();
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "保存分类失败");
  } finally {
    categoryDialogSaving.value = false;
  }
}

function handleDeleteCategory() {
  if (typeof activeCategory.value !== "number") return;
  const categoryId = activeCategory.value;
  Modal.confirm({
    title: "删除分类",
    content: "删除分类不会删除提示词，但分类下仍有提示词时不可删除。",
    okText: "删除",
    cancelText: "取消",
    async onOk() {
      try {
        await removeCategory(categoryId);
        activeCategory.value = "all";
        await refreshCurrent();
        message.success("分类已删除");
      } catch (err: any) {
        message.error(err?.response?.data?.detail || "删除分类失败");
      }
    },
  });
}
</script>

<template>
  <a-modal
    :open="open"
    :footer="null"
    :width="1120"
    centered
    destroy-on-close
    wrap-class-name="user-prompt-library-modal-wrap"
    @update:open="emit('update:open', $event)"
    @cancel="closeDialog"
  >
    <template #title>
      <div class="prompt-modal-header">
        <div class="prompt-modal-header-left">
          <div class="prompt-modal-header-title">{{ title }}</div>
          <div class="prompt-count-pill">提示词 {{ libraryTotal }}</div>
        </div>
        <div class="prompt-modal-header-right">
          <div class="prompt-search">
            <a-input
              v-model:value="keyword"
              allow-clear
              placeholder="搜索标题或提示词内容"
              @press-enter="handleSearch"
            />
            <button type="button" class="prompt-search-btn" aria-label="搜索提示词" @click="handleSearch">
              <SearchOutlined />
            </button>
          </div>
        </div>
        <div class="prompt-toolbar-right">
          <a-button type="text" :class="{ 'prompt-batch-toggle-active': batchMode }" @click="toggleBatchMode">
            <template #icon><CheckSquareOutlined /></template>
            {{ batchMode ? "退出批量" : "批量管理" }}
          </a-button>
          <a-button :loading="loading" @click="refreshCurrent">
            <template #icon><ReloadOutlined /></template>
            刷新
          </a-button>
          <a-button type="primary" :loading="saving || promptDialogSaving" @click="openCreatePromptDialog">
            新建提示词
          </a-button>
        </div>
      </div>
    </template>
    <div class="prompt-picker">
      <aside class="prompt-sidebar">
        <div class="prompt-sidebar-header">
          <div class="prompt-sidebar-title">分类</div>
          <div class="prompt-sidebar-actions">
            <button type="button" class="prompt-side-icon-btn" title="新建分类" @click="openCreateCategoryDialog">
              <FolderAddOutlined />
            </button>
            <button
              v-if="typeof activeCategory === 'number'"
              type="button"
              class="prompt-side-icon-btn"
              title="重命名分类"
              @click="openRenameCategoryDialog"
            >
              <FolderOpenOutlined />
            </button>
            <button
              v-if="typeof activeCategory === 'number'"
              type="button"
              class="prompt-side-icon-btn danger"
              title="删除分类"
              @click="handleDeleteCategory"
            >
              <DeleteOutlined />
            </button>
          </div>
        </div>
        <div class="prompt-category-list">
          <button
            v-for="item in categoryTabs"
            :key="String(item.key)"
            type="button"
            class="prompt-category-btn"
            :class="{ active: activeCategory === item.key }"
            @click="changeCategory(item.key)"
          >
            <span>{{ item.label }}</span>
            <span>{{ item.count }}</span>
          </button>
        </div>
      </aside>

      <section class="prompt-main">
        <div class="prompt-content-shell">
          <div v-if="batchMode && prompts.length" class="prompt-batch-bar">
            <div class="prompt-batch-summary">
              已选 {{ selectedCount }} 项 / 当前 {{ allVisiblePromptIds.length }} 项
            </div>
            <div class="prompt-batch-actions">
              <a-button size="small" @click="toggleSelectAllPrompts">
                {{ allVisibleSelected ? "取消全选" : "全选" }}
              </a-button>
              <a-button size="small" :disabled="!selectedCount" @click="clearPromptSelection">
                清空
              </a-button>
              <a-button size="small" :disabled="!selectedCount" @click="openBatchMoveCategoryDialog">
                批量修改分类
              </a-button>
              <a-button size="small" danger :loading="batchDeleting" :disabled="!selectedCount" @click="handleBatchDeletePrompts">
                批量删除
              </a-button>
            </div>
          </div>
          <div v-if="loading" class="prompt-loading-mask">
            <a-spin />
          </div>
          <div class="prompt-content">
            <div v-if="prompts.length" class="prompt-list">
              <div
                v-for="item in prompts"
                :key="item.id"
                class="prompt-card"
                :class="{
                  'prompt-card-selected': selectedPromptIds.includes(item.id),
                  'prompt-card-batch-selectable': batchMode,
                }"
                @click="handlePromptCardClick(item.id)"
              >
                <div v-if="batchMode" class="prompt-card-check" @click.stop>
                  <a-checkbox
                    :checked="selectedPromptIds.includes(item.id)"
                    @update:checked="handleSelectPromptChange(item.id, $event)"
                  />
                </div>
                <div class="prompt-card-header">
                  <div class="prompt-card-title">{{ item.title }}</div>
                  <div v-if="!batchMode" class="prompt-card-actions">
                    <a-button type="link" size="small" class="prompt-card-action-btn" @click="handleUsePrompt(item)">使用</a-button>
                    <a-button type="link" size="small" class="prompt-card-icon-btn" @click="openEditPromptDialog(item)">
                      <template #icon><EditOutlined /></template>
                    </a-button>
                    <a-button type="link" size="small" class="prompt-card-icon-btn" title="复制提示词" @click="copyPromptContent(item)">
                      <template #icon><CopyOutlined /></template>
                    </a-button>
                    <a-button type="link" size="small" danger @click="handleDeletePrompt(item)">
                      <template #icon><DeleteOutlined /></template>
                    </a-button>
                  </div>
                </div>
                <div class="prompt-card-meta-row">
                  <div class="prompt-card-category">{{ item.category_name || "未分类" }}</div>
                  <div class="prompt-card-date">{{ item.updated_at ? item.updated_at.slice(0, 10) : "-" }}</div>
                </div>
                <div class="prompt-card-content">{{ item.content }}</div>
              </div>
            </div>
            <div v-else class="prompt-empty">
              <div class="prompt-empty-title">暂无提示词</div>
              <div class="prompt-empty-desc">新建后可在这里统一管理，并一键回填到当前编辑区。</div>
            </div>
          </div>
        </div>
      </section>
    </div>

    <a-modal
      v-model:open="promptDialogOpen"
      :title="promptDialogMode === 'create' ? '新建提示词' : '编辑提示词'"
      :confirm-loading="promptDialogSaving"
      ok-text="保存"
      cancel-text="取消"
      @ok="submitPromptDialog"
    >
      <div class="user-prompt-form">
        <div class="user-prompt-form-item">
          <label>标题</label>
          <a-input v-model:value="promptTitle" :maxlength="255" placeholder="例如：电影感人物海报" />
        </div>
        <div class="user-prompt-form-item">
          <label>分类</label>
          <a-select v-model:value="promptCategoryValue" :get-popup-container="getBodyPopupContainer">
            <a-select-option value="uncategorized">未分类</a-select-option>
            <a-select-option v-for="item in categories" :key="item.id" :value="item.id">{{ item.name }}</a-select-option>
          </a-select>
        </div>
        <div class="user-prompt-form-item">
          <label>提示词内容</label>
          <a-textarea v-model:value="promptContent" :rows="8" :maxlength="10000" show-count placeholder="请输入提示词内容" />
        </div>
      </div>
    </a-modal>

    <a-modal
      v-model:open="categoryDialogOpen"
      :title="categoryDialogMode === 'create' ? '新建分类' : '重命名分类'"
      :confirm-loading="categoryDialogSaving"
      ok-text="保存"
      cancel-text="取消"
      @ok="submitCategoryDialog"
    >
      <a-input v-model:value="categoryDialogValue" :maxlength="100" placeholder="请输入分类名称" />
    </a-modal>

    <a-modal
      v-model:open="moveCategoryDialogOpen"
      title="批量修改分类"
      :confirm-loading="moveCategoryDialogSaving"
      ok-text="保存"
      cancel-text="取消"
      @ok="submitBatchMoveCategoryDialog"
    >
      <div class="user-prompt-form">
        <div class="user-prompt-form-item">
          <label>将已选 {{ selectedCount }} 项移动到</label>
          <a-select v-model:value="moveCategoryDialogValue" :get-popup-container="getBodyPopupContainer">
            <a-select-option value="uncategorized">未分类</a-select-option>
            <a-select-option v-for="item in categories" :key="item.id" :value="item.id">{{ item.name }}</a-select-option>
          </a-select>
        </div>
      </div>
    </a-modal>
  </a-modal>
</template>

<style scoped lang="scss">
.prompt-picker {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 18px;
  height: 620px;
  max-height: calc(100vh - 220px);
  min-height: 0;
}

.prompt-sidebar {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--theme-panel-border);
  border-radius: 18px;
  padding: 14px;
  background: var(--theme-panel-bg-soft);
  min-height: 0;
}

.prompt-sidebar-header,
.prompt-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.prompt-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-right: 16px;
}

.prompt-modal-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.prompt-modal-header-title {
  flex-shrink: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.prompt-modal-header-right {
  display: flex;
  align-items: center;
  min-width: 0;
  flex: 1;
  justify-content: flex-end;
}

.prompt-sidebar-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--theme-title);
}

.prompt-sidebar-actions,
.prompt-toolbar-right,
.prompt-toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.prompt-side-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 10px;
  border: 1px solid var(--theme-control-border);
  background: var(--theme-control-bg);
  color: var(--theme-accent-text);
  cursor: pointer;
}

.prompt-side-icon-btn.danger {
  color: #d25959;
}

.prompt-category-list {
  margin-top: 14px;
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: var(--theme-border-strong) var(--theme-panel-bg-muted);
}

.prompt-category-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid transparent;
  background: var(--theme-control-bg);
  color: var(--theme-title);
  cursor: pointer;
}

.prompt-category-btn.active {
  border-color: var(--theme-accent);
  background: var(--theme-control-hover-bg);
  color: var(--theme-accent-text);
}

.prompt-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.prompt-content-shell {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  margin-top: 0;
  min-height: 0;
  overflow: hidden;
}

.prompt-batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  padding: 10px 14px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 14px;
  background: var(--theme-panel-bg-strong);
}

.prompt-batch-summary {
  color: var(--theme-accent-text);
  font-size: 13px;
  font-weight: 600;
}

.prompt-batch-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.prompt-loading-mask {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: grid;
  place-items: center;
  border-radius: 18px;
  background: color-mix(in srgb, var(--theme-page-base) 48%, transparent);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  pointer-events: none;
}

.prompt-content {
  width: 100%;
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
  overflow-x: hidden;
  overflow-y: scroll;
  padding: 0 4px 4px 0;
  scrollbar-width: thin;
  scrollbar-color: var(--theme-border-strong) var(--theme-panel-bg-muted);
}

.prompt-content::-webkit-scrollbar,
.prompt-category-list::-webkit-scrollbar {
  width: 8px;
}

.prompt-content::-webkit-scrollbar-track,
.prompt-category-list::-webkit-scrollbar-track {
  border-radius: 999px;
  background: var(--theme-panel-bg-muted);
}

.prompt-content::-webkit-scrollbar-thumb,
.prompt-category-list::-webkit-scrollbar-thumb {
  border-radius: 999px;
  border: 2px solid var(--theme-panel-bg-muted);
  background: var(--theme-border-strong);
}

.prompt-content::-webkit-scrollbar-thumb:hover,
.prompt-category-list::-webkit-scrollbar-thumb:hover {
  background: var(--theme-accent);
}

.prompt-search {
  display: flex;
  align-items: stretch;
  width: 280px;
  min-height: 38px;
  border-radius: 999px;
  overflow: hidden;
  border: 1px solid var(--theme-control-border);
  background: var(--theme-control-bg);
  box-shadow: 0 8px 18px var(--theme-shadow-soft);
}

.prompt-search :deep(.ant-input-affix-wrapper) {
  flex: 1;
  min-width: 0;
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  border-radius: 0 !important;
  padding-inline: 14px 8px;
}

.prompt-search :deep(.ant-input) {
  color: var(--theme-title);
}

.prompt-search :deep(.ant-input::placeholder) {
  color: var(--text-muted);
}

.prompt-search-btn {
  flex-shrink: 0;
  width: 42px;
  border: none;
  border-left: 1px solid var(--theme-control-border);
  background: var(--theme-control-hover-bg);
  color: var(--theme-accent-text);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.prompt-batch-toggle-active {
  color: var(--theme-accent-text);
  background: var(--theme-control-hover-bg);
}

.prompt-count-pill {
  padding: 8px 12px;
  border-radius: 999px;
  background: var(--theme-pill-bg);
  color: var(--theme-pill-text);
  font-size: 13px;
  font-weight: 600;
}

.prompt-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-content: start;
  gap: 14px;
  min-height: 100%;
}

.prompt-card {
  position: relative;
  overflow: hidden;
  border-radius: 18px;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-surface-strong);
  box-shadow: 0 12px 28px var(--theme-shadow-soft);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.prompt-card-selected {
  border-color: var(--theme-accent);
  box-shadow: 0 18px 34px var(--theme-shadow-medium);
}

.prompt-card-batch-selectable {
  cursor: pointer;
}

.prompt-card-check {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 2;
  line-height: 1;
}

.prompt-card-header,
.prompt-card-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.prompt-card-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--theme-title);
}

.prompt-card-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.prompt-card-action-btn,
.prompt-card-icon-btn {
  color: var(--theme-accent-text);
}

.prompt-card-action-btn:hover,
.prompt-card-action-btn:focus,
.prompt-card-icon-btn:hover,
.prompt-card-icon-btn:focus {
  color: var(--theme-accent-text-hover);
}

.prompt-card-meta-row {
  font-size: 12px;
  color: var(--text-secondary);
}

.prompt-card-content {
  font-size: 13px;
  line-height: 1.7;
  color: var(--theme-title);
  white-space: pre-wrap;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 6;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.prompt-empty {
  min-height: 100%;
  padding: 28px 20px;
  border-radius: 22px;
  border: 1px dashed var(--theme-empty-border);
  background: var(--theme-empty-bg);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.prompt-empty-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--theme-title);
}

.prompt-empty-desc {
  margin-top: 8px;
  color: var(--text-secondary);
  line-height: 1.7;
  max-width: 360px;
}

.user-prompt-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.user-prompt-form-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.user-prompt-form-item label {
  font-weight: 600;
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-sidebar {
  background: var(--theme-panel-bg-soft);
  border-color: var(--theme-panel-border);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-sidebar-title,
html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-modal-header-title,
html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-card-title,
html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-empty-title,
html:is([data-theme="dark"], [data-theme="midnight"]) .user-prompt-form-item label {
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-side-icon-btn {
  background: var(--theme-panel-bg);
  border-color: var(--theme-panel-border);
  color: var(--theme-text-secondary);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-side-icon-btn:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-side-icon-btn:focus {
  background: var(--theme-control-hover-bg);
  border-color: var(--theme-border-strong);
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-side-icon-btn.danger {
  color: #de8f84;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-category-btn {
  background: var(--theme-panel-bg);
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-category-btn.active {
  background: var(--theme-panel-bg-strong);
  border-color: var(--theme-panel-border-strong);
  color: var(--theme-accent-text);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-batch-bar {
  background: var(--theme-panel-bg-soft);
  border-color: var(--theme-panel-border);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-batch-summary,
html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-card-meta-row,
html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-empty-desc {
  color: var(--theme-text-secondary);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-card-action-btn,
html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-card-icon-btn {
  color: var(--theme-accent-text);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-card-action-btn:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-card-action-btn:focus,
html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-card-icon-btn:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-card-icon-btn:focus {
  color: var(--theme-accent-text);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-loading-mask {
  background: rgba(var(--theme-surface-strong-rgb), 0.42);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-search {
  background: var(--theme-panel-bg);
  border-color: var(--theme-panel-border);
  box-shadow: 0 10px 20px rgba(0, 0, 0, 0.16);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-search :deep(.ant-input),
html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-search :deep(.ant-input-affix-wrapper) {
  color: var(--theme-title) !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-search :deep(.ant-input::placeholder) {
  color: var(--theme-text-secondary);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-search :deep(.ant-input-clear-icon) {
  color: var(--theme-text-secondary);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-search-btn {
  background: linear-gradient(180deg, rgba(61, 49, 31, 0.96), rgba(46, 37, 24, 0.96));
  border-left-color: rgba(214, 168, 84, 0.28);
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-batch-toggle-active,
html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-count-pill {
  background: var(--theme-panel-bg-strong);
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-toolbar-right :deep(.ant-btn-text) {
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-card {
  background: var(--theme-panel-bg-soft);
  border-color: var(--theme-panel-border);
  box-shadow: 0 12px 28px var(--theme-shadow-soft);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-card-selected {
  background: var(--theme-panel-bg-strong);
  border-color: var(--theme-panel-border-strong);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-card-content {
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-empty {
  border-color: var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .user-prompt-form :deep(.ant-input-textarea-show-count) {
  color: var(--theme-title) !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .user-prompt-form :deep(.ant-input-textarea-show-count)::after,
html:is([data-theme="dark"], [data-theme="midnight"]) .user-prompt-form :deep(.ant-input-data-count) {
  color: var(--theme-title) !important;
}

@media (max-width: 900px) {
  .prompt-picker {
    grid-template-columns: 1fr;
    height: auto;
    max-height: none;
    min-height: auto;
  }

  .prompt-list {
    grid-template-columns: 1fr;
  }

  .prompt-content {
    height: auto;
    min-height: auto;
    overflow: visible;
    padding-right: 0;
  }

  .prompt-category-list {
    overflow: visible;
    padding-right: 0;
  }

  .prompt-search {
    width: 100%;
  }

  .prompt-modal-header {
    flex-direction: column;
    align-items: stretch;
    padding-right: 0;
  }

  .prompt-modal-header-left,
  .prompt-modal-header-right,
  .prompt-toolbar-right {
    width: 100%;
    flex-wrap: wrap;
  }

  .prompt-batch-bar {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
