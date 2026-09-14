<script setup lang="ts">
import { reactive, ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { message } from "ant-design-vue";
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";
import { AccountBookOutlined, ArrowLeftOutlined, CopyOutlined } from "@ant-design/icons-vue";
import { listPaymentOrders } from "@/api/admin";
import AdminUserInfoDialog from "@/components/admin/AdminUserInfoDialog.vue";
import { getAvatarImageSrc } from "@/api/images";
import type { AdminPaymentOrder, AdminUser } from "@/types";

const router = useRouter();

type DateShortcut = "today" | "last7Days" | "last30Days" | "thisWeek" | "thisMonth";

const loading = ref(false);
const items = ref<AdminPaymentOrder[]>([]);
const users = ref<AdminUser[]>([]);
const dateShortcut = ref<DateShortcut | undefined>("today");
const detailVisible = ref(false);
const selectedOrder = ref<AdminPaymentOrder | null>(null);
const userInfoOpen = ref(false);
const userInfoTarget = ref<AdminUser | null>(null);

const filters = reactive({
  user: "",
  status: undefined as AdminPaymentOrder["status"] | undefined,
  dateRange: [dayjs().startOf("day"), dayjs().endOf("day")] as [Dayjs, Dayjs] | null,
});

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
});

const columns = [
  { title: "订单", key: "order", width: "23%" },
  { title: "用户", dataIndex: "username", width: "17%" },
  { title: "套餐", dataIndex: "subject", width: "15%" },
  { title: "金额/积分", key: "amount", width: "12%" },
  { title: "状态", key: "status", width: "12%" },
  { title: "时间", key: "time", width: "15%" },
  { title: "操作", key: "action", width: 88 },
];

function formatQueryDate(value?: Dayjs) {
  return value ? value.format("YYYY-MM-DDTHH:mm:ss") : undefined;
}

function fmtTime(t?: string | null) {
  return t
    ? new Date(t).toLocaleString("zh-CN", {
        timeZone: "Asia/Shanghai",
        hour12: false,
      })
    : "-";
}

function formatMoney(value: number) {
  return `¥${Number(value || 0).toFixed(2)}`;
}

function statusText(status: AdminPaymentOrder["status"]) {
  const map: Record<AdminPaymentOrder["status"], string> = {
    created: "已创建",
    pending_pay: "待支付",
    paid: "已支付",
    credited: "已入账",
    closed: "已关闭",
    failed: "失败",
  };
  return map[status] || status;
}

function statusClass(status: AdminPaymentOrder["status"]) {
  if (status === "credited" || status === "paid") return "warm-tag-whitelist";
  if (status === "pending_pay" || status === "created") return "warm-tag-role-admin";
  if (status === "closed") return "warm-tag-muted";
  return "warm-tag-danger";
}

function openDetail(record: AdminPaymentOrder) {
  selectedOrder.value = record;
  detailVisible.value = true;
}

function findAdminUser(userId?: string | null) {
  if (!userId) return null;
  return users.value.find((item) => item.id === userId) || null;
}

function openUserInfo(record: AdminPaymentOrder) {
  const matchedUser = findAdminUser(record.user_id);
  userInfoTarget.value = matchedUser || {
    id: record.user_id,
    username: record.username || "未知用户",
    email: record.user_email || "",
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

function detailText(value?: string | number | null) {
  if (value === undefined || value === null || value === "") return "-";
  return String(value);
}

const detailRows: Array<{ label: string; key: keyof AdminPaymentOrder; type?: "money" | "status" | "time" }> = [
  { label: "订单 ID", key: "id" },
  { label: "订单号", key: "order_no" },
  { label: "商户交易号", key: "out_trade_no" },
  { label: "支付宝交易号", key: "alipay_trade_no" },
  { label: "用户 ID", key: "user_id" },
  { label: "用户名", key: "username" },
  { label: "用户邮箱", key: "user_email" },
  { label: "套餐 Key", key: "plan_key" },
  { label: "套餐名称", key: "subject" },
  { label: "订单金额", key: "amount_yuan", type: "money" },
  { label: "金额分", key: "amount_fen" },
  { label: "积分", key: "credits" },
  { label: "订单状态", key: "status", type: "status" },
  { label: "支付宝状态", key: "trade_status" },
  { label: "买家 ID", key: "buyer_id" },
  { label: "支付时间", key: "paid_at", type: "time" },
  { label: "入账时间", key: "credited_at", type: "time" },
  { label: "关闭时间", key: "closed_at", type: "time" },
  { label: "失败时间", key: "failed_at", type: "time" },
  { label: "创建时间", key: "created_at", type: "time" },
  { label: "更新时间", key: "updated_at", type: "time" },
];

function formatDetailValue(row: (typeof detailRows)[number]) {
  const order = selectedOrder.value;
  if (!order) return "-";
  const value = order[row.key];
  if (row.type === "money") return formatMoney(Number(value || 0));
  if (row.type === "status") return statusText(value as AdminPaymentOrder["status"]);
  if (row.type === "time") return fmtTime(value as string | null | undefined);
  return detailText(value as string | number | null | undefined);
}

async function load() {
  loading.value = true;
  try {
    const res = await listPaymentOrders({
      page: pagination.page,
      page_size: pagination.pageSize,
      user: filters.user.trim() || undefined,
      status: filters.status,
      start_date: formatQueryDate(filters.dateRange?.[0].startOf("day")),
      end_date: formatQueryDate(filters.dateRange?.[1].endOf("day")),
    });
    items.value = res.items;
    pagination.total = res.total;
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取购买订单失败");
  } finally {
    loading.value = false;
  }
}

function handleFilter() {
  pagination.page = 1;
  load();
}

function handleReset() {
  filters.user = "";
  filters.status = undefined;
  filters.dateRange = null;
  dateShortcut.value = undefined;
  pagination.page = 1;
  load();
}

function applyDateShortcut(type: DateShortcut) {
  const now = dayjs();
  dateShortcut.value = type;
  if (type === "today") {
    filters.dateRange = [now.startOf("day"), now.endOf("day")];
  } else if (type === "last7Days") {
    filters.dateRange = [now.subtract(6, "day").startOf("day"), now.endOf("day")];
  } else if (type === "last30Days") {
    filters.dateRange = [now.subtract(29, "day").startOf("day"), now.endOf("day")];
  } else if (type === "thisWeek") {
    filters.dateRange = [now.startOf("week"), now.endOf("week")];
  } else {
    filters.dateRange = [now.startOf("month"), now.endOf("month")];
  }
  handleFilter();
}

function handleDateShortcutChange(event: { target: { value: DateShortcut } }) {
  applyDateShortcut(event.target.value);
}

function handleDateRangeChange() {
  dateShortcut.value = undefined;
}

function handlePageChange(page: number, pageSize?: number) {
  pagination.page = page;
  if (pageSize) pagination.pageSize = pageSize;
  load();
}

async function handleCopy(text?: string, successText = "内容已复制") {
  const normalized = String(text || "").trim();
  if (!normalized) return;
  try {
    await navigator.clipboard.writeText(normalized);
    message.success(successText);
  } catch {
    message.error("复制失败，请重试");
  }
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
          <AccountBookOutlined />
        </div>
        <div>
          <div class="warm-page-title">购买订单</div>
          <div class="warm-page-desc">查看在线购买积分订单，支持按时间、用户和订单状态筛选。</div>
        </div>
      </div>
      <a-button class="back-btn" @click="router.push('/admin/revenue')">
        <template #icon><ArrowLeftOutlined /></template>
        返回营业额
      </a-button>
    </div>

    <div class="warm-card payment-order-filter-bar motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <a-input
        v-model:value="filters.user"
        allow-clear
        placeholder="用户/邮箱/订单号/交易号"
        class="warm-input payment-order-filter-user"
      />
      <a-select
        v-model:value="filters.status"
        allow-clear
        placeholder="订单状态"
        class="warm-select payment-order-filter-status"
      >
        <a-select-option value="created">已创建</a-select-option>
        <a-select-option value="pending_pay">待支付</a-select-option>
        <a-select-option value="paid">已支付</a-select-option>
        <a-select-option value="credited">已入账</a-select-option>
        <a-select-option value="closed">已关闭</a-select-option>
        <a-select-option value="failed">失败</a-select-option>
      </a-select>
      <a-range-picker
        v-model:value="filters.dateRange"
        :placeholder="['创建开始', '创建结束']"
        class="analytics-filter-date payment-order-filter-date"
        @change="handleDateRangeChange"
      />
      <div class="analytics-filter-panel-compact">
        <a-radio-group
          v-model:value="dateShortcut"
          class="analytics-segmented-group analytics-segmented-group-secondary"
          button-style="solid"
          @change="handleDateShortcutChange"
        >
          <a-radio-button value="today">今日</a-radio-button>
          <a-radio-button value="last7Days">近 7 天</a-radio-button>
          <a-radio-button value="last30Days">近 30 天</a-radio-button>
          <a-radio-button value="thisWeek">本周</a-radio-button>
          <a-radio-button value="thisMonth">本月</a-radio-button>
        </a-radio-group>
      </div>
      <a-button type="primary" class="analytics-action-btn action-btn" @click="handleFilter">筛选</a-button>
      <a-button class="analytics-action-btn analytics-action-btn-secondary action-btn" @click="handleReset">重置</a-button>
    </div>

    <div class="warm-card warm-table-card motion-fade-up motion-card-lift" style="--motion-delay: 180ms">
      <a-table
        :columns="columns"
        :data-source="items"
        :loading="loading"
        :pagination="false"
        row-key="id"
        :scroll="{ x: 960 }"
        class="admin-mobile-table compact-payment-order-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'order'">
            <div class="order-cell">
              <div class="id-cell">
                <span class="order-no-text">{{ record.order_no }}</span>
                <a-button type="text" size="small" class="id-copy-btn" @click="handleCopy(record.order_no, '订单号已复制')">
                  <template #icon><CopyOutlined /></template>
                </a-button>
              </div>
              <div v-if="record.alipay_trade_no" class="sub-id-cell">
                <span class="sub-label">支付宝</span>
                <span class="sub-id-text">{{ record.alipay_trade_no }}</span>
              </div>
            </div>
          </template>
          <template v-else-if="column.dataIndex === 'username'">
            <div class="user-cell">
              <div class="user-main-row">
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
                <span class="cell-main-text">{{ record.username || "-" }}</span>
              </div>
              <span v-if="record.user_email" class="muted-line">{{ record.user_email }}</span>
            </div>
          </template>
          <template v-else-if="column.dataIndex === 'subject'">
            <div class="plan-cell">
              <span class="cell-main-text">{{ record.subject || "-" }}</span>
              <span v-if="record.plan_key" class="muted-line">{{ record.plan_key }}</span>
            </div>
          </template>
          <template v-else-if="column.key === 'amount'">
            <div class="amount-cell">
              <span class="money-text">{{ formatMoney(record.amount_yuan) }}</span>
              <span class="muted-line">{{ record.credits }} 积分</span>
            </div>
          </template>
          <template v-else-if="column.key === 'status'">
            <div class="status-cell">
              <a-tag class="warm-tag" :class="statusClass(record.status)">
                {{ statusText(record.status) }}
              </a-tag>
              <span v-if="record.trade_status" class="muted-line">{{ record.trade_status }}</span>
            </div>
          </template>
          <template v-else-if="column.key === 'time'">
            <div class="time-cell">
              <span class="cell-main-text">{{ fmtTime(record.created_at) }}</span>
              <span v-if="record.paid_at" class="muted-line">支付：{{ fmtTime(record.paid_at) }}</span>
            </div>
          </template>
          <template v-else-if="column.key === 'action'">
            <div class="action-cell">
              <a-button type="link" size="small" class="detail-link-btn" @click="openDetail(record)">详情</a-button>
            </div>
          </template>
        </template>
      </a-table>
    </div>

    <div class="warm-pagination">
      <div class="pagination-summary">共 {{ pagination.total }} 笔订单</div>
      <a-pagination
        v-if="pagination.total > pagination.pageSize"
        :current="pagination.page"
        :total="pagination.total"
        :page-size="pagination.pageSize"
        show-size-changer
        @change="handlePageChange"
        @showSizeChange="handlePageChange"
      />
    </div>

    <a-drawer
      v-model:open="detailVisible"
      title="订单详情"
      placement="right"
      width="520"
      class="payment-order-detail-drawer"
    >
      <template v-if="selectedOrder">
        <div class="detail-summary-card">
          <div>
            <div class="detail-summary-label">订单金额</div>
            <div class="detail-summary-value">{{ formatMoney(selectedOrder.amount_yuan) }}</div>
          </div>
          <div>
            <div class="detail-summary-label">积分</div>
            <div class="detail-summary-value">{{ selectedOrder.credits }}</div>
          </div>
          <div>
            <div class="detail-summary-label">状态</div>
            <a-tag class="warm-tag" :class="statusClass(selectedOrder.status)">
              {{ statusText(selectedOrder.status) }}
            </a-tag>
          </div>
        </div>

        <div class="detail-list">
          <div v-for="row in detailRows" :key="row.key" class="detail-row">
            <div class="detail-label">{{ row.label }}</div>
            <div class="detail-value">
              <span>{{ formatDetailValue(row) }}</span>
              <a-button
                v-if="['order_no', 'out_trade_no', 'alipay_trade_no', 'user_id', 'buyer_id'].includes(row.key as string) && selectedOrder[row.key]"
                type="text"
                size="small"
                class="id-copy-btn"
                @click="handleCopy(detailText(selectedOrder[row.key] as string | number | null), `${row.label}已复制`)"
              >
                <template #icon><CopyOutlined /></template>
              </a-button>
            </div>
          </div>
        </div>
      </template>
    </a-drawer>

    <AdminUserInfoDialog v-model:open="userInfoOpen" :user="userInfoTarget" />
  </div>
</template>

<style scoped lang="scss">
.back-btn {
  border-radius: 12px;
  border-color: var(--theme-panel-border-strong);
  background: var(--theme-panel-bg-strong);
  color: var(--theme-accent-text);
}

.payment-order-filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.payment-order-filter-user {
  width: 220px;
  flex: 0 0 220px;
}

.payment-order-filter-status {
  width: 120px;
  flex: 0 0 120px;
}

.payment-order-filter-date {
  width: 320px;
  flex: 0 0 320px;
}

.action-btn {
  min-width: 72px;
  height: 36px;
  padding-inline: 12px;
  flex: 0 0 auto;
}

.id-cell {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  max-width: 100%;
}

.id-copy-btn {
  width: 24px;
  min-width: 24px;
  height: 24px;
  padding: 0 !important;
  color: #b16d10 !important;
}

.order-no-text {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.order-cell,
.user-cell,
.plan-cell,
.amount-cell,
.status-cell,
.time-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.user-main-row {
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

.sub-id-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.sub-label,
.muted-line {
  color: #8c7458;
  font-size: 12px;
  line-height: 1.35;
}

.sub-id-text {
  min-width: 0;
  color: #8c7458;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-main-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.money-text,
.credit-amount {
  color: #a05f00;
  font-weight: 700;
}

.detail-link-btn {
  padding: 0;
  color: #b16d10;
}

.action-cell {
  min-width: 56px;
  white-space: nowrap;
}

.pagination-summary {
  color: #8c7458;
  font-size: 13px;
  white-space: nowrap;
}

.detail-summary-card {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 14px;
  margin-bottom: 16px;
  border: 1px solid rgba(193, 141, 72, 0.2);
  border-radius: 14px;
  background: rgba(255, 248, 234, 0.72);
}

.detail-summary-label {
  margin-bottom: 6px;
  color: #8c7458;
  font-size: 12px;
}

.detail-summary-value {
  color: #a05f00;
  font-size: 16px;
  font-weight: 700;
}

.detail-list {
  display: flex;
  flex-direction: column;
  border-top: 1px solid rgba(193, 141, 72, 0.16);
}

.detail-row {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  gap: 12px;
  padding: 11px 0;
  border-bottom: 1px solid rgba(193, 141, 72, 0.16);
}

.detail-label {
  color: #8c7458;
  font-size: 13px;
}

.detail-value {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  color: #4a3824;
  font-size: 13px;
  overflow-wrap: anywhere;
}

:deep(.compact-payment-order-table .ant-table) {
  font-size: 13px;
}

:deep(.compact-payment-order-table .ant-table-thead > tr > th),
:deep(.compact-payment-order-table .ant-table-tbody > tr > td) {
  padding: 10px 8px;
  vertical-align: top;
}

:deep(.compact-payment-order-table .ant-table-cell) {
  word-break: break-word;
}

@media (max-width: 768px) {
  .payment-order-filter-user,
  .payment-order-filter-status,
  .payment-order-filter-date,
  .action-btn {
    width: 100%;
    flex: 1 1 100%;
  }

  .pagination-summary {
    white-space: normal;
  }

  .detail-summary-card {
    grid-template-columns: 1fr;
  }

  .detail-row {
    grid-template-columns: 1fr;
    gap: 6px;
  }

  :deep(.payment-order-detail-drawer .ant-drawer-content-wrapper) {
    width: 100% !important;
  }
}
</style>
