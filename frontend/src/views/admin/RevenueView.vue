<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { message, Modal } from "ant-design-vue";
import datePickerZhCN from "ant-design-vue/es/date-picker/locale/zh_CN";
import dayjs from "dayjs";
import "dayjs/locale/zh-cn";
import type { Dayjs } from "dayjs";
import { AccountBookOutlined, BellOutlined, CalendarOutlined, PlusOutlined, UnorderedListOutlined } from "@ant-design/icons-vue";
import {
  createOfflineOrder,
  getAdminAnalyticsOfflineOrderRevenue,
  getAdminAnalyticsPaymentRevenue,
  getAdminAnalyticsRedeemRevenue,
  listOfflineOrders,
  listUserOptions,
  sendAdminDailyReportRange,
  testAdminDailyReportNotify,
} from "@/api/admin";
import { isSessionExpiredError } from "@/lib/authError";
import { useAuthStore } from "@/stores/auth";
import RedeemRevenueTable from "@/components/admin/RedeemRevenueTable.vue";
import RevenueTimeseriesChart from "@/components/admin/RevenueTimeseriesChart.vue";
import type { AdminAnalyticsRedeemRevenue, AdminDailyReportTestResult, AdminOfflineOrder, AdminUser } from "@/types";

type DatePreset = "today" | "3d" | "7d" | "30d";

dayjs.locale("zh-cn");

const auth = useAuthStore();
const router = useRouter();
const loading = ref(false);
const sendingDailyReport = ref(false);
const sendingCurrentPeriodDailyReport = ref(false);
const creatingOfflineOrder = ref(false);
const offlineOrderModalOpen = ref(false);
const preset = ref<DatePreset | undefined>("today");
const dateRange = ref<[Dayjs, Dayjs] | null>(null);
const selectedMonth = ref<Dayjs | null>(null);
const redeemRevenue = ref<AdminAnalyticsRedeemRevenue | null>(null);
const paymentRevenue = ref<AdminAnalyticsRedeemRevenue | null>(null);
const offlineOrderRevenue = ref<AdminAnalyticsRedeemRevenue | null>(null);
const revenueChartRef = ref<{ reload: () => Promise<void> } | null>(null);
const offlineOrderItems = ref<AdminOfflineOrder[]>([]);
const users = ref<AdminUser[]>([]);
const usersLoading = ref(false);
const offlineOrderForm = reactive({
  user_id: undefined as string | undefined,
  order_type: "purchase" as "purchase" | "refund",
  credit_amount: 0,
  amount_yuan: undefined as number | undefined,
  remark: "",
});

const totalRevenueAmount = computed(() => (
  Number(paymentRevenue.value?.total_amount || 0)
  + Number(redeemRevenue.value?.total_amount || 0)
  + Number(offlineOrderRevenue.value?.total_amount || 0)
));

function formatQueryDate(value?: Dayjs) {
  return value ? value.format("YYYY-MM-DDTHH:mm:ss") : undefined;
}

function applyPreset(nextPreset: DatePreset) {
  const now = dayjs();
  preset.value = nextPreset;
  selectedMonth.value = null;
  if (nextPreset === "today") {
    dateRange.value = [now.startOf("day"), now.endOf("day")];
    return;
  }
  if (nextPreset === "3d") {
    dateRange.value = [now.subtract(2, "day").startOf("day"), now.endOf("day")];
    return;
  }
  if (nextPreset === "7d") {
    dateRange.value = [now.subtract(6, "day").startOf("day"), now.endOf("day")];
    return;
  }
  dateRange.value = [now.subtract(29, "day").startOf("day"), now.endOf("day")];
}

function applyMonth(month: Dayjs) {
  preset.value = undefined;
  selectedMonth.value = month;
  dateRange.value = [month.startOf("month"), month.endOf("month")];
}

function handlePresetChange(value: DatePreset) {
  applyPreset(value);
  load();
}

function handleMonthChange(value: Dayjs | null) {
  if (!value) {
    selectedMonth.value = null;
    return;
  }
  applyMonth(value);
  load();
}

function handleDateRangeChange() {
  preset.value = undefined;
  selectedMonth.value = null;
  if (dateRange.value?.[0] && dateRange.value?.[1]) {
    load();
  }
}

function handleReset() {
  selectedMonth.value = null;
  applyPreset("today");
  load();
}

function showDailyReportResult(result: AdminDailyReportTestResult, title = "报告发送结果") {
  Modal.info({
    title,
    width: 560,
    okText: "知道了",
    content: h("div", { class: "daily-report-result" }, [
      h("p", null, `发送状态：${result.sent ? "成功" : "未发送"}`),
      h("p", null, `报告周期：${result.report_date}`),
      h("p", null, `统计区间：${result.range_start} ~ ${result.range_end}`),
      h("p", { class: "daily-report-total" }, `总营业额：¥${Number(result.total_revenue_yuan || 0).toFixed(2)}`),
      h("p", null, `在线支付营业额：¥${Number(result.revenue_yuan || 0).toFixed(2)}`),
      h("p", null, `支付成功订单数：${result.paid_order_count}`),
      h("p", null, `线下订单营业额：¥${Number(result.offline_order_revenue_yuan || 0).toFixed(2)}`),
      h("p", null, `线下订单录入数：${result.offline_order_count}`),
      h("p", null, `兑换码营业额：¥${Number(result.redeem_revenue_yuan || 0).toFixed(2)}`),
      h("p", null, `兑换码使用次数：${result.redeem_used_count}`),
      h("p", null, `任务总数：${result.task_total_count}`),
      h("p", null, `成功任务数：${result.task_success_count}`),
      h("p", null, `失败任务数：${result.task_failed_count}`),
      h("p", null, `积分消耗：${result.credit_consumed}`),
    ]),
  });
}

function formatPeriodRangeLabel(range: [Dayjs, Dayjs]) {
  const start = range[0].startOf("day");
  const end = range[1].endOf("day");
  return `${start.format("YYYY-MM-DD HH:mm:ss")} ~ ${end.format("YYYY-MM-DD HH:mm:ss")}`;
}

async function handleSendDailyReport() {
  sendingDailyReport.value = true;
  try {
    const result = await testAdminDailyReportNotify();
    message.success(result.sent ? "报告发送成功" : "报告未发送，请检查企业微信配置");
    showDailyReportResult(result);
  } catch (err: unknown) {
    if (isSessionExpiredError(err)) return;
    message.error((err as any)?.response?.data?.detail || "发送报告失败");
  } finally {
    sendingDailyReport.value = false;
  }
}

function handleSendCurrentPeriodDailyReport() {
  if (!dateRange.value?.[0] || !dateRange.value?.[1]) {
    message.warning("请先选择统计周期");
    return;
  }
  const periodRange: [Dayjs, Dayjs] = [dateRange.value[0], dateRange.value[1]];
  Modal.confirm({
    title: "确认发送当前周期数据",
    okText: "确认发送",
    cancelText: "取消",
    content: h("div", { class: "daily-report-result" }, [
      h("p", null, "将发送以下统计周期数据到企业微信："),
      h("p", { class: "daily-report-total" }, formatPeriodRangeLabel(periodRange)),
    ]),
    onOk: () => confirmSendCurrentPeriodDailyReport(periodRange),
  });
}

async function confirmSendCurrentPeriodDailyReport(periodRange: [Dayjs, Dayjs]) {
  sendingCurrentPeriodDailyReport.value = true;
  try {
    const [startDate, endDate] = periodRange;
    const result = await sendAdminDailyReportRange({
      start_date: formatQueryDate(startDate.startOf("day"))!,
      end_date: formatQueryDate(endDate.add(1, "day").startOf("day"))!,
    });
    message.success(result.sent ? "当前周期数据发送成功" : "当前周期数据未发送，请检查企业微信配置");
    showDailyReportResult(result, "当前周期数据发送结果");
  } catch (err: unknown) {
    if (isSessionExpiredError(err)) return;
    message.error((err as any)?.response?.data?.detail || "发送当前周期数据失败");
    throw err;
  } finally {
    sendingCurrentPeriodDailyReport.value = false;
  }
}

async function load() {
  if (!dateRange.value?.[0] || !dateRange.value?.[1]) {
    return;
  }
  loading.value = true;
  try {
    const query = {
      granularity: "day",
      start_date: formatQueryDate(dateRange.value[0].startOf("day")),
      end_date: formatQueryDate(dateRange.value[1].endOf("day")),
    } as const;
    const [redeemResult, paymentResult, offlineOrderResult, offlineOrderListResult] = await Promise.all([
      getAdminAnalyticsRedeemRevenue(query),
      getAdminAnalyticsPaymentRevenue(query),
      getAdminAnalyticsOfflineOrderRevenue(query),
      listOfflineOrders({
        page: 1,
        page_size: 100,
        start_date: formatQueryDate(dateRange.value[0].startOf("day")),
        end_date: formatQueryDate(dateRange.value[1].endOf("day")),
      }),
    ]);
    redeemRevenue.value = redeemResult;
    paymentRevenue.value = paymentResult;
    offlineOrderRevenue.value = offlineOrderResult;
    offlineOrderItems.value = offlineOrderListResult.items;
  } catch (err: unknown) {
    if (isSessionExpiredError(err)) return;
    message.error("获取营业额数据失败");
  } finally {
    loading.value = false;
  }
}

const offlineOrderColumns = [
  { title: "类型", dataIndex: "order_type", width: 90 },
  { title: "用户", dataIndex: "username", width: 120, ellipsis: true },
  { title: "积分", dataIndex: "credit_amount", width: 100 },
  { title: "金额（元）", dataIndex: "amount_yuan", width: 120 },
  { title: "备注", dataIndex: "remark", width: 220, ellipsis: true },
  { title: "时间", dataIndex: "created_at", width: 168 },
];

function formatMoney(value?: number) {
  return Number(value || 0).toFixed(2);
}

function formatOfflineOrderType(value: AdminOfflineOrder["order_type"]) {
  return value === "refund" ? "退款" : "购入";
}

function offlineOrderRowKey(record: AdminOfflineOrder) {
  return String(record.business_id || record.id);
}

async function loadUsers() {
  if (users.value.length || usersLoading.value) return;
  usersLoading.value = true;
  try {
    users.value = await listUserOptions();
  } catch (err: unknown) {
    if (isSessionExpiredError(err)) return;
    message.error("获取用户列表失败");
  } finally {
    usersLoading.value = false;
  }
}

function handleOfflineOrderUserDropdownVisible(open: boolean) {
  if (open) void loadUsers();
}

function openOfflineOrderModal() {
  offlineOrderForm.user_id = undefined;
  offlineOrderForm.order_type = "purchase";
  offlineOrderForm.credit_amount = 0;
  offlineOrderForm.amount_yuan = undefined;
  offlineOrderForm.remark = "";
  offlineOrderModalOpen.value = true;
}

async function handleCreateOfflineOrder() {
  if (!offlineOrderForm.user_id) {
    message.warning("请选择用户");
    return;
  }
  if (!offlineOrderForm.credit_amount || offlineOrderForm.credit_amount <= 0) {
    message.warning("请输入有效积分");
    return;
  }
  if (offlineOrderForm.amount_yuan === undefined || offlineOrderForm.amount_yuan === null || offlineOrderForm.amount_yuan <= 0) {
    message.warning("请输入有效金额");
    return;
  }
  creatingOfflineOrder.value = true;
  try {
    await createOfflineOrder({
      user_id: offlineOrderForm.user_id,
      order_type: offlineOrderForm.order_type,
      credit_amount: offlineOrderForm.credit_amount,
      amount_yuan: Number(offlineOrderForm.amount_yuan),
      remark: offlineOrderForm.remark.trim(),
    });
    message.success("线下订单录入成功");
    offlineOrderModalOpen.value = false;
    await Promise.all([load(), revenueChartRef.value?.reload()]);
  } catch (err: unknown) {
    if (isSessionExpiredError(err)) return;
    message.error((err as any)?.response?.data?.detail || "线下订单录入失败");
  } finally {
    creatingOfflineOrder.value = false;
  }
}

onMounted(() => {
  applyPreset("today");
  load();
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
          <div class="warm-page-title">营业额</div>
          <div class="warm-page-desc">统计在线购买与积分兑换码营业额，支持按日期区间或月份筛选；每日收入图按月对比，不受顶部日期影响。</div>
        </div>
      </div>
      <a-button
        v-if="auth.isAdmin"
        type="primary"
        class="warm-primary-btn"
        @click="openOfflineOrderModal"
      >
        <template #icon><PlusOutlined /></template>
        录入线下订单
      </a-button>
      <a-button
        v-if="auth.isSuperAdmin"
        type="primary"
        class="warm-primary-btn revenue-header-btn"
        :loading="sendingDailyReport"
        @click="handleSendDailyReport"
      >
        <template #icon><BellOutlined /></template>
        发送日报到企业微信
      </a-button>
      <a-button
        v-if="auth.isSuperAdmin"
        type="primary"
        class="warm-primary-btn revenue-custom-report-btn"
        :loading="sendingCurrentPeriodDailyReport"
        @click="handleSendCurrentPeriodDailyReport"
      >
        <template #icon><CalendarOutlined /></template>
        发送当前周期数据
      </a-button>
    </div>

    <RevenueTimeseriesChart ref="revenueChartRef" />

    <div class="analytics-filter warm-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <div class="analytics-filter-row">
        <a-range-picker
          v-model:value="dateRange"
          :placeholder="['开始日期', '结束日期']"
          class="analytics-filter-date"
          @change="handleDateRangeChange"
        />
        <a-date-picker
          v-model:value="selectedMonth"
          picker="month"
          placeholder="选择月份"
          format="YYYY年M月"
          :locale="datePickerZhCN"
          class="analytics-filter-date analytics-filter-month"
          @change="handleMonthChange"
        />
        <div class="analytics-filter-panel-compact">
          <a-radio-group
            :value="preset"
            class="analytics-segmented-group analytics-segmented-group-secondary"
            button-style="solid"
            @update:value="handlePresetChange"
          >
            <a-radio-button value="today">今日</a-radio-button>
            <a-radio-button value="3d">近 3 天</a-radio-button>
            <a-radio-button value="7d">近 7 天</a-radio-button>
            <a-radio-button value="30d">近 30 天</a-radio-button>
          </a-radio-group>
        </div>
        <a-button type="primary" class="analytics-action-btn" :loading="loading" @click="load">查询</a-button>
        <a-button class="analytics-action-btn analytics-action-btn-secondary" @click="handleReset">重置</a-button>
        <div class="revenue-total-summary">
          <span class="revenue-total-label">总金额</span>
          <span class="revenue-total-value">¥{{ formatMoney(totalRevenueAmount) }}</span>
        </div>
      </div>
    </div>

    <div class="revenue-section-stack">
      <RedeemRevenueTable
        :data="paymentRevenue"
        :loading="loading"
        title="在线购买营业额"
        count-label="购买"
      >
        <template #footer-extra>
          <a-button type="primary" class="warm-primary-btn" @click="router.push('/admin/payment-orders')">
            <template #icon><UnorderedListOutlined /></template>
            订单详情
          </a-button>
        </template>
      </RedeemRevenueTable>
      <RedeemRevenueTable
        :data="redeemRevenue"
        :loading="loading"
        title="兑换码营业额"
        count-label="兑换"
      >
        <template #footer-extra>
          <a-button
            type="primary"
            class="warm-primary-btn"
            @click="router.push({ path: '/admin/redeem-keys', query: { preset: 'today', is_used: 'true' } })"
          >
            <template #icon><UnorderedListOutlined /></template>
            兑换码详情
          </a-button>
        </template>
      </RedeemRevenueTable>
      <RedeemRevenueTable
        :data="offlineOrderRevenue"
        :loading="loading"
        title="线下订单营业额"
        count-label="录入"
      />
      <div class="offline-order-detail-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 320ms">
        <div class="offline-order-detail-head">
          <div class="redeem-revenue-title">线下订单明细</div>
        </div>
        <a-table
          :columns="offlineOrderColumns"
          :data-source="offlineOrderItems"
          :pagination="false"
          :row-key="offlineOrderRowKey"
          :scroll="{ x: 780 }"
          size="middle"
          class="offline-order-detail-table admin-mobile-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.dataIndex === 'order_type'">
              {{ formatOfflineOrderType(record.order_type) }}
            </template>
            <template v-else-if="column.dataIndex === 'amount_yuan'">
              {{ record.order_type === "refund" ? "-" : "" }}{{ formatMoney(record.amount_yuan) }}
            </template>
            <template v-else-if="column.dataIndex === 'remark'">
              {{ record.remark || "-" }}
            </template>
            <template v-else-if="column.dataIndex === 'created_at'">
              {{ record.created_at ? dayjs(record.created_at).format("YYYY-MM-DD HH:mm:ss") : "-" }}
            </template>
          </template>
        </a-table>
      </div>
    </div>

    <a-modal
      v-model:open="offlineOrderModalOpen"
      title="录入线下订单"
      ok-text="提交"
      cancel-text="取消"
      :confirm-loading="creatingOfflineOrder"
      @ok="handleCreateOfflineOrder"
    >
      <a-form layout="vertical">
        <a-form-item label="用户">
          <a-select
            v-model:value="offlineOrderForm.user_id"
            show-search
            placeholder="请选择用户"
            option-filter-prop="label"
            :loading="usersLoading"
            :options="users.map((user) => ({
              label: user.email ? `${user.username} (${user.email})` : `${user.username} (${user.id})`,
              value: user.id,
            }))"
            @dropdownVisibleChange="handleOfflineOrderUserDropdownVisible"
          />
        </a-form-item>
        <a-form-item label="类型">
          <a-radio-group v-model:value="offlineOrderForm.order_type">
            <a-radio value="purchase">购入</a-radio>
            <a-radio value="refund">退款</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item label="积分">
          <a-input-number
            v-model:value="offlineOrderForm.credit_amount"
            :min="1"
            :precision="0"
            style="width: 100%"
            placeholder="请输入积分"
          />
        </a-form-item>
        <a-form-item label="金额（人民币元）">
          <a-input-number
            v-model:value="offlineOrderForm.amount_yuan"
            :min="0.01"
            :precision="2"
            style="width: 100%"
            placeholder="请输入金额，例如 19.90"
          />
        </a-form-item>
        <a-form-item label="备注">
          <a-textarea
            v-model:value="offlineOrderForm.remark"
            :rows="3"
            :maxlength="500"
            placeholder="可选，填写线下订单备注"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped lang="scss">
.warm-page {
  min-width: 0;
  overflow-x: hidden;
}

.analytics-filter-month {
  width: 148px;
}

.revenue-total-summary {
  margin-left: auto;
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 14px;
  background: rgba(255, 196, 91, 0.18);
  color: #8c7458;
  font-size: 13px;
  font-weight: 600;
}

.revenue-total-value {
  color: #a05f00;
  font-size: 18px;
  font-weight: 800;
  line-height: 1;
}

.revenue-section-stack {
  display: grid;
  gap: 16px;
  min-width: 0;
  margin-top: 0;
}

.offline-order-detail-card {
  padding: 16px 18px 10px;
  min-width: 0;
  overflow: hidden;
}

.offline-order-detail-head {
  margin-bottom: 12px;
}

.offline-order-detail-table {
  min-width: 0;

  :deep(.ant-table) {
    background: transparent;
  }

  :deep(.ant-table-thead > tr > th) {
    background: rgba(255, 248, 236, 0.92);
    color: #8c7458;
    font-weight: 600;
  }

  :deep(.ant-table-tbody > tr > td) {
    color: #5d4526;
  }
}

.revenue-header-btn {
  min-width: 180px;
  margin-left: auto;
}

.revenue-custom-report-btn {
  min-width: 160px;
}

:deep(.daily-report-result) {
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--theme-text);

  p {
    margin: 0;
    line-height: 1.7;
  }

  .daily-report-total {
    color: #a05f00;
    font-weight: 700;
  }
}

@media (max-width: 768px) {
  .analytics-filter-row {
    align-items: stretch;
  }

  .analytics-filter-date,
  .analytics-action-btn {
    width: 100%;
  }

  .analytics-filter-month {
    width: 100%;
  }

  .revenue-total-summary {
    width: 100%;
    justify-content: space-between;
    margin-left: 0;
  }

  .offline-order-detail-card {
    padding-inline: 14px;
  }

  .revenue-header-btn {
    width: 100%;
    margin-left: 0;
  }

  .revenue-custom-report-btn {
    width: 100%;
  }
}
</style>
