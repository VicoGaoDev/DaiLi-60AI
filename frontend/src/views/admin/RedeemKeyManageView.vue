<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { useRoute } from "vue-router";
import { message, Modal } from "ant-design-vue";
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";
import { CopyOutlined, GiftOutlined } from "@ant-design/icons-vue";
import { createRedeemKeysBatch, listRedeemKeys, updateRedeemKeyStatus } from "@/api/admin";
import AdminUserInfoDialog from "@/components/admin/AdminUserInfoDialog.vue";
import { copyText } from "@/lib/clipboard";
import { getAvatarImageSrc } from "@/api/images";
import type { AdminRedeemKey, AdminRedeemKeyBatchResult, AdminUser, RedeemKeyStatus } from "@/types";

type RedeemListState = {
  items: AdminRedeemKey[];
  loading: boolean;
  page: number;
  pageSize: number;
  total: number;
  selectedRowKeys: number[];
};

function createListState(): RedeemListState {
  return reactive({
    items: [],
    loading: false,
    page: 1,
    pageSize: 20,
    total: 0,
    selectedRowKeys: [],
  });
}

const generating = ref(false);
const createDialogOpen = ref(false);
const statusLoadingId = ref<number | null>(null);
const latestBatch = ref<AdminRedeemKeyBatchResult | null>(null);
const saleList = createListState();
const giftList = createListState();
const users = ref<AdminUser[]>([]);
const userInfoOpen = ref(false);
const userInfoTarget = ref<AdminUser | null>(null);
const route = useRoute();
type DateShortcut = "today" | "last7Days" | "thisWeek";
const dateShortcut = ref<DateShortcut | undefined>();

const batchForm = reactive({
  count: 1,
  creditAmount: 100,
  saleAmountYuan: undefined as number | undefined,
  isGift: false,
});

const filters = reactive({
  batchNo: "",
  redeemKey: "",
  creditAmount: undefined as number | undefined,
  status: undefined as RedeemKeyStatus | undefined,
  isUsed: undefined as boolean | undefined,
  usedBy: "",
  dateRange: null as [Dayjs, Dayjs] | null,
});

const sharedColumns = [
  { title: "批次", dataIndex: "batch_no", width: 170 },
  { title: "兑换码", dataIndex: "redeem_key", width: 190 },
  { title: "积分值", dataIndex: "credit_amount", width: 88 },
  { title: "发行人", dataIndex: "created_by_username", width: 120 },
];

const statusColumns = [
  { title: "状态", dataIndex: "status", width: 90 },
  { title: "是否已使用", dataIndex: "is_used", width: 100 },
  { title: "使用人", dataIndex: "used_by_username", width: 220 },
  { title: "使用时间", dataIndex: "used_at", width: 170 },
  { title: "操作", key: "action", width: 120 },
];

const saleColumns = [
  ...sharedColumns,
  { title: "售价", dataIndex: "sale_amount_yuan", width: 100 },
  ...statusColumns,
];

const giftColumns = [...sharedColumns, ...statusColumns];

function onSalePageChange(page: number, pageSize: number) {
  handlePageChange(saleList, false, page, pageSize);
}

function onGiftPageChange(page: number, pageSize: number) {
  handlePageChange(giftList, true, page, pageSize);
}

const tableSections = [
  { kind: "sale" as const, title: "售卖积分", state: saleList, isGift: false, columns: saleColumns, scrollX: 1100, onPageChange: onSalePageChange },
  { kind: "gift" as const, title: "赠送积分", state: giftList, isGift: true, columns: giftColumns, scrollX: 1000, onPageChange: onGiftPageChange },
];

function findAdminUser(userId?: string | null) {
  if (!userId) return null;
  return users.value.find((item) => item.id === userId) || null;
}

function listQuery(state: RedeemListState, isGift: boolean) {
  return {
    page: state.page,
    page_size: state.pageSize,
    batch_no: filters.batchNo.trim() || undefined,
    redeem_key: filters.redeemKey.trim() || undefined,
    credit_amount: filters.creditAmount,
    status: filters.status,
    is_used: filters.isUsed,
    is_gift: isGift,
    used_by: filters.usedBy.trim() || undefined,
    source: "system" as const,
    start_date: formatQueryDate(filters.dateRange?.[0].startOf("day")),
    end_date: formatQueryDate(filters.dateRange?.[1].endOf("day")),
  };
}

async function loadList(state: RedeemListState, isGift: boolean) {
  state.loading = true;
  try {
    const res = await listRedeemKeys(listQuery(state, isGift));
    state.items = res.items;
    state.total = res.total;
    state.selectedRowKeys = [];
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取兑换码列表失败");
  } finally {
    state.loading = false;
  }
}

async function load() {
  await Promise.all([loadList(saleList, false), loadList(giftList, true)]);
}

function resetBatchForm() {
  batchForm.count = 1;
  batchForm.creditAmount = 100;
  batchForm.saleAmountYuan = undefined;
  batchForm.isGift = false;
}

function openCreateDialog() {
  resetBatchForm();
  createDialogOpen.value = true;
}

function handleGiftChange(checked: boolean) {
  batchForm.isGift = checked;
  if (checked) {
    batchForm.saleAmountYuan = undefined;
  }
}

function formatSalePrice(item: Pick<AdminRedeemKey, "is_gift" | "sale_amount_yuan">) {
  if (item.is_gift) return "赠送";
  if (item.sale_amount_yuan != null && item.sale_amount_yuan > 0) {
    return `¥${item.sale_amount_yuan.toFixed(2)}`;
  }
  return "预算";
}

function latestBatchSummary(batch: AdminRedeemKeyBatchResult) {
  const extra = batch.is_gift
    ? "，赠送积分，不计入营业额"
    : batch.sale_amount_yuan != null && batch.sale_amount_yuan > 0
      ? `，售价 ¥${batch.sale_amount_yuan.toFixed(2)}`
      : "，按预算单价";
  return `最近批次：${batch.batch_no}，共 ${batch.count} 个，每个 ${batch.credit_amount} 积分${extra}`;
}

function confirmGiftBatch() {
  const count = batchForm.count;
  const creditAmount = batchForm.creditAmount;
  return new Promise<void>((resolve, reject) => {
    Modal.confirm({
      title: "确认生成赠送兑换码",
      content: `将生成 ${count} 个赠送兑换码，每个 ${creditAmount} 积分，不计入营业额。生成后类型不可修改。`,
      okText: "确认生成",
      cancelText: "取消",
      centered: true,
      zIndex: 1100,
      onOk: () => resolve(),
      onCancel: () => reject(),
    });
  });
}

async function submitCreateBatch() {
  generating.value = true;
  try {
    latestBatch.value = await createRedeemKeysBatch(batchForm.count, batchForm.creditAmount, {
      saleAmountYuan: batchForm.isGift ? undefined : batchForm.saleAmountYuan,
      isGift: batchForm.isGift,
    });
    message.success(`已生成 ${latestBatch.value.count} 个兑换码`);
    createDialogOpen.value = false;
    saleList.page = 1;
    giftList.page = 1;
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "生成兑换码失败");
    throw err;
  } finally {
    generating.value = false;
  }
}

async function handleCreateBatch() {
  if (!batchForm.count || batchForm.count <= 0) {
    message.warning("请输入有效的生成数量");
    return Promise.reject();
  }
  if (!batchForm.creditAmount || batchForm.creditAmount <= 0) {
    message.warning("请输入有效的积分值");
    return Promise.reject();
  }
  if (!batchForm.isGift && batchForm.saleAmountYuan != null && batchForm.saleAmountYuan <= 0) {
    message.warning("金额必须大于 0");
    return Promise.reject();
  }
  if (batchForm.isGift) {
    await confirmGiftBatch();
  }
  await submitCreateBatch();
}

function handleFilter() {
  saleList.page = 1;
  giftList.page = 1;
  load();
}

function handleReset() {
  filters.batchNo = "";
  filters.redeemKey = "";
  filters.creditAmount = undefined;
  filters.status = undefined;
  filters.isUsed = undefined;
  filters.usedBy = "";
  filters.dateRange = null;
  dateShortcut.value = undefined;
  saleList.page = 1;
  giftList.page = 1;
  load();
}

function setDateShortcut(type: DateShortcut) {
  const now = dayjs();
  dateShortcut.value = type;
  if (type === "today") {
    filters.dateRange = [now.startOf("day"), now.endOf("day")];
  } else if (type === "last7Days") {
    filters.dateRange = [now.subtract(6, "day").startOf("day"), now.endOf("day")];
  } else {
    filters.dateRange = [now.startOf("week"), now.endOf("week")];
  }
}

function applyDateShortcut(type: DateShortcut) {
  setDateShortcut(type);
  handleFilter();
}

function handleDateShortcutChange(event: { target: { value: DateShortcut } }) {
  applyDateShortcut(event.target.value);
}

function handleDateRangeChange() {
  dateShortcut.value = undefined;
}

function handlePageChange(state: RedeemListState, isGift: boolean, page: number, pageSize?: number) {
  state.page = page;
  if (pageSize) state.pageSize = pageSize;
  void loadList(state, isGift);
}

function selectedItemsOf(state: RedeemListState) {
  const keySet = new Set(state.selectedRowKeys);
  return state.items.filter((item) => keySet.has(item.id));
}

function isPageFullySelected(state: RedeemListState) {
  return state.items.length > 0 && state.items.every((item) => state.selectedRowKeys.includes(item.id));
}

function tableRowSelection(state: RedeemListState) {
  return {
    selectedRowKeys: state.selectedRowKeys,
    onChange: (keys: Array<string | number>) => {
      state.selectedRowKeys = keys.map((key) => Number(key));
    },
  };
}

async function handleCopy(text: string, successText = "内容已复制") {
  try {
    await copyText(text);
    message.success(successText);
  } catch {
    message.error("复制失败，请重试");
  }
}

async function copyLatestBatch() {
  const keys = latestBatch.value?.items?.map((item) => item.redeem_key).join("\n");
  if (!keys) {
    message.warning("暂无可复制的兑换码");
    return;
  }
  await handleCopy(keys, "兑换码已复制");
}

function toggleSelectCurrentPage(state: RedeemListState) {
  state.selectedRowKeys = isPageFullySelected(state) ? [] : state.items.map((item) => item.id);
}

async function copySelectedKeys(state: RedeemListState) {
  const selectedItems = selectedItemsOf(state);
  const keys = selectedItems.map((item) => item.redeem_key).join("\n");
  if (!keys) {
    message.warning("请先选择当前页兑换码");
    return;
  }
  await handleCopy(keys, `已复制 ${selectedItems.length} 个兑换码`);
}

function openUserInfo(item: AdminRedeemKey) {
  if (!item.used_by_user_id && !item.used_by_username) return;
  const matchedUser = findAdminUser(item.used_by_user_id);
  userInfoTarget.value = matchedUser || {
    id: item.used_by_user_id || "",
    username: item.used_by_username || "未知用户",
    email: item.used_by_user_email || "",
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

async function toggleStatus(item: AdminRedeemKey) {
  if (item.is_used) return;
  const nextStatus: RedeemKeyStatus = item.status === "enabled" ? "disabled" : "enabled";
  statusLoadingId.value = item.id;
  try {
    await updateRedeemKeyStatus(item.id, nextStatus);
    message.success(nextStatus === "enabled" ? "兑换码已启用" : "兑换码已禁用");
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "兑换码状态更新失败");
  } finally {
    statusLoadingId.value = null;
  }
}

function fmtTime(t?: string | null) {
  return t
    ? new Date(t).toLocaleString("zh-CN", {
        timeZone: "Asia/Shanghai",
        hour12: false,
      })
    : "-";
}

function formatQueryDate(value?: Dayjs) {
  return value ? value.format("YYYY-MM-DDTHH:mm:ss") : undefined;
}

function normalizeQueryValue(value: unknown) {
  return Array.isArray(value) ? value[0] : value;
}

function parseBooleanQuery(value: unknown) {
  const normalized = normalizeQueryValue(value);
  if (normalized === "true" || normalized === "1") return true;
  if (normalized === "false" || normalized === "0") return false;
  return undefined;
}

function applyRouteQueryFilters() {
  const presetQuery = normalizeQueryValue(route.query.preset);
  if (presetQuery === "today" || presetQuery === "last7Days" || presetQuery === "thisWeek") {
    setDateShortcut(presetQuery);
  }

  const isUsedQuery = parseBooleanQuery(route.query.is_used ?? route.query.isUsed);
  if (isUsedQuery !== undefined) {
    filters.isUsed = isUsedQuery;
  }
}

onMounted(() => {
  applyRouteQueryFilters();
  void load();
});
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <GiftOutlined />
        </div>
        <div>
          <div class="warm-page-title">兑换码管理</div>
          <div class="warm-page-desc">支持批量生成积分兑换码、查看是否已使用，并对未使用兑换码执行启用或禁用。</div>
        </div>
      </div>
      <div class="header-actions">
        <a-button type="primary" class="warm-primary-btn action-btn" @click="openCreateDialog">
          生成兑换码
        </a-button>
        <a-button class="filter-reset-btn action-btn" @click="copyLatestBatch">复制最近一批</a-button>
      </div>
    </div>

    <div v-if="latestBatch" class="warm-card redeem-batch-summary-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <div class="redeem-batch-summary">
        {{ latestBatchSummary(latestBatch) }}
      </div>
    </div>

    <div class="warm-card redeem-filter-bar motion-fade-up motion-card-lift" style="--motion-delay: 180ms">
      <a-input
        v-model:value="filters.batchNo"
        allow-clear
        placeholder="按批次号筛选"
        class="warm-input redeem-filter-input"
      />
      <a-input
        v-model:value="filters.redeemKey"
        allow-clear
        placeholder="按兑换码筛选"
        class="warm-input redeem-filter-input"
      />
      <a-input-number
        v-model:value="filters.creditAmount"
        :min="1"
        placeholder="按积分值筛选"
        class="warm-input-number redeem-filter-number"
      />
      <a-select
        v-model:value="filters.status"
        allow-clear
        placeholder="兑换码状态"
        class="warm-select redeem-filter-select"
      >
        <a-select-option value="enabled">启用</a-select-option>
        <a-select-option value="disabled">禁用</a-select-option>
      </a-select>
      <a-select
        v-model:value="filters.isUsed"
        allow-clear
        placeholder="使用状态"
        class="warm-select redeem-filter-select"
      >
        <a-select-option :value="true">已使用</a-select-option>
        <a-select-option :value="false">未使用</a-select-option>
      </a-select>
      <a-input
        v-model:value="filters.usedBy"
        allow-clear
        placeholder="按使用人/邮箱筛选"
        class="warm-input redeem-filter-input"
      />
      <a-range-picker
        v-model:value="filters.dateRange"
        :placeholder="['使用开始', '使用结束']"
        class="analytics-filter-date redeem-filter-date"
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
          <a-radio-button value="thisWeek">本周</a-radio-button>
        </a-radio-group>
      </div>
      <a-button type="primary" class="analytics-action-btn action-btn" @click="handleFilter">筛选</a-button>
      <a-button class="analytics-action-btn analytics-action-btn-secondary action-btn" @click="handleReset">重置</a-button>
    </div>

    <div
      v-for="(section, index) in tableSections"
      :key="section.kind"
      class="warm-card warm-table-card redeem-table-card motion-fade-up motion-card-lift"
      :style="{ '--motion-delay': `${240 + index * 60}ms` }"
    >
      <div class="table-section-head">
        <div class="section-title" :class="section.kind === 'gift' ? 'section-title-gift' : 'section-title-sale'">
          {{ section.title }}
        </div>
        <div class="table-toolbar">
          <div class="table-toolbar-summary">
            当前页已选 <span>{{ selectedItemsOf(section.state).length }}</span> / {{ section.state.items.length }}
          </div>
          <div class="table-toolbar-actions">
            <a-button class="filter-reset-btn action-btn table-toolbar-btn" @click="toggleSelectCurrentPage(section.state)">
              {{ isPageFullySelected(section.state) ? "取消全选本页" : "全选本页" }}
            </a-button>
            <a-button class="filter-reset-btn action-btn table-toolbar-btn" @click="copySelectedKeys(section.state)">
              批量复制已选
            </a-button>
          </div>
        </div>
      </div>
      <a-table
        :columns="section.columns"
        :data-source="section.state.items"
        :loading="section.state.loading"
        :pagination="false"
        row-key="id"
        :row-selection="tableRowSelection(section.state)"
        :scroll="{ x: section.scrollX }"
        class="admin-mobile-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'batch_no'">
            <span class="batch-no-text">{{ record.batch_no }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'redeem_key'">
            <div class="id-cell">
              <span class="redeem-key-text">{{ record.redeem_key }}</span>
              <a-button type="text" size="small" class="id-copy-btn" @click="handleCopy(record.redeem_key)">
                <template #icon><CopyOutlined /></template>
              </a-button>
            </div>
          </template>
          <template v-else-if="column.dataIndex === 'credit_amount'">
            <span class="credit-amount">{{ record.credit_amount }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'sale_amount_yuan'">
            <span class="sale-amount">{{ formatSalePrice(record) }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <a-tag class="warm-tag" :class="record.status === 'enabled' ? 'warm-tag-whitelist' : 'warm-tag-muted'">
              {{ record.status === "enabled" ? "启用" : "禁用" }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'is_used'">
            <a-tag class="warm-tag" :class="record.is_used ? 'warm-tag-role-admin' : 'warm-tag-muted'">
              {{ record.is_used ? "已使用" : "未使用" }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'used_by_username'">
            <div v-if="record.used_by_username || record.used_by_user_email" class="used-user-cell">
              <div class="used-user-main">
                <button
                  v-if="record.used_by_user_id || record.used_by_username"
                  type="button"
                  class="user-avatar-btn"
                  title="查看用户信息"
                  @click="openUserInfo(record)"
                >
                  <a-avatar :size="28" :src="getAvatarImageSrc(findAdminUser(record.used_by_user_id)?.avatar_url) || undefined" class="user-avatar">
                    {{ record.used_by_username?.charAt(0)?.toUpperCase() }}
                  </a-avatar>
                </button>
                <span>{{ record.used_by_username || "-" }}</span>
              </div>
              <span v-if="record.used_by_user_email" class="used-user-email">{{ record.used_by_user_email }}</span>
            </div>
            <span v-else>-</span>
          </template>
          <template v-else-if="column.dataIndex === 'used_at'">
            {{ fmtTime(record.used_at) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-button
              type="link"
              size="small"
              class="user-action-btn"
              :class="record.status === 'enabled' ? 'user-action-btn-danger' : 'user-action-btn-secondary'"
              :danger="record.status === 'enabled'"
              :disabled="record.is_used"
              :loading="statusLoadingId === record.id"
              @click="toggleStatus(record)"
            >
              {{ record.status === "enabled" ? "禁用" : "启用" }}
            </a-button>
          </template>
        </template>
      </a-table>
      <div class="warm-pagination redeem-table-pagination">
        <div class="pagination-summary">共 {{ section.state.total }} 个{{ section.kind === "gift" ? "赠送" : "售卖" }}兑换码</div>
        <a-pagination
          v-if="section.state.total > section.state.pageSize"
          :current="section.state.page"
          :total="section.state.total"
          :page-size="section.state.pageSize"
          show-size-changer
          @change="section.onPageChange"
          @showSizeChange="section.onPageChange"
        />
      </div>
    </div>

    <AdminUserInfoDialog v-model:open="userInfoOpen" :user="userInfoTarget" />

    <a-modal
      v-model:open="createDialogOpen"
      title="生成兑换码"
      centered
      :confirm-loading="generating"
      ok-text="生成"
      cancel-text="取消"
      :width="480"
      @ok="handleCreateBatch"
    >
      <a-form layout="vertical" class="redeem-create-form">
        <a-form-item label="生成数量" required>
          <a-input-number v-model:value="batchForm.count" :min="1" :max="1000" class="warm-input-number redeem-full-number" />
        </a-form-item>
        <a-form-item label="每个积分" required>
          <a-input-number v-model:value="batchForm.creditAmount" :min="1" class="warm-input-number redeem-full-number" />
        </a-form-item>
        <a-form-item label="金额（元）">
          <a-input-number
            v-model:value="batchForm.saleAmountYuan"
            :min="0.01"
            :precision="2"
            :disabled="batchForm.isGift"
            class="warm-input-number redeem-full-number"
            placeholder="不填则按预算单价计算营业额"
          />
        </a-form-item>
        <a-form-item label="赠送积分">
          <a-switch v-model:checked="batchForm.isGift" @change="handleGiftChange" />
          <div class="redeem-form-hint">勾选后该批兑换码不计入营业额</div>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped lang="scss">
.header-actions,
.redeem-filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.redeem-table-card {
  margin-bottom: 16px;
}

.table-section-head {
  padding: 16px 16px 0;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--theme-title);
  font-size: 16px;
  font-weight: 800;
}

.section-title-sale {
  color: #b45309;
}

.section-title-gift {
  color: #1f7a45;
}

.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 0 16px;
  flex-wrap: wrap;
}

.redeem-table-pagination {
  padding: 4px 16px 16px;
}

.table-toolbar-summary {
  color: #8c7458;
  font-size: 13px;

  span {
    color: #b26c04;
    font-weight: 700;
  }
}

.table-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.table-toolbar-btn {
  min-width: 108px;
}

.redeem-create-form {
  padding-top: 8px;
}

.redeem-full-number {
  width: 100%;
}

.redeem-form-hint {
  margin-top: 8px;
  color: #8c7458;
  font-size: 12px;
  line-height: 1.5;
}

.redeem-batch-summary-card {
  padding: 16px 20px;
  margin-bottom: 16px;
}

.redeem-batch-summary {
  color: #8c7458;
  font-size: 14px;
}

.redeem-filter-bar {
  padding: 12px 14px;
  margin-bottom: 16px;
  flex-wrap: nowrap;
  overflow-x: auto;
}

.redeem-filter-input {
  width: 148px;
  flex: 0 0 148px;
}

.redeem-half-number {
  width: 112px;
}

.redeem-filter-number {
  width: 112px;
  flex: 0 0 112px;
}

.redeem-filter-select {
  width: 104px;
  flex: 0 0 104px;
}

.redeem-filter-date {
  width: 218px;
  flex: 0 0 218px;
}

.action-btn {
  min-width: 72px;
  height: 36px;
  padding-inline: 12px;
  flex: 0 0 auto;
}

.pagination-summary {
  color: #8c7458;
  font-size: 13px;
  white-space: nowrap;
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
  color: var(--theme-accent-text) !important;
}

.redeem-key-text {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  font-weight: 700;
  color: #8c7458;
}

.batch-no-text {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  font-weight: 700;
  color: #8c7458;
}

.credit-amount,
.sale-amount {
  font-weight: 700;
  color: var(--theme-accent-text);
}

.warm-tag-gift {
  color: #1f7a45 !important;
  background: #e6f7ed !important;
  border-color: #8fd4a8 !important;
}

.warm-tag-sale {
  color: #b45309 !important;
  background: #fff1d6 !important;
  border-color: #f0b45a !important;
}

.used-user-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.used-user-main {
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

.used-user-email {
  color: #8c7458;
  font-size: 12px;
  word-break: break-all;
}

.user-action-btn {
  height: 30px;
  padding-inline: 6px;
  border-radius: 9px;
  font-weight: 600;
  font-size: 12px;
  margin: 0;
}

.user-action-btn.user-action-btn-secondary {
  color: var(--theme-accent-text) !important;
  background: var(--theme-panel-bg-soft) !important;
}

.user-action-btn.user-action-btn-danger {
  color: #d6574b !important;
  background: #fff1ef !important;
}

.warm-tag {
  border-radius: 999px;
  border-width: 1px;
  font-weight: 600;
}

.warm-tag-role-admin {
  color: var(--theme-accent-text);
  background: var(--theme-panel-bg-strong);
  border-color: var(--theme-panel-border-strong);
}

.warm-tag-whitelist {
  color: var(--theme-accent-text-hover);
  background: var(--theme-panel-bg-strong);
  border-color: var(--theme-border-strong);
}

.warm-tag-muted {
  color: var(--text-secondary);
  background: var(--theme-empty-bg);
  border-color: var(--theme-panel-border);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .section-title-gift {
  color: #8ee0a8;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .section-title-sale {
  color: #ffc56a;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .warm-tag-gift {
  color: #8ee0a8 !important;
  background: #1c3a28 !important;
  border-color: #3f7a54 !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .warm-tag-sale {
  color: #ffc56a !important;
  background: #3a2710 !important;
  border-color: #8a5c1e !important;
}

.filter-reset-btn {
  height: 36px;
  border-radius: 12px;
  border: 1px solid var(--theme-control-border-strong) !important;
  background: var(--theme-control-bg) !important;
  color: var(--theme-accent-text) !important;
}

.filter-reset-btn:hover {
  border-color: var(--theme-border-strong) !important;
  background: var(--theme-control-hover-bg) !important;
  color: var(--theme-accent-text-hover) !important;
}

:deep(.admin-mobile-table .ant-table-thead > tr > th) {
  padding: 11px 12px;
  white-space: nowrap;
}

:deep(.admin-mobile-table .ant-table-tbody > tr > td) {
  padding: 8px 12px;
}

@media (max-width: 768px) {
  .header-actions,
  .redeem-filter-bar,
  .table-section-head,
  .table-toolbar,
  .table-toolbar-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .redeem-filter-input,
  .redeem-half-number,
  .redeem-filter-number,
  .redeem-filter-select,
  .redeem-filter-date {
    width: 100%;
    flex-basis: auto;
  }

  .action-btn {
    width: 100%;
  }

  :deep(.admin-mobile-table .ant-table-content) {
    overflow-x: auto !important;
  }
}
</style>
