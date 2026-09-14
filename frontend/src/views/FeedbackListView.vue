<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { CopyOutlined, MessageOutlined, UndoOutlined } from "@ant-design/icons-vue";
import FeedbackDetailDrawer from "@/components/feedback/FeedbackDetailDrawer.vue";
import { message } from "ant-design-vue";
import dayjs from "dayjs";
import { listMyFeedbacks, markAllMyFeedbackAsRead, markMyFeedbackAsRead } from "@/api/feedback";
import { copyText as copyToClipboard } from "@/lib/clipboard";
import { setStoredUserCompletedUnreadFeedbackCount } from "@/lib/userFeedbackNotice";
import type { FeedbackItem, FeedbackStatus } from "@/types";

const loading = ref(false);
const items = ref<FeedbackItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const readSubmitting = ref<string | null>(null);
const readAllLoading = ref(false);
const detailDrawerOpen = ref(false);
const activeFeedbackId = ref<string | null>(null);

const filters = reactive<{
  status: FeedbackStatus | undefined;
}>({
  status: undefined,
});

const columns = [
  { title: "反馈编号", dataIndex: "feedback_id", width: 220 },
  { title: "反馈内容", dataIndex: "content", width: 260, ellipsis: true },
  { title: "处理进度", dataIndex: "process_note", width: 260, ellipsis: true },
  { title: "处理结果", dataIndex: "result_note", width: 260, ellipsis: true },
  { title: "状态", dataIndex: "status", width: 120 },
  { title: "阅读状态", dataIndex: "is_read", width: 110 },
  { title: "更新时间", dataIndex: "updated_at", width: 180 },
  { title: "操作", key: "actions", width: 100, fixed: "right" as const },
];

const activeFilterSummary = computed(() => {
  const chips: string[] = [];
  if (filters.status) chips.push(statusLabel(filters.status));
  return chips;
});

function statusLabel(status: FeedbackStatus) {
  return {
    pending: "待处理",
    processing: "处理中",
    completed: "已完成",
  }[status];
}

function statusColor(status: FeedbackStatus) {
  return {
    pending: "gold",
    processing: "blue",
    completed: "green",
  }[status];
}

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

async function copyFeedbackId(feedbackId: string) {
  try {
    await copyToClipboard(feedbackId);
    message.success("反馈编号已复制");
  } catch {
    message.error("复制失败，请重试");
  }
}

async function load() {
  loading.value = true;
  try {
    const res = await listMyFeedbacks(page.value, pageSize.value, {
      status: filters.status,
    });
    items.value = res.items;
    total.value = res.total;
  } catch {
    message.error("获取我的反馈失败");
  } finally {
    loading.value = false;
  }
}

function openDetail(feedbackId: string) {
  activeFeedbackId.value = feedbackId;
  detailDrawerOpen.value = true;
}

function handleDrawerChanged() {
  void load();
}

async function handleMarkRead(record: FeedbackItem) {
  if (record.is_read) return;
  readSubmitting.value = record.feedback_id;
  try {
    const updated = await markMyFeedbackAsRead(record.feedback_id);
    items.value = items.value.map((item) => (item.feedback_id === updated.feedback_id ? updated : item));
    setStoredUserCompletedUnreadFeedbackCount(
      Math.max(0, items.value.filter((item) => item.status === "completed" && !item.is_read).length),
    );
    message.success("已标记为已读");
  } catch {
    message.error("更新已读状态失败");
  } finally {
    readSubmitting.value = null;
  }
}

async function handleMarkAllRead() {
  readAllLoading.value = true;
  try {
    const res = await markAllMyFeedbackAsRead();
    items.value = items.value.map((item) => ({ ...item, is_read: true }));
    setStoredUserCompletedUnreadFeedbackCount(0);
    message.success(res.count > 0 ? `已将 ${res.count} 条反馈标记为已读` : "没有未读反馈");
  } catch {
    message.error("一键已读失败");
  } finally {
    readAllLoading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  void load();
}

function handleReset() {
  filters.status = undefined;
  page.value = 1;
  void load();
}

function handlePageChange(nextPage: number, nextPageSize: number) {
  page.value = nextPage;
  pageSize.value = nextPageSize;
  void load();
}

onMounted(load);
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <MessageOutlined />
        </div>
        <div>
          <div class="warm-page-title">我的反馈</div>
          <div class="warm-page-desc">查看已提交的任务反馈、处理进度与最终结果。</div>
        </div>
      </div>
      <div class="feedback-total">共 {{ total }} 条反馈</div>
    </div>

    <div class="warm-card filter-bar motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <a-select v-model:value="filters.status" allow-clear placeholder="反馈状态" class="filter-select warm-select">
        <a-select-option value="pending">待处理</a-select-option>
        <a-select-option value="processing">处理中</a-select-option>
        <a-select-option value="completed">已完成</a-select-option>
      </a-select>
      <a-button type="primary" class="warm-primary-btn" @click="handleSearch">查询</a-button>
      <a-button class="filter-secondary-btn" :loading="readAllLoading" @click="handleMarkAllRead">一键已读</a-button>
      <a-button class="filter-reset-btn" @click="handleReset">
        <template #icon><UndoOutlined /></template>
        重置
      </a-button>
      <div class="filter-summary">
        <span v-if="activeFilterSummary.length">{{ activeFilterSummary.join(" / ") }}</span>
        <span v-else>全部反馈</span>
      </div>
    </div>

    <div class="warm-card warm-table-card motion-fade-up motion-card-lift" style="--motion-delay: 200ms">
      <a-table
        :columns="columns"
        :data-source="items"
        :loading="loading"
        row-key="feedback_id"
        :pagination="{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          onChange: handlePageChange,
          onShowSizeChange: handlePageChange,
        }"
        :scroll="{ x: 1280 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'feedback_id'">
            <div class="id-cell">
              <a-tooltip :title="record.feedback_id">
                <div class="id-cell-text">{{ record.feedback_id }}</div>
              </a-tooltip>
              <a-button type="text" size="small" class="copy-id-btn" @click="copyFeedbackId(record.feedback_id)">
                <template #icon><CopyOutlined /></template>
              </a-button>
            </div>
          </template>
          <template v-else-if="column.dataIndex === 'content'">
            <a-tooltip :title="record.content || '-'">
              <div class="content-cell clamp-text">{{ record.content || "-" }}</div>
            </a-tooltip>
          </template>
          <template v-else-if="column.dataIndex === 'process_note'">
            <a-tooltip :title="record.process_note || '暂未更新处理进度'">
              <div class="content-cell muted-cell clamp-text">{{ record.process_note || "暂未更新处理进度" }}</div>
            </a-tooltip>
          </template>
          <template v-else-if="column.dataIndex === 'result_note'">
            <a-tooltip :title="record.result_note || '暂未填写处理结果'">
              <div class="content-cell muted-cell clamp-text">{{ record.result_note || "暂未填写处理结果" }}</div>
            </a-tooltip>
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <a-tag class="warm-tag" :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'is_read'">
            <a-tag class="warm-tag" :color="record.is_read ? 'green' : 'orange'">
              {{ record.is_read ? "已读" : "未读" }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'updated_at'">
            {{ formatTime(record.updated_at) }}
          </template>
          <template v-else-if="column.key === 'actions'">
            <div class="action-group">
              <a-button type="link" class="mark-read-btn" @click="openDetail(record.feedback_id)">详情</a-button>
              <a-button
                v-if="!record.is_read"
                type="link"
                class="mark-read-btn"
                :loading="readSubmitting === record.feedback_id"
                @click="handleMarkRead(record)"
              >
                已读
              </a-button>
            </div>
          </template>
        </template>
      </a-table>
    </div>

    <FeedbackDetailDrawer
      v-model:open="detailDrawerOpen"
      :feedback-id="activeFeedbackId"
      mode="user"
      @changed="handleDrawerChanged"
    />
  </div>
</template>

<style scoped lang="scss">
.feedback-total {
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 600;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.filter-select {
  width: 160px;
}

.filter-reset-btn {
  height: 36px;
  border-radius: 12px;
  border: 1px solid var(--theme-panel-border-strong) !important;
  background: var(--theme-panel-bg-strong) !important;
  color: var(--theme-accent-text) !important;
}

.filter-secondary-btn {
  height: 36px;
  border-radius: 12px;
}

.filter-summary {
  margin-left: auto;
  color: var(--text-secondary);
  font-size: 14px;
}

.content-cell {
  max-width: 420px;
  color: var(--theme-title);
  line-height: 1.7;
  word-break: break-word;
}

.clamp-text {
  display: -webkit-box;
  overflow: hidden;
  text-overflow: ellipsis;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.muted-cell {
  color: var(--theme-text-secondary);
}

.id-cell {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
}

.id-cell-text {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--theme-accent-text);
  font-weight: 600;
}

.copy-id-btn {
  width: 24px;
  min-width: 24px;
  height: 24px;
  padding: 0 !important;
  color: var(--theme-accent-text) !important;
}

.warm-tag {
  border-radius: 999px;
  font-weight: 600;
}

.mark-read-btn {
  padding-inline: 0;
  font-weight: 600;
}

.action-placeholder {
  color: var(--theme-text-secondary);
}

@media (max-width: 768px) {
  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-select {
    width: 100%;
  }

  .filter-summary {
    margin-left: 0;
  }
}
</style>
