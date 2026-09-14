<script setup lang="ts">
import "@wangeditor/editor/dist/css/style.css";

import { computed, onBeforeUnmount, onMounted, reactive, ref, shallowRef } from "vue";
import { Editor, Toolbar } from "@wangeditor/editor-for-vue";
import type { IDomEditor, IEditorConfig, IToolbarConfig } from "@wangeditor/editor";
import { MailOutlined, PlusOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import dayjs from "dayjs";
import { listUserOptions } from "@/api/admin";
import { createAdminSystemMessage, getAdminSystemMessageDetail, listAdminSystemMessages } from "@/api/systemMessages";
import type { AdminUser, SystemMessageDetail, SystemMessageItem, SystemMessageRecipientScope } from "@/types";

const loading = ref(false);
const submitting = ref(false);
const modalOpen = ref(false);
const detailOpen = ref(false);
const detailLoading = ref(false);
const detail = ref<SystemMessageDetail | null>(null);
const items = ref<SystemMessageItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const users = ref<AdminUser[]>([]);
const usersLoading = ref(false);
const editorRef = shallowRef<IDomEditor>();

const form = reactive({
  subject: "",
  contentHtml: "",
  recipientScope: "selected" as SystemMessageRecipientScope,
  recipientUserIds: [] as string[],
});

const columns = [
  { title: "主题", dataIndex: "subject", width: 260, ellipsis: true },
  { title: "发送人", dataIndex: "sender", width: 120 },
  { title: "接收范围", dataIndex: "recipient_scope", width: 120 },
  { title: "接收人数", dataIndex: "recipient_count", width: 100 },
  { title: "摘要", dataIndex: "content_text", width: 320, ellipsis: true },
  { title: "发送时间", dataIndex: "created_at", width: 180 },
  { title: "操作", key: "actions", width: 110, fixed: "right" as const },
];

const toolbarConfig: Partial<IToolbarConfig> = {
  excludeKeys: ["uploadVideo", "insertVideo", "fullScreen"],
};

const editorConfig: Partial<IEditorConfig> = {
  placeholder: "请输入系统消息正文，可使用标题、列表、加粗、链接等富文本格式",
  MENU_CONF: {
    uploadImage: {
      allowedFileTypes: ["image/*"],
      maxFileSize: 10 * 1024 * 1024,
      async customUpload(file: File, insertFn: (url: string, alt?: string, href?: string) => void) {
        try {
          insertFn(await fileToDataUrl(file), file.name);
        } catch {
          message.error("图片读取失败，请重试");
        }
      },
    },
    insertLink: {
      checkLink: (text: string, url: string) => {
        if (!/^https?:\/\//i.test(url) && !/^mailto:/i.test(url)) {
          return "链接需以 http://、https:// 或 mailto: 开头";
        }
        return true;
      },
    },
  },
};

const userOptions = computed(() =>
  users.value.map((user) => ({
    label: `${user.username}${user.email ? `（${user.email}）` : ""}`,
    value: user.id,
  })),
);

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
        return;
      }
      reject(new Error("invalid file reader result"));
    };
    reader.onerror = () => reject(reader.error || new Error("file read failed"));
    reader.readAsDataURL(file);
  });
}

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function scopeLabel(scope: SystemMessageRecipientScope) {
  return scope === "all" ? "全部用户" : "指定用户";
}

const readCount = computed(() => detail.value?.recipients?.filter((item) => item.is_read).length || 0);

function resetForm() {
  form.subject = "";
  form.contentHtml = "";
  form.recipientScope = "selected";
  form.recipientUserIds = [];
}

async function load() {
  loading.value = true;
  try {
    const res = await listAdminSystemMessages(page.value, pageSize.value);
    items.value = res.items;
    total.value = res.total;
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取系统邮件失败");
  } finally {
    loading.value = false;
  }
}

async function loadUsers() {
  if (users.value.length || usersLoading.value) return;
  usersLoading.value = true;
  try {
    users.value = (await listUserOptions()).filter((user) => user.status === "active");
  } catch {
    message.error("获取用户列表失败");
  } finally {
    usersLoading.value = false;
  }
}

function handleRecipientUserDropdownVisible(open: boolean) {
  if (open) void loadUsers();
}

async function openCreateModal() {
  resetForm();
  modalOpen.value = true;
}

function handlePageChange(nextPage: number, nextPageSize: number) {
  page.value = nextPage;
  pageSize.value = nextPageSize;
  void load();
}

function handleEditorCreated(editor: IDomEditor) {
  editorRef.value = editor;
}

async function openDetail(messageId: string) {
  detailOpen.value = true;
  detailLoading.value = true;
  detail.value = null;
  try {
    detail.value = await getAdminSystemMessageDetail(messageId);
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取系统邮件详情失败");
  } finally {
    detailLoading.value = false;
  }
}

async function handleSubmit() {
  const subject = form.subject.trim();
  const contentText = editorRef.value?.getText().trim() || "";
  if (!subject) {
    message.warning("请填写消息主题");
    return;
  }
  if (!contentText) {
    message.warning("请填写消息内容");
    return;
  }
  if (form.recipientScope === "selected" && !form.recipientUserIds.length) {
    message.warning("请选择接收用户");
    return;
  }

  submitting.value = true;
  try {
    await createAdminSystemMessage({
      subject,
      content_html: form.contentHtml,
      recipient_scope: form.recipientScope,
      recipient_user_ids: form.recipientScope === "selected" ? form.recipientUserIds : [],
    });
    message.success("系统邮件已发送");
    modalOpen.value = false;
    resetForm();
    page.value = 1;
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "发送系统邮件失败");
  } finally {
    submitting.value = false;
  }
}

onMounted(load);

onBeforeUnmount(() => {
  editorRef.value?.destroy();
});
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <MailOutlined />
        </div>
        <div>
          <div class="warm-page-title">系统邮件</div>
          <div class="warm-page-desc">向指定用户或当前全部用户发送单向系统消息。</div>
        </div>
      </div>
      <a-button type="primary" class="warm-primary-btn" @click="openCreateModal">
        <template #icon><PlusOutlined /></template>
        新建系统邮件
      </a-button>
    </div>

    <div class="warm-card warm-table-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <a-table
        :columns="columns"
        :data-source="items"
        :loading="loading"
        row-key="message_id"
        :pagination="{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          onChange: handlePageChange,
          onShowSizeChange: handlePageChange,
        }"
        :scroll="{ x: 1180 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'sender'">
            {{ record.sender?.username || "-" }}
          </template>
          <template v-else-if="column.dataIndex === 'recipient_scope'">
            <a-tag class="warm-tag" :color="record.recipient_scope === 'all' ? 'blue' : 'purple'">
              {{ scopeLabel(record.recipient_scope) }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'content_text'">
            <a-tooltip :title="record.content_text || '-'">
              <div class="message-summary">{{ record.content_text || "-" }}</div>
            </a-tooltip>
          </template>
          <template v-else-if="column.dataIndex === 'created_at'">
            {{ formatTime(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-button type="link" class="view-btn" @click="openDetail(record.message_id)">查看详情</a-button>
          </template>
        </template>
      </a-table>
    </div>

    <a-modal
      v-model:open="modalOpen"
      title="新建系统邮件"
      width="860px"
      :confirm-loading="submitting"
      ok-text="发送"
      cancel-text="取消"
      @ok="handleSubmit"
    >
      <div class="message-form">
        <a-form layout="vertical">
          <a-form-item label="主题" required>
            <a-input v-model:value="form.subject" :maxlength="200" show-count placeholder="请输入消息主题" />
          </a-form-item>
          <a-form-item label="接收范围" required>
            <a-radio-group v-model:value="form.recipientScope">
              <a-radio value="selected">指定用户</a-radio>
              <a-radio value="all">全部用户</a-radio>
            </a-radio-group>
          </a-form-item>
          <a-form-item v-if="form.recipientScope === 'selected'" label="接收用户" required>
            <a-select
              v-model:value="form.recipientUserIds"
              mode="multiple"
              show-search
              :loading="usersLoading"
              :options="userOptions"
              placeholder="请选择一个或多个用户"
              option-filter-prop="label"
              @dropdownVisibleChange="handleRecipientUserDropdownVisible"
            />
          </a-form-item>
          <a-form-item label="消息内容" required>
            <div class="editor-shell">
              <Toolbar
                class="message-toolbar"
                :editor="editorRef"
                :default-config="toolbarConfig"
                mode="default"
              />
              <Editor
                v-model="form.contentHtml"
                class="message-editor"
                :default-config="editorConfig"
                mode="default"
                @on-created="handleEditorCreated"
              />
            </div>
          </a-form-item>
        </a-form>
      </div>
    </a-modal>

    <a-modal
      v-model:open="detailOpen"
      title="系统邮件详情"
      width="900px"
      :footer="null"
    >
      <a-spin :spinning="detailLoading">
        <div v-if="detail" class="detail-modal-content">
          <div class="detail-head">
            <h3>{{ detail.subject }}</h3>
            <div class="detail-meta">
              <span>发送人：80AI管理员</span>
              <span>发送时间：{{ formatTime(detail.created_at) }}</span>
              <span>接收范围：{{ scopeLabel(detail.recipient_scope) }}</span>
              <span>接收人数：{{ detail.recipient_count }}</span>
              <span>已读：{{ readCount }} / {{ detail.recipient_count }}</span>
            </div>
          </div>
          <a-divider />
          <article class="detail-content" v-html="detail.content_html" />
          <a-divider />
          <div class="recipient-section">
            <div class="recipient-title">接收用户</div>
            <div class="recipient-list">
              <a-tag
                v-for="recipient in detail.recipients || []"
                :key="recipient.user_id"
                class="warm-tag"
                :color="recipient.is_read ? 'green' : 'orange'"
              >
                {{ recipient.username || recipient.user_id }} · {{ recipient.is_read ? "已读" : "未读" }}
              </a-tag>
            </div>
          </div>
        </div>
      </a-spin>
    </a-modal>
  </div>
</template>

<style scoped lang="scss">
.message-summary {
  max-width: 300px;
  overflow: hidden;
  color: var(--theme-text);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.message-form {
  padding-top: 6px;
}

.editor-shell {
  overflow: hidden;
  border: 1px solid var(--theme-panel-border-strong);
  border-radius: 14px;
  background: #fff;
}

.message-toolbar {
  border-bottom: 1px solid #f0f0f0;
}

.message-editor {
  min-height: 300px;
}

.detail-modal-content {
  color: var(--theme-text);
}

.detail-head h3 {
  margin: 0 0 12px;
  color: var(--theme-heading);
  font-size: 20px;
  line-height: 1.4;
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  color: var(--theme-muted-text);
  font-size: 13px;
}

.detail-content {
  max-height: 48vh;
  overflow: auto;
  padding-right: 6px;
  color: var(--theme-text);
  font-size: 15px;
  line-height: 1.8;
  word-break: break-word;
}

.detail-content :deep(p) {
  margin: 0 0 12px;
}

.detail-content :deep(h1),
.detail-content :deep(h2),
.detail-content :deep(h3),
.detail-content :deep(h4) {
  margin: 18px 0 10px;
  color: var(--theme-heading);
  line-height: 1.35;
}

.detail-content :deep(ul),
.detail-content :deep(ol) {
  margin: 0 0 14px 22px;
  padding-left: 18px;
}

.detail-content :deep(img) {
  max-width: 100%;
  height: auto;
  margin: 12px 0;
  border-radius: 12px;
}

.recipient-title {
  margin-bottom: 10px;
  color: var(--theme-heading);
  font-weight: 700;
}

.recipient-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-height: 160px;
  overflow: auto;
}
</style>
