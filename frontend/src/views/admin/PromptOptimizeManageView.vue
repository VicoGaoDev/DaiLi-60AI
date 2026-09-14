<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined, ThunderboltOutlined } from "@ant-design/icons-vue";
import { message, Modal } from "ant-design-vue";

import {
  createPromptOptimizeStyle,
  deletePromptOptimizeStyle,
  listPromptOptimizeStyles,
  setPromptOptimizeStyleDefault,
  updatePromptOptimizeStyle,
  updatePromptOptimizeStyleStatus,
} from "@/api/admin";
import type { PromptOptimizeStyle, PromptOptimizeStylePayload } from "@/types";

const loading = ref(false);
const saving = ref(false);
const items = ref<PromptOptimizeStyle[]>([]);
const modalOpen = ref(false);
const editingId = ref<number | null>(null);

const columns = [
  { title: "风格名称", dataIndex: "name", width: 180 },
  { title: "描述", dataIndex: "description", width: 260, ellipsis: true },
  { title: "排序", dataIndex: "sort_order", width: 90 },
  { title: "状态", dataIndex: "status", width: 110 },
  { title: "默认", dataIndex: "is_default", width: 100 },
  { title: "使用次数", dataIndex: "usage_count", width: 110 },
  { title: "更新时间", dataIndex: "updated_at", width: 180 },
  { title: "操作", key: "actions", width: 340, fixed: "right" as const },
];

const formState = reactive<PromptOptimizeStylePayload>({
  name: "",
  description: "",
  style_prompt: "",
  sort_order: 100,
  status: "enabled",
  is_default: false,
});

const modalTitle = computed(() => (editingId.value ? "编辑提示词优化风格" : "新增提示词优化风格"));

function formatTime(value?: string | null) {
  return value || "-";
}

function resetForm() {
  editingId.value = null;
  formState.name = "";
  formState.description = "";
  formState.style_prompt = "";
  formState.sort_order = 100;
  formState.status = "enabled";
  formState.is_default = false;
}

async function load() {
  loading.value = true;
  try {
    items.value = await listPromptOptimizeStyles();
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "获取提示词优化风格失败");
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  resetForm();
  modalOpen.value = true;
}

function openEdit(item: PromptOptimizeStyle) {
  editingId.value = item.id;
  formState.name = item.name;
  formState.description = item.description || "";
  formState.style_prompt = item.style_prompt || "";
  formState.sort_order = item.sort_order || 100;
  formState.status = item.status;
  formState.is_default = !!item.is_default;
  modalOpen.value = true;
}

async function handleSave() {
  if (!formState.name.trim()) {
    message.warning("请输入风格名称");
    return;
  }
  if (!formState.style_prompt.trim()) {
    message.warning("请输入风格提示词");
    return;
  }
  saving.value = true;
  try {
    const payload: PromptOptimizeStylePayload = {
      name: formState.name.trim(),
      description: formState.description.trim(),
      style_prompt: formState.style_prompt.trim(),
      sort_order: Number(formState.sort_order || 0),
      status: formState.status,
      is_default: formState.is_default,
    };
    if (editingId.value) {
      await updatePromptOptimizeStyle(editingId.value, payload);
      message.success("提示词优化风格已更新");
    } else {
      await createPromptOptimizeStyle(payload);
      message.success("提示词优化风格已创建");
    }
    modalOpen.value = false;
    resetForm();
    await load();
  } catch (err: any) {
    message.error(err?.response?.data?.detail || (editingId.value ? "更新风格失败" : "创建风格失败"));
  } finally {
    saving.value = false;
  }
}

function handleDelete(item: PromptOptimizeStyle) {
  Modal.confirm({
    title: `删除风格「${item.name}」？`,
    content: "删除后该风格不会再出现在用户选择列表中；历史任务会保留快照信息。",
    centered: true,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      await deletePromptOptimizeStyle(item.id);
      message.success("风格已删除");
      await load();
    },
  });
}

async function handleToggleStatus(item: PromptOptimizeStyle) {
  const nextStatus = item.status === "enabled" ? "disabled" : "enabled";
  try {
    await updatePromptOptimizeStyleStatus(item.id, nextStatus);
    message.success(nextStatus === "enabled" ? "风格已启用" : "风格已停用");
    await load();
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "更新风格状态失败");
  }
}

async function handleSetDefault(item: PromptOptimizeStyle) {
  try {
    await setPromptOptimizeStyleDefault(item.id);
    message.success("默认风格已更新");
    await load();
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "设置默认风格失败");
  }
}

void load();
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <ThunderboltOutlined />
        </div>
        <div>
          <div class="warm-page-title">提示词优化</div>
          <div class="warm-page-desc">管理用户执行提示词优化时可选的系统风格，支持默认风格、启停和软删除。</div>
        </div>
      </div>
      <div class="page-actions">
        <a-button class="warm-secondary-btn" @click="load">
          <template #icon><ReloadOutlined /></template>
          刷新列表
        </a-button>
        <a-button type="primary" class="warm-primary-btn" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新增风格
        </a-button>
      </div>
    </div>

    <div class="warm-card warm-table-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <a-table
        :columns="columns"
        :data-source="items"
        :loading="loading"
        row-key="id"
        :pagination="false"
        :scroll="{ x: 1280 }"
        class="admin-mobile-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'description'">
            <a-tooltip :title="record.description || '-'">
              <div class="desc-summary">{{ record.description || "-" }}</div>
            </a-tooltip>
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <a-tag :color="record.status === 'enabled' ? 'green' : 'default'">
              {{ record.status === "enabled" ? "启用中" : "已停用" }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'is_default'">
            <a-tag :color="record.is_default ? 'gold' : 'default'">
              {{ record.is_default ? "默认" : "-" }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'updated_at'">
            {{ formatTime(record.updated_at) }}
          </template>
          <template v-else-if="column.key === 'actions'">
            <div class="table-actions">
              <a-button type="link" size="small" class="action-btn action-btn-primary" @click="openEdit(record)">
                <template #icon><EditOutlined /></template>
                编辑
              </a-button>
              <a-divider type="vertical" />
              <a-button type="link" size="small" class="action-btn" @click="handleToggleStatus(record)">
                {{ record.status === "enabled" ? "停用" : "启用" }}
              </a-button>
              <a-divider type="vertical" />
              <a-button type="link" size="small" class="action-btn" :disabled="record.is_default || record.status !== 'enabled'" @click="handleSetDefault(record)">
                设为默认
              </a-button>
              <a-divider type="vertical" />
              <a-button type="link" danger size="small" class="action-btn action-btn-danger" @click="handleDelete(record)">
                <template #icon><DeleteOutlined /></template>
                删除
              </a-button>
            </div>
          </template>
        </template>
      </a-table>
    </div>

    <a-modal
      v-model:open="modalOpen"
      :title="modalTitle"
      centered
      :confirm-loading="saving"
      ok-text="保存"
      cancel-text="取消"
      :width="820"
      @ok="handleSave"
      @cancel="resetForm"
    >
      <a-form layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="风格名称" required>
              <a-input v-model:value="formState.name" class="warm-input" :maxlength="100" show-count placeholder="例如：电影感写实" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="风格描述">
              <a-input v-model:value="formState.description" class="warm-input" :maxlength="255" show-count placeholder="用于用户选择时的简短说明" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="排序">
              <a-input-number v-model:value="formState.sort_order" class="full-width" :min="0" :max="999999" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="状态">
              <a-select v-model:value="formState.status" class="warm-select">
                <a-select-option value="enabled">启用</a-select-option>
                <a-select-option value="disabled">停用</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item>
          <a-checkbox v-model:checked="formState.is_default">设为默认风格</a-checkbox>
        </a-form-item>
        <a-form-item label="风格提示词" required>
          <a-textarea
            v-model:value="formState.style_prompt"
            class="warm-textarea"
            :rows="10"
            :maxlength="10000"
            show-count
            placeholder="请输入该风格的系统提示词，用于在保留用户原意前提下调整优化方向。"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped lang="scss">
.page-actions {
  display: flex;
  gap: 12px;
}

.desc-summary {
  max-width: 240px;
  overflow: hidden;
  color: var(--theme-muted-text);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.table-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.full-width {
  width: 100%;
}
</style>
