<script setup lang="ts">
import { reactive, ref, onMounted } from "vue";
import { message, Modal } from "ant-design-vue";
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";
import {
  BookOutlined,
  CopyOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  KeyOutlined,
  PlusOutlined,
} from "@ant-design/icons-vue";
import {
  createUserApiKey,
  deleteUserApiKey,
  listUserApiKeys,
  updateUserApiKey,
} from "@/api/userApiKeys";
import type { UserApiKey, UserApiKeyStatus } from "@/types";

const loading = ref(false);
const saving = ref(false);
const items = ref<UserApiKey[]>([]);
const modalOpen = ref(false);
const editingItem = ref<UserApiKey | null>(null);
const visibleKeyIds = ref(new Set<number>());

const form = reactive({
  key_name: "",
  status: "enabled" as UserApiKeyStatus,
  expire_time: null as Dayjs | null,
});

const columns = [
  { title: "名称", dataIndex: "key_name", width: 180 },
  { title: "API Key", dataIndex: "api_key", width: 360 },
  { title: "状态", dataIndex: "status", width: 100 },
  { title: "过期时间", dataIndex: "expire_time", width: 170 },
  { title: "创建时间", dataIndex: "created_at", width: 170 },
  { title: "操作", key: "action", width: 190 },
];

onMounted(load);

async function load() {
  loading.value = true;
  try {
    const res = await listUserApiKeys();
    items.value = res.items;
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取 API Key 失败");
  } finally {
    loading.value = false;
  }
}

function openCreateModal() {
  editingItem.value = null;
  form.key_name = "";
  form.status = "enabled";
  form.expire_time = null;
  modalOpen.value = true;
}

function openEditModal(item: UserApiKey) {
  editingItem.value = item;
  form.key_name = item.key_name || "";
  form.status = item.status;
  form.expire_time = item.expire_time ? dayjs(item.expire_time) : null;
  modalOpen.value = true;
}

async function handleSave() {
  saving.value = true;
  try {
    const payload = {
      key_name: form.key_name.trim(),
      status: form.status,
      expire_time: form.expire_time ? form.expire_time.format("YYYY-MM-DDTHH:mm:ss") : null,
    };
    if (editingItem.value) {
      await updateUserApiKey(editingItem.value.id, payload);
      message.success("API Key 已更新");
    } else {
      const created = await createUserApiKey(payload);
      message.success("API Key 已创建");
      await copyText(created.api_key, "新 API Key 已复制");
    }
    modalOpen.value = false;
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "保存 API Key 失败");
  } finally {
    saving.value = false;
  }
}

async function toggleStatus(item: UserApiKey) {
  const nextStatus: UserApiKeyStatus = item.status === "enabled" ? "disabled" : "enabled";
  try {
    await updateUserApiKey(item.id, { status: nextStatus });
    message.success(nextStatus === "enabled" ? "API Key 已启用" : "API Key 已禁用");
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "状态更新失败");
  }
}

function confirmDelete(item: UserApiKey) {
  Modal.confirm({
    title: "删除 API Key",
    content: `确认删除「${item.key_name || item.api_key}」吗？删除后该 Key 将无法继续调用 API。`,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      await deleteUserApiKey(item.id);
      message.success("API Key 已删除");
      await load();
    },
  });
}

async function copyText(text: string, successText = "API Key 已复制") {
  try {
    await navigator.clipboard.writeText(text);
    message.success(successText);
  } catch {
    message.error("复制失败，请手动复制");
  }
}

function isKeyVisible(id: number) {
  return visibleKeyIds.value.has(id);
}

function toggleKeyVisible(id: number) {
  const next = new Set(visibleKeyIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  visibleKeyIds.value = next;
}

function maskedKey(apiKey: string) {
  if (!apiKey) return "";
  return "*".repeat(apiKey.length);
}

function fmtTime(t?: string | null) {
  return t
    ? new Date(t).toLocaleString("zh-CN", {
        timeZone: "Asia/Shanghai",
        hour12: false,
      })
    : "永不过期";
}

function openApiDocs() {
  window.open("https://80ai.net/docs-api/", "_blank", "noopener,noreferrer");
}
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <KeyOutlined />
        </div>
        <div>
          <div class="warm-page-title">API 调用</div>
          <div class="warm-page-desc">创建和管理你的 API 调用密钥</div>
        </div>
      </div>
      <a-space>
        <a-button class="warm-secondary-btn" @click="openApiDocs">
          <template #icon><BookOutlined /></template>
          接口文档
        </a-button>
        <a-button type="primary" class="warm-primary-btn" @click="openCreateModal">
          <template #icon><PlusOutlined /></template>
          新建 Key
        </a-button>
      </a-space>
    </div>

    <div class="warm-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <a-alert
        show-icon
        type="warning"
        message="请妥善保管 API Key"
        description="API Key 默认隐藏展示，任何持有该 Key 的调用方都可以消耗你的账号积分。"
        class="api-key-alert"
      />
      <a-table
        :columns="columns"
        :data-source="items"
        :loading="loading"
        :row-key="(record: UserApiKey) => record.id"
        :pagination="false"
        :scroll="{ x: 1100 }"
        class="warm-table api-key-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'api_key'">
            <div class="key-cell">
              <code>{{ isKeyVisible(record.id) ? record.api_key : maskedKey(record.api_key) }}</code>
              <a-button class="warm-soft-btn key-icon-btn" size="small" @click="toggleKeyVisible(record.id)">
                <template #icon>
                  <EyeInvisibleOutlined v-if="isKeyVisible(record.id)" />
                  <EyeOutlined v-else />
                </template>
              </a-button>
              <a-button class="warm-soft-btn key-icon-btn" size="small" title="复制 API Key" @click="copyText(record.api_key)">
                <template #icon><CopyOutlined /></template>
              </a-button>
            </div>
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <a-tag :color="record.status === 'enabled' ? 'green' : 'default'">
              {{ record.status === "enabled" ? "启用" : "禁用" }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'expire_time'">
            {{ fmtTime(record.expire_time) }}
          </template>
          <template v-else-if="column.dataIndex === 'created_at'">
            {{ record.created_at ? fmtTime(record.created_at) : "-" }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space size="small">
              <a-button size="small" class="warm-soft-btn key-action-btn" @click="openEditModal(record)">编辑</a-button>
              <a-button size="small" class="warm-soft-btn key-action-btn" @click="toggleStatus(record)">
                {{ record.status === "enabled" ? "禁用" : "启用" }}
              </a-button>
              <a-button size="small" class="warm-danger-btn key-action-btn" danger @click="confirmDelete(record)">删除</a-button>
            </a-space>
          </template>
        </template>
      </a-table>
    </div>

    <a-modal
      v-model:open="modalOpen"
      :title="editingItem ? '编辑 API Key' : '新建 API Key'"
      :confirm-loading="saving"
      ok-text="保存"
      cancel-text="取消"
      @ok="handleSave"
    >
      <a-form layout="vertical">
        <a-form-item label="名称">
          <a-input v-model:value="form.key_name" maxlength="100" placeholder="例如：生产环境调用" />
        </a-form-item>
        <a-form-item label="状态">
          <a-select v-model:value="form.status">
            <a-select-option value="enabled">启用</a-select-option>
            <a-select-option value="disabled">禁用</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="过期时间">
          <a-date-picker
            v-model:value="form.expire_time"
            show-time
            allow-clear
            format="YYYY-MM-DD HH:mm:ss"
            placeholder="不设置则永不过期"
            style="width: 100%"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.api-key-alert {
  margin-bottom: 16px;
}

.api-key-table {
  width: 100%;
  border-radius: 16px;
  overflow: hidden;
}

.api-key-table :deep(.ant-table-container),
.api-key-table :deep(.ant-table-content),
.api-key-table :deep(.ant-table) {
  border-radius: 16px;
  overflow: hidden;
}

.api-key-table :deep(.ant-table-thead > tr > th:first-child) {
  border-start-start-radius: 16px;
}

.api-key-table :deep(.ant-table-thead > tr > th:last-child) {
  border-start-end-radius: 16px;
}

.key-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.key-cell code {
  min-width: 300px;
  padding: 3px 8px;
  border-radius: 8px;
  background: rgba(31, 41, 55, 0.06);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  word-break: break-all;
}

.key-icon-btn {
  width: 30px;
  padding-inline: 0;
}

.key-action-btn {
  height: 26px;
  padding: 0 8px;
  font-size: 12px;
  border-radius: 8px;
}
</style>
