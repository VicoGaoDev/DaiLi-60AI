<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import dayjs from "dayjs";
import { BellOutlined } from "@ant-design/icons-vue";
import { getMyUnreadFeedbackCount } from "@/api/feedback";
import { getMyUnreadSystemMessageCount } from "@/api/systemMessages";
import { listUpdateLogs } from "@/api/updateLogs";
import NotificationCenterDialog from "@/components/update-log/NotificationCenterDialog.vue";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const dialogOpen = ref(false);
const hasRecentUpdateLog = ref(false);
const feedbackUnreadCount = ref(0);
const systemMessageUnreadCount = ref(0);
const unreadNoticeCount = computed(() => feedbackUnreadCount.value + systemMessageUnreadCount.value);
const hasNoticeHighlight = computed(() => hasRecentUpdateLog.value || unreadNoticeCount.value > 0);

async function loadHighlightState() {
  try {
    const tasks: Promise<any>[] = [listUpdateLogs(1, 1)];
    if (auth.isLoggedIn) {
      tasks.push(getMyUnreadFeedbackCount(), getMyUnreadSystemMessageCount());
    }
    const [updateLogRes, feedbackUnreadRes, systemUnreadRes] = await Promise.all(tasks);
    const latest = updateLogRes.items[0];
    const cutoff = dayjs().subtract(7, "day");
    const hasRecentUpdate = !!latest?.effective_at
      && (dayjs(latest.effective_at).isAfter(cutoff) || dayjs(latest.effective_at).isSame(cutoff));
    hasRecentUpdateLog.value = hasRecentUpdate;
    feedbackUnreadCount.value = Number(feedbackUnreadRes?.count || 0);
    systemMessageUnreadCount.value = Number(systemUnreadRes?.count || 0);
  } catch {
    hasRecentUpdateLog.value = false;
    feedbackUnreadCount.value = 0;
    systemMessageUnreadCount.value = 0;
  }
}

function openDialog() {
  dialogOpen.value = true;
}

onMounted(() => {
  void loadHighlightState();
});
</script>

<template>
  <a-tooltip title="通知中心">
    <button
      type="button"
      class="update-log-entry-btn"
      :class="{ 'is-recent': hasNoticeHighlight }"
      aria-label="打开通知中心"
      @click="openDialog"
    >
      <BellOutlined />
      <span v-if="unreadNoticeCount > 0" class="update-log-entry-count">
        {{ unreadNoticeCount > 99 ? "99+" : unreadNoticeCount }}
      </span>
    </button>
  </a-tooltip>

  <NotificationCenterDialog v-model:open="dialogOpen" @read-state-change="loadHighlightState" />
</template>

<style scoped lang="scss">
.update-log-entry-btn {
  position: relative;
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
  color: var(--theme-accent-text);
  font-size: 24px;
  cursor: pointer;
  transition:
    transform var(--motion-duration-hover) var(--motion-ease-enter),
    color var(--motion-duration-hover) var(--motion-ease-soft),
    opacity var(--motion-duration-hover) var(--motion-ease-soft);
}

.update-log-entry-btn:hover {
  transform: translateY(-1px);
  color: var(--theme-accent-text-hover);
  opacity: 0.9;
}

.update-log-entry-btn.is-recent {
  color: var(--theme-accent);
}

.update-log-entry-btn.is-recent:hover {
  color: var(--theme-accent-text-hover);
  opacity: 0.92;
}

.update-log-entry-count {
  position: absolute;
  top: -5px;
  right: -5px;
  min-width: 17px;
  height: 17px;
  padding: 0 5px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--theme-accent-contrast);
  background: var(--theme-accent);
  font-size: 10px;
  font-weight: 800;
  line-height: 1;
  box-shadow: 0 6px 12px var(--theme-shadow-strong);
}
</style>
