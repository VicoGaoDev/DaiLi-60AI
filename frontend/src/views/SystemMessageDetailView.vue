<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeftOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import dayjs from "dayjs";
import { getMySystemMessageDetail, getMyUnreadSystemMessageCount } from "@/api/systemMessages";
import { setStoredUnreadSystemMessageCount } from "@/lib/systemMessageNotice";
import type { SystemMessageDetail } from "@/types";

const route = useRoute();
const router = useRouter();
const loading = ref(false);
const detail = ref<SystemMessageDetail | null>(null);

const messageId = computed(() => String(route.params.messageId || ""));

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

async function refreshUnreadCount() {
  try {
    const { count } = await getMyUnreadSystemMessageCount();
    setStoredUnreadSystemMessageCount(count);
  } catch {
    // ignore unread count sync failures
  }
}

async function load() {
  if (!messageId.value) return;
  loading.value = true;
  try {
    detail.value = await getMySystemMessageDetail(messageId.value);
    await refreshUnreadCount();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取系统消息详情失败");
  } finally {
    loading.value = false;
  }
}

watch(messageId, () => {
  void load();
});

onMounted(load);
</script>

<template>
  <div class="warm-page motion-page-enter">
    <a-spin :spinning="loading">
      <div v-if="detail" class="warm-card message-detail-card motion-fade-up motion-card-lift" style="--motion-delay: 40ms">
        <a-button class="back-btn message-back-btn" @click="router.push('/system-messages')">
          <template #icon><ArrowLeftOutlined /></template>
          返回列表
        </a-button>
        <div class="message-head">
          <h3>{{ detail.subject }}</h3>
          <div class="message-meta">
            <span>发送人：80AI管理员</span>
            <span>发送时间：{{ formatTime(detail.created_at) }}</span>
            <span>阅读状态：{{ detail.is_read ? "已读" : "未读" }}</span>
          </div>
        </div>
        <a-divider />
        <article class="message-content" v-html="detail.content_html" />
      </div>
    </a-spin>
  </div>
</template>

<style scoped lang="scss">
.back-btn {
  border-radius: 12px;
  border-color: var(--theme-panel-border-strong);
  background: var(--theme-panel-bg-strong);
  color: var(--theme-accent-text);
}

.message-detail-card {
  position: relative;
  padding: 28px;
}

.message-back-btn {
  position: absolute;
  top: 24px;
  right: 24px;
}

.message-head {
  padding-right: 112px;
}

.message-head h3 {
  margin: 0 0 14px;
  color: var(--theme-heading);
  font-size: 20px;
  line-height: 1.4;
}

.message-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
  color: var(--theme-muted-text);
  font-size: 13px;
}

.message-content {
  color: var(--theme-text);
  font-size: 15px;
  line-height: 1.8;
  word-break: break-word;
}

.message-content :deep(p) {
  margin: 0 0 12px;
}

.message-content :deep(h1),
.message-content :deep(h2),
.message-content :deep(h3),
.message-content :deep(h4) {
  margin: 18px 0 10px;
  color: var(--theme-heading);
  line-height: 1.35;
}

.message-content :deep(ul),
.message-content :deep(ol) {
  margin: 0 0 14px 22px;
  padding-left: 18px;
}

.message-content :deep(li) {
  margin: 4px 0;
}

.message-content :deep(a) {
  color: var(--theme-accent-text);
}

.message-content :deep(img) {
  max-width: 100%;
  height: auto;
  margin: 12px 0;
  border-radius: 12px;
}

.message-content :deep(table) {
  width: 100%;
  margin: 14px 0;
  border-collapse: collapse;
}

.message-content :deep(th),
.message-content :deep(td) {
  padding: 8px 10px;
  border: 1px solid var(--theme-panel-border-strong);
}

.message-content :deep(blockquote) {
  margin: 12px 0;
  padding: 10px 14px;
  border-left: 4px solid var(--theme-panel-border-strong);
  background: var(--theme-panel-bg);
}

.message-content :deep(pre) {
  overflow: auto;
  padding: 12px;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.06);
}
</style>
