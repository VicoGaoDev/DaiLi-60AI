<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { CopyOutlined, MessageOutlined, SearchOutlined, UndoOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import dayjs from "dayjs";
import { listAdminFeedbacks } from "@/api/admin";
import AdminUserInfoDialog from "@/components/admin/AdminUserInfoDialog.vue";
import FeedbackDetailDrawer from "@/components/feedback/FeedbackDetailDrawer.vue";
import { getAvatarImageSrc } from "@/api/images";
import type { AdminUser, FeedbackItem, FeedbackStatus, FeedbackType } from "@/types";

const loading = ref(false);
const items = ref<FeedbackItem[]>([]);
const users = ref<AdminUser[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const userInfoOpen = ref(false);
const userInfoTarget = ref<AdminUser | null>(null);
const detailDrawerOpen = ref(false);
const activeFeedbackId = ref<string | null>(null);

const filters = reactive<{
  feedback_id: string;
  user_id: string;
  task_id: string;
  status: FeedbackStatus | undefined;
  feedback_type: FeedbackType | undefined;
}>({
  feedback_id: "",
  user_id: "",
  task_id: "",
  status: undefined,
  feedback_type: undefined,
});

const columns = [
  { title: "反馈编号", dataIndex: "feedback_id", width: 220 },
  { title: "用户", dataIndex: "username", width: 140 },
  { title: "类型", dataIndex: "feedback_type", width: 140 },
  { title: "反馈内容", dataIndex: "content", width: 240, ellipsis: true },
  { title: "处理进度", dataIndex: "process_note", width: 240, ellipsis: true },
  { title: "处理结果", dataIndex: "result_note", width: 240, ellipsis: true },
  { title: "状态", dataIndex: "status", width: 120 },
  { title: "更新时间", dataIndex: "updated_at", width: 180 },
  { title: "操作", key: "action", width: 120, fixed: "right" as const },
];

function findAdminUser(userId?: string | null) {
  if (!userId) return null;
  return users.value.find((item) => item.id === userId) || null;
}

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

function feedbackTypeLabel(feedbackType: FeedbackType) {
  return {
    general: "通用反馈",
    image_task: "图片任务反馈",
    video_task: "视频任务反馈",
    canvas: "Canvas反馈",
    purchase: "购买积分反馈",
    feature_request: "加新功能",
    bug_report: "我要提BUG",
    optimization: "优化建议",
  }[feedbackType];
}

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

async function copyFeedbackId(feedbackId: string) {
  try {
    await navigator.clipboard.writeText(feedbackId);
    message.success("反馈编号已复制");
  } catch {
    message.error("复制失败，请重试");
  }
}

async function load() {
  loading.value = true;
  try {
    const res = await listAdminFeedbacks(page.value, pageSize.value, {
      feedback_id: filters.feedback_id.trim() || undefined,
      user_id: filters.user_id.trim() || undefined,
      task_id: filters.task_id.trim() || undefined,
      status: filters.status,
      feedback_type: filters.feedback_type,
    });
    items.value = res.items;
    total.value = res.total;
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取 用户反馈 失败");
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  void load();
}

function handleReset() {
  filters.feedback_id = "";
  filters.user_id = "";
  filters.task_id = "";
  filters.status = undefined;
  filters.feedback_type = undefined;
  page.value = 1;
  void load();
}

function handlePageChange(nextPage: number, nextPageSize: number) {
  page.value = nextPage;
  pageSize.value = nextPageSize;
  void load();
}

function openDetail(feedbackId: string) {
  activeFeedbackId.value = feedbackId;
  detailDrawerOpen.value = true;
}

function handleDrawerChanged() {
  void load();
}

function openUserInfo(record: FeedbackItem) {
  const matchedUser = findAdminUser(record.user_id);
  userInfoTarget.value = matchedUser || {
    id: record.user_id,
    username: record.username || "未知用户",
    email: "",
    avatar_url: "",
    role: "user",
    status: "active",
    is_whitelisted: false,
    credits: 0,
    consumed_credits: 0,
    created_at: "",
  };
  userInfoOpen.value = true;
}

onMounted(async () => {
  await load();
});
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <MessageOutlined />
        </div>
        <div>
          <div class="warm-page-title">用户反馈</div>
          <div class="warm-page-desc">查看所有用户反馈并按用户、任务和状态筛选。</div>
        </div>
      </div>
      <div class="feedback-total">共 {{ total }} 条反馈</div>
    </div>

    <div class="warm-card filter-bar motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <a-input
        v-model:value="filters.feedback_id"
        allow-clear
        placeholder="按反馈编号筛选"
        class="filter-input warm-input"
        @press-enter="handleSearch"
      >
        <template #prefix><SearchOutlined /></template>
      </a-input>
      <a-input
        v-model:value="filters.user_id"
        allow-clear
        placeholder="按用户 ID 筛选"
        class="filter-input warm-input"
        @press-enter="handleSearch"
      >
        <template #prefix><SearchOutlined /></template>
      </a-input>
      <a-input
        v-model:value="filters.task_id"
        allow-clear
        placeholder="按任务 ID 筛选"
        class="filter-input warm-input"
        @press-enter="handleSearch"
      >
        <template #prefix><SearchOutlined /></template>
      </a-input>
      <a-select v-model:value="filters.status" allow-clear placeholder="反馈状态" class="filter-select warm-select">
        <a-select-option value="pending">待处理</a-select-option>
        <a-select-option value="processing">处理中</a-select-option>
        <a-select-option value="completed">已完成</a-select-option>
      </a-select>
      <a-select v-model:value="filters.feedback_type" allow-clear placeholder="反馈类型" class="filter-select warm-select">
        <a-select-option value="general">通用反馈</a-select-option>
        <a-select-option value="image_task">图片任务反馈</a-select-option>
        <a-select-option value="video_task">视频任务反馈</a-select-option>
        <a-select-option value="canvas">Canvas反馈</a-select-option>
        <a-select-option value="purchase">购买积分反馈</a-select-option>
        <a-select-option value="feature_request">加新功能</a-select-option>
        <a-select-option value="bug_report">我要提BUG</a-select-option>
        <a-select-option value="optimization">优化建议</a-select-option>
      </a-select>
      <a-button type="primary" class="warm-primary-btn" @click="handleSearch">查询</a-button>
      <a-button class="filter-reset-btn" @click="handleReset">
        <template #icon><UndoOutlined /></template>
        重置
      </a-button>
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
        :scroll="{ x: 1520 }"
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
          <template v-else-if="column.dataIndex === 'username'">
            <div class="user-cell">
              <button
                type="button"
                class="user-avatar-btn"
                title="查看用户信息"
                @click="openUserInfo(record)"
              >
                <a-avatar :size="28" :src="getAvatarImageSrc(findAdminUser(record.user_id)?.avatar_url) || undefined" class="user-avatar">
                  {{ record.username?.charAt(0)?.toUpperCase() }}
                </a-avatar>
              </button>
              <span class="user-name">{{ record.username || "-" }}</span>
            </div>
          </template>
          <template v-else-if="column.dataIndex === 'content'">
            <div class="content-cell">{{ record.content }}</div>
          </template>
          <template v-else-if="column.dataIndex === 'feedback_type'">
            <a-tag class="warm-tag" color="geekblue">{{ feedbackTypeLabel(record.feedback_type) }}</a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'process_note'">
            <div class="content-cell muted-cell">{{ record.process_note || "暂未更新处理进度" }}</div>
          </template>
          <template v-else-if="column.dataIndex === 'result_note'">
            <div class="content-cell muted-cell">{{ record.result_note || "暂未填写处理结果" }}</div>
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <a-tag class="warm-tag" :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'updated_at'">
            {{ formatTime(record.updated_at) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-button type="link" class="view-btn" @click="openDetail(record.feedback_id)">查看详情</a-button>
          </template>
        </template>
      </a-table>
    </div>

    <AdminUserInfoDialog v-model:open="userInfoOpen" :user="userInfoTarget" />
    <FeedbackDetailDrawer
      v-model:open="detailDrawerOpen"
      :feedback-id="activeFeedbackId"
      mode="admin"
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

.filter-input {
  width: 220px;
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

.content-cell {
  max-width: 420px;
  color: var(--theme-title);
  line-height: 1.7;
  word-break: break-word;
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.user-avatar {
  flex: 0 0 auto;
  background: linear-gradient(180deg, var(--theme-brand-bg-start), var(--theme-brand-bg-end));
  color: var(--theme-accent-contrast);
  font-weight: 700;
}

.user-avatar-btn {
  appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  padding: 0;
  margin: 0;
  background: transparent;
  line-height: 0;
  cursor: pointer;
  border-radius: 999px;

  &:focus-visible {
    outline: 2px solid rgba(255, 171, 37, 0.8);
    outline-offset: 2px;
  }
}

.user-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

.view-btn {
  padding-inline: 0;
  color: var(--theme-link) !important;
  font-weight: 600;
}

@media (max-width: 768px) {
  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-input,
  .filter-select {
    width: 100%;
  }
}
</style>
