<script setup lang="ts">
import { computed, ref, watch } from "vue";
import dayjs from "dayjs";
import { message } from "ant-design-vue";
import { listUpdateLogs } from "@/api/updateLogs";
import type { UpdateLogItem, UpdateLogTagType } from "@/types";

const props = defineProps<{
  open: boolean;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
}>();

const loading = ref(false);
const items = ref<UpdateLogItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(10);

const hasItems = computed(() => items.value.length > 0);

function closeDialog() {
  emit("update:open", false);
}

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "-";
}

function tagLabel(tag: UpdateLogTagType) {
  if (tag === "notice") return "通知";
  if (tag === "feature") return "新功能";
  if (tag === "optimization") return "优化";
  if (tag === "bugfix") return "Bug修复";
  return "其他调整";
}

function tagColor(tag: UpdateLogTagType) {
  if (tag === "notice") return "purple";
  if (tag === "feature") return "green";
  if (tag === "optimization") return "cyan";
  if (tag === "bugfix") return "red";
  return "gold";
}

function formatContent(content: string) {
  return (content || "").trim().split(/\n+/).filter(Boolean);
}

async function load() {
  loading.value = true;
  try {
    const res = await listUpdateLogs(page.value, pageSize.value);
    items.value = res.items;
    total.value = res.total;
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取更新日志失败");
  } finally {
    loading.value = false;
  }
}

function handlePageChange(nextPage: number, nextPageSize: number) {
  page.value = nextPage;
  pageSize.value = nextPageSize;
  void load();
}

watch(
  () => props.open,
  (value) => {
    if (value) {
      void load();
    }
  },
);
</script>

<template>
  <a-modal
    :open="open"
    :footer="null"
    :width="760"
    centered
    title="更新日志"
    @cancel="closeDialog"
  >
    <div class="update-log-dialog">
      <a-spin :spinning="loading">
        <div v-if="hasItems" class="log-list">
          <article v-for="item in items" :key="item.log_id" class="log-card">
            <div class="log-card-meta">
              <a-tag class="warm-tag" :color="tagColor(item.tag_type)">
                {{ tagLabel(item.tag_type) }}
              </a-tag>
              <span class="log-card-time">{{ formatTime(item.effective_at) }}</span>
            </div>
            <h3 class="log-card-title">{{ item.title }}</h3>
            <div class="log-card-content">
              <p v-for="(paragraph, index) in formatContent(item.content)" :key="`${item.log_id}-${index}`">
                {{ paragraph }}
              </p>
            </div>
          </article>
        </div>
        <a-empty v-else class="warm-empty" description="暂无已生效的更新日志" />
      </a-spin>

      <div v-if="total > pageSize" class="dialog-pagination">
        <a-pagination
          size="small"
          :current="page"
          :page-size="pageSize"
          :total="total"
          :show-size-changer="true"
          @change="handlePageChange"
          @showSizeChange="handlePageChange"
        />
      </div>
    </div>
  </a-modal>
</template>

<style scoped lang="scss">
.update-log-dialog {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.log-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 60vh;
  overflow: auto;
  padding-right: 6px;
}

.log-card {
  padding: 14px 16px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 18px;
  background: var(--theme-panel-bg-soft);
}

.log-card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  color: var(--theme-muted-text);
  font-size: 13px;
}

.log-card-time {
  flex-shrink: 0;
}

.log-card-meta :deep(.ant-tag) {
  padding: 2px 10px;
  font-size: 13px;
  line-height: 22px;
  border-radius: 999px;
}

.log-card-title {
  margin: 0 0 8px;
  color: var(--theme-heading);
  font-size: 17px;
  line-height: 1.4;
}

.log-card-content {
  color: var(--theme-text);
  font-size: 14px;
  line-height: 1.55;
  word-break: break-word;

  p {
    margin: 0;
  }

  p + p {
    margin-top: 6px;
  }
}

.dialog-pagination {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 768px) {
  .log-card {
    padding: 12px 14px;
    border-radius: 16px;
  }

  .log-card-meta {
    align-items: flex-start;
    flex-direction: column;
  }

  .dialog-pagination {
    justify-content: center;
  }
}
</style>
