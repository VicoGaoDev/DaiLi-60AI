<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { message } from "ant-design-vue";
import {
  ThunderboltOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
} from "@ant-design/icons-vue";
import { useAuthStore } from "@/stores/auth";
import { getCreditLogs as getUserCreditLogs } from "@/api/auth";
import { getCreditLogs as getAdminCreditLogs, listUserOptions } from "@/api/admin";
import type { CreditLog, AdminUser, TaskType } from "@/types";
import dayjs from "dayjs";

const auth = useAuthStore();
const isAdmin = computed(() => auth.isAdmin);

const items = ref<CreditLog[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const loading = ref(false);

const filterUserId = ref<string | undefined>(undefined);
const filterDateRange = ref<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
const filterDirection = ref<"increase" | "decrease" | undefined>(undefined);
const filterMode = ref<TaskType | "manual" | "redeem" | "purchase" | undefined>(undefined);

const userList = ref<AdminUser[]>([]);
const usersLoading = ref(false);

const columns = computed(() => {
  const base = [
    { title: "时间", dataIndex: "created_at", width: 180 },
    { title: "变动方向", dataIndex: "type", width: 110 },
    { title: "任务类型", dataIndex: "mode", width: 120 },
    { title: "积分变动", dataIndex: "amount", width: 120 },
    { title: "说明", dataIndex: "description", ellipsis: true },
  ];
  if (isAdmin.value) {
    base.splice(1, 0, { title: "用户", dataIndex: "username", width: 120 });
    base.push({ title: "操作人", dataIndex: "operator_name", width: 120 });
  }
  return base;
});

async function loadLogs() {
  loading.value = true;
  try {
    const params: Record<string, unknown> = {
      page: page.value,
      page_size: pageSize.value,
    };
    if (isAdmin.value && filterUserId.value) {
      params.user_id = filterUserId.value;
    }
    if (filterDateRange.value) {
      params.start_date = formatQueryDate(filterDateRange.value[0].startOf("day"));
      params.end_date = formatQueryDate(filterDateRange.value[1].endOf("day"));
    }
    if (filterDirection.value) {
      params.direction = filterDirection.value;
    }
    if (filterMode.value) {
      params.mode = filterMode.value;
    }
    const res = isAdmin.value
      ? await getAdminCreditLogs(
        page.value,
        pageSize.value,
        filterUserId.value,
        params.start_date as string | undefined,
        params.end_date as string | undefined,
        filterDirection.value,
        filterMode.value,
      )
      : await getUserCreditLogs(params as any);
    items.value = res.items;
    total.value = res.total;
  } catch {
    message.error("获取积分明细失败");
  } finally {
    loading.value = false;
  }
}

async function loadUsers() {
  if (!isAdmin.value || userList.value.length || usersLoading.value) return;
  usersLoading.value = true;
  try {
    userList.value = await listUserOptions();
  } catch {
    /* ignore */
  } finally {
    usersLoading.value = false;
  }
}

function handleUserDropdownVisible(open: boolean) {
  if (open) void loadUsers();
}

function handlePageChange(p: number) {
  page.value = p;
  loadLogs();
}

function handlePageSizeChange(_: number, size: number) {
  page.value = 1;
  pageSize.value = size;
  loadLogs();
}

function handleFilter() {
  page.value = 1;
  loadLogs();
}

function handleReset() {
  filterUserId.value = undefined;
  filterDateRange.value = null;
  filterDirection.value = undefined;
  filterMode.value = undefined;
  page.value = 1;
  loadLogs();
}

function formatTime(t: string) {
  return t ? dayjs(t).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function formatQueryDate(value?: dayjs.Dayjs) {
  return value ? value.format("YYYY-MM-DDTHH:mm:ss") : undefined;
}

function directionLabel(record: CreditLog) {
  return record.amount > 0 ? "增加" : "消耗";
}

function modeLabel(mode: CreditLog["mode"]) {
  if (mode === "text_generate") return "文生图";
  if (mode === "image_edit") return "图编辑";
  if (mode === "inpaint") return "局部重绘";
  if (mode === "smart_cutout") return "智能抠图";
  if (mode === "promptReverse") return "提示词反推";
  if (mode === "promptOptimize") return "提示词优化";
  if (mode === "redeem") return "兑换积分";
  if (mode === "purchase") return "在线购买";
  return "手动调整";
}

onMounted(() => {
  loadLogs();
});
</script>

<template>
  <div class="credit-logs-page">
    <div class="page-header">
      <ThunderboltOutlined class="header-icon" />
      <h2>积分明细</h2>
      <div class="balance-badge" v-if="auth.user">
        余额: <strong>{{ auth.user.credits }}</strong> 积分
      </div>
    </div>

    <div class="filter-bar">
      <a-select
        v-if="isAdmin"
        v-model:value="filterUserId"
        placeholder="全部用户"
        allowClear
        show-search
        option-filter-prop="label"
        style="width: 180px"
        :loading="usersLoading"
        @dropdownVisibleChange="handleUserDropdownVisible"
      >
        <a-select-option
          v-for="u in userList"
          :key="u.id"
          :value="u.id"
          :label="u.username"
        >
          {{ u.username }}
        </a-select-option>
      </a-select>

      <a-range-picker
        v-model:value="filterDateRange"
        :placeholder="['开始日期', '结束日期']"
        style="width: 260px"
      />

      <a-select
        v-model:value="filterDirection"
        allow-clear
        placeholder="全部变动"
        style="width: 140px"
      >
        <a-select-option value="increase">积分增加</a-select-option>
        <a-select-option value="decrease">积分消耗</a-select-option>
      </a-select>

      <a-select
        v-model:value="filterMode"
        allow-clear
        placeholder="全部任务类型"
        style="width: 160px"
      >
        <a-select-option value="text_generate">文生图</a-select-option>
        <a-select-option value="image_edit">图编辑</a-select-option>
        <a-select-option value="inpaint">局部重绘</a-select-option>
        <a-select-option value="smart_cutout">智能抠图</a-select-option>
        <a-select-option value="promptReverse">提示词反推</a-select-option>
        <a-select-option value="promptOptimize">提示词优化</a-select-option>
        <a-select-option value="redeem">兑换积分</a-select-option>
        <a-select-option value="purchase">在线购买</a-select-option>
        <a-select-option value="manual">手动调整</a-select-option>
      </a-select>

      <a-button type="primary" class="credit-filter-btn credit-filter-btn-primary" @click="handleFilter">
        筛选
      </a-button>
      <a-button class="credit-filter-btn credit-filter-btn-secondary" @click="handleReset">重置</a-button>
    </div>

    <div class="table-shell">
      <a-table
        :columns="columns"
        :data-source="items"
        :loading="loading"
        :pagination="false"
        row-key="id"
        :scroll="{ x: 700 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'created_at'">
            {{ formatTime(record.created_at) }}
          </template>
          <template v-else-if="column.dataIndex === 'type'">
            <a-tag class="credit-type-tag" :class="record.amount > 0 ? 'credit-type-tag-income' : 'credit-type-tag-expense'">
              {{ directionLabel(record) }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'mode'">
            {{ modeLabel(record.mode) }}
          </template>
          <template v-else-if="column.dataIndex === 'amount'">
            <span :class="record.amount > 0 ? 'amount-plus' : 'amount-minus'">
              <ArrowUpOutlined v-if="record.amount > 0" />
              <ArrowDownOutlined v-else />
              {{ record.amount > 0 ? "+" : "" }}{{ record.amount }}
            </span>
          </template>
          <template v-else-if="column.dataIndex === 'operator_name'">
            {{ record.operator_name || "-" }}
          </template>
        </template>
      </a-table>
    </div>

    <div class="pagination-wrap" v-if="total > pageSize">
      <a-pagination
        :current="page"
        :total="total"
        :page-size="pageSize"
        show-size-changer
        @change="handlePageChange"
        @showSizeChange="handlePageSizeChange"
      />
    </div>
  </div>
</template>

<style scoped>
.credit-logs-page {
  max-width: 960px;
  margin: 32px auto;
  padding: 0 24px;
  animation: credit-page-enter var(--motion-duration-reveal) ease both;
}

@keyframes credit-page-enter {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes credit-fade-up {
  from {
    opacity: 0;
    transform: translate3d(0, 16px, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
  animation: credit-fade-up var(--motion-duration-reveal) var(--motion-ease-enter) 0.04s both;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--theme-title);
}

.header-icon {
  font-size: 22px;
  color: var(--theme-accent-text);
}

.balance-badge {
  margin-left: auto;
  background: var(--theme-panel-bg);
  border: 1px solid var(--theme-panel-border);
  border-radius: 8px;
  padding: 6px 16px;
  font-size: 14px;
  color: var(--theme-accent-text);
  transition:
    transform var(--motion-duration-micro) var(--motion-ease-soft),
    box-shadow var(--motion-duration-base) var(--motion-ease-soft),
    border-color var(--motion-duration-base) var(--motion-ease-soft);
}

.balance-badge:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 24px var(--theme-shadow-soft);
  border-color: var(--theme-border-strong);
}

.balance-badge strong {
  font-size: 18px;
  margin: 0 2px;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  animation: credit-fade-up var(--motion-duration-reveal) var(--motion-ease-enter) 0.12s both;
}

.credit-filter-btn {
  height: 36px;
  border-radius: 12px;
  font-weight: 600;
  box-shadow: none;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    box-shadow var(--motion-duration-base) var(--motion-ease-soft),
    background var(--motion-duration-base) var(--motion-ease-soft),
    border-color var(--motion-duration-base) var(--motion-ease-soft),
    color var(--motion-duration-base) var(--motion-ease-soft);
}

.credit-filter-btn:active {
  transform: scale(0.96);
}

.credit-filter-btn-primary {
  border-color: var(--theme-accent) !important;
  background: var(--theme-accent) !important;
  color: var(--theme-accent-contrast) !important;
}

.credit-filter-btn-primary:hover,
.credit-filter-btn-primary:focus {
  border-color: var(--theme-accent-strong) !important;
  background: var(--theme-accent-strong) !important;
  color: var(--theme-accent-contrast) !important;
  transform: translateY(-1px);
  box-shadow: 0 14px 24px var(--theme-shadow-strong) !important;
}

.credit-filter-btn-secondary {
  border-color: var(--theme-panel-border-strong) !important;
  background: var(--theme-panel-bg-strong) !important;
  color: var(--theme-accent-text) !important;
}

.credit-filter-btn-secondary:hover,
.credit-filter-btn-secondary:focus {
  border-color: var(--theme-border-strong) !important;
  background: var(--theme-control-hover-bg) !important;
  color: var(--theme-accent-text-hover) !important;
  transform: translateY(-1px);
  box-shadow: 0 12px 20px var(--theme-shadow-soft) !important;
}

.table-shell {
  overflow: hidden;
  border-radius: 24px;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-modal-bg);
  box-shadow: 0 18px 40px var(--theme-shadow-soft);
  animation: credit-fade-up var(--motion-duration-reveal-soft-plus) var(--motion-ease-enter) 0.2s both;
}

.table-shell :deep(.ant-table) {
  background: transparent;
}

.table-shell :deep(.ant-table-container table > thead > tr > th) {
  background: var(--theme-table-head-bg) !important;
  color: var(--theme-title) !important;
  font-weight: 700;
  border-bottom: 1px solid var(--theme-border) !important;
}

.table-shell :deep(.ant-table-tbody > tr > td) {
  border-bottom: 1px solid var(--theme-border) !important;
  background: var(--theme-table-row-bg);
  transition: background var(--motion-duration-fast) var(--motion-ease-soft), transform var(--motion-duration-fast) var(--motion-ease-soft);
}

.table-shell :deep(.ant-table-tbody > tr:hover > td) {
  background: var(--theme-table-row-hover) !important;
}

.credit-type-tag {
  border-radius: 999px;
  border-width: 1px;
  font-weight: 600;
  transition: transform var(--motion-duration-micro) var(--motion-ease-soft), box-shadow var(--motion-duration-micro) var(--motion-ease-soft);
}

.credit-type-tag:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 16px var(--theme-shadow-soft);
}

.credit-type-tag-income {
  color: var(--theme-accent-text);
  background: var(--theme-panel-bg-strong);
  border-color: var(--theme-panel-border-strong);
}

.credit-type-tag-expense {
  color: var(--text-secondary);
  background: var(--theme-panel-bg-soft);
  border-color: var(--theme-panel-border);
}

.amount-plus {
  color: #52c41a;
  font-weight: 600;
}

.amount-minus {
  color: #ff4d4f;
  font-weight: 600;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
  animation: credit-fade-up var(--motion-duration-reveal-soft) var(--motion-ease-enter) 0.28s both;
}

.pagination-wrap :deep(.ant-pagination-item) {
  border-radius: 10px;
  border-color: var(--theme-control-border-strong);
}

.pagination-wrap :deep(.ant-pagination-item:hover) {
  border-color: var(--theme-border-strong);
}

.pagination-wrap :deep(.ant-pagination-item a) {
  color: var(--text-secondary);
}

.pagination-wrap :deep(.ant-pagination-item-active) {
  border-color: var(--theme-accent);
  background: var(--theme-accent);
}

.pagination-wrap :deep(.ant-pagination-item-active a) {
  color: var(--theme-accent-contrast);
  font-weight: 600;
}

.pagination-wrap :deep(.ant-pagination-prev button),
.pagination-wrap :deep(.ant-pagination-next button) {
  border-radius: 10px;
  color: var(--text-secondary);
}

.pagination-wrap :deep(.ant-pagination-options .ant-select-selector) {
  border-radius: 10px;
  border-color: var(--theme-control-border-strong) !important;
}

@media (prefers-reduced-motion: reduce) {
  .credit-logs-page,
  .page-header,
  .filter-bar,
  .table-shell,
  .pagination-wrap {
    animation: none !important;
  }

  .balance-badge,
  .credit-filter-btn,
  .table-shell :deep(.ant-table-tbody > tr > td),
  .credit-type-tag {
    transition: none !important;
  }
}
</style>
