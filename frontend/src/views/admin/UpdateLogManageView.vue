<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import dayjs, { type Dayjs } from "dayjs";
import { message, Modal } from "ant-design-vue";
import { BellOutlined, DeleteOutlined, DownOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons-vue";
import {
  createAdminUpdateLog,
  deleteAdminUpdateLog,
  listAdminUpdateLogs,
  updateAdminUpdateLog,
} from "@/api/updateLogs";
import type { UpdateLogItem, UpdateLogPayload, UpdateLogTagType } from "@/types";

const loading = ref(false);
const saving = ref(false);
const modalOpen = ref(false);
const editingId = ref<string | null>(null);
const items = ref<UpdateLogItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);

const formState = reactive<{
  title: string;
  content: string;
  tag_type: UpdateLogTagType;
  effective_at: Dayjs | null;
}>({
  title: "",
  content: "",
  tag_type: "feature",
  effective_at: null,
});

const columns = [
  { title: "标签", dataIndex: "tag_type", width: 120 },
  { title: "标题", dataIndex: "title", width: 240, ellipsis: true },
  { title: "内容摘要", dataIndex: "content", width: 420, ellipsis: true },
  { title: "生效时间", dataIndex: "effective_at", width: 180 },
  { title: "更新时间", dataIndex: "updated_at", width: 180 },
  { title: "操作", key: "actions", width: 140, fixed: "right" as const },
];

const tagOptions: Array<{ label: string; value: UpdateLogTagType }> = [
  { label: "通知", value: "notice" },
  { label: "新功能", value: "feature" },
  { label: "优化", value: "optimization" },
  { label: "Bug修复", value: "bugfix" },
  { label: "其他调整", value: "other" },
];

const formTitle = computed(() => (editingId.value ? "编辑更新日志" : "新增更新日志"));

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function tagLabel(tag: UpdateLogTagType) {
  return tagOptions.find((item) => item.value === tag)?.label || "其他调整";
}

function tagColor(tag: UpdateLogTagType) {
  if (tag === "notice") return "purple";
  if (tag === "feature") return "green";
  if (tag === "optimization") return "blue";
  if (tag === "bugfix") return "red";
  return "gold";
}

function handleSelectTag({ key }: { key: string }) {
  formState.tag_type = key as UpdateLogTagType;
}

function resetForm() {
  editingId.value = null;
  formState.title = "";
  formState.content = "";
  formState.tag_type = "feature";
  formState.effective_at = null;
}

async function load() {
  loading.value = true;
  try {
    const res = await listAdminUpdateLogs(page.value, pageSize.value);
    items.value = res.items;
    total.value = res.total;
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取更新日志失败");
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  resetForm();
  modalOpen.value = true;
}

function openEdit(item: UpdateLogItem) {
  editingId.value = item.log_id;
  formState.title = item.title;
  formState.content = item.content;
  formState.tag_type = item.tag_type;
  formState.effective_at = item.effective_at ? dayjs(item.effective_at) : null;
  modalOpen.value = true;
}

function buildPayload(): UpdateLogPayload {
  return {
    title: formState.title.trim(),
    content: formState.content.trim(),
    tag_type: formState.tag_type,
    effective_at: formState.effective_at ? formState.effective_at.format("YYYY-MM-DDTHH:mm:ss") : null,
  };
}

async function handleSave() {
  if (!formState.title.trim()) {
    message.warning("请输入标题");
    return;
  }
  if (!formState.content.trim()) {
    message.warning("请输入内容");
    return;
  }
  saving.value = true;
  try {
    const payload = buildPayload();
    if (editingId.value) {
      await updateAdminUpdateLog(editingId.value, payload);
      message.success("更新日志更新成功");
    } else {
      await createAdminUpdateLog(payload);
      message.success("更新日志创建成功");
    }
    modalOpen.value = false;
    resetForm();
    page.value = 1;
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || (editingId.value ? "更新失败" : "创建失败"));
  } finally {
    saving.value = false;
  }
}

function handleDelete(item: UpdateLogItem) {
  Modal.confirm({
    title: `删除更新日志「${item.title}」？`,
    content: "删除后将无法在前台更新日志中查看。",
    centered: true,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      await deleteAdminUpdateLog(item.log_id);
      message.success("更新日志已删除");
      await load();
    },
  });
}

function handlePageChange(nextPage: number, nextPageSize: number) {
  page.value = nextPage;
  pageSize.value = nextPageSize;
  void load();
}

onMounted(() => {
  void load();
});
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <BellOutlined />
        </div>
        <div>
          <div class="warm-page-title">更新日志</div>
          <div class="warm-page-desc">维护面向用户展示的版本更新说明，支持手动设置生效时间。</div>
        </div>
      </div>
      <div class="page-actions">
        <a-button class="warm-secondary-btn" @click="load">
          <template #icon><ReloadOutlined /></template>
          刷新列表
        </a-button>
        <a-button type="primary" class="warm-primary-btn" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新增更新日志
        </a-button>
      </div>
    </div>

    <div class="warm-card warm-table-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <a-table
        :columns="columns"
        :data-source="items"
        :loading="loading"
        row-key="log_id"
        :pagination="{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          onChange: handlePageChange,
          onShowSizeChange: handlePageChange,
        }"
        :scroll="{ x: 1260 }"
        class="admin-mobile-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'tag_type'">
            <a-tag class="warm-tag" :color="tagColor(record.tag_type)">
              {{ tagLabel(record.tag_type) }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'content'">
            <a-tooltip :title="record.content || '-'">
              <div class="content-summary">{{ record.content || "-" }}</div>
            </a-tooltip>
          </template>
          <template v-else-if="column.dataIndex === 'effective_at'">
            {{ formatTime(record.effective_at) }}
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
      <a-form layout="vertical" class="update-log-form">
        <div class="form-grid">
          <a-form-item label="标签类型" required>
            <a-dropdown trigger="click">
              <button type="button" class="tag-picker-trigger">
                <a-tag class="warm-tag" :color="tagColor(formState.tag_type)">
                  {{ tagLabel(formState.tag_type) }}
                </a-tag>
                <DownOutlined class="tag-picker-caret" />
              </button>
              <template #overlay>
                <a-menu @click="handleSelectTag">
                  <a-menu-item v-for="option in tagOptions" :key="option.value">
                    <a-tag class="warm-tag" :color="tagColor(option.value)">
                      {{ option.label }}
                    </a-tag>
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </a-form-item>
          <a-form-item label="生效时间">
            <a-date-picker
              v-model:value="formState.effective_at"
              show-time
              class="full-width"
              placeholder="留空则默认使用创建时间"
            />
          </a-form-item>
        </div>
        <a-form-item label="标题" required>
          <a-input v-model:value="formState.title" class="warm-input" :maxlength="200" show-count placeholder="请输入更新日志标题" />
        </a-form-item>
        <a-form-item label="内容" required>
          <a-textarea
            v-model:value="formState.content"
            class="warm-textarea"
            :rows="8"
            :maxlength="10000"
            show-count
            placeholder="请输入更新日志内容，支持多段纯文本。"
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

.content-summary {
  max-width: 380px;
  overflow: hidden;
  color: var(--theme-muted-text);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.table-actions {
  display: inline-flex;
  align-items: center;
}

.update-log-form {
  padding-top: 8px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

.full-width {
  width: 100%;
}

.tag-picker-trigger {
  width: 100%;
  min-height: 40px;
  padding: 8px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--theme-control-border);
  border-radius: 12px;
  background: var(--theme-control-bg);
  cursor: pointer;
}

.tag-picker-caret {
  color: var(--theme-muted-text);
  font-size: 12px;
}

.warm-textarea {
  :deep(textarea) {
    border-radius: 16px;
    border-color: var(--theme-control-border);
    background: var(--theme-control-bg);
  }
}

@media (max-width: 768px) {
  .page-actions {
    width: 100%;
    flex-direction: column;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
