<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { message, Modal } from "ant-design-vue";
import { CopyOutlined, DeleteOutlined, GiftOutlined } from "@ant-design/icons-vue";
import { createAgentRedeemKeysBatch, deleteAgentRedeemKey, getAgentOverview, listAgentRedeemKeys, updateAgentRedeemKeyStatus } from "@/api/agent";
import { copyText } from "@/lib/clipboard";
import type { AdminRedeemKey, AdminRedeemKeyBatchResult, AgentOverview, RedeemKeyStatus } from "@/types";

const loading = ref(false);
const generating = ref(false);
const statusLoadingId = ref<number | null>(null);
const deletingId = ref<number | null>(null);
const latestBatch = ref<AdminRedeemKeyBatchResult | null>(null);
const items = ref<AdminRedeemKey[]>([]);
const selectedRowKeys = ref<number[]>([]);
const overview = ref<AgentOverview>({ pool_credits: 0, unused_redeem_credits: 0, issuable_credits: 0, redeemed_credits: 0 });
const batchForm = reactive({ count: 10, creditAmount: 10 });
const filters = reactive({ batchNo: "", redeemKey: "", creditAmount: undefined as number | undefined, status: undefined as RedeemKeyStatus | undefined, isUsed: undefined as boolean | undefined, usedBy: "" });
const pagination = reactive({ page: 1, pageSize: 20, total: 0 });

const columns = [
  { title: "批次", dataIndex: "batch_no", width: 170 },
  { title: "兑换码", dataIndex: "redeem_key", width: 190 },
  { title: "积分值", dataIndex: "credit_amount", width: 88 },
  { title: "状态", dataIndex: "status", width: 90 },
  { title: "是否已使用", dataIndex: "is_used", width: 100 },
  { title: "使用人", dataIndex: "used_by_username", width: 160 },
  { title: "使用时间", dataIndex: "used_at", width: 170 },
  { title: "操作", key: "action", width: 160 },
];
const selectedItems = computed(() => items.value.filter((item) => selectedRowKeys.value.includes(item.id)));
const batchTotalCredits = computed(() => Number(batchForm.count || 0) * Number(batchForm.creditAmount || 0));
const rowSelection = computed(() => ({
  selectedRowKeys: selectedRowKeys.value,
  onChange: (keys: Array<string | number>) => { selectedRowKeys.value = keys.map((key) => Number(key)); },
}));

async function load() {
  loading.value = true;
  try {
    const [summary, res] = await Promise.all([getAgentOverview(), listAgentRedeemKeys({
      page: pagination.page,
      page_size: pagination.pageSize,
      batch_no: filters.batchNo.trim() || undefined,
      redeem_key: filters.redeemKey.trim() || undefined,
      credit_amount: filters.creditAmount,
      status: filters.status,
      is_used: filters.isUsed,
      used_by: filters.usedBy.trim() || undefined,
    })]);
    overview.value = summary;
    items.value = res.items;
    pagination.total = res.total;
    selectedRowKeys.value = [];
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取兑换码列表失败");
  } finally {
    loading.value = false;
  }
}

async function handleCreateBatch() {
  if (!batchForm.count || batchForm.count <= 0 || !batchForm.creditAmount || batchForm.creditAmount <= 0) {
    message.warning("请输入有效的生成数量和积分值");
    return;
  }
  if (batchTotalCredits.value > overview.value.issuable_credits) {
    message.warning(`本批需要 ${batchTotalCredits.value} 积分，当前最多还可发放 ${overview.value.issuable_credits} 积分`);
    return;
  }
  generating.value = true;
  try {
    latestBatch.value = await createAgentRedeemKeysBatch(batchForm.count, batchForm.creditAmount);
    message.success(`已生成 ${latestBatch.value.count} 个兑换码`);
    pagination.page = 1;
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "生成兑换码失败");
  } finally {
    generating.value = false;
  }
}

async function copyKeys(keys: string[], successText: string) {
  if (!keys.length) {
    message.warning("暂无可复制的兑换码");
    return;
  }
  try {
    await copyText(keys.join("\n"));
    message.success(successText);
  } catch {
    message.error("复制失败，请重试");
  }
}

function handleFilter() { pagination.page = 1; load(); }
function handleReset() {
  filters.batchNo = "";
  filters.redeemKey = "";
  filters.creditAmount = undefined;
  filters.status = undefined;
  filters.isUsed = undefined;
  filters.usedBy = "";
  pagination.page = 1;
  load();
}
function handlePageChange(page: number, pageSize?: number) { pagination.page = page; if (pageSize) pagination.pageSize = pageSize; load(); }
function fmtTime(t?: string | null) { return t ? new Date(t).toLocaleString("zh-CN", { hour12: false }) : "-"; }

async function toggleStatus(item: AdminRedeemKey) {
  const nextStatus: RedeemKeyStatus = item.status === "enabled" ? "disabled" : "enabled";
  statusLoadingId.value = item.id;
  try {
    await updateAgentRedeemKeyStatus(item.id, nextStatus);
    message.success(nextStatus === "enabled" ? "兑换码已启用" : "兑换码已禁用");
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "兑换码状态更新失败");
  } finally {
    statusLoadingId.value = null;
  }
}

function confirmDelete(item: AdminRedeemKey) {
  Modal.confirm({
    title: `确认删除兑换码 ${item.redeem_key}？`,
    content: "仅未使用的代理兑换码可以删除，删除后会释放占用额度。",
    okText: "删除",
    okButtonProps: { danger: true },
    centered: true,
    async onOk() {
      deletingId.value = item.id;
      try {
        await deleteAgentRedeemKey(item.id);
        message.success("兑换码已删除");
        await load();
      } catch (err: any) {
        message.error(err.response?.data?.detail || "删除失败");
      } finally {
        deletingId.value = null;
      }
    },
  });
}

onMounted(load);
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon"><GiftOutlined /></div>
        <div>
          <div class="warm-page-title">代理兑换码</div>
          <div class="warm-page-desc">发码不预扣积分池；用户兑换成功时才从代理积分池扣减。</div>
        </div>
      </div>
      <div class="header-actions">
        <a-form layout="inline" class="redeem-create-form">
          <a-form-item label="生成数量"><a-input-number v-model:value="batchForm.count" :min="1" :max="1000" class="warm-input-number redeem-half-number" /></a-form-item>
          <a-form-item label="每个积分"><a-input-number v-model:value="batchForm.creditAmount" :min="1" class="warm-input-number redeem-half-number" /></a-form-item>
          <a-button type="primary" class="warm-primary-btn action-btn" :loading="generating" @click="handleCreateBatch">批量生成</a-button>
          <a-button class="filter-reset-btn action-btn" @click="copyKeys(latestBatch?.items?.map((item) => item.redeem_key) || [], '兑换码已复制')">复制最近一批</a-button>
        </a-form>
      </div>
    </div>

    <div class="overview-grid motion-fade-up" style="--motion-delay: 100ms">
      <div class="warm-card overview-card">
        <div class="overview-label">积分池剩余</div>
        <div class="overview-value">{{ overview.pool_credits }}</div>
      </div>
      <div class="warm-card overview-card">
        <div class="overview-label">未兑启用码占用</div>
        <div class="overview-value warning">{{ overview.unused_redeem_credits }}</div>
      </div>
      <div class="warm-card overview-card">
        <div class="overview-label">还能发放</div>
        <div class="overview-value success">{{ overview.issuable_credits }}</div>
      </div>
      <div class="warm-card overview-card">
        <div class="overview-label">本批需要</div>
        <div class="overview-value">{{ batchTotalCredits }}</div>
      </div>
    </div>

    <div v-if="latestBatch" class="warm-card redeem-batch-summary-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      最近批次：{{ latestBatch.batch_no }}，共 {{ latestBatch.count }} 个，每个 {{ latestBatch.credit_amount }} 积分
    </div>

    <div class="warm-card redeem-filter-bar motion-fade-up motion-card-lift" style="--motion-delay: 180ms">
      <a-input v-model:value="filters.batchNo" allow-clear placeholder="按批次号筛选" class="warm-input redeem-filter-input" />
      <a-input v-model:value="filters.redeemKey" allow-clear placeholder="按兑换码筛选" class="warm-input redeem-filter-input" />
      <a-input-number v-model:value="filters.creditAmount" :min="1" placeholder="积分值" class="warm-input-number redeem-filter-number" />
      <a-select v-model:value="filters.status" allow-clear placeholder="状态" class="warm-select redeem-filter-select">
        <a-select-option value="enabled">启用</a-select-option>
        <a-select-option value="disabled">禁用</a-select-option>
      </a-select>
      <a-select v-model:value="filters.isUsed" allow-clear placeholder="使用状态" class="warm-select redeem-filter-select">
        <a-select-option :value="true">已使用</a-select-option>
        <a-select-option :value="false">未使用</a-select-option>
      </a-select>
      <a-input v-model:value="filters.usedBy" allow-clear placeholder="使用人/邮箱" class="warm-input redeem-filter-input" />
      <a-button type="primary" class="analytics-action-btn action-btn" @click="handleFilter">筛选</a-button>
      <a-button class="analytics-action-btn analytics-action-btn-secondary action-btn" @click="handleReset">重置</a-button>
    </div>

    <div class="warm-card warm-table-card motion-fade-up motion-card-lift" style="--motion-delay: 240ms">
      <div class="table-toolbar">
        <div class="table-toolbar-summary">当前页已选 <span>{{ selectedItems.length }}</span> / {{ items.length }}</div>
        <a-button class="filter-reset-btn action-btn table-toolbar-btn" @click="copyKeys(selectedItems.map((item) => item.redeem_key), `已复制 ${selectedItems.length} 个兑换码`)">复制已选</a-button>
      </div>
      <a-table :columns="columns" :data-source="items" :loading="loading" :pagination="false" row-key="id" :row-selection="rowSelection" :scroll="{ x: 1040 }" class="admin-mobile-table">
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'redeem_key'">
            <div class="id-cell"><span class="redeem-key-text">{{ record.redeem_key }}</span><a-button type="text" size="small" class="id-copy-btn" @click="copyKeys([record.redeem_key], '兑换码已复制')"><template #icon><CopyOutlined /></template></a-button></div>
          </template>
          <template v-else-if="column.dataIndex === 'credit_amount'"><span class="credit-amount">{{ record.credit_amount }}</span></template>
          <template v-else-if="column.dataIndex === 'status'"><a-tag class="warm-tag" :class="record.status === 'enabled' ? 'warm-tag-whitelist' : 'warm-tag-muted'">{{ record.status === "enabled" ? "启用" : "禁用" }}</a-tag></template>
          <template v-else-if="column.dataIndex === 'is_used'"><a-tag class="warm-tag" :class="record.is_used ? 'warm-tag-role-admin' : 'warm-tag-muted'">{{ record.is_used ? "已使用" : "未使用" }}</a-tag></template>
          <template v-else-if="column.dataIndex === 'used_by_username'">{{ record.used_by_username || "-" }}</template>
          <template v-else-if="column.dataIndex === 'used_at'">{{ fmtTime(record.used_at) }}</template>
          <template v-else-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" :danger="record.status === 'enabled'" :disabled="record.is_used" :loading="statusLoadingId === record.id" @click="toggleStatus(record)">{{ record.status === "enabled" ? "禁用" : "启用" }}</a-button>
              <a-button type="link" size="small" danger :disabled="record.is_used" :loading="deletingId === record.id" @click="confirmDelete(record)"><template #icon><DeleteOutlined /></template>删除</a-button>
            </a-space>
          </template>
        </template>
      </a-table>
    </div>

    <div class="warm-pagination">
      <div class="pagination-summary">共 {{ pagination.total }} 个兑换码</div>
      <a-pagination v-if="pagination.total > pagination.pageSize" :current="pagination.page" :total="pagination.total" :page-size="pagination.pageSize" show-size-changer @change="handlePageChange" @showSizeChange="handlePageChange" />
    </div>
  </div>
</template>

<style scoped lang="scss">
.header-actions,
.redeem-filter-bar,
.table-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.redeem-create-form { display: flex; flex-wrap: wrap; gap: 12px; justify-content: flex-end; }
.overview-grid { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.overview-card { flex: 1 1 180px; padding: 18px; }
.overview-label { color: #8c7458; font-size: 13px; }
.overview-value { margin-top: 6px; color: var(--theme-title); font-size: 28px; font-weight: 800; }
.overview-value.warning { color: #d48806; }
.overview-value.success { color: #389e0d; }
.redeem-batch-summary-card { padding: 16px 20px; margin-bottom: 16px; color: #8c7458; }
.redeem-filter-bar { padding: 12px 14px; margin-bottom: 16px; overflow-x: auto; }
.redeem-filter-input { width: 148px; flex: 0 0 148px; }
.redeem-half-number { width: 112px; }
.redeem-filter-number { width: 112px; flex: 0 0 112px; }
.redeem-filter-select { width: 104px; flex: 0 0 104px; }
.action-btn { min-width: 72px; height: 36px; padding-inline: 12px; flex: 0 0 auto; }
.table-toolbar { justify-content: space-between; padding: 16px 16px 18px; }
.table-toolbar-summary { color: #8c7458; font-size: 13px; }
.table-toolbar-summary span,
.credit-amount { color: #b26c04; font-weight: 800; }
.id-cell { display: inline-flex; align-items: center; gap: 4px; }
.redeem-key-text { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-weight: 800; letter-spacing: 0.04em; }
.pagination-summary { color: #8c7458; font-size: 13px; }
</style>
