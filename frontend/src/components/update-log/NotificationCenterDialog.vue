<script setup lang="ts">
import { computed, ref, watch } from "vue";
import dayjs from "dayjs";
import { MessageOutlined, MailOutlined, BellOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import { useRouter } from "vue-router";
import {
  getMyUnreadFeedbackCount,
  listMyFeedbacks,
  markAllMyFeedbackAsRead,
  markMyFeedbackAsRead,
} from "@/api/feedback";
import {
  getMyUnreadSystemMessageCount,
  listMySystemMessages,
  markAllMySystemMessagesAsRead,
} from "@/api/systemMessages";
import { listUpdateLogs } from "@/api/updateLogs";
import FeedbackDetailDrawer from "@/components/feedback/FeedbackDetailDrawer.vue";
import { useAuthStore } from "@/stores/auth";
import type { FeedbackItem, FeedbackStatus, SystemMessageItem, UpdateLogItem, UpdateLogTagType } from "@/types";

type NotificationTabKey = "feedback" | "system-messages" | "update-logs";

const props = defineProps<{
  open: boolean;
  defaultTab?: NotificationTabKey;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  "read-state-change": [];
}>();

const auth = useAuthStore();
const router = useRouter();
const activeTab = ref<NotificationTabKey>(props.defaultTab || "update-logs");

const feedbackLoading = ref(false);
const feedbackItems = ref<FeedbackItem[]>([]);
const feedbackTotal = ref(0);
const feedbackPage = ref(1);
const feedbackPageSize = ref(10);
const feedbackUnreadCount = ref(0);
const feedbackMarkingAllRead = ref(false);
const feedbackDetailDrawerOpen = ref(false);
const activeFeedbackId = ref<string | null>(null);

const systemLoading = ref(false);
const systemItems = ref<SystemMessageItem[]>([]);
const systemTotal = ref(0);
const systemPage = ref(1);
const systemPageSize = ref(10);
const systemUnreadCount = ref(0);
const systemMarkingAllRead = ref(false);

const updateLogLoading = ref(false);
const updateLogItems = ref<UpdateLogItem[]>([]);
const updateLogTotal = ref(0);
const updateLogPage = ref(1);
const updateLogPageSize = ref(10);
const hasRecentUpdateLog = ref(false);

const tabItems = [
  { key: "feedback" as const, label: "我的反馈", icon: MessageOutlined },
  { key: "system-messages" as const, label: "系统消息", icon: MailOutlined },
  { key: "update-logs" as const, label: "更新日志", icon: BellOutlined },
];

const currentPagination = computed(() => {
  if (activeTab.value === "feedback") {
    return { current: feedbackPage.value, pageSize: feedbackPageSize.value, total: feedbackTotal.value };
  }
  if (activeTab.value === "system-messages") {
    return { current: systemPage.value, pageSize: systemPageSize.value, total: systemTotal.value };
  }
  return { current: updateLogPage.value, pageSize: updateLogPageSize.value, total: updateLogTotal.value };
});

function getTabUnreadCount(tabKey: NotificationTabKey) {
  if (tabKey === "feedback") return feedbackUnreadCount.value;
  if (tabKey === "system-messages") return systemUnreadCount.value;
  return 0;
}

function closeDialog() {
  emit("update:open", false);
}

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "-";
}

function feedbackStatusLabel(status: FeedbackStatus) {
  return {
    pending: "待处理",
    processing: "处理中",
    completed: "已完成",
  }[status];
}

function feedbackStatusColor(status: FeedbackStatus) {
  return {
    pending: "gold",
    processing: "blue",
    completed: "green",
  }[status];
}

function updateLogTagLabel(tag: UpdateLogTagType) {
  if (tag === "notice") return "通知";
  if (tag === "feature") return "新功能";
  if (tag === "optimization") return "优化";
  if (tag === "bugfix") return "Bug修复";
  return "其他调整";
}

function updateLogTagColor(tag: UpdateLogTagType) {
  if (tag === "notice") return "purple";
  if (tag === "feature") return "green";
  if (tag === "optimization") return "cyan";
  if (tag === "bugfix") return "red";
  return "gold";
}

function checkRecentUpdateLog(items: UpdateLogItem[]) {
  const latest = items[0];
  if (!latest?.effective_at) {
    hasRecentUpdateLog.value = false;
    return;
  }
  const cutoff = dayjs().subtract(7, "day");
  const latestAt = dayjs(latest.effective_at);
  hasRecentUpdateLog.value = latestAt.isAfter(cutoff) || latestAt.isSame(cutoff);
}

function formatContent(content: string) {
  return (content || "").trim().split(/\n+/).filter(Boolean);
}

async function loadUnreadCounts() {
  if (!auth.isLoggedIn) {
    feedbackUnreadCount.value = 0;
    systemUnreadCount.value = 0;
    return;
  }
  try {
    const [feedbackRes, systemRes] = await Promise.all([
      getMyUnreadFeedbackCount(),
      getMyUnreadSystemMessageCount(),
    ]);
    feedbackUnreadCount.value = Number(feedbackRes.count || 0);
    systemUnreadCount.value = Number(systemRes.count || 0);
  } catch {
    // Keep the last known badge counts when lightweight refresh fails.
  }
}

async function loadFeedbacks() {
  if (!auth.isLoggedIn) {
    feedbackItems.value = [];
    feedbackTotal.value = 0;
    return;
  }
  feedbackLoading.value = true;
  try {
    const res = await listMyFeedbacks(feedbackPage.value, feedbackPageSize.value);
    feedbackItems.value = res.items;
    feedbackTotal.value = res.total;
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取我的反馈失败");
  } finally {
    feedbackLoading.value = false;
  }
}

async function loadSystemMessages() {
  if (!auth.isLoggedIn) {
    systemItems.value = [];
    systemTotal.value = 0;
    return;
  }
  systemLoading.value = true;
  try {
    const res = await listMySystemMessages(systemPage.value, systemPageSize.value);
    systemItems.value = res.items;
    systemTotal.value = res.total;
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取系统消息失败");
  } finally {
    systemLoading.value = false;
  }
}

async function loadUpdateLogs() {
  updateLogLoading.value = true;
  try {
    const res = await listUpdateLogs(updateLogPage.value, updateLogPageSize.value);
    updateLogItems.value = res.items;
    updateLogTotal.value = res.total;
    if (updateLogPage.value === 1) {
      checkRecentUpdateLog(res.items);
    }
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取更新日志失败");
  } finally {
    updateLogLoading.value = false;
  }
}

async function markFeedbacksAllRead() {
  if (!auth.isLoggedIn || feedbackMarkingAllRead.value || feedbackUnreadCount.value <= 0) return;
  feedbackMarkingAllRead.value = true;
  try {
    await markAllMyFeedbackAsRead();
    feedbackUnreadCount.value = 0;
    feedbackItems.value = feedbackItems.value.map((item) => ({ ...item, is_read: true }));
    emit("read-state-change");
    message.success("我的反馈已全部标记为已读");
  } catch (err: any) {
    message.error(err.response?.data?.detail || "标记反馈已读失败");
  } finally {
    feedbackMarkingAllRead.value = false;
  }
}

async function markSystemMessagesAllRead() {
  if (!auth.isLoggedIn || systemMarkingAllRead.value || systemUnreadCount.value <= 0) return;
  systemMarkingAllRead.value = true;
  try {
    await markAllMySystemMessagesAsRead();
    systemUnreadCount.value = 0;
    systemItems.value = systemItems.value.map((item) => ({ ...item, is_read: true }));
    emit("read-state-change");
    message.success("系统消息已全部标记为已读");
  } catch (err: any) {
    message.error(err.response?.data?.detail || "标记系统消息已读失败");
  } finally {
    systemMarkingAllRead.value = false;
  }
}

async function loadRecentUpdateLogState() {
  try {
    const res = await listUpdateLogs(1, 1);
    checkRecentUpdateLog(res.items);
  } catch {
    hasRecentUpdateLog.value = false;
  }
}

function loadActiveTab() {
  if (activeTab.value === "feedback") {
    void loadFeedbacks();
    return;
  }
  if (activeTab.value === "system-messages") {
    void loadSystemMessages();
    return;
  }
  void loadUpdateLogs();
}

function switchTab(key: NotificationTabKey) {
  activeTab.value = key;
}

async function openFeedbackDetail(item: FeedbackItem) {
  if (!item.is_read) {
    try {
      await markMyFeedbackAsRead(item.feedback_id);
      feedbackItems.value = feedbackItems.value.map((feedbackItem) => (
        feedbackItem.feedback_id === item.feedback_id ? { ...feedbackItem, is_read: true } : feedbackItem
      ));
      feedbackUnreadCount.value = Math.max(feedbackUnreadCount.value - 1, 0);
      emit("read-state-change");
    } catch {
      // Reading the detail is still allowed if the read-state update fails.
    }
  }
  activeFeedbackId.value = item.feedback_id;
  feedbackDetailDrawerOpen.value = true;
}

async function handleFeedbackDrawerChanged() {
  emit("read-state-change");
  await Promise.all([loadUnreadCounts(), loadFeedbacks()]);
}

function openSystemMessageDetail(item: SystemMessageItem) {
  closeDialog();
  void router.push(`/system-messages/${item.message_id}`);
}

function handlePageChange(nextPage: number, nextPageSize: number) {
  if (activeTab.value === "feedback") {
    feedbackPage.value = nextPage;
    feedbackPageSize.value = nextPageSize;
    void loadFeedbacks();
    return;
  }
  if (activeTab.value === "system-messages") {
    systemPage.value = nextPage;
    systemPageSize.value = nextPageSize;
    void loadSystemMessages();
    return;
  }
  updateLogPage.value = nextPage;
  updateLogPageSize.value = nextPageSize;
  void loadUpdateLogs();
}

watch(
  () => props.open,
  (value) => {
    if (value) {
      activeTab.value = props.defaultTab || "update-logs";
      void loadRecentUpdateLogState();
      void loadUnreadCounts();
      loadActiveTab();
    }
  },
);

watch(activeTab, () => {
  if (props.open) {
    loadActiveTab();
  }
});
</script>

<template>
  <a-modal
    :open="open"
    :footer="null"
    :width="780"
    centered
    @cancel="closeDialog"
  >
    <template #title>
      <div class="notification-title-tabs">
        <button
          v-for="tab in tabItems"
          :key="tab.key"
          type="button"
          class="notification-title-tab"
          :class="{ active: activeTab === tab.key }"
          @click="switchTab(tab.key)"
        >
          <component :is="tab.icon" />
          <span>{{ tab.label }}</span>
          <span v-if="getTabUnreadCount(tab.key)" class="notification-title-count">
            {{ getTabUnreadCount(tab.key) }}
          </span>
          <span v-if="tab.key === 'update-logs' && hasRecentUpdateLog" class="notification-title-badge">NEW</span>
        </button>
      </div>
    </template>

    <div class="notification-dialog">
      <div v-if="activeTab === 'feedback'" class="notification-panel">
        <div v-if="!auth.isLoggedIn" class="notification-empty-state">登录后可查看我的反馈。</div>
        <template v-else>
          <div class="notification-panel-toolbar">
            <span class="notification-unread-summary">未读反馈 {{ feedbackUnreadCount }} 条</span>
            <a-button
              size="small"
              type="primary"
              ghost
              :disabled="feedbackUnreadCount <= 0"
              :loading="feedbackMarkingAllRead"
              @click="markFeedbacksAllRead"
            >
              一键已读
            </a-button>
          </div>
          <a-spin :spinning="feedbackLoading">
            <div v-if="feedbackItems.length" class="notification-list">
              <article
                v-for="item in feedbackItems"
                :key="item.feedback_id"
                class="notification-card notification-card-clickable"
                :class="{ unread: !item.is_read }"
                @click="openFeedbackDetail(item)"
              >
                <div class="notification-meta">
                  <div class="notification-meta-left">
                    <a-tag class="warm-tag" :color="feedbackStatusColor(item.status)">{{ feedbackStatusLabel(item.status) }}</a-tag>
                    <a-tag class="warm-tag" :color="item.is_read ? 'green' : 'orange'">
                      {{ item.is_read ? "已读" : "未读" }}
                    </a-tag>
                  </div>
                  <span class="notification-time">{{ formatTime(item.updated_at || item.created_at) }}</span>
                </div>
                <div class="notification-text">{{ item.content || "-" }}</div>
                <div v-if="item.process_note" class="notification-subtext">处理进度：{{ item.process_note }}</div>
                <div class="notification-subtext">处理结果：{{ item.result_note || "暂未填写处理结果" }}</div>
              </article>
            </div>
            <a-empty v-else class="warm-empty" description="暂无反馈记录" />
          </a-spin>
        </template>
      </div>

      <div v-else-if="activeTab === 'system-messages'" class="notification-panel">
        <div v-if="!auth.isLoggedIn" class="notification-empty-state">登录后可查看系统消息。</div>
        <template v-else>
          <div class="notification-panel-toolbar">
            <span class="notification-unread-summary">未读消息 {{ systemUnreadCount }} 条</span>
            <a-button
              size="small"
              type="primary"
              ghost
              :disabled="systemUnreadCount <= 0"
              :loading="systemMarkingAllRead"
              @click="markSystemMessagesAllRead"
            >
              一键已读
            </a-button>
          </div>
          <a-spin :spinning="systemLoading">
            <div v-if="systemItems.length" class="notification-list">
              <article
                v-for="item in systemItems"
                :key="item.message_id"
                class="notification-card notification-card-clickable"
                :class="{ unread: !item.is_read }"
                @click="openSystemMessageDetail(item)"
              >
                <div class="notification-meta">
                  <div class="notification-meta-left">
                    <a-tag class="warm-tag" :color="item.is_read ? 'green' : 'orange'">
                      {{ item.is_read ? "已读" : "未读" }}
                    </a-tag>
                  </div>
                  <span class="notification-time">{{ formatTime(item.created_at) }}</span>
                </div>
                <div class="notification-title">{{ item.subject }}</div>
                <div class="notification-text">{{ item.content_text || "-" }}</div>
              </article>
            </div>
            <a-empty v-else class="warm-empty" description="暂无系统消息" />
          </a-spin>
        </template>
      </div>

      <div v-else class="notification-panel">
        <a-spin :spinning="updateLogLoading">
          <div v-if="updateLogItems.length" class="notification-list">
            <article v-for="item in updateLogItems" :key="item.log_id" class="notification-card">
              <div class="notification-meta">
                <div class="notification-meta-left">
                  <a-tag class="warm-tag" :color="updateLogTagColor(item.tag_type)">
                    {{ updateLogTagLabel(item.tag_type) }}
                  </a-tag>
                </div>
                <span class="notification-time">{{ formatTime(item.effective_at) }}</span>
              </div>
              <div class="notification-title">{{ item.title }}</div>
              <div class="notification-log-text">
                <p v-for="(paragraph, index) in formatContent(item.content)" :key="`${item.log_id}-${index}`">
                  {{ paragraph }}
                </p>
              </div>
            </article>
          </div>
          <a-empty v-else class="warm-empty" description="暂无已生效的更新日志" />
        </a-spin>
      </div>

      <div v-if="currentPagination.total > currentPagination.pageSize" class="dialog-pagination">
        <a-pagination
          size="small"
          :current="currentPagination.current"
          :page-size="currentPagination.pageSize"
          :total="currentPagination.total"
          :show-size-changer="true"
          @change="handlePageChange"
          @showSizeChange="handlePageChange"
        />
      </div>
    </div>
  </a-modal>

  <FeedbackDetailDrawer
    v-model:open="feedbackDetailDrawerOpen"
    mode="user"
    :feedback-id="activeFeedbackId"
    @changed="handleFeedbackDrawerChanged"
  />
</template>

<style scoped lang="scss">
.notification-title-tabs {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.notification-title-tab {
  min-height: 34px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: var(--theme-muted-text);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition:
    background var(--motion-duration-hover) var(--motion-ease-soft),
    color var(--motion-duration-hover) var(--motion-ease-soft),
    border-color var(--motion-duration-hover) var(--motion-ease-soft);
}

.notification-title-tab.active {
  border-color: color-mix(in srgb, var(--theme-accent) 24%, transparent);
  background: color-mix(in srgb, var(--theme-accent) 12%, transparent);
  color: var(--theme-accent-text);
}

.notification-title-count,
.notification-title-badge {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--theme-accent);
  color: var(--theme-accent-contrast);
  font-size: 11px;
  font-weight: 700;
  line-height: 18px;
}

.notification-title-count {
  min-width: 18px;
  text-align: center;
}

.notification-dialog {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 560px;
}

.notification-panel {
  flex: 1;
  min-height: 500px;
}

.notification-panel-toolbar {
  min-height: 34px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.notification-unread-summary {
  color: var(--theme-muted-text);
  font-size: 13px;
  font-weight: 600;
}

.notification-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 60vh;
  overflow: auto;
  padding-right: 6px;
}

.notification-card {
  padding: 14px 16px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 18px;
  background: var(--theme-panel-bg-soft);
}

.notification-card.unread {
  border-color: rgba(255, 127, 39, 0.32);
  background: rgba(255, 127, 39, 0.06);
}

.notification-card-clickable {
  cursor: pointer;
  transition:
    transform var(--motion-duration-hover) var(--motion-ease-enter),
    box-shadow var(--motion-duration-hover) var(--motion-ease-soft),
    border-color var(--motion-duration-hover) var(--motion-ease-soft);
}

.notification-card-clickable:hover {
  transform: translateY(-2px);
  border-color: var(--theme-border-strong);
  box-shadow: 0 12px 24px var(--theme-shadow-soft);
}

.notification-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  color: var(--theme-muted-text);
  font-size: 13px;
}

.notification-meta-left {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.notification-time {
  flex-shrink: 0;
}

.notification-title {
  margin-bottom: 8px;
  color: var(--theme-heading);
  font-size: 16px;
  font-weight: 700;
  line-height: 1.4;
}

.notification-text,
.notification-subtext,
.notification-log-text {
  color: var(--theme-text);
  font-size: 14px;
  line-height: 1.55;
  word-break: break-word;
}

.notification-subtext {
  margin-top: 6px;
  color: var(--theme-muted-text);
}

.notification-log-text p {
  margin: 0;
}

.notification-log-text p + p {
  margin-top: 6px;
}

.notification-empty-state {
  min-height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--theme-muted-text);
  font-size: 14px;
}

.dialog-pagination {
  min-height: 32px;
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 768px) {
  .notification-title-tabs {
    gap: 6px;
  }

  .notification-title-tab {
    min-height: 32px;
    padding: 0 12px;
    font-size: 13px;
  }

  .notification-card {
    padding: 12px 14px;
    border-radius: 16px;
  }

  .notification-meta {
    align-items: flex-start;
    flex-direction: column;
  }

  .dialog-pagination {
    justify-content: center;
  }
}
</style>
