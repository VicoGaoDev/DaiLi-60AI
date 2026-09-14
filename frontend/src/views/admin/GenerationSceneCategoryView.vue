<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined, TagsOutlined } from "@ant-design/icons-vue";
import { message, Modal } from "ant-design-vue";

import {
  createGenerationSceneCategory,
  deleteGenerationSceneCategory,
  listExternalApiSceneBindings,
  listGenerationSceneCategories,
  updateGenerationSceneCategory,
  updateGenerationSceneCategoryStatus,
} from "@/api/admin";
import type {
  ExternalApiSceneBinding,
  GenerationSceneCategory,
  GenerationSceneCategoryPayload,
  GenerationSceneCategoryType,
} from "@/types";

const loading = ref(false);
const saving = ref(false);
const items = ref<GenerationSceneCategory[]>([]);
const sceneBindings = ref<ExternalApiSceneBinding[]>([]);
const modalOpen = ref(false);
const editingId = ref<number | null>(null);

const columns = [
  { title: "分类名称", dataIndex: "name", width: 180 },
  { title: "类型", dataIndex: "scene_type", width: 110 },
  { title: "描述", dataIndex: "description", width: 220, ellipsis: true },
  { title: "包含场景", dataIndex: "scene_keys", width: 320 },
  { title: "排序", dataIndex: "sort_order", width: 90 },
  { title: "状态", dataIndex: "status", width: 110 },
  { title: "更新时间", dataIndex: "updated_at", width: 180 },
  { title: "操作", key: "actions", width: 260, fixed: "right" as const },
];

const formState = reactive<GenerationSceneCategoryPayload>({
  name: "",
  description: "",
  scene_type: "generate",
  scene_keys: [],
  sort_order: 100,
  status: "enabled",
});

const modalTitle = computed(() => (editingId.value ? "编辑生图场景分类" : "新增生图场景分类"));

const allAssignableScenes = computed(() => (
  sceneBindings.value.filter((item) => item.scene_type === "generate" || item.scene_type === "image_edit")
));

const assignableScenes = computed(() => (
  allAssignableScenes.value.filter((item) => item.scene_type === formState.scene_type)
));

const occupiedSceneMap = computed(() => {
  const mapping = new Map<string, GenerationSceneCategory>();
  items.value.forEach((category) => {
    if (editingId.value && category.id === editingId.value) return;
    category.scene_keys.forEach((key) => mapping.set(key, category));
  });
  return mapping;
});

const sceneLabelMap = computed(() => {
  const mapping = new Map<string, string>();
  allAssignableScenes.value.forEach((item) => {
    mapping.set(item.scene_key, item.scene_label || item.display_name || item.scene_key);
  });
  return mapping;
});

function formatTime(value?: string | null) {
  return value || "-";
}

function sceneTypeLabel(sceneType?: GenerationSceneCategoryType | ExternalApiSceneBinding["scene_type"] | null) {
  return sceneType === "image_edit" ? "图编辑" : "文生图";
}

function sceneOptionLabel(item: ExternalApiSceneBinding) {
  const occupied = occupiedSceneMap.value.get(item.scene_key);
  const base = item.scene_label || item.display_name || item.scene_key;
  return occupied ? `${base} · 已属于 ${occupied.name}` : base;
}

function syncSceneKeysToType() {
  const allowed = new Set(assignableScenes.value.map((item) => item.scene_key));
  formState.scene_keys = formState.scene_keys.filter((key) => allowed.has(key));
}

watch(() => formState.scene_type, () => {
  syncSceneKeysToType();
});

function sceneKeysLabel(keys: string[]) {
  if (!keys.length) return "未选择场景";
  return keys.map((key) => sceneLabelMap.value.get(key) || key).join("、");
}

function resetForm() {
  editingId.value = null;
  formState.name = "";
  formState.description = "";
  formState.scene_type = "generate";
  formState.scene_keys = [];
  formState.sort_order = 100;
  formState.status = "enabled";
}

async function load() {
  loading.value = true;
  try {
    const [categories, scenes] = await Promise.all([
      listGenerationSceneCategories(),
      listExternalApiSceneBindings(),
    ]);
    items.value = categories;
    sceneBindings.value = scenes;
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "获取生图场景分类失败");
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  resetForm();
  modalOpen.value = true;
}

function openEdit(item: GenerationSceneCategory) {
  editingId.value = item.id;
  formState.name = item.name;
  formState.description = item.description || "";
  formState.scene_type = item.scene_type === "image_edit" ? "image_edit" : "generate";
  formState.scene_keys = [...item.scene_keys];
  formState.sort_order = item.sort_order || 100;
  formState.status = item.status;
  modalOpen.value = true;
}

async function handleSave() {
  if (!formState.name.trim()) {
    message.warning("请输入分类名称");
    return;
  }
  syncSceneKeysToType();
  saving.value = true;
  try {
    const payload: GenerationSceneCategoryPayload = {
      name: formState.name.trim(),
      description: formState.description.trim(),
      scene_type: formState.scene_type,
      scene_keys: [...formState.scene_keys],
      sort_order: Number(formState.sort_order || 0),
      status: formState.status,
    };
    if (editingId.value) {
      await updateGenerationSceneCategory(editingId.value, payload);
      message.success("生图场景分类已更新");
    } else {
      await createGenerationSceneCategory(payload);
      message.success("生图场景分类已创建");
    }
    modalOpen.value = false;
    resetForm();
    await load();
  } catch (err: any) {
    message.error(err?.response?.data?.detail || (editingId.value ? "更新分类失败" : "创建分类失败"));
  } finally {
    saving.value = false;
  }
}

function handleDelete(item: GenerationSceneCategory) {
  Modal.confirm({
    title: `删除分类「${item.name}」？`,
    content: "删除后该分类不会再出现在生图模型下拉中，原场景会回到一级列表。",
    centered: true,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      await deleteGenerationSceneCategory(item.id);
      message.success("分类已删除");
      await load();
    },
  });
}

async function handleToggleStatus(item: GenerationSceneCategory) {
  const nextStatus = item.status === "enabled" ? "disabled" : "enabled";
  try {
    await updateGenerationSceneCategoryStatus(item.id, nextStatus);
    message.success(nextStatus === "enabled" ? "分类已启用" : "分类已停用");
    await load();
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "更新分类状态失败");
  }
}

void load();
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <TagsOutlined />
        </div>
        <div>
          <div class="warm-page-title">生图分类</div>
          <div class="warm-page-desc">管理文生图、图编辑各自的模型分类。分类只能选择同类型场景，无需改动场景本身。</div>
        </div>
      </div>
      <div class="page-actions">
        <a-button class="warm-secondary-btn" @click="load">
          <template #icon><ReloadOutlined /></template>
          刷新列表
        </a-button>
        <a-button type="primary" class="warm-primary-btn" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新增分类
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
        :scroll="{ x: 1400 }"
        class="admin-mobile-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'scene_type'">
            <a-tag :color="record.scene_type === 'image_edit' ? 'purple' : 'blue'">
              {{ sceneTypeLabel(record.scene_type) }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'description'">
            <a-tooltip :title="record.description || '-'">
              <div class="desc-summary">{{ record.description || "-" }}</div>
            </a-tooltip>
          </template>
          <template v-else-if="column.dataIndex === 'scene_keys'">
            <a-tooltip :title="sceneKeysLabel(record.scene_keys)">
              <div class="desc-summary scene-summary">{{ sceneKeysLabel(record.scene_keys) }}</div>
            </a-tooltip>
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <a-tag :color="record.status === 'enabled' ? 'green' : 'default'">
              {{ record.status === "enabled" ? "启用中" : "已停用" }}
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
      :width="720"
      @ok="handleSave"
      @cancel="resetForm"
    >
      <a-form layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="分类名称" required>
              <a-input v-model:value="formState.name" class="warm-input" :maxlength="100" show-count placeholder="例如：Banana 系列" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="所属类型" required>
              <a-radio-group v-model:value="formState.scene_type" class="warm-radio-group" button-style="solid">
                <a-radio-button value="generate">文生图</a-radio-button>
                <a-radio-button value="image_edit">图编辑</a-radio-button>
              </a-radio-group>
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="分类描述">
          <a-input v-model:value="formState.description" class="warm-input" :maxlength="255" show-count placeholder="用于后台识别，不展示给用户" />
        </a-form-item>
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
        <a-form-item :label="`所属场景（${sceneTypeLabel(formState.scene_type)}）`">
          <a-select
            v-model:value="formState.scene_keys"
            mode="multiple"
            allow-clear
            class="warm-select"
            :placeholder="`选择要聚合到该${sceneTypeLabel(formState.scene_type)}分类下的场景`"
            :options="assignableScenes.map((item) => ({
              value: item.scene_key,
              label: sceneOptionLabel(item),
              disabled: occupiedSceneMap.has(item.scene_key),
            }))"
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

.scene-summary {
  max-width: 300px;
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
