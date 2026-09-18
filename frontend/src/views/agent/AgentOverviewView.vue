<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { message, Modal } from "ant-design-vue";
import { CopyOutlined, DeleteOutlined, GiftOutlined, HistoryOutlined, LockOutlined, UnlockOutlined, WalletOutlined } from "@ant-design/icons-vue";
import {
  createAgentRedeemKeysBatch,
  deleteAgentRedeemKey,
  getAgentCreditLogs,
  getAgentOverview,
  listAgentRedeemKeys,
  updateAgentRedeemKeyLock,
  updateAgentRedeemKeyStatus,
} from "@/api/agent";
import { copyText } from "@/lib/clipboard";
import type { AdminRedeemKey, AdminRedeemKeyBatchResult, AgentOverview, CreditLog, RedeemKeyStatus } from "@/types";

type AgentLogTypeFilter = "allocate" | "agent_pool_deduct";

const overviewLoading = ref(false);
const redeemLoading = ref(false);
const logsLoading = ref(false);
const generating = ref(false);
const deletingBatch = ref(false);
const batchLockingAction = ref<"lock" | "unlock" | null>(null);
const activeSectionTab = ref("redeem");
const lockLoadingId = ref<number | null>(null);
const statusLoadingId = ref<number | null>(null);
const deletingId = ref<number | null>(null);

const overview = ref<AgentOverview>({
  pool_credits: 0,
  unused_redeem_credits: 0,
  issuable_credits: 0,
  redeemed_credits: 0,
});

const latestBatch = ref<AdminRedeemKeyBatchResult | null>(null);
const redeemItems = ref<AdminRedeemKey[]>([]);
const selectedRowKeys = ref<number[]>([]);
const logItems = ref<CreditLog[]>([]);
const filteredRedeemedCredits = ref(0);

const batchForm = reactive({ count: 10, creditAmount: 10 });
const redeemFilters = reactive({
  batchNo: "",
  redeemKey: "",
  creditAmount: undefined as number | undefined,
  status: undefined as RedeemKeyStatus | undefined,
  isUsed: undefined as boolean | undefined,
  usedBy: "",
});
const logsFilters = reactive({
  userKeyword: "",
  type: undefined as AgentLogTypeFilter | undefined,
  redeemKey: "",
});
const logsDateRange = ref<string[]>(getTodayDateRange());

const redeemPagination = reactive({ page: 1, pageSize: 20, total: 0 });
const logsPagination = reactive({ page: 1, pageSize: 20, total: 0 });

const redeemColumns = [
  { title: "批次", dataIndex: "batch_no", width: 170 },
  { title: "兑换码", dataIndex: "redeem_key", width: 190 },
  { title: "积分值", dataIndex: "credit_amount", width: 88 },
  { title: "状态", dataIndex: "status", width: 90 },
  { title: "锁定状态", dataIndex: "is_locked", width: 110 },
  { title: "是否已使用", dataIndex: "is_used", width: 100 },
  { title: "使用人", dataIndex: "used_by_username", width: 160 },
  { title: "使用时间", dataIndex: "used_at", width: 170 },
  { title: "操作", key: "action", width: 240 },
];

const selectedRedeemItems = computed(() => redeemItems.value.filter((item) => selectedRowKeys.value.includes(item.id)));
const deletableSelectedRedeemItems = computed(() => selectedRedeemItems.value.filter((item) => !item.is_used && !item.is_locked));
const selectedLockedRedeemItems = computed(() => selectedRedeemItems.value.filter((item) => item.is_locked));
const selectedUnlockedRedeemItems = computed(() => selectedRedeemItems.value.filter((item) => !item.is_locked));
const selectedUsedRedeemItems = computed(() => selectedRedeemItems.value.filter((item) => item.is_used));
const recoverableSelectedCredits = computed(() =>
  deletableSelectedRedeemItems.value.reduce(
    (sum, item) => sum + (item.status === "enabled" && !item.is_used ? Number(item.credit_amount || 0) : 0),
    0,
  )
);
const batchTotalCredits = computed(() => Number(batchForm.count || 0) * Number(batchForm.creditAmount || 0));
const rowSelection = computed(() => ({
  selectedRowKeys: selectedRowKeys.value,
  onChange: (keys: Array<string | number>) => {
    selectedRowKeys.value = keys.map((key) => Number(key));
  },
}));

async function loadOverview() {
  overviewLoading.value = true;
  try {
    overview.value = await getAgentOverview();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取代理人总览失败");
  } finally {
    overviewLoading.value = false;
  }
}

async function loadRedeemKeys() {
  redeemLoading.value = true;
  try {
    const res = await listAgentRedeemKeys({
      page: redeemPagination.page,
      page_size: redeemPagination.pageSize,
      batch_no: redeemFilters.batchNo.trim() || undefined,
      redeem_key: redeemFilters.redeemKey.trim() || undefined,
      credit_amount: redeemFilters.creditAmount,
      status: redeemFilters.status,
      is_used: redeemFilters.isUsed,
      used_by: redeemFilters.usedBy.trim() || undefined,
    });
    redeemItems.value = res.items;
    redeemPagination.total = res.total;
    selectedRowKeys.value = [];
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取兑换码列表失败");
  } finally {
    redeemLoading.value = false;
  }
}

async function loadCreditLogs() {
  logsLoading.value = true;
  try {
    const res = await getAgentCreditLogs({
      page: logsPagination.page,
      page_size: logsPagination.pageSize,
      user_keyword: logsFilters.userKeyword.trim() || undefined,
      type: logsFilters.type,
      redeem_key: logsFilters.redeemKey.trim() || undefined,
      start_date: logsDateRange.value[0] ? `${logsDateRange.value[0]} 00:00:00` : undefined,
      end_date: logsDateRange.value[1] ? `${logsDateRange.value[1]} 23:59:59` : undefined,
    });
    logItems.value = res.items;
    logsPagination.total = res.total;
    filteredRedeemedCredits.value = Number(res.redeemed_credits || 0);
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取积分池流水失败");
  } finally {
    logsLoading.value = false;
  }
}

async function loadAll() {
  await Promise.all([loadOverview(), loadRedeemKeys(), loadCreditLogs()]);
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
  Modal.confirm({
    title: "确认批量生成兑换码？",
    content: `将生成 ${batchForm.count} 个兑换码，每个 ${batchForm.creditAmount} 积分，本批共 ${batchTotalCredits.value} 积分。`,
    okText: "确认生成",
    cancelText: "取消",
    centered: true,
    async onOk() {
      generating.value = true;
      try {
        latestBatch.value = await createAgentRedeemKeysBatch(batchForm.count, batchForm.creditAmount);
        message.success(`已生成 ${latestBatch.value.count} 个兑换码`);
        redeemPagination.page = 1;
        await Promise.all([loadOverview(), loadRedeemKeys()]);
      } catch (err: any) {
        message.error(err.response?.data?.detail || "生成兑换码失败");
      } finally {
        generating.value = false;
      }
    },
  });
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

function handleRedeemFilter() {
  redeemPagination.page = 1;
  void loadRedeemKeys();
}

function handleRedeemReset() {
  redeemFilters.batchNo = "";
  redeemFilters.redeemKey = "";
  redeemFilters.creditAmount = undefined;
  redeemFilters.status = undefined;
  redeemFilters.isUsed = undefined;
  redeemFilters.usedBy = "";
  redeemPagination.page = 1;
  void loadRedeemKeys();
}

function handleRedeemPageChange(page: number, pageSize?: number) {
  redeemPagination.page = page;
  if (pageSize) redeemPagination.pageSize = pageSize;
  void loadRedeemKeys();
}

function handleLogsPageChange(page: number, pageSize?: number) {
  logsPagination.page = page;
  if (pageSize) logsPagination.pageSize = pageSize;
  void loadCreditLogs();
}

function handleLogsFilter() {
  logsPagination.page = 1;
  void loadCreditLogs();
}

function handleLogsReset() {
  logsFilters.userKeyword = "";
  logsFilters.type = undefined;
  logsFilters.redeemKey = "";
  logsDateRange.value = getTodayDateRange();
  logsPagination.page = 1;
  void loadCreditLogs();
}

function pad2(value: number) {
  return String(value).padStart(2, "0");
}

function formatDateOnly(date: Date) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function getTodayDateRange() {
  const today = formatDateOnly(new Date());
  return [today, today];
}

function fmtTime(t?: string | null) {
  return t ? new Date(t).toLocaleString("zh-CN", { hour12: false }) : "-";
}

function fmtAgentLogType(log: CreditLog) {
  if (log.type === "agent_pool_deduct") return "用户兑换扣减";
  if (log.type === "allocate") return Number(log.amount || 0) >= 0 ? "管理员充值" : "管理员扣减";
  return log.type || "-";
}

function fmtAgentLogDescription(log: CreditLog) {
  const description = (log.description || "").trim();
  if (!description) return "-";
  if (log.type === "agent_pool_deduct") {
    return "用户兑换";
  }
  return description;
}

async function toggleStatus(item: AdminRedeemKey) {
  const nextStatus: RedeemKeyStatus = item.status === "enabled" ? "disabled" : "enabled";
  statusLoadingId.value = item.id;
  try {
    await updateAgentRedeemKeyStatus(item.id, nextStatus);
    message.success(nextStatus === "enabled" ? "兑换码已启用" : "兑换码已禁用");
    await Promise.all([loadOverview(), loadRedeemKeys()]);
  } catch (err: any) {
    message.error(err.response?.data?.detail || "兑换码状态更新失败");
  } finally {
    statusLoadingId.value = null;
  }
}

async function toggleLock(item: AdminRedeemKey) {
  const nextLocked = !item.is_locked;
  lockLoadingId.value = item.id;
  try {
    await updateAgentRedeemKeyLock(item.id, nextLocked);
    message.success(nextLocked ? "兑换码已锁定" : "兑换码已解除锁定");
    await loadRedeemKeys();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "兑换码锁定状态更新失败");
  } finally {
    lockLoadingId.value = null;
  }
}

function confirmBatchLock(targetLocked: boolean) {
  if (!selectedRedeemItems.value.length) {
    message.warning(`请先选择要${targetLocked ? "锁定" : "解锁"}的兑换码`);
    return;
  }
  if (selectedUsedRedeemItems.value.length) {
    message.warning("已使用兑换码不可批量修改锁定状态，请先取消这些勾选");
    return;
  }

  const targetItems = targetLocked ? selectedUnlockedRedeemItems.value : selectedLockedRedeemItems.value;
  if (!targetItems.length) {
    message.warning(targetLocked ? "所选兑换码已全部锁定" : "所选兑换码已全部解锁");
    return;
  }

  Modal.confirm({
    title: `确认批量${targetLocked ? "锁定" : "解锁"}兑换码？`,
    content: `将${targetLocked ? "锁定" : "解锁"} ${targetItems.length} 个兑换码。`,
    okText: targetLocked ? "确认锁定" : "确认解锁",
    cancelText: "取消",
    centered: true,
    async onOk() {
      batchLockingAction.value = targetLocked ? "lock" : "unlock";
      try {
        for (const item of targetItems) {
          await updateAgentRedeemKeyLock(item.id, targetLocked);
        }
        message.success(`已${targetLocked ? "锁定" : "解锁"} ${targetItems.length} 个兑换码`);
        await loadRedeemKeys();
      } catch (err: any) {
        message.error(err.response?.data?.detail || `批量${targetLocked ? "锁定" : "解锁"}失败`);
      } finally {
        batchLockingAction.value = null;
      }
    },
  });
}

function confirmDelete(item: AdminRedeemKey) {
  if (item.is_locked) {
    message.warning("兑换码已锁定，请先解除锁定后再删除");
    return;
  }
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
        await Promise.all([loadOverview(), loadRedeemKeys()]);
      } catch (err: any) {
        message.error(err.response?.data?.detail || "删除失败");
      } finally {
        deletingId.value = null;
      }
    },
  });
}

function confirmBatchDelete() {
  if (!selectedRedeemItems.value.length) {
    message.warning("请先选择要删除的兑换码");
    return;
  }
  if (selectedUsedRedeemItems.value.length) {
    message.warning("已使用兑换码不可批量删除，请先取消这些勾选");
    return;
  }
  if (selectedLockedRedeemItems.value.length) {
    message.warning("已锁定兑换码不可批量删除，请先解除锁定后再删除");
    return;
  }
  Modal.confirm({
    title: "确认批量删除兑换码？",
    content: `将删除 ${deletableSelectedRedeemItems.value.length} 个兑换码，可回收占用积分 ${recoverableSelectedCredits.value}。`,
    okText: "确认删除",
    cancelText: "取消",
    okButtonProps: { danger: true },
    centered: true,
    async onOk() {
      deletingBatch.value = true;
      try {
        for (const item of deletableSelectedRedeemItems.value) {
          await deleteAgentRedeemKey(item.id);
        }
        message.success(`已删除 ${deletableSelectedRedeemItems.value.length} 个兑换码`);
        await Promise.all([loadOverview(), loadRedeemKeys()]);
      } catch (err: any) {
        message.error(err.response?.data?.detail || "批量删除失败");
      } finally {
        deletingBatch.value = false;
      }
    },
  });
}

onMounted(() => {
  void loadAll();
});
</script>

<template>
  <div class="warm-page motion-page-enter agent-overview-page">
    <a-spin :spinning="overviewLoading">
      <div class="warm-card top-summary-card motion-fade-up motion-card-lift" style="--motion-delay: 40ms">
        <div class="top-summary-layout">
          <div class="warm-page-heading">
            <div class="warm-page-icon"><WalletOutlined /></div>
            <div>
              <div class="warm-page-title">代理后台</div>
              <div class="warm-page-desc">查看代理积分池、未兑启用码占用和可继续发放额度。</div>
            </div>
          </div>
          <div class="overview-grid">
            <div class="overview-mini-card">
              <div class="overview-label">积分池剩余</div>
              <div class="overview-value">{{ overview.pool_credits }}</div>
            </div>
            <div class="overview-operator" aria-hidden="true">=</div>
            <div class="overview-mini-card">
              <div class="overview-label">未兑启用码占用</div>
              <div class="overview-value warning">{{ overview.unused_redeem_credits }}</div>
            </div>
            <div class="overview-operator" aria-hidden="true">+</div>
            <div class="overview-mini-card">
              <div class="overview-label">还能发放</div>
              <div class="overview-value success">{{ overview.issuable_credits }}</div>
            </div>
          </div>
        </div>
      </div>
    </a-spin>

    <div class="warm-card section-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <a-tabs v-model:activeKey="activeSectionTab" class="agent-section-tabs">
        <a-tab-pane key="redeem" tab="兑换码管理">
          <div class="tab-pane-content redeem-section-card">
            <div class="section-header">
              <div class="section-title-wrap">
                <div class="section-icon"><GiftOutlined /></div>
                <div>
                  <div class="section-title">兑换码管理</div>
                  <div class="section-desc">发码不预扣积分池；用户兑换成功时才从代理积分池扣减。</div>
                </div>
              </div>
              <a-form layout="inline" class="redeem-create-form">
                <a-form-item label="生成数量">
                  <a-input-number v-model:value="batchForm.count" :min="1" :max="1000" class="warm-input-number redeem-half-number" />
                </a-form-item>
                <a-form-item label="每个积分">
                  <a-input-number v-model:value="batchForm.creditAmount" :min="1" class="warm-input-number redeem-half-number" />
                </a-form-item>
                <a-form-item label="本批需要">
                  <a-input :value="String(batchTotalCredits)" class="warm-input redeem-readonly-input" readonly />
                </a-form-item>
                <a-button type="primary" class="warm-primary-btn action-btn" :loading="generating" @click="handleCreateBatch">批量生成</a-button>
                <a-button class="filter-reset-btn action-btn" @click="copyKeys(latestBatch?.items?.map((item) => item.redeem_key) || [], '兑换码已复制')">复制最近一批</a-button>
              </a-form>
            </div>

            <div v-if="latestBatch" class="redeem-batch-summary-card">
              最近批次：{{ latestBatch.batch_no }}，共 {{ latestBatch.count }} 个，每个 {{ latestBatch.credit_amount }} 积分
            </div>

            <div class="redeem-filter-bar">
              <a-input v-model:value="redeemFilters.batchNo" allow-clear placeholder="按批次号筛选" class="warm-input redeem-filter-input" />
              <a-input v-model:value="redeemFilters.redeemKey" allow-clear placeholder="按兑换码筛选" class="warm-input redeem-filter-input" />
              <a-input-number v-model:value="redeemFilters.creditAmount" :min="1" placeholder="积分值" class="warm-input-number redeem-filter-number" />
              <a-select v-model:value="redeemFilters.status" allow-clear placeholder="状态" class="warm-select redeem-filter-select">
                <a-select-option value="enabled">启用</a-select-option>
                <a-select-option value="disabled">禁用</a-select-option>
              </a-select>
              <a-select v-model:value="redeemFilters.isUsed" allow-clear placeholder="使用状态" class="warm-select redeem-filter-select">
                <a-select-option :value="true">已使用</a-select-option>
                <a-select-option :value="false">未使用</a-select-option>
              </a-select>
              <a-input v-model:value="redeemFilters.usedBy" allow-clear placeholder="使用人/邮箱" class="warm-input redeem-filter-input" />
              <a-button type="primary" class="analytics-action-btn action-btn" @click="handleRedeemFilter">筛选</a-button>
              <a-button class="analytics-action-btn analytics-action-btn-secondary action-btn" @click="handleRedeemReset">重置</a-button>
            </div>

            <div class="warm-table-card">
              <div class="table-toolbar">
                <div class="table-toolbar-summary">当前页已选 <span>{{ selectedRedeemItems.length }}</span> / {{ redeemItems.length }}</div>
                <div class="table-toolbar-actions">
                  <a-button class="filter-reset-btn action-btn table-toolbar-btn" @click="copyKeys(selectedRedeemItems.map((item) => item.redeem_key), `已复制 ${selectedRedeemItems.length} 个兑换码`)">复制已选</a-button>
                  <a-button class="action-btn table-toolbar-btn" :loading="batchLockingAction === 'lock'" @click="confirmBatchLock(true)">批量锁定</a-button>
                  <a-button class="action-btn table-toolbar-btn" :loading="batchLockingAction === 'unlock'" @click="confirmBatchLock(false)">批量解锁</a-button>
                  <a-button danger class="action-btn table-toolbar-btn" :loading="deletingBatch" @click="confirmBatchDelete">批量删除</a-button>
                </div>
              </div>
              <a-table
                :columns="redeemColumns"
                :data-source="redeemItems"
                :loading="redeemLoading"
                :pagination="false"
                row-key="id"
                :row-selection="rowSelection"
                :scroll="{ x: 1180 }"
                class="admin-mobile-table"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.dataIndex === 'redeem_key'">
                    <div class="id-cell">
                      <span class="redeem-key-text">{{ record.redeem_key }}</span>
                      <a-button type="text" size="small" class="id-copy-btn" @click="copyKeys([record.redeem_key], '兑换码已复制')">
                        <template #icon><CopyOutlined /></template>
                      </a-button>
                    </div>
                  </template>
                  <template v-else-if="column.dataIndex === 'credit_amount'">
                    <span class="credit-amount">{{ record.credit_amount }}</span>
                  </template>
                  <template v-else-if="column.dataIndex === 'status'">
                    <a-tag class="warm-tag" :class="record.status === 'enabled' ? 'warm-tag-whitelist' : 'warm-tag-muted'">
                      {{ record.status === "enabled" ? "启用" : "禁用" }}
                    </a-tag>
                  </template>
                  <template v-else-if="column.dataIndex === 'is_locked'">
                    <a-tag class="warm-tag" :class="record.is_locked ? 'warm-tag-warning' : 'warm-tag-whitelist'">
                      {{ record.is_locked ? "已锁定" : "未锁定" }}
                    </a-tag>
                  </template>
                  <template v-else-if="column.dataIndex === 'is_used'">
                    <a-tag class="warm-tag" :class="record.is_used ? 'warm-tag-role-admin' : 'warm-tag-muted'">
                      {{ record.is_used ? "已使用" : "未使用" }}
                    </a-tag>
                  </template>
                  <template v-else-if="column.dataIndex === 'used_by_username'">
                    {{ record.used_by_username || "-" }}
                  </template>
                  <template v-else-if="column.dataIndex === 'used_at'">
                    {{ fmtTime(record.used_at) }}
                  </template>
                  <template v-else-if="column.key === 'action'">
                    <a-space>
                      <a-button
                        type="link"
                        size="small"
                        :danger="record.status === 'enabled'"
                        :disabled="record.is_used"
                        :loading="statusLoadingId === record.id"
                        @click="toggleStatus(record)"
                      >
                        {{ record.status === "enabled" ? "禁用" : "启用" }}
                      </a-button>
                      <a-button
                        type="link"
                        size="small"
                        :loading="lockLoadingId === record.id"
                        :disabled="record.is_used"
                        @click="toggleLock(record)"
                      >
                        <template #icon><component :is="record.is_locked ? UnlockOutlined : LockOutlined" /></template>
                        {{ record.is_locked ? "解锁" : "锁定" }}
                      </a-button>
                      <a-button
                        type="link"
                        size="small"
                        danger
                        :disabled="record.is_used || record.is_locked"
                        :loading="deletingId === record.id"
                        @click="confirmDelete(record)"
                      >
                        <template #icon><DeleteOutlined /></template>删除
                      </a-button>
                    </a-space>
                  </template>
                </template>
              </a-table>
            </div>

            <div class="warm-pagination">
              <div class="pagination-summary">共 {{ redeemPagination.total }} 个兑换码</div>
              <a-pagination
                v-if="redeemPagination.total > redeemPagination.pageSize"
                :current="redeemPagination.page"
                :total="redeemPagination.total"
                :page-size="redeemPagination.pageSize"
                show-size-changer
                @change="handleRedeemPageChange"
                @showSizeChange="handleRedeemPageChange"
              />
            </div>
          </div>
        </a-tab-pane>

        <a-tab-pane key="logs" tab="积分池流水">
          <div class="tab-pane-content logs-section-card">
            <div class="section-header">
              <div class="section-title-wrap">
                <div class="section-icon"><HistoryOutlined /></div>
                <div>
                  <div class="section-title">积分池流水</div>
                  <div class="section-desc">只展示代理积分池的管理员充扣和用户兑换扣减记录。</div>
                </div>
              </div>
              <div class="overview-mini-card logs-summary-card">
                <div class="overview-label">当前筛选已兑付</div>
                <div class="overview-value">{{ filteredRedeemedCredits }}</div>
              </div>
            </div>

            <div class="redeem-filter-bar">
              <a-input v-model:value="logsFilters.userKeyword" allow-clear placeholder="按用户/邮箱筛选" class="warm-input redeem-filter-input logs-filter-input-wide" />
              <a-select v-model:value="logsFilters.type" allow-clear placeholder="类型" class="warm-select redeem-filter-select logs-filter-select-wide">
                <a-select-option value="allocate">管理员充值/扣减</a-select-option>
                <a-select-option value="agent_pool_deduct">用户兑换扣减</a-select-option>
              </a-select>
              <a-input v-model:value="logsFilters.redeemKey" allow-clear placeholder="按兑换码筛选" class="warm-input redeem-filter-input logs-filter-input-wide" />
              <a-range-picker
                v-model:value="logsDateRange"
                value-format="YYYY-MM-DD"
                class="warm-input logs-date-range"
              />
              <a-button type="primary" class="analytics-action-btn action-btn" @click="handleLogsFilter">筛选</a-button>
              <a-button class="analytics-action-btn analytics-action-btn-secondary action-btn" @click="handleLogsReset">重置</a-button>
            </div>

            <div class="warm-table-card">
              <a-table :data-source="logItems" :loading="logsLoading" row-key="id" :pagination="false" :scroll="{ x: 980 }">
                <a-table-column title="时间" data-index="created_at" width="180">
                  <template #default="{ record }">{{ fmtTime(record.created_at) }}</template>
                </a-table-column>
                <a-table-column title="变动" data-index="amount" width="100">
                  <template #default="{ record }">
                    <span :class="record.amount >= 0 ? 'amount-plus' : 'amount-minus'">{{ record.amount > 0 ? `+${record.amount}` : record.amount }}</span>
                  </template>
                </a-table-column>
                <a-table-column title="类型" data-index="type" width="140">
                  <template #default="{ record }">{{ fmtAgentLogType(record) }}</template>
                </a-table-column>
                <a-table-column title="使用兑换码" data-index="redeem_key" width="190">
                  <template #default="{ record }">{{ record.redeem_key || "-" }}</template>
                </a-table-column>
                <a-table-column title="说明" data-index="description">
                  <template #default="{ record }">{{ fmtAgentLogDescription(record) }}</template>
                </a-table-column>
                <a-table-column title="操作人" data-index="operator_name" width="140" />
              </a-table>
            </div>

            <div class="warm-pagination">
              <div class="pagination-summary">共 {{ logsPagination.total }} 条流水</div>
              <a-pagination
                v-if="logsPagination.total > logsPagination.pageSize"
                :current="logsPagination.page"
                :total="logsPagination.total"
                :page-size="logsPagination.pageSize"
                show-size-changer
                @change="handleLogsPageChange"
                @showSizeChange="handleLogsPageChange"
              />
            </div>
          </div>
        </a-tab-pane>
      </a-tabs>
    </div>
  </div>
</template>

<style scoped lang="scss">
.top-summary-card {
  margin-bottom: 16px;
  padding: 18px 20px;
}

.section-card {
  margin-bottom: 16px;
  padding: 18px 20px;
  position: relative;
  overflow: visible;
}

.agent-section-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 18px;
}

.agent-section-tabs :deep(.ant-tabs-tab-btn) {
  font-size: 18px;
  font-weight: 700;
}

.agent-section-tabs :deep(.ant-tabs-content-holder) {
  overflow: visible;
}

.tab-pane-content {
  overflow: visible;
}

.tab-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.redeem-tab-toolbar {
  justify-content: flex-end;
}

.logs-tab-toolbar {
  justify-content: flex-end;
}

.redeem-section-card {
  z-index: 5;
}

.logs-section-card {
  z-index: 1;
}

.top-summary-layout,
.section-header,
.redeem-filter-bar,
.table-toolbar {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.top-summary-layout {
  justify-content: space-between;
}

.overview-grid {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  flex: 1 1 640px;
}

.overview-operator {
  color: var(--theme-title);
  font-size: 42px;
  font-weight: 800;
  line-height: 1;
  flex: 0 0 auto;
}

.overview-mini-card {
  min-width: 170px;
  padding: 14px 16px;
  border-radius: 18px;
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-soft));
  border: 1px solid var(--theme-panel-border);
  box-shadow: 0 10px 26px var(--theme-shadow-soft);
}

.overview-label {
  color: #8c7458;
  font-size: 13px;
}

.overview-value {
  margin-top: 6px;
  color: var(--theme-title);
  font-size: 22px;
  font-weight: 800;
}

.overview-value.warning { color: #d48806; }
.overview-value.success { color: #389e0d; }

.section-header {
  justify-content: space-between;
  margin-bottom: 16px;
}

.section-title-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-icon {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--theme-accent-text);
  background: var(--theme-panel-bg-strong);
}

.section-title {
  color: var(--theme-title);
  font-size: 18px;
  font-weight: 700;
}

.section-desc {
  color: #8c7458;
  font-size: 13px;
}

.redeem-create-form {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: flex-end;
}

.redeem-readonly-input {
  width: 110px;
}

.redeem-batch-summary-card {
  margin-bottom: 16px;
  color: #8c7458;
}

.redeem-filter-bar {
  margin-bottom: 16px;
  overflow-x: auto;
}

.redeem-filter-input {
  width: 148px;
  flex: 0 0 148px;
}

.logs-filter-input-wide {
  width: 180px;
  flex-basis: 180px;
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

.logs-filter-select-wide {
  width: 160px;
  flex-basis: 160px;
}

.logs-date-range {
  min-width: 240px;
}

.logs-summary-card {
  min-width: 190px;
}

.action-btn {
  min-width: 72px;
  height: 36px;
  padding-inline: 12px;
  flex: 0 0 auto;
  border-radius: 10px !important;
}

.table-toolbar-btn {
  border-radius: 10px !important;
}

.warm-table-card {
  overflow: visible;
}

.table-toolbar {
  justify-content: space-between;
  padding: 0 0 18px;
}

.table-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.table-toolbar-summary {
  color: #8c7458;
  font-size: 13px;
}

.table-toolbar-summary span,
.credit-amount {
  color: #b26c04;
  font-weight: 800;
}

.id-cell {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.redeem-key-text {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-weight: 800;
  letter-spacing: 0.04em;
}

.pagination-summary {
  color: #8c7458;
  font-size: 13px;
}

.warm-pagination {
  position: relative;
  z-index: 6;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.warm-pagination :deep(.ant-pagination) {
  margin-left: auto;
}

.amount-plus { color: #389e0d; font-weight: 800; }
.amount-minus { color: #cf1322; font-weight: 800; }
.warm-tag-warning { color: #ad6800; background: #fff7e6; border-color: #ffd591; }

@media (max-width: 960px) {
  .top-summary-layout,
  .section-header {
    flex-direction: column;
  }

  .overview-grid {
    width: 100%;
    justify-content: stretch;
  }

  .overview-operator {
    display: none;
  }

  .overview-mini-card {
    flex: 1 1 calc(50% - 6px);
    min-width: 0;
  }
}
</style>

<style lang="scss">
.agent-overview-page + * {
  position: relative;
}

.ant-select-dropdown {
  z-index: 1600;
}
</style>
