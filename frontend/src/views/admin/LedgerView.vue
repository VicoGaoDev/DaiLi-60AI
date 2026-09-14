<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { message, Modal } from "ant-design-vue";
import datePickerZhCN from "ant-design-vue/es/date-picker/locale/zh_CN";
import dayjs, { type Dayjs } from "dayjs";
import { PlusOutlined, WalletOutlined } from "@ant-design/icons-vue";
import {
  createAdminLedger,
  getAdminLedger,
  refreshAdminLedgerIncome,
  updateAdminLedger,
} from "@/api/admin";
import { uploadReferenceImage } from "@/api/upload";
import type { AdminLedger, AdminLedgerExpensePayload, AdminLedgerExpenseType } from "@/types";

type ExpenseForm = AdminLedgerExpensePayload & {
  clientKey: string;
  uploading: boolean;
};

const selectedMonth = ref<Dayjs>(dayjs().startOf("month"));
const ledger = ref<AdminLedger | null>(null);
const loading = ref(false);
const saving = ref(false);
const refreshingIncome = ref(false);
const uploadingLedgerScreenshot = ref(false);
const expenseModalOpen = ref(false);
const expenseDetailDrawerOpen = ref(false);
const editingExpenseIndex = ref<number | null>(null);
const detailExpense = ref<ExpenseForm | null>(null);
const form = reactive({
  title: "",
  description: "",
  screenshot_urls: [] as string[],
});
const expenses = ref<ExpenseForm[]>([]);
const expenseDraft = reactive<ExpenseForm>({
  clientKey: "",
  expense_type: "server",
  title: "",
  amount_yuan: 0,
  content: "",
  description: "",
  screenshot_urls: [],
  uploading: false,
});

const monthText = computed(() => selectedMonth.value.format("YYYY-MM"));
const pageStatusText = computed(() => ledger.value?.exists ? "已创建，可继续编辑" : "未创建，保存后生成本月账本");
const expenseModalTitle = computed(() => editingExpenseIndex.value === null ? "新增支出" : "编辑支出");
const income = computed(() => ledger.value?.income || {
  online_revenue_yuan: 0,
  redeem_revenue_yuan: 0,
  offline_revenue_yuan: 0,
  total_income_yuan: 0,
});
const expenseTotal = computed(() => expenses.value.reduce((sum, item) => sum + Number(item.amount_yuan || 0), 0));
const netIncome = computed(() => Number(income.value.total_income_yuan || 0) - expenseTotal.value);
const expenseColumns = [
  { title: "支出类型", dataIndex: "expense_type", width: 170 },
  { title: "标题", dataIndex: "title", width: 220, ellipsis: true },
  { title: "金额", dataIndex: "amount_yuan", width: 140 },
  { title: "描述说明", dataIndex: "description", width: 180, ellipsis: true },
  { title: "截图", dataIndex: "screenshot_urls", width: 90 },
  { title: "操作", key: "action", width: 210 },
];

function buildClientKey() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatMoney(value: number) {
  return `¥${Number(value || 0).toFixed(2)}`;
}

function expenseTypeLabel(type: AdminLedgerExpenseType) {
  if (type === "server") return "服务器成本支出";
  if (type === "third_party_api") return "第三方接口成本支出";
  return "其他支出";
}

function logActionColor(action: string) {
  if (action === "create") return "green";
  if (action === "delete") return "red";
  return "blue";
}

function applyLedger(nextLedger: AdminLedger) {
  ledger.value = nextLedger;
  form.title = nextLedger.title || `${nextLedger.month} 账本`;
  form.description = nextLedger.description || nextLedger.content || "";
  form.screenshot_urls = [...(nextLedger.screenshot_urls || [])];
  expenses.value = (nextLedger.expenses || []).map((item) => ({
    id: item.id,
    clientKey: `expense-${item.id}`,
    expense_type: item.expense_type,
    title: item.title,
    amount_yuan: item.amount_yuan,
    content: "",
    description: item.description || item.content || "",
    screenshot_urls: [...(item.screenshot_urls || [])],
    uploading: false,
  }));
}

async function loadLedger() {
  loading.value = true;
  try {
    const result = await getAdminLedger(monthText.value);
    applyLedger(result);
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "获取账本失败");
  } finally {
    loading.value = false;
  }
}

function handleMonthChange(value: Dayjs | null) {
  if (!value) return;
  selectedMonth.value = value.startOf("month");
  loadLedger();
}

function resetExpenseDraft() {
  Object.assign(expenseDraft, {
    clientKey: buildClientKey(),
    expense_type: "server",
    title: "",
    amount_yuan: 0,
    content: "",
    description: "",
    screenshot_urls: [],
    uploading: false,
  });
}

function openCreateExpenseDialog() {
  editingExpenseIndex.value = null;
  resetExpenseDraft();
  expenseModalOpen.value = true;
}

function openEditExpenseDialog(index: number) {
  const item = expenses.value[index];
  editingExpenseIndex.value = index;
  Object.assign(expenseDraft, {
    ...item,
    screenshot_urls: [...item.screenshot_urls],
  });
  expenseModalOpen.value = true;
}

function openExpenseDetailDrawer(index: number) {
  const item = expenses.value[index];
  detailExpense.value = {
    ...item,
    screenshot_urls: [...item.screenshot_urls],
  };
  expenseDetailDrawerOpen.value = true;
}

async function confirmExpenseDialog() {
  const editingIndex = editingExpenseIndex.value;
  const isCreatingExpense = editingIndex === null;
  const nextItem: ExpenseForm = {
    ...expenseDraft,
    title: expenseDraft.title.trim(),
    amount_yuan: Number(expenseDraft.amount_yuan || 0),
    content: "",
    description: expenseDraft.description || "",
    screenshot_urls: [...expenseDraft.screenshot_urls],
    uploading: false,
  };
  if (isCreatingExpense) {
    expenses.value.push(nextItem);
  } else {
    expenses.value.splice(editingIndex, 1, nextItem);
  }
  expenseModalOpen.value = false;
  if (isCreatingExpense) {
    await handleSave();
  }
}

function removeExpense(index: number) {
  expenses.value.splice(index, 1);
}

function removeScreenshot(urls: string[], index: number) {
  urls.splice(index, 1);
}

function confirmRemoveScreenshot(urls: string[], index: number) {
  Modal.confirm({
    title: "确认删除截图",
    content: "删除后该截图将不再作为账本依据展示，已上传到 COS 的文件不会被物理删除。",
    okText: "确认删除",
    cancelText: "取消",
    okButtonProps: { danger: true },
    onOk: () => removeScreenshot(urls, index),
  });
}

function setLedgerScreenshotUploading(value: boolean) {
  uploadingLedgerScreenshot.value = value;
}

function setExpenseDraftUploading(value: boolean) {
  expenseDraft.uploading = value;
}

async function uploadFiles(files: FileList | null, targetUrls: string[], setUploading: (value: boolean) => void) {
  if (!files?.length) return;
  setUploading(true);
  try {
    for (const file of Array.from(files)) {
      const result = await uploadReferenceImage(file, "admin_ledger");
      targetUrls.push(result.url);
    }
    message.success("截图上传成功");
  } catch (err: any) {
    message.error(err?.message || "截图上传失败");
  } finally {
    setUploading(false);
  }
}

async function uploadFileArray(files: File[], targetUrls: string[], setUploading: (value: boolean) => void) {
  if (!files.length) return;
  setUploading(true);
  try {
    for (const file of files) {
      const result = await uploadReferenceImage(file, "admin_ledger");
      targetUrls.push(result.url);
    }
    message.success("截图上传成功");
  } catch (err: any) {
    message.error(err?.message || "截图上传失败");
  } finally {
    setUploading(false);
  }
}

function handleLedgerScreenshotChange(event: Event) {
  const input = event.target as HTMLInputElement;
  uploadFiles(input.files, form.screenshot_urls, (value) => {
    uploadingLedgerScreenshot.value = value;
  }).finally(() => {
    input.value = "";
  });
}

function handleExpenseScreenshotChange(event: Event, item: ExpenseForm) {
  const input = event.target as HTMLInputElement;
  uploadFiles(input.files, item.screenshot_urls, (value) => {
    item.uploading = value;
  }).finally(() => {
    input.value = "";
  });
}

function handlePasteScreenshots(
  event: ClipboardEvent,
  targetUrls: string[],
  setUploading: (value: boolean) => void,
) {
  const imageFiles = Array.from(event.clipboardData?.files || []).filter((file) => file.type.startsWith("image/"));
  if (!imageFiles.length) return;
  event.preventDefault();
  uploadFileArray(imageFiles, targetUrls, setUploading);
}

function buildPayload() {
  return {
    title: form.title.trim() || `${monthText.value} 账本`,
    content: "",
    description: form.description,
    screenshot_urls: form.screenshot_urls,
    expenses: expenses.value.map(({ clientKey, uploading, ...item }) => ({
      ...item,
      content: "",
      title: item.title.trim(),
      amount_yuan: Number(item.amount_yuan || 0),
    })),
  };
}

async function handleSave() {
  saving.value = true;
  try {
    const payload = buildPayload();
    const wasExisting = ledger.value?.exists;
    const result = wasExisting
      ? await updateAdminLedger(monthText.value, payload)
      : await createAdminLedger({ ...payload, month: monthText.value });
    applyLedger(result);
    message.success(wasExisting ? "账本已保存" : "账本已创建");
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "保存账本失败");
  } finally {
    saving.value = false;
  }
}

function handleRefreshIncome() {
  if (!ledger.value?.exists) {
    loadLedger();
    return;
  }
  Modal.confirm({
    title: "确认刷新收入数据",
    content: "将重新检索该月在线购买、淘宝兑换码和线下订单营业额，并记录操作日志。",
    okText: "确认刷新",
    cancelText: "取消",
    onOk: refreshIncome,
  });
}

async function refreshIncome() {
  refreshingIncome.value = true;
  try {
    const result = await refreshAdminLedgerIncome(monthText.value);
    applyLedger(result);
    message.success("收入数据已刷新");
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "刷新收入失败");
    throw err;
  } finally {
    refreshingIncome.value = false;
  }
}

onMounted(loadLedger);
</script>

<template>
  <div class="warm-page ledger-page motion-page-enter">
    <div class="warm-page-header ledger-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <WalletOutlined />
        </div>
        <div>
          <div class="warm-page-title">账本</div>
          <div class="warm-page-desc">按月维护收入、支出、截图依据和操作日志。</div>
        </div>
      </div>
      <div class="ledger-toolbar">
        <a-date-picker
          :value="selectedMonth"
          picker="month"
          :locale="datePickerZhCN"
          format="YYYY-MM"
          :allow-clear="false"
          @change="handleMonthChange"
        />
        <a-button class="ledger-action-btn ledger-action-btn-secondary" :loading="loading" @click="loadLedger">重新加载</a-button>
        <a-button class="ledger-action-btn ledger-action-btn-secondary" :loading="refreshingIncome" @click="handleRefreshIncome">刷新收入</a-button>
        <a-button type="primary" class="warm-primary-btn ledger-action-btn" :loading="saving" @click="handleSave">
          {{ ledger?.exists ? "保存修改" : "新建账本" }}
        </a-button>
      </div>
    </div>

    <a-spin :spinning="loading">
      <div class="ledger-status">
        <span>{{ monthText }}</span>
        <a-tag :color="ledger?.exists ? 'green' : 'orange'">{{ pageStatusText }}</a-tag>
      </div>

      <div class="summary-grid summary-grid-top">
        <div class="summary-card">
          <span>收入合计</span>
          <strong>{{ formatMoney(income.total_income_yuan) }}</strong>
        </div>
        <div class="summary-card">
          <span>支出合计</span>
          <strong>{{ formatMoney(expenseTotal) }}</strong>
        </div>
        <div class="summary-card">
          <span>净收入</span>
          <strong :class="netIncome >= 0 ? 'amount-positive' : 'amount-negative'">{{ formatMoney(netIncome) }}</strong>
        </div>
      </div>

      <div class="ledger-grid">
        <a-card title="收入统计" class="ledger-card warm-card motion-card-lift">
          <div class="income-grid">
            <div class="metric-card">
              <div class="metric-label">在线购买营业额</div>
              <div class="metric-value">{{ formatMoney(income.online_revenue_yuan) }}</div>
            </div>
            <div class="metric-card">
              <div class="metric-label">淘宝兑换码营业额</div>
              <div class="metric-value">{{ formatMoney(income.redeem_revenue_yuan) }}</div>
            </div>
            <div class="metric-card">
              <div class="metric-label">线下订单营业额</div>
              <div class="metric-value">{{ formatMoney(income.offline_revenue_yuan) }}</div>
            </div>
            <div class="metric-card metric-card-strong">
              <div class="metric-label">收入合计</div>
              <div class="metric-value">{{ formatMoney(income.total_income_yuan) }}</div>
            </div>
          </div>
        </a-card>

        <a-card class="ledger-card expense-card warm-card motion-card-lift">
        <template #title>
          <div class="section-title-row">
            <span>支出明细</span>
            <a-button type="primary" class="warm-primary-btn ledger-add-expense-btn" @click="openCreateExpenseDialog">
              <template #icon><PlusOutlined /></template>
              新增支出
            </a-button>
          </div>
        </template>

        <a-empty v-if="!expenses.length" description="暂无支出，点击新增支出录入" />
        <a-table
          v-else
          :columns="expenseColumns"
          :data-source="expenses"
          :pagination="false"
          row-key="clientKey"
          class="ledger-expense-table admin-mobile-table"
          :scroll="{ x: 900 }"
        >
          <template #bodyCell="{ column, record, index }">
            <template v-if="column.dataIndex === 'expense_type'">
              <a-tag>{{ expenseTypeLabel(record.expense_type) }}</a-tag>
            </template>
            <template v-else-if="column.dataIndex === 'amount_yuan'">
              <span class="expense-amount">{{ formatMoney(record.amount_yuan) }}</span>
            </template>
            <template v-else-if="column.dataIndex === 'description'">
              {{ record.description || "-" }}
            </template>
            <template v-else-if="column.dataIndex === 'screenshot_urls'">
              {{ record.screenshot_urls?.length || 0 }} 张
            </template>
            <template v-else-if="column.key === 'action'">
              <a-space>
                <a-button size="small" class="ledger-table-action-btn" @click="openExpenseDetailDrawer(index)">查看</a-button>
                <a-button size="small" class="ledger-table-action-btn" @click="openEditExpenseDialog(index)">编辑</a-button>
                <a-button danger size="small" class="ledger-table-action-btn ledger-table-action-btn-danger" @click="removeExpense(index)">删除</a-button>
              </a-space>
            </template>
          </template>
        </a-table>
        </a-card>
      </div>

      <div class="ledger-bottom-grid">
        <a-card title="账本摘要" class="ledger-card warm-card motion-card-lift">
          <a-form layout="vertical">
            <a-form-item label="标题">
              <a-input v-model:value="form.title" placeholder="请输入账本标题" />
            </a-form-item>
            <a-form-item label="描述说明">
              <a-textarea v-model:value="form.description" placeholder="请输入账本描述说明" :rows="5" />
            </a-form-item>
            <a-form-item label="截图依据">
              <div
                class="screenshot-dropzone"
                tabindex="0"
                @paste="(event) => handlePasteScreenshots(event, form.screenshot_urls, setLedgerScreenshotUploading)"
              >
                <div class="screenshot-dropzone-title">粘贴截图或点击上传</div>
                <div class="screenshot-dropzone-desc">支持 JPG、PNG、WEBP、GIF，图片会上传到 COS 的 admin_ledger 文件夹。</div>
                <label class="upload-button">
                  <input type="file" accept="image/*" multiple @change="handleLedgerScreenshotChange" />
                  {{ uploadingLedgerScreenshot ? "上传中..." : "上传截图" }}
                </label>
                <div v-if="form.screenshot_urls.length" class="screenshot-list">
                  <div v-for="(url, index) in form.screenshot_urls" :key="url" class="screenshot-item">
                    <a-image :src="url" alt="账本截图" />
                    <button type="button" @click="confirmRemoveScreenshot(form.screenshot_urls, index)">删除</button>
                  </div>
                </div>
              </div>
            </a-form-item>
          </a-form>
        </a-card>

        <a-card title="操作日志" class="ledger-card warm-card motion-card-lift">
          <a-empty v-if="!ledger?.logs?.length" description="暂无操作日志" />
          <a-timeline v-else>
            <a-timeline-item v-for="log in ledger.logs" :key="log.id" :color="logActionColor(log.action)">
              <div class="log-summary">{{ log.summary }}</div>
              <div class="log-meta">
                {{ log.operator_username || "未知用户" }} · {{ log.created_at ? dayjs(log.created_at).format("YYYY-MM-DD HH:mm:ss") : "-" }}
              </div>
            </a-timeline-item>
          </a-timeline>
        </a-card>
      </div>
    </a-spin>

    <a-modal
      v-model:open="expenseModalOpen"
      :title="expenseModalTitle"
      class="ledger-expense-modal"
      :width="640"
      ok-text="保存"
      cancel-text="取消"
      @ok="confirmExpenseDialog"
    >
      <a-form layout="vertical">
        <a-form-item label="支出类型">
          <a-select v-model:value="expenseDraft.expense_type">
            <a-select-option value="server">{{ expenseTypeLabel("server") }}</a-select-option>
            <a-select-option value="third_party_api">{{ expenseTypeLabel("third_party_api") }}</a-select-option>
            <a-select-option value="other">{{ expenseTypeLabel("other") }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="标题">
          <a-input v-model:value="expenseDraft.title" placeholder="例如：8 月服务器费用" />
        </a-form-item>
        <a-form-item label="金额">
          <a-input-number v-model:value="expenseDraft.amount_yuan" :min="0" :precision="2" style="width: 100%" addon-before="¥" />
        </a-form-item>
        <a-form-item label="描述说明">
          <a-textarea v-model:value="expenseDraft.description" :rows="4" placeholder="请输入支出描述说明" />
        </a-form-item>
        <a-form-item label="截图依据">
          <div
            class="screenshot-dropzone"
            tabindex="0"
            @paste="(event) => handlePasteScreenshots(event, expenseDraft.screenshot_urls, setExpenseDraftUploading)"
          >
            <div class="screenshot-dropzone-title">粘贴截图或点击上传</div>
            <div class="screenshot-dropzone-desc">截图将作为这条支出的依据保存。</div>
            <label class="upload-button">
              <input type="file" accept="image/*" multiple @change="(event) => handleExpenseScreenshotChange(event, expenseDraft)" />
              {{ expenseDraft.uploading ? "上传中..." : "上传截图" }}
            </label>
            <div v-if="expenseDraft.screenshot_urls.length" class="screenshot-list">
              <div v-for="(url, index) in expenseDraft.screenshot_urls" :key="url" class="screenshot-item">
                <a-image :src="url" alt="支出截图" />
                <button type="button" @click="confirmRemoveScreenshot(expenseDraft.screenshot_urls, index)">删除</button>
              </div>
            </div>
          </div>
        </a-form-item>
      </a-form>
    </a-modal>

    <a-drawer
      v-model:open="expenseDetailDrawerOpen"
      title="支出详情"
      placement="right"
      width="420"
      root-class-name="ledger-expense-drawer"
    >
      <div v-if="detailExpense" class="expense-detail-drawer">
        <div class="detail-row">
          <span>支出类型</span>
          <strong>{{ expenseTypeLabel(detailExpense.expense_type) }}</strong>
        </div>
        <div class="detail-row">
          <span>标题</span>
          <strong>{{ detailExpense.title || "-" }}</strong>
        </div>
        <div class="detail-row">
          <span>金额</span>
          <strong>{{ formatMoney(detailExpense.amount_yuan) }}</strong>
        </div>
        <div class="detail-block">
          <div class="detail-block-title">描述说明</div>
          <div class="detail-block-content">{{ detailExpense.description || "-" }}</div>
        </div>
        <div class="detail-block">
          <div class="detail-block-title">截图依据</div>
          <a-empty v-if="!detailExpense.screenshot_urls.length" description="暂无截图" />
          <div v-else class="drawer-screenshot-list">
            <div
              v-for="url in detailExpense.screenshot_urls"
              :key="url"
              class="drawer-screenshot-item"
            >
              <a-image :src="url" alt="支出截图" />
            </div>
          </div>
        </div>
      </div>
    </a-drawer>
  </div>
</template>

<style scoped>
.ledger-page {
  padding: 24px;
}

.ledger-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.ledger-toolbar {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.ledger-action-btn {
  height: 36px;
  min-width: 96px;
  border-radius: 999px;
  font-weight: 600;
}

.ledger-action-btn-secondary {
  border-color: rgba(255, 171, 39, 0.45);
  color: #8a5a12 !important;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(255, 248, 235, 0.92)) !important;
  box-shadow: 0 8px 18px rgba(255, 171, 39, 0.12);
}

.ledger-action-btn-secondary:hover {
  border-color: var(--theme-accent) !important;
  color: #7a4a00 !important;
  background: var(--theme-control-hover-bg) !important;
}

.ledger-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  color: #6b7280;
}

.ledger-grid {
  display: grid;
  grid-template-columns: minmax(220px, 20%) minmax(0, 80%);
  gap: 16px;
  align-items: stretch;
}

.ledger-card {
  min-width: 0;
  margin-bottom: 16px;
  border-radius: 18px;
}

.ledger-expense-table {
  margin-top: 4px;
}

:deep(.ledger-expense-table .ant-table-content) {
  overflow-x: auto !important;
  -webkit-overflow-scrolling: touch;
}

:deep(.ledger-expense-table .ant-table-thead > tr > th),
:deep(.ledger-expense-table .ant-table-tbody > tr > td) {
  white-space: nowrap;
}

.ledger-bottom-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.ledger-table-action-btn {
  border-color: rgba(255, 171, 39, 0.38);
  border-radius: 999px;
  color: #8a5a12;
  background: var(--theme-page-base);
}

.ledger-table-action-btn:hover {
  border-color: var(--theme-accent) !important;
  color: #7a4a00 !important;
  background: #fff4df !important;
}

.ledger-table-action-btn-danger {
  border-color: rgba(220, 38, 38, 0.24);
  color: #dc2626;
  background: #fff7f7;
}

.ledger-table-action-btn-danger:hover {
  border-color: #ff4d4f !important;
  color: #cf1322 !important;
  background: #fff1f0 !important;
}

.expense-amount {
  color: #1f2937;
  font-size: 15px;
  font-weight: 800;
}

.income-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

.metric-card,
.summary-card {
  padding: 16px;
  border: 1px solid #f1e5d7;
  border-radius: 16px;
  background: var(--theme-page-base);
}

.metric-card-strong {
  background: #fff4df;
}

.metric-label,
.summary-card span {
  color: #6b7280;
  font-size: 13px;
}

.metric-value,
.summary-card strong {
  display: block;
  margin-top: 8px;
  font-size: 24px;
  font-weight: 700;
  color: #1f2937;
}

.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.ledger-add-expense-btn.ant-btn-primary,
.ledger-add-expense-btn.ant-btn-primary:hover,
.ledger-add-expense-btn.ant-btn-primary:focus,
.ledger-add-expense-btn.ant-btn-primary:active {
  border: none !important;
  background: var(--theme-accent) !important;
  color: var(--theme-accent-contrast) !important;
  box-shadow: none !important;
  transition: none !important;
  transform: none !important;
}

.upload-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 96px;
  height: 32px;
  padding: 0 14px;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  background: #fff;
  color: #374151;
  cursor: pointer;
  transition: all 0.2s ease;
}

.upload-button:hover {
  border-color: var(--theme-accent);
  color: #8a5a12;
}

.upload-button input {
  display: none;
}

.screenshot-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}

.screenshot-dropzone {
  padding: 14px;
  border: 1px dashed rgba(255, 171, 39, 0.45);
  border-radius: 16px;
  background: rgba(255, 250, 244, 0.72);
  outline: none;
  transition: all 0.2s ease;
}

.screenshot-dropzone:focus,
.screenshot-dropzone:hover {
  border-color: var(--theme-accent);
  background: #fff7ea;
}

.screenshot-dropzone-title {
  margin-bottom: 4px;
  color: #1f2937;
  font-weight: 600;
}

.screenshot-dropzone-desc {
  margin-bottom: 12px;
  color: #9ca3af;
  font-size: 12px;
}

.screenshot-item {
  position: relative;
  width: 96px;
  height: 96px;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid #f1e5d7;
  background: #fff;
}

.screenshot-item :deep(.ant-image),
.screenshot-item :deep(.ant-image-img) {
  width: 100%;
  height: 100%;
}

.screenshot-item :deep(.ant-image-img) {
  object-fit: cover;
}

.screenshot-item button {
  position: absolute;
  right: 4px;
  bottom: 4px;
  border: 0;
  border-radius: 999px;
  padding: 2px 8px;
  background: rgba(0, 0, 0, 0.65);
  color: #fff;
  font-size: 12px;
  cursor: pointer;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.summary-grid-top {
  margin-bottom: 18px;
}

.amount-positive {
  color: #16a34a !important;
}

.amount-negative {
  color: #dc2626 !important;
}

.log-summary {
  color: #1f2937;
  font-weight: 600;
}

.log-meta {
  margin-top: 4px;
  color: #9ca3af;
  font-size: 12px;
}

.expense-detail-drawer {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f1e5d7;
}

.detail-row span,
.detail-block-title {
  color: #9ca3af;
  font-size: 13px;
}

.detail-row strong {
  color: #1f2937;
  text-align: right;
}

.detail-block {
  padding: 14px;
  border: 1px solid #f1e5d7;
  border-radius: 16px;
  background: var(--theme-page-base);
}

.detail-block-title {
  margin-bottom: 8px;
}

.detail-block-content {
  white-space: pre-wrap;
  color: #374151;
  line-height: 1.7;
}

.drawer-screenshot-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.drawer-screenshot-item {
  display: block;
  overflow: hidden;
  aspect-ratio: 1 / 1;
  border: 1px solid #f1e5d7;
  border-radius: 14px;
  background: #fff;
}

.drawer-screenshot-item :deep(.ant-image),
.drawer-screenshot-item :deep(.ant-image-img) {
  width: 100%;
  height: 100%;
}

.drawer-screenshot-item :deep(.ant-image-img) {
  object-fit: cover;
  transition: transform 0.2s ease;
}

.drawer-screenshot-item:hover :deep(.ant-image-img) {
  transform: scale(1.04);
}

:deep(.ledger-expense-modal .ant-modal-body) {
  max-height: min(620px, calc(100vh - 240px));
  overflow-y: auto;
  padding-right: 18px;
}

:deep(.ledger-expense-modal .ant-form-item) {
  margin-bottom: 14px;
}

:deep(.ledger-expense-modal .screenshot-dropzone) {
  padding: 12px;
}

:deep(.ledger-expense-modal .screenshot-item) {
  width: 76px;
  height: 76px;
}

@media (max-width: 960px) {
  .ledger-header,
  .ledger-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .ledger-grid,
  .ledger-bottom-grid,
  .summary-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .section-title-row {
    flex-wrap: wrap;
  }
}

@media (max-width: 768px) {
  .ledger-page {
    padding: 12px;
  }

  .ledger-toolbar :deep(.ant-picker),
  .ledger-action-btn {
    width: 100%;
  }

  .income-grid,
  .expense-form-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .metric-card,
  .summary-card {
    padding: 12px;
  }

  .metric-value,
  .summary-card strong {
    font-size: 20px;
    word-break: break-all;
  }

  .section-title-row {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }

  .ledger-add-expense-btn {
    width: 100%;
  }

  :deep(.ledger-card .ant-card-head) {
    padding-inline: 14px;
  }

  :deep(.ledger-card .ant-card-body) {
    padding: 14px;
  }

  :deep(.expense-card .ant-card-body) {
    overflow-x: hidden;
  }

  :deep(.ledger-expense-modal) {
    max-width: calc(100vw - 24px) !important;
    margin: 12px auto;
  }

  :deep(.ledger-expense-modal .ant-modal-body) {
    max-height: min(70vh, calc(100vh - 180px));
    padding-right: 12px;
  }
}

:global(html[data-theme="midnight"]) {
  .ledger-action-btn-secondary {
    border-color: var(--theme-pill-border) !important;
    color: var(--theme-accent-text) !important;
    background: var(--theme-panel-bg-strong) !important;
    box-shadow: none !important;
  }

  .ledger-action-btn-secondary:hover {
    border-color: var(--theme-accent) !important;
    color: var(--theme-accent-text-hover) !important;
    background: var(--theme-control-hover-bg) !important;
  }

  .ledger-status {
    color: var(--text-secondary);
  }

  .ledger-table-action-btn {
    border-color: var(--theme-pill-border);
    color: var(--theme-accent-text);
    background: var(--theme-panel-bg);
  }

  .ledger-table-action-btn:hover {
    border-color: var(--theme-accent) !important;
    color: var(--theme-accent-text-hover) !important;
    background: var(--theme-control-hover-bg) !important;
  }

  .ledger-table-action-btn-danger {
    border-color: rgba(220, 38, 38, 0.36);
    color: #ff7875;
    background: color-mix(in srgb, #cf3f36 14%, var(--theme-panel-bg));
  }

  .ledger-table-action-btn-danger:hover {
    border-color: #ff4d4f !important;
    color: #ffa39e !important;
    background: color-mix(in srgb, #cf3f36 22%, var(--theme-panel-bg)) !important;
  }

  .expense-amount,
  .metric-value,
  .summary-card strong,
  .log-summary,
  .detail-row strong,
  .detail-block-content,
  .screenshot-dropzone-title {
    color: var(--theme-title) !important;
  }

  .metric-card,
  .summary-card,
  .detail-block,
  .screenshot-item,
  .drawer-screenshot-item {
    border-color: var(--theme-panel-border);
    background: var(--theme-panel-bg);
  }

  .metric-card-strong {
    background: var(--theme-panel-bg-strong);
  }

  .metric-label,
  .summary-card span,
  .log-meta,
  .screenshot-dropzone-desc,
  .detail-row span,
  .detail-block-title {
    color: var(--text-secondary) !important;
  }

  .upload-button {
    border-color: var(--theme-control-border);
    background: var(--theme-control-bg);
    color: var(--text);
  }

  .upload-button:hover {
    border-color: var(--theme-accent);
    color: var(--theme-accent-text);
  }

  .screenshot-dropzone {
    border-color: var(--theme-pill-border);
    background: var(--theme-panel-bg-muted);
  }

  .screenshot-dropzone:focus,
  .screenshot-dropzone:hover {
    border-color: var(--theme-accent);
    background: var(--theme-control-hover-bg);
  }

  .detail-row {
    border-bottom-color: var(--theme-panel-border);
  }

  :deep(.ledger-card .ant-card-head),
  :deep(.ledger-card .ant-card-head-title),
  :deep(.section-title-row) {
    color: var(--theme-title);
    background: transparent;
    border-color: var(--theme-panel-border);
  }

  :deep(.ledger-card .ant-card-body),
  :deep(.ant-form-item-label > label) {
    color: var(--text);
  }

  :deep(.ant-empty-description) {
    color: var(--text-secondary);
  }
}

:global(html[data-theme="midnight"] .ledger-expense-drawer .ant-drawer-header),
:global(html[data-theme="midnight"] .ledger-expense-drawer .ant-drawer-body) {
  background: var(--theme-panel-bg);
  color: var(--theme-title);
  border-color: var(--theme-panel-border);
}

:global(html[data-theme="midnight"] .ledger-expense-drawer .ant-drawer-title) {
  color: var(--theme-title);
}
</style>
