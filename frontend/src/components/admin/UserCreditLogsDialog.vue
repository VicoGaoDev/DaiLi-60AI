<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { message } from "ant-design-vue";
import { ArrowDownOutlined, ArrowUpOutlined } from "@ant-design/icons-vue";
import dayjs from "dayjs";
import { getCreditLogs } from "@/api/admin";
import type { AdminUser, CreditLog } from "@/types";

const props = defineProps<{
  open: boolean;
  user: AdminUser | null;
}>();

const emit = defineEmits<{
  (event: "update:open", value: boolean): void;
}>();

const loading = ref(false);
const items = ref<CreditLog[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;

const dialogTitle = computed(() =>
  props.user ? `积分明细 — ${props.user.username}` : "积分明细",
);

const columns = [
  { title: "时间", dataIndex: "created_at", width: 168 },
  { title: "类型", dataIndex: "mode", width: 110 },
  { title: "积分变动", dataIndex: "amount", width: 110 },
  { title: "说明", dataIndex: "description", ellipsis: true },
  { title: "操作人", dataIndex: "operator_name", width: 100 },
];

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function modeLabel(mode: CreditLog["mode"]) {
  if (mode === "text_generate") return "文生图";
  if (mode === "image_edit") return "图编辑";
  if (mode === "inpaint") return "局部重绘";
  if (mode === "promptReverse") return "提示词反推";
  if (mode === "promptOptimize") return "提示词优化";
  if (mode === "redeem") return "兑换积分";
  if (mode === "purchase") return "在线购买";
  return "手动调整";
}

async function loadLogs() {
  const userId = props.user?.id;
  if (!props.open || !userId) return;

  loading.value = true;
  try {
    const res = await getCreditLogs(page.value, pageSize, userId);
    items.value = res.items;
    total.value = res.total;
  } catch {
    message.error("获取积分明细失败");
  } finally {
    loading.value = false;
  }
}

function handlePageChange(nextPage: number) {
  page.value = nextPage;
  void loadLogs();
}

function closeDialog() {
  emit("update:open", false);
}

watch(
  () => [props.open, props.user?.id] as const,
  ([open, userId], previous) => {
    if (!open || !userId) return;
    const prevOpen = previous?.[0];
    const prevUserId = previous?.[1];
    if (!prevOpen || prevUserId !== userId) {
      page.value = 1;
      items.value = [];
      total.value = 0;
    }
    void loadLogs();
  },
  { immediate: true },
);
</script>

<template>
  <a-modal
    :open="open"
    :title="dialogTitle"
    :footer="null"
    :width="760"
    centered
    destroy-on-close
    class="user-credit-logs-modal"
    @cancel="closeDialog"
  >
    <a-spin :spinning="loading">
      <div v-if="user" class="credit-logs-dialog">
        <div class="credit-logs-summary">
          <div class="credit-logs-stat">
            <span>剩余积分</span>
            <strong>{{ user.credits || 0 }}</strong>
          </div>
          <div class="credit-logs-stat">
            <span>已消耗积分</span>
            <strong class="consumed">{{ user.consumed_credits || 0 }}</strong>
          </div>
          <div class="credit-logs-stat">
            <span>变动记录</span>
            <strong>{{ total }}</strong>
          </div>
        </div>

        <div class="credit-logs-body">
          <a-table
            :columns="columns"
            :data-source="items"
            :pagination="false"
            :loading="false"
            row-key="id"
            size="small"
            :scroll="{ x: 640 }"
            :locale="{ emptyText: '暂无积分变动记录' }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.dataIndex === 'created_at'">
                {{ formatTime(record.created_at) }}
              </template>
              <template v-else-if="column.dataIndex === 'mode'">
                {{ modeLabel(record.mode) }}
              </template>
              <template v-else-if="column.dataIndex === 'amount'">
                <span :class="record.amount > 0 ? 'amount-plus' : 'amount-minus'">
                  <ArrowUpOutlined v-if="record.amount > 0" />
                  <ArrowDownOutlined v-else />
                  {{ record.amount > 0 ? `+${record.amount}` : record.amount }}
                </span>
              </template>
              <template v-else-if="column.dataIndex === 'description'">
                {{ record.description || "-" }}
              </template>
              <template v-else-if="column.dataIndex === 'operator_name'">
                {{ record.operator_name || "-" }}
              </template>
            </template>
          </a-table>
        </div>

        <div v-if="total > pageSize" class="credit-logs-pagination">
          <a-pagination
            :current="page"
            :total="total"
            :page-size="pageSize"
            size="small"
            show-less-items
            @change="handlePageChange"
          />
        </div>

        <div class="credit-logs-actions">
          <a-button class="credit-logs-close-btn" @click="closeDialog">关闭</a-button>
        </div>
      </div>
    </a-spin>
  </a-modal>
</template>

<style scoped lang="scss">
.credit-logs-dialog {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: min(68vh, 640px);
}

.credit-logs-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  flex-shrink: 0;
}

.credit-logs-stat {
  padding: 12px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 14px;
  background: var(--theme-panel-bg-soft);

  span {
    display: block;
    color: var(--theme-text-secondary);
    font-size: 12px;
  }

  strong {
    display: block;
    margin-top: 6px;
    color: var(--theme-title);
    font-size: 18px;
  }

  strong.consumed {
    color: #cf1322;
  }
}

.credit-logs-body {
  flex: 1 1 auto;
  min-height: 0;
  max-height: min(48vh, 420px);
  overflow: auto;
  border: 1px solid var(--theme-panel-border);
  border-radius: 14px;
  background: var(--theme-panel-bg);
}

.credit-logs-pagination {
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}

.credit-logs-actions {
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}

.credit-logs-close-btn {
  border-radius: 999px;
  font-weight: 700;
  border-color: var(--theme-border);
  background: var(--theme-panel-bg);
  color: var(--theme-title);
}

.amount-plus,
.amount-minus {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 700;
}

.amount-plus {
  color: #1f9d63;
}

.amount-minus {
  color: #cf1322;
}

:deep(.ant-table-thead > tr > th) {
  background: var(--theme-panel-bg-soft);
  color: var(--theme-title);
  font-weight: 700;
}

:deep(.ant-table-tbody > tr > td) {
  color: var(--theme-title);
}
</style>
