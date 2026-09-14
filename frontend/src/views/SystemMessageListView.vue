<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { MailOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import dayjs from "dayjs";
import { listMySystemMessages, markAllMySystemMessagesAsRead } from "@/api/systemMessages";
import { setStoredUnreadSystemMessageCount } from "@/lib/systemMessageNotice";
import type { SystemMessageItem } from "@/types";

const router = useRouter();
const loading = ref(false);
const items = ref<SystemMessageItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const readAllLoading = ref(false);

const columns = [
  { title: "主题", dataIndex: "subject", width: 260, ellipsis: true },
  { title: "摘要", dataIndex: "content_text", width: 360, ellipsis: true },
  { title: "阅读状态", dataIndex: "is_read", width: 110 },
  { title: "发送时间", dataIndex: "created_at", width: 180 },
  { title: "操作", key: "actions", width: 110, fixed: "right" as const },
];

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

async function load() {
  loading.value = true;
  try {
    const res = await listMySystemMessages(page.value, pageSize.value);
    items.value = res.items;
    total.value = res.total;
    setStoredUnreadSystemMessageCount(res.items.filter((item) => !item.is_read).length);
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取系统消息失败");
  } finally {
    loading.value = false;
  }
}

async function handleMarkAllRead() {
  readAllLoading.value = true;
  try {
    const res = await markAllMySystemMessagesAsRead();
    items.value = items.value.map((item) => ({
      ...item,
      is_read: true,
      read_at: item.read_at || new Date().toISOString(),
    }));
    setStoredUnreadSystemMessageCount(0);
    message.success(res.count > 0 ? `已将 ${res.count} 条系统消息标记为已读` : "没有未读系统消息");
  } catch (err: any) {
    message.error(err.response?.data?.detail || "一键已读失败");
  } finally {
    readAllLoading.value = false;
  }
}

function handlePageChange(nextPage: number, nextPageSize: number) {
  page.value = nextPage;
  pageSize.value = nextPageSize;
  void load();
}

function openDetail(messageId: string) {
  router.push(`/system-messages/${messageId}`);
}

onMounted(load);
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <MailOutlined />
        </div>
        <div>
          <div class="warm-page-title">系统消息</div>
          <div class="warm-page-desc">查看平台发送给你的系统邮件和重要通知。</div>
        </div>
      </div>
      <div class="header-actions">
        <a-button class="filter-secondary-btn" :loading="readAllLoading" @click="handleMarkAllRead">
          一键已读
        </a-button>
        <div class="message-total">共 {{ total }} 条消息</div>
      </div>
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
        :row-class-name="(record: SystemMessageItem) => (!record.is_read ? 'unread-row' : '')"
        :scroll="{ x: 1020 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'subject'">
            <div class="subject-cell">
              <span v-if="!record.is_read" class="unread-dot" />
              <span>{{ record.subject }}</span>
            </div>
          </template>
          <template v-else-if="column.dataIndex === 'content_text'">
            <a-tooltip :title="record.content_text || '-'">
              <div class="message-summary">{{ record.content_text || "-" }}</div>
            </a-tooltip>
          </template>
          <template v-else-if="column.dataIndex === 'is_read'">
            <a-tag class="warm-tag" :color="record.is_read ? 'green' : 'orange'">
              {{ record.is_read ? "已读" : "未读" }}
            </a-tag>
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
  </div>
</template>

<style scoped lang="scss">
.message-total {
  color: var(--theme-muted-text);
  font-size: 14px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.subject-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-weight: 700;
}

.unread-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: #ff4d4f;
}

.message-summary {
  max-width: 340px;
  overflow: hidden;
  color: var(--theme-muted-text);
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.unread-row) {
  background: rgba(255, 77, 79, 0.04);
}
</style>
