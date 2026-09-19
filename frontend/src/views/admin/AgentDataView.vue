<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { message } from "ant-design-vue";
import datePickerZhCN from "ant-design-vue/es/date-picker/locale/zh_CN";
import dayjs from "dayjs";
import "dayjs/locale/zh-cn";
import type { Dayjs } from "dayjs";
import { PlusOutlined, ReloadOutlined, SearchOutlined, TeamOutlined, WalletOutlined } from "@ant-design/icons-vue";
import { allocateCredits, listOfflineOrders, listUsers } from "@/api/admin";
import { isSessionExpiredError } from "@/lib/authError";
import type { AdminOfflineOrder, AdminUser } from "@/types";

dayjs.locale("zh-cn");

const agents = ref<AdminUser[]>([]);
const agentOptions = ref<AdminUser[]>([]);
const agentTotal = ref(0);
const agentsLoading = ref(false);
const agentKeyword = ref("");
const agentPage = ref(1);
const agentPageSize = 20;

const allocationLogs = ref<AdminOfflineOrder[]>([]);
const allocationTotal = ref(0);
const allocationsLoading = ref(false);
const allocationPage = ref(1);
const allocationPageSize = 20;
const allocationKeyword = ref("");
const allocationDateRange = ref<[Dayjs, Dayjs]>([
  dayjs().startOf("month"),
  dayjs().endOf("day"),
]);

const modalOpen = ref(false);
const submitLoading = ref(false);
const form = reactive({
  user_id: undefined as string | undefined,
  amount: undefined as number | undefined,
  amount_yuan: undefined as number | undefined,
  description: "",
});

const agentColumns = [
  { title: "代理人", dataIndex: "username", width: 180 },
  { title: "联系方式", dataIndex: "contact", width: 220 },
  { title: "代理积分池", dataIndex: "pool_credits", width: 120 },
  { title: "个人积分", dataIndex: "personal_credits", width: 110 },
  { title: "状态", dataIndex: "status", width: 90 },
  { title: "创建时间", dataIndex: "created_at", width: 170 },
  { title: "操作", key: "action", width: 130, fixed: "right" as const },
];

const allocationColumns = [
  { title: "流水单号", dataIndex: "business_id", width: 160 },
  { title: "代理人", dataIndex: "username", width: 150 },
  { title: "分配积分", dataIndex: "credit_amount", width: 110 },
  { title: "分配金额（元）", dataIndex: "amount_yuan", width: 130 },
  { title: "备注", dataIndex: "remark", width: 260 },
  { title: "操作人", dataIndex: "created_by_username", width: 120 },
  { title: "时间", dataIndex: "created_at", width: 170 },
];

const currentPagePoolCredits = computed(() => agents.value.reduce((sum, item) => sum + Number(item.pool_credits || 0), 0));
const currentPageAllocationAmount = computed(() => allocationLogs.value.reduce((sum, item) => sum + Number(item.amount_yuan || 0), 0));

function fmtDateTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function fmtMoney(value?: number) {
  return Number(value || 0).toFixed(2);
}

function fmtStatus(status?: string) {
  return status === "active" ? "启用" : "禁用";
}

function formatQueryDate(value?: Dayjs, endOfDay = false) {
  if (!value) return undefined;
  return (endOfDay ? value.endOf("day") : value.startOf("day")).format("YYYY-MM-DDTHH:mm:ss");
}

function resetForm() {
  form.user_id = undefined;
  form.amount = undefined;
  form.amount_yuan = undefined;
  form.description = "";
}

function openCreateModal(agent?: AdminUser) {
  resetForm();
  if (agent) form.user_id = agent.id;
  if (!agentOptions.value.length) {
    void loadAgentOptions();
  }
  modalOpen.value = true;
}

async function loadAgentOptions() {
  try {
    const result = await listUsers(1, 100, {
      role: "agent",
      sort: "created_at_desc",
    });
    agentOptions.value = result.items;
  } catch (err: unknown) {
    if (isSessionExpiredError(err)) return;
    message.error("获取代理人选项失败");
  }
}

async function loadAgents(page = agentPage.value) {
  agentsLoading.value = true;
  try {
    const result = await listUsers(page, agentPageSize, {
      role: "agent",
      keyword: agentKeyword.value.trim() || undefined,
      sort: "created_at_desc",
    });
    agents.value = result.items;
    agentTotal.value = result.total;
    agentPage.value = result.page || page;
  } catch (err: unknown) {
    if (isSessionExpiredError(err)) return;
    message.error("获取代理人列表失败");
  } finally {
    agentsLoading.value = false;
  }
}

async function loadAllocationLogs(page = allocationPage.value) {
  allocationsLoading.value = true;
  try {
    const result = await listOfflineOrders({
      page,
      page_size: allocationPageSize,
      user: allocationKeyword.value.trim() || undefined,
      source: "agent_pool_allocate",
      start_date: formatQueryDate(allocationDateRange.value?.[0]),
      end_date: formatQueryDate(allocationDateRange.value?.[1], true),
    });
    allocationLogs.value = result.items;
    allocationTotal.value = result.total;
    allocationPage.value = page;
  } catch (err: unknown) {
    if (isSessionExpiredError(err)) return;
    message.error("获取代理池分配流水失败");
  } finally {
    allocationsLoading.value = false;
  }
}

async function handleSubmit() {
  if (!form.user_id) {
    message.warning("请选择代理人");
    return;
  }
  if (!form.amount || form.amount <= 0) {
    message.warning("请输入有效积分");
    return;
  }
  if (!form.amount_yuan || form.amount_yuan <= 0) {
    message.warning("请输入有效金额");
    return;
  }
  if (!form.description.trim()) {
    message.warning("请填写备注说明");
    return;
  }
  submitLoading.value = true;
  try {
    await allocateCredits(form.user_id, form.amount, form.description.trim(), Number(form.amount_yuan));
    message.success("代理池积分分配成功");
    modalOpen.value = false;
    await Promise.all([loadAgents(), loadAllocationLogs(1)]);
  } catch (err: unknown) {
    if (isSessionExpiredError(err)) return;
    message.error((err as any)?.response?.data?.detail || "代理池积分分配失败");
  } finally {
    submitLoading.value = false;
  }
}

function handleAgentSearch() {
  agentPage.value = 1;
  void loadAgents(1);
}

function handleAllocationSearch() {
  allocationPage.value = 1;
  void loadAllocationLogs(1);
}

function handleAgentReset() {
  agentKeyword.value = "";
  agentPage.value = 1;
  void loadAgents(1);
}

function handleAgentPageChange(page: number) {
  void loadAgents(page);
}

function handleAllocationReset() {
  allocationKeyword.value = "";
  allocationDateRange.value = [dayjs().startOf("month"), dayjs().endOf("day")];
  allocationPage.value = 1;
  void loadAllocationLogs(1);
}

function handleAllocationPageChange(page: number) {
  void loadAllocationLogs(page);
}

function agentRowKey(record: AdminUser) {
  return record.id;
}

function allocationRowKey(record: AdminOfflineOrder) {
  return record.business_id || String(record.id);
}

onMounted(() => {
  void Promise.all([loadAgents(), loadAgentOptions(), loadAllocationLogs()]);
});
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <TeamOutlined />
        </div>
        <div>
          <div class="warm-page-title">代理人数据</div>
          <div class="warm-page-desc">查看代理人账户与代理积分池分配流水，并可在此直接给代理人分配代理池积分。</div>
        </div>
      </div>
      <a-button type="primary" class="warm-primary-btn" @click="openCreateModal()">
        <template #icon><PlusOutlined /></template>
        分配代理池积分
      </a-button>
    </div>

    <div class="agent-overview-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 100ms">
      <div class="overview-head">
        <div>
          <div class="section-title">代理人概览</div>
          <div class="section-desc">快速查看当前代理人规模、当前页代理池余额和分配情况。</div>
        </div>
      </div>
      <div class="agent-summary-grid">
        <div class="summary-card">
          <div class="summary-label">代理人数</div>
          <div class="summary-value">{{ agentTotal }}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">当前页代理池合计</div>
          <div class="summary-value">{{ currentPagePoolCredits }}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">当前页分配流水</div>
          <div class="summary-value">{{ allocationLogs.length }}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">当前页分配金额</div>
          <div class="summary-value">¥{{ fmtMoney(currentPageAllocationAmount) }}</div>
        </div>
      </div>
    </div>

    <div class="warm-card agent-section-card motion-card-lift motion-fade-up" style="--motion-delay: 140ms">
      <div class="section-head">
        <div class="section-head-left">
          <div class="section-icon">
            <TeamOutlined />
          </div>
          <div>
          <div class="section-title">代理人列表</div>
          <div class="section-desc">只展示代理人账号，可从这里直接发放代理积分池。</div>
          </div>
        </div>
      </div>
      <div class="section-filter-bar toolbar-row">
        <a-input
          v-model:value="agentKeyword"
          allow-clear
          class="toolbar-input"
          placeholder="搜索用户名 / 邮箱 / 用户ID"
          @pressEnter="handleAgentSearch"
        >
          <template #prefix><SearchOutlined /></template>
        </a-input>
        <a-button type="primary" class="warm-primary-btn" @click="handleAgentSearch">查询</a-button>
        <a-button class="warm-secondary-btn" @click="handleAgentReset">重置</a-button>
      </div>
      <a-table
        :columns="agentColumns"
        :data-source="agents"
        :loading="agentsLoading"
        :pagination="false"
        :row-key="agentRowKey"
        :scroll="{ x: 980 }"
        size="middle"
        class="admin-mobile-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'username'">
            <div class="user-name-cell">
              <span>{{ record.username }}</span>
              <a-tag class="warm-tag warm-tag-agent">代理人</a-tag>
            </div>
          </template>
          <template v-else-if="column.dataIndex === 'contact'">
            {{ record.email || record.phone || record.id }}
          </template>
          <template v-else-if="column.dataIndex === 'pool_credits'">
            <span class="table-number">{{ record.pool_credits || 0 }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'personal_credits'">
            <span class="table-number">{{ record.personal_credits || 0 }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <a-tag :class="record.status === 'active' ? 'status-tag-active' : 'status-tag-disabled'">
              {{ fmtStatus(record.status) }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'created_at'">
            {{ fmtDateTime(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-button type="primary" class="warm-primary-btn action-btn" @click="openCreateModal(record)">
              <template #icon><WalletOutlined /></template>
              分配
            </a-button>
          </template>
        </template>
      </a-table>
      <div class="warm-pagination">
        <div class="pagination-summary">
          {{
            agentTotal
              ? `当前第 ${(agentPage - 1) * agentPageSize + 1}-${Math.min(agentPage * agentPageSize, agentTotal)} 条 / 共 ${agentTotal} 条`
              : "当前第 0-0 条 / 共 0 条"
          }}
        </div>
        <a-pagination
          v-if="agentTotal > agentPageSize"
          :current="agentPage"
          :page-size="agentPageSize"
          :total="agentTotal"
          :show-size-changer="false"
          @change="handleAgentPageChange"
        />
      </div>
    </div>

    <div class="warm-card agent-section-card motion-card-lift motion-fade-up" style="--motion-delay: 180ms">
      <div class="section-head">
        <div class="section-head-left">
          <div class="section-icon">
            <WalletOutlined />
          </div>
          <div>
          <div class="section-title">代理池分配流水</div>
          <div class="section-desc">这里展示所有计入营业额的代理池分配记录。</div>
          </div>
        </div>
      </div>
      <div class="section-filter-bar toolbar-row toolbar-row-wrap">
        <a-input
          v-model:value="allocationKeyword"
          allow-clear
          class="toolbar-input"
          placeholder="搜索代理人 / 邮箱 / 流水单号"
          @pressEnter="handleAllocationSearch"
        >
          <template #prefix><SearchOutlined /></template>
        </a-input>
        <a-range-picker
          v-model:value="allocationDateRange"
          class="toolbar-date"
          :locale="datePickerZhCN"
          :allow-clear="false"
        />
        <a-button type="primary" class="warm-primary-btn" @click="handleAllocationSearch">查询</a-button>
        <a-button class="warm-secondary-btn" @click="handleAllocationReset">重置</a-button>
        <a-button class="warm-secondary-btn" @click="loadAllocationLogs()">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
      </div>
      <a-table
        :columns="allocationColumns"
        :data-source="allocationLogs"
        :loading="allocationsLoading"
        :pagination="false"
        :row-key="allocationRowKey"
        :scroll="{ x: 1180 }"
        size="middle"
        class="admin-mobile-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'amount_yuan'">
            <span class="amount-text">¥{{ fmtMoney(record.amount_yuan) }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'remark'">
            {{ record.remark || "-" }}
          </template>
          <template v-else-if="column.dataIndex === 'created_by_username'">
            {{ record.created_by_username || record.created_by || "-" }}
          </template>
          <template v-else-if="column.dataIndex === 'created_at'">
            {{ fmtDateTime(record.created_at) }}
          </template>
        </template>
      </a-table>
      <div class="warm-pagination">
        <div class="pagination-summary">
          {{
            allocationTotal
              ? `当前第 ${(allocationPage - 1) * allocationPageSize + 1}-${Math.min(allocationPage * allocationPageSize, allocationTotal)} 条 / 共 ${allocationTotal} 条`
              : "当前第 0-0 条 / 共 0 条"
          }}
        </div>
        <a-pagination
          v-if="allocationTotal > allocationPageSize"
          :current="allocationPage"
          :page-size="allocationPageSize"
          :total="allocationTotal"
          :show-size-changer="false"
          @change="handleAllocationPageChange"
        />
      </div>
    </div>

    <a-modal
      v-model:open="modalOpen"
      title="分配代理池积分"
      ok-text="确认分配"
      cancel-text="取消"
      centered
      :width="460"
      :confirm-loading="submitLoading"
      :ok-button-props="{ class: 'warm-primary-btn' }"
      :cancel-button-props="{ class: 'warm-secondary-btn' }"
      @ok="handleSubmit"
    >
      <a-form layout="vertical" style="margin-top: 16px">
        <a-form-item label="代理人">
          <a-select
            v-model:value="form.user_id"
            show-search
            placeholder="请选择代理人"
            option-filter-prop="label"
            :options="agentOptions.map((item) => ({
              value: item.id,
              label: item.email ? `${item.username} (${item.email})` : `${item.username} (${item.id})`,
            }))"
          />
        </a-form-item>
        <a-form-item label="分配积分">
          <a-input-number
            v-model:value="form.amount"
            style="width: 100%"
            :min="1"
            :precision="0"
            placeholder="请输入本次分配积分"
          />
        </a-form-item>
        <a-form-item label="金额（人民币元）">
          <a-input-number
            v-model:value="form.amount_yuan"
            style="width: 100%"
            :min="0.01"
            :precision="2"
            placeholder="请输入本次分配金额"
          />
        </a-form-item>
        <a-form-item label="备注说明" style="margin-bottom: 0">
          <a-textarea
            v-model:value="form.description"
            :rows="3"
            :maxlength="300"
            placeholder="请填写本次代理池分配说明"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped lang="scss">
.agent-overview-card {
  margin-bottom: 16px;
  padding: 18px;
}

.overview-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.agent-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.summary-card {
  padding: 16px 18px;
  border-radius: 18px;
  border: 1px solid rgba(255, 222, 173, 0.65);
  background: linear-gradient(180deg, rgba(255, 250, 241, 0.98) 0%, rgba(255, 244, 222, 0.86) 100%);
  box-shadow: 0 10px 24px rgba(234, 188, 113, 0.12);
}

.summary-label {
  color: #8c7458;
  font-size: 13px;
  font-weight: 600;
}

.summary-value {
  margin-top: 10px;
  color: #5d4526;
  font-size: 24px;
  font-weight: 800;
  line-height: 1;
}

.agent-section-card {
  padding: 18px 18px 12px;
  margin-bottom: 16px;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.section-head-left {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.section-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  background: rgba(255, 196, 91, 0.16);
  color: #a05f00;
  font-size: 18px;
  flex-shrink: 0;
}

.section-title {
  color: #5d4526;
  font-size: 16px;
  font-weight: 700;
}

.section-desc {
  margin-top: 4px;
  color: #8c7458;
  font-size: 13px;
}

.toolbar-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.section-filter-bar {
  padding: 14px;
  border-radius: 16px;
  background: rgba(255, 248, 236, 0.9);
  border: 1px solid rgba(255, 230, 190, 0.78);
}

.toolbar-row-wrap {
  flex-wrap: wrap;
}

.toolbar-input {
  width: 360px;
}

.toolbar-date {
  min-width: 300px;
}

.user-name-cell {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.warm-tag-agent {
  border-color: rgba(52, 120, 246, 0.18);
  background: rgba(52, 120, 246, 0.1);
  color: #1d4ed8;
}

.status-tag-active {
  border-color: rgba(34, 197, 94, 0.18);
  background: rgba(34, 197, 94, 0.1);
  color: #15803d;
}

.status-tag-disabled {
  border-color: rgba(239, 68, 68, 0.18);
  background: rgba(239, 68, 68, 0.1);
  color: #b91c1c;
}

.table-number {
  color: #8a5300;
  font-weight: 700;
}

.amount-text {
  color: #a05f00;
  font-weight: 700;
}

.action-btn {
  min-width: 88px;
}

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

.warm-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
  flex-wrap: wrap;
}

.pagination-summary {
  color: #8c7458;
  font-size: 12px;
}

:deep(.warm-pagination .ant-pagination) {
  margin-left: auto;
}

@media (max-width: 1200px) {
  .agent-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .agent-overview-card,
  .agent-section-card {
    padding-inline: 14px;
  }

  .agent-summary-grid {
    grid-template-columns: 1fr;
  }

  .toolbar-row {
    align-items: stretch;
    flex-direction: column;
  }

  .toolbar-input,
  .toolbar-date {
    width: 100%;
    min-width: 0;
  }

  .warm-pagination {
    align-items: stretch;
    flex-direction: column;
  }

  :deep(.warm-pagination .ant-pagination) {
    margin-left: 0;
  }
}
</style>
