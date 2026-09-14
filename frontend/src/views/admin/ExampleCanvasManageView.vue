<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { message, Modal } from "ant-design-vue";
import {
  DeleteOutlined,
  EditOutlined,
  NumberOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons-vue";
import { getPreviewImageSrc } from "@/api/images";
import {
  createAdminExampleCanvasProject,
  deleteAdminExampleCanvasProject,
  listAdminExampleCanvasProjects,
  updateAdminExampleCanvasProject,
} from "@/api/exampleCanvases";
import type { ExampleCanvasProject, ExampleCanvasStatus } from "@/types";

const loading = ref(false);
const saving = ref(false);
const refreshingExampleId = ref<number | null>(null);
const modalOpen = ref(false);
const editingId = ref<number | null>(null);
const examples = ref<ExampleCanvasProject[]>([]);

const formState = reactive({
  project_id: "",
  title: "",
  subtitle: "",
  cover_url: "",
  sort_order: 0,
  status: "draft" as ExampleCanvasStatus,
});

const columns = [
  { title: "封面", dataIndex: "cover_url", width: 108 },
  { title: "示例信息", key: "info", width: 280 },
  { title: "源画布", key: "source", width: 220 },
  { title: "状态", dataIndex: "status", width: 110 },
  { title: "排序", dataIndex: "sort_order", width: 90 },
  { title: "更新时间", dataIndex: "updated_at", width: 180 },
  { title: "操作", key: "action", width: 260 },
];

const statusOptions: Array<{ label: string; value: ExampleCanvasStatus }> = [
  { label: "草稿", value: "draft" },
  { label: "已发布", value: "published" },
  { label: "已停用", value: "disabled" },
];

const formTitle = computed(() => (editingId.value ? "编辑示例项目" : "新增示例项目"));

function resetForm() {
  editingId.value = null;
  formState.project_id = "";
  formState.title = "";
  formState.subtitle = "";
  formState.cover_url = "";
  formState.sort_order = 0;
  formState.status = "draft";
}

function formatTime(value?: string | null) {
  return value ? new Date(value).toLocaleString("zh-CN") : "-";
}

function statusText(status: ExampleCanvasStatus) {
  if (status === "published") return "已发布";
  if (status === "disabled") return "已停用";
  return "草稿";
}

async function loadExamples() {
  loading.value = true;
  try {
    examples.value = (await listAdminExampleCanvasProjects()).items;
  } catch {
    message.error("获取示例项目失败");
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  resetForm();
  modalOpen.value = true;
}

function openEdit(example: ExampleCanvasProject) {
  editingId.value = example.id;
  formState.project_id = example.source_project_id;
  formState.title = example.title;
  formState.subtitle = example.subtitle || "";
  formState.cover_url = example.cover_url || "";
  formState.sort_order = example.sort_order || 0;
  formState.status = example.status;
  modalOpen.value = true;
}

async function handleSave() {
  const projectId = formState.project_id.trim();
  if (!projectId) {
    message.warning("请输入源画布 project_id");
    return;
  }
  saving.value = true;
  try {
    const payload = {
      project_id: projectId,
      title: formState.title.trim(),
      subtitle: formState.subtitle.trim(),
      cover_url: formState.cover_url.trim(),
      sort_order: Number(formState.sort_order || 0),
      status: formState.status,
    };
    if (editingId.value) {
      await updateAdminExampleCanvasProject(editingId.value, payload);
      message.success("示例项目更新成功");
    } else {
      await createAdminExampleCanvasProject(payload);
      message.success("示例项目创建成功");
    }
    modalOpen.value = false;
    resetForm();
    await loadExamples();
  } catch (err: any) {
    message.error(err.response?.data?.detail || (editingId.value ? "更新失败" : "创建失败"));
  } finally {
    saving.value = false;
  }
}

async function handleRefreshSnapshot(example: ExampleCanvasProject) {
  if (refreshingExampleId.value) return;
  refreshingExampleId.value = example.id;
  try {
    await updateAdminExampleCanvasProject(example.id, { refresh_snapshot: true });
    message.success("示例快照已刷新");
    await loadExamples();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "刷新快照失败");
  } finally {
    refreshingExampleId.value = null;
  }
}

function handleDelete(example: ExampleCanvasProject) {
  Modal.confirm({
    title: `删除示例项目「${example.title}」？`,
    content: "删除后，前台将不再展示该示例项目。",
    centered: true,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      await deleteAdminExampleCanvasProject(example.id);
      message.success("示例项目已删除");
      await loadExamples();
    },
  });
}

onMounted(() => {
  loadExamples();
});
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <NumberOutlined />
        </div>
        <div>
          <div class="warm-page-title">示例画布管理</div>
          <div class="warm-page-desc">通过源画布 `project_id` 发布示例项目，并维护前台展示信息。</div>
        </div>
      </div>
      <div class="page-actions">
        <a-button class="warm-secondary-btn" @click="loadExamples">
          <template #icon><ReloadOutlined /></template>
          刷新列表
        </a-button>
        <a-button type="primary" class="warm-primary-btn" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新增示例项目
        </a-button>
      </div>
    </div>

    <div class="warm-card warm-table-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <a-table
        :columns="columns"
        :data-source="examples"
        :loading="loading"
        row-key="id"
        :pagination="false"
        :scroll="{ x: 1320 }"
        class="admin-mobile-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'cover_url'">
            <div class="cover-box">
              <img v-if="record.cover_url" :src="getPreviewImageSrc(record.cover_url)" alt="示例封面" />
              <div v-else class="cover-placeholder">暂无封面</div>
            </div>
          </template>
          <template v-else-if="column.key === 'info'">
            <div class="info-cell">
              <div class="info-title">{{ record.title }}</div>
              <div v-if="record.subtitle" class="info-subtitle">{{ record.subtitle }}</div>
              <div class="preview-meta">预览图 {{ record.preview_urls.length }} 张</div>
            </div>
          </template>
          <template v-else-if="column.key === 'source'">
            <div class="source-cell">
              <div>{{ record.source_canvas_name || "未命名画布" }}</div>
              <div class="source-project-id">{{ record.source_project_id }}</div>
            </div>
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <a-tag :color="record.status === 'published' ? 'green' : record.status === 'disabled' ? 'default' : 'orange'">
              {{ statusText(record.status) }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'updated_at'">
            {{ formatTime(record.updated_at) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <div class="table-actions">
              <a-button type="link" size="small" class="action-btn action-btn-primary" @click="openEdit(record)">
                <template #icon><EditOutlined /></template>
                编辑
              </a-button>
              <a-divider type="vertical" />
              <a-button
                type="link"
                size="small"
                class="action-btn action-btn-primary"
                :loading="refreshingExampleId === record.id"
                @click="handleRefreshSnapshot(record)"
              >
                <template #icon><ReloadOutlined /></template>
                刷新快照
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
      :title="formTitle"
      centered
      :confirm-loading="saving"
      ok-text="保存"
      cancel-text="取消"
      :width="760"
      @ok="handleSave"
      @cancel="resetForm"
    >
      <a-form layout="vertical" class="example-form">
        <div class="form-grid">
          <a-form-item label="源画布 project_id" required>
            <a-input v-model:value="formState.project_id" class="warm-input" :maxlength="16" placeholder="输入 16 位 project_id" />
          </a-form-item>
          <a-form-item label="展示状态">
            <a-select v-model:value="formState.status" :options="statusOptions" />
          </a-form-item>
          <a-form-item label="标题">
            <a-input v-model:value="formState.title" class="warm-input" :maxlength="100" placeholder="留空则使用源画布名称" />
          </a-form-item>
          <a-form-item label="排序">
            <a-input-number v-model:value="formState.sort_order" class="sort-input" :min="0" :precision="0" />
          </a-form-item>
        </div>
        <a-form-item label="副标题">
          <a-input v-model:value="formState.subtitle" class="warm-input" :maxlength="255" placeholder="用于前台卡片说明" />
        </a-form-item>
        <a-form-item label="封面图 URL">
          <a-input v-model:value="formState.cover_url" class="warm-input" :maxlength="1000" placeholder="留空则自动使用第一张预览图" />
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

.cover-box {
  width: 72px;
  height: 72px;
  overflow: hidden;
  border: 1px solid var(--theme-panel-border);
  border-radius: 14px;
  background: var(--theme-panel-bg-soft);

  img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: cover;
  }
}

.cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--theme-text-secondary);
  font-size: 12px;
}

.info-cell,
.source-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-title {
  color: var(--theme-title);
  font-weight: 700;
}

.info-subtitle,
.preview-meta,
.source-project-id {
  color: var(--theme-text-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.table-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.action-btn {
  height: 30px;
  padding-inline: 10px;
  border-radius: 10px;
  font-weight: 600;
}

.action-btn.action-btn-primary {
  color: #c7770d !important;
  background: #fff4df !important;
}

.action-btn.action-btn-danger {
  color: #d6574b !important;
  background: #fff1ef !important;
}

.example-form {
  margin-top: 16px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

.sort-input {
  width: 100%;
}

@media (max-width: 720px) {
  :deep(.admin-mobile-table .ant-table-content) {
    overflow-x: auto !important;
  }

  .page-actions,
  .form-grid {
    grid-template-columns: 1fr;
    flex-direction: column;
  }
}
</style>
