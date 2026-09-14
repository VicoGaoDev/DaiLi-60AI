<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { message, Modal } from "ant-design-vue";
import { useRouter } from "vue-router";
import {
  DeleteOutlined,
  EditOutlined,
  NumberOutlined,
  PictureOutlined,
  PlusOutlined,
  TagsOutlined,
} from "@ant-design/icons-vue";
import { getGenerationModels } from "@/api/config";
import {
  createTemplateTag,
  createTemplate,
  deleteTemplateTag,
  deleteTemplate,
  getTemplateDetail,
  listAdminTemplates,
  listTemplateTags,
  updateTemplateTag,
  updateTemplate,
  type TemplatePayload,
} from "@/api/templates";
import { getPreviewImageSrc } from "@/api/images";
import TemplateFormDialog from "@/components/templates/TemplateFormDialog.vue";
import type { CreativeTemplate, GenerationModelOption, TemplateTag } from "@/types";

const router = useRouter();
const templates = ref<CreativeTemplate[]>([]);
const tags = ref<TemplateTag[]>([]);
const modelOptions = ref<GenerationModelOption[]>([]);
const loading = ref(false);
const modalOpen = ref(false);
const saving = ref(false);
const editingId = ref<number | null>(null);
const activeTagId = ref<number | null>(null);
const tagManageOpen = ref(false);
const savingTag = ref(false);
const editingTag = ref<TemplateTag | null>(null);
const formInitialValue = ref<TemplatePayload | null>(null);

const columns = [
  { title: "结果图", dataIndex: "result_image", width: 110 },
  { title: "提示词", dataIndex: "prompt", width: 280, ellipsis: true },
  { title: "标签", key: "tags", width: 220 },
  { title: "排序", dataIndex: "sort_order", width: 90 },
  { title: "参数", key: "meta", width: 180 },
  { title: "创建时间", dataIndex: "created_at", width: 180 },
  { title: "操作", key: "action", width: 160 },
];

const filteredTemplates = computed(() => {
  if (activeTagId.value === null) return templates.value;
  return templates.value.filter((item) => item.tags.some((tag) => tag.id === activeTagId.value));
});

const renameForm = reactive({
  name: "",
});

function resetForm() {
  editingId.value = null;
  formInitialValue.value = {
    prompt: "",
    model: modelOptions.value[0]?.model_key || "banana_pro",
    reference_images: [],
    num_images: 1,
    size: "9:16",
    resolution: "2K",
    custom_size: "",
    result_image: "",
    sort_order: 0,
    tag_names: [],
  };
}

function resetTagForm() {
  editingTag.value = null;
  renameForm.name = "";
}

async function load() {
  loading.value = true;
  try {
    templates.value = await listAdminTemplates();
  } catch {
    message.error("获取模版列表失败");
  } finally {
    loading.value = false;
  }
}

async function loadTags() {
  try {
    tags.value = await listTemplateTags();
    if (activeTagId.value !== null && !tags.value.some((tag) => tag.id === activeTagId.value)) {
      activeTagId.value = null;
    }
  } catch {
    // ignore
  }
}

async function loadModels() {
  try {
    modelOptions.value = await getGenerationModels();
  } catch {
    // ignore
  }
}

onMounted(() => {
  load();
  loadTags();
  loadModels();
});

function openCreate() {
  resetForm();
  modalOpen.value = true;
}

function openTagManage() {
  resetTagForm();
  tagManageOpen.value = true;
}

function goExampleCanvases() {
  router.push("/admin/example-canvases");
}

function openRenameTag(tag: TemplateTag) {
  editingTag.value = tag;
  renameForm.name = tag.name;
}

async function openEdit(item: CreativeTemplate) {
  try {
    const detail = await getTemplateDetail(item.id);
    editingId.value = item.id;
    formInitialValue.value = {
      prompt: detail.prompt,
      model: detail.model || modelOptions.value[0]?.model_key || "banana_pro",
      reference_images: [...detail.reference_images],
      num_images: 1,
      size: detail.size,
      resolution: detail.resolution,
      custom_size: detail.custom_size || "",
      result_image: detail.result_image,
      sort_order: detail.sort_order ?? 0,
      tag_names: detail.tags.map((tag) => tag.name),
    };
    modalOpen.value = true;
  } catch {
    message.error("获取模版详情失败");
  }
}

async function handleSave(payload: TemplatePayload) {
  saving.value = true;
  try {
    if (editingId.value) await updateTemplate(editingId.value, payload);
    else await createTemplate(payload);
    message.success(editingId.value ? "模版更新成功" : "模版创建成功");
    modalOpen.value = false;
    resetForm();
    load();
    loadTags();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function handleSaveTag() {
  const name = renameForm.name.trim();
  if (!name) {
    message.warning("请输入标签名称");
    return;
  }
  savingTag.value = true;
  try {
    if (editingTag.value) {
      await updateTemplateTag(editingTag.value.id, { name });
      message.success("标签更新成功");
      await Promise.all([load(), loadTags()]);
    } else {
      await createTemplateTag({ name });
      message.success("标签创建成功");
      await loadTags();
    }
    resetTagForm();
  } catch (err: any) {
    message.error(err.response?.data?.detail || (editingTag.value ? "标签更新失败" : "标签创建失败"));
  } finally {
    savingTag.value = false;
  }
}

function handleDelete(item: CreativeTemplate) {
  Modal.confirm({
    title: "确认删除该模版？",
    centered: true,
    async onOk() {
      await deleteTemplate(item.id);
      message.success("删除成功");
      load();
      loadTags();
    },
  });
}

function handleDeleteTag(tag: TemplateTag) {
  Modal.confirm({
    title: `确认删除标签「${tag.name}」？`,
    content: "删除后会同步移除该标签与模板的关联关系。",
    centered: true,
    async onOk() {
      await deleteTemplateTag(tag.id);
      message.success("标签删除成功");
      await Promise.all([load(), loadTags()]);
    },
  });
}

function fmtTime(t: string) {
  return t ? new Date(t).toLocaleString("zh-CN") : "-";
}
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <PictureOutlined />
        </div>
        <div>
          <div class="warm-page-title">模版管理</div>
          <div class="warm-page-desc">维护创意模版内容、标签和展示结果图。</div>
        </div>
      </div>
      <div class="page-actions">
        <a-button class="warm-secondary-btn" @click="goExampleCanvases">
          <template #icon><NumberOutlined /></template>
          示例画布
        </a-button>
        <a-button type="primary" class="warm-primary-btn" @click="openTagManage">
          <template #icon><TagsOutlined /></template>
          标签管理
        </a-button>
        <a-button type="primary" class="warm-primary-btn" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新增模版
        </a-button>
      </div>
    </div>

    <div class="tag-filter-row motion-fade-up" style="--motion-delay: 120ms">
      <a-tag class="manage-filter-tag" :class="{ active: activeTagId === null }" @click="activeTagId = null">
        全部模版
      </a-tag>
      <a-tag
        v-for="tag in tags"
        :key="tag.id"
        class="manage-filter-tag"
        :class="{ active: activeTagId === tag.id }"
        @click="activeTagId = tag.id"
      >
        {{ tag.name }}
      </a-tag>
    </div>

    <div class="warm-card warm-table-card motion-fade-up motion-card-lift" style="--motion-delay: 200ms">
      <a-table
        :columns="columns"
        :data-source="filteredTemplates"
        :loading="loading"
        row-key="id"
        :pagination="false"
        :scroll="{ x: 1220 }"
        class="admin-mobile-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'result_image'">
            <div class="thumb-box">
              <img v-if="record.result_image" :src="getPreviewImageSrc(record.result_image_thumb || record.result_image)" alt="结果图" loading="lazy" />
            </div>
          </template>
          <template v-else-if="column.key === 'tags'">
            <div class="tag-list">
              <a-tag v-for="tag in record.tags" :key="tag.id" class="warm-tag">{{ tag.name }}</a-tag>
            </div>
          </template>
          <template v-else-if="column.dataIndex === 'sort_order'">
            {{ record.sort_order ?? 0 }}
          </template>
          <template v-else-if="column.key === 'meta'">
            <div class="meta-cell">
              {{ record.model || "-" }} / {{ record.size }}
              <span v-if="record.resolution"> / {{ record.resolution }}</span>
              <span v-if="record.custom_size"> / {{ record.custom_size }}</span>
            </div>
          </template>
          <template v-else-if="column.dataIndex === 'created_at'">
            {{ fmtTime(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <div class="table-actions">
              <a-button type="link" size="small" class="template-action-btn template-action-btn-primary" @click="openEdit(record)">
                <template #icon><EditOutlined /></template>
                编辑
              </a-button>
              <a-divider type="vertical" />
              <a-button type="link" danger size="small" class="template-action-btn template-action-btn-danger" @click="handleDelete(record)">
                <template #icon><DeleteOutlined /></template>
                删除
              </a-button>
            </div>
          </template>
        </template>
      </a-table>
    </div>

    <TemplateFormDialog
      v-model:open="modalOpen"
      :title="editingId ? '编辑模版' : '新增模版'"
      :initial-value="formInitialValue"
      :generation-models="modelOptions"
      :tags="tags"
      :confirm-loading="saving"
      @save="handleSave"
      @cancel="resetForm"
    />

    <a-modal
      v-model:open="tagManageOpen"
      title="标签管理"
      :confirm-loading="savingTag"
      :ok-button-props="{ class: 'warm-primary-btn' }"
      :cancel-button-props="{ class: 'warm-secondary-btn' }"
      ok-text="提交"
      cancel-text="取消"
      centered
      :width="760"
      @ok="handleSaveTag"
      @cancel="resetTagForm"
    >
      <a-form layout="vertical" style="margin-top: 16px">
        <a-form-item :label="editingTag ? '重命名标签' : '新增标签'">
          <div class="tag-create-box">
            <a-input
              v-model:value="renameForm.name"
              class="warm-input"
              :maxlength="50"
              :placeholder="editingTag ? '请输入新的标签名称' : '输入新标签名称'"
              @pressEnter="handleSaveTag"
            />
            <a-button v-if="editingTag" class="template-secondary-btn" @click="resetTagForm">取消编辑</a-button>
          </div>
        </a-form-item>
      </a-form>

      <div v-if="tags.length" class="tag-manage-list">
        <div v-for="tag in tags" :key="tag.id" class="tag-manage-item">
          <div class="tag-manage-main">
            <a-tag class="warm-tag">{{ tag.name }}</a-tag>
            <span class="tag-manage-count">关联 {{ tag.template_count ?? 0 }} 个模版</span>
          </div>
          <div class="tag-manage-actions">
            <a-button type="link" size="small" class="template-action-btn template-action-btn-primary" @click="openRenameTag(tag)">重命名</a-button>
            <a-divider type="vertical" />
            <a-button type="link" danger size="small" class="template-action-btn template-action-btn-danger" @click="handleDeleteTag(tag)">删除</a-button>
          </div>
        </div>
      </div>
      <a-empty v-else class="warm-empty" description="暂无标签，可先新增标签" />
    </a-modal>
  </div>
</template>

<style scoped lang="scss">
.page-actions {
  display: flex;
  gap: 12px;
}

.tag-manage-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.tag-manage-title {
  color: #4c341a;
  font-size: 16px;
  font-weight: 700;
}

.tag-manage-desc {
  margin-top: 6px;
  color: #8d7457;
  font-size: 13px;
}

.tag-create-box {
  display: flex;
  gap: 12px;
  width: min(100%, 420px);
}

.tag-filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.manage-filter-tag {
  cursor: pointer;
  border-radius: 999px;
  padding: 6px 12px;
  font-weight: 600;

  &.active {
    color: #8a5400;
    background: linear-gradient(180deg, #fff0cc, #ffe2a9);
    border-color: #f0c46d;
  }
}

.tag-manage-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.tag-manage-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg);
}

.tag-manage-main {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  min-width: 0;
}

.tag-manage-count {
  color: #8d7457;
  font-size: 13px;
}

.tag-manage-actions {
  flex-shrink: 0;
}

.thumb-box {
  width: 72px;
  height: 72px;
  border-radius: 12px;
  overflow: hidden;
  background: #fff8ec;
  border: 1px solid #f0dfbe;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.meta-cell {
  color: #6b5436;
  font-weight: 600;
}

.table-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.table-actions :deep(.ant-divider-vertical),
.tag-manage-actions :deep(.ant-divider-vertical) {
  margin-inline: 2px;
  border-inline-start-color: #efd7b1;
}

.template-action-btn {
  height: 30px;
  padding-inline: 10px;
  border-radius: 10px;
  font-weight: 600;
}

.template-action-btn.template-action-btn-primary {
  color: var(--theme-accent-text) !important;
  background: var(--theme-panel-bg-strong) !important;
}

.template-action-btn.template-action-btn-danger {
  color: #d6574b !important;
  background: #fff1ef !important;
}

.template-action-btn:hover,
.template-action-btn:focus {
  opacity: 0.92;
}

.template-secondary-btn {
  border-color: var(--theme-control-border-strong) !important;
  background: var(--theme-control-bg) !important;
  color: var(--theme-accent-text) !important;
  border-radius: 12px !important;
  font-weight: 600;
}

.template-secondary-btn:hover,
.template-secondary-btn:focus {
  border-color: var(--theme-border-strong) !important;
  background: var(--theme-control-hover-bg) !important;
  color: var(--theme-accent-text-hover) !important;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

.result-upload {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.result-preview {
  width: 132px;
  height: 132px;
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
  flex-shrink: 0;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
}

.result-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  font-size: 13px;
}

.ref-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.ref-item {
  position: relative;
  width: 84px;
  height: 84px;
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
}

.ref-remove {
  position: absolute;
  top: 4px;
  right: 4px;
  background: rgba(var(--theme-surface-strong-rgb), 0.92) !important;
  border: 1px solid var(--theme-panel-border) !important;
  color: #d6574b !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .warm-page .template-action-btn.template-action-btn-primary {
  background: var(--theme-panel-bg-strong) !important;
  color: var(--theme-accent-text) !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .warm-page .template-action-btn.template-action-btn-danger {
  background: rgba(185, 56, 42, 0.12) !important;
  color: #de8f84 !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .warm-page .ref-remove {
  background: rgba(var(--theme-surface-strong-rgb), 0.92) !important;
  border-color: var(--theme-panel-border) !important;
  color: #de8f84 !important;
}

.ref-add {
  height: 84px;
  min-width: 120px;
  border-radius: 14px;
}

@media (max-width: 720px) {
  :deep(.admin-mobile-table .ant-table-content) {
    overflow-x: auto !important;
  }

  .page-actions,
  .tag-manage-header,
  .tag-create-box {
    flex-direction: column;
  }

  .tag-create-box {
    width: 100%;
  }

  .tag-manage-list {
    grid-template-columns: 1fr;
  }

  .tag-manage-item {
    align-items: flex-start;
    flex-direction: column;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .result-upload {
    flex-direction: column;
  }
}
</style>
