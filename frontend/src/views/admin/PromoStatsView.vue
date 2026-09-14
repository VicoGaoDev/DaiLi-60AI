<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import {
  GiftOutlined,
  ReloadOutlined,
  ShareAltOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  UndoOutlined,
} from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import datePickerZhCN from "ant-design-vue/es/date-picker/locale/zh_CN";
import dayjs, { type Dayjs } from "dayjs";
import "dayjs/locale/zh-cn";

import { getAdminPromoStatsDashboard, getAdminPromoStatsUserDetail } from "@/api/admin";
import type {
  AdminPromoStatsDashboard,
  AdminPromoStatsUserItem,
  AdminUserPromoDashboard,
} from "@/types";

dayjs.locale("zh-cn");

const loading = ref(false);
const detailLoading = ref(false);
const detailOpen = ref(false);
const dashboard = ref<AdminPromoStatsDashboard>({
  summary: {
    total_referrals: 0,
    active_promoters: 0,
    total_promo_codes: 0,
    used_promo_codes: 0,
    whitelisted_users: 0,
    reward_credits: 0,
    purchase_count: 0,
    purchase_credits: 0,
    redeem_count: 0,
    redeem_credits: 0,
    reward_grant_count: 0,
    total_reward_amount_yuan: 0,
    start_at: null,
  },
  users: [],
  recent_referrals: [],
});
const userDetail = ref<AdminUserPromoDashboard | null>(null);
const detailUserId = ref("");
const currentBeijingMonth = dayjs().startOf("month");
const selectedStatsMonth = ref<Dayjs | undefined>(currentBeijingMonth);
const detailFilters = reactive({
  month: undefined as Dayjs | undefined,
  dateRange: undefined as [Dayjs, Dayjs] | undefined,
});

const hasDetailPeriodFilter = computed(() => Boolean(detailFilters.month || detailFilters.dateRange?.[0] || detailFilters.dateRange?.[1]));
const rebateRanking = computed(() => (
  [...dashboard.value.users]
    .filter((item) => Number(item.month_reward_amount_yuan || 0) > 0)
    .sort((a, b) => Number(b.month_reward_amount_yuan || 0) - Number(a.month_reward_amount_yuan || 0))
    .slice(0, 10)
));
const maxRebateAmount = computed(() => Math.max(...rebateRanking.value.map((item) => Number(item.month_reward_amount_yuan || 0)), 0));

function formatQueryDate(value?: Dayjs | null) {
  return value ? value.format("YYYY-MM-DDTHH:mm:ss") : undefined;
}

function formatQueryMonth(value?: Dayjs | null) {
  return value ? value.format("YYYY-MM") : undefined;
}

function disabledFutureMonth(current: Dayjs) {
  return current.isAfter(currentBeijingMonth, "month");
}

function disabledFutureDate(current: Dayjs) {
  return current.isAfter(dayjs(), "day");
}

const userColumns = [
  { title: "推广人", key: "user", width: "22%" },
  { title: "推广码数", dataIndex: "promo_code_count", width: 100 },
  { title: "已使用码", dataIndex: "used_code_count", width: 100 },
  { title: "推广注册", dataIndex: "total_referrals", width: 100 },
  { title: "注册奖励积分", dataIndex: "reward_credits", width: 120 },
  { title: "推广用户购买积分", dataIndex: "purchase_credits", width: 140 },
  { title: "推广用户兑换积分", dataIndex: "redeem_credits", width: 140 },
  { title: "月返利次数", dataIndex: "month_reward_grant_count", width: 110 },
  { title: "月返利金额", dataIndex: "month_reward_amount_yuan", width: 120 },
  { title: "返利次数", dataIndex: "reward_grant_count", width: 100 },
  { title: "累计返利", dataIndex: "total_reward_amount_yuan", width: 120 },
  { title: "最近推广", dataIndex: "last_referral_at", width: 170 },
  { title: "操作", key: "action", width: 96, fixed: "right" as const },
];

const referralColumns = [
  { title: "推广人", dataIndex: "promoter_username", width: 130 },
  { title: "推广用户", dataIndex: "invitee_username", width: 140 },
  { title: "推广码", dataIndex: "promo_code", width: 120 },
  { title: "平台", dataIndex: "platform_name", width: 140 },
  { title: "注册奖励积分", dataIndex: "reward_credits", width: 120 },
  { title: "注册时间", dataIndex: "registered_at", width: 170 },
];

const detailPromoColumns = [
  { title: "推广码", dataIndex: "code", width: 140 },
  { title: "平台", dataIndex: "platform_name", width: 160 },
  { title: "使用人数", dataIndex: "referral_count", width: 100 },
  { title: "状态", dataIndex: "status", width: 100 },
  { title: "创建时间", dataIndex: "created_at", width: 170 },
];

const detailReferralColumns = [
  { title: "用户", key: "user", width: "24%" },
  { title: "推广码", dataIndex: "promo_code", width: 120 },
  { title: "平台", dataIndex: "platform_name", width: 140 },
  { title: "注册奖励积分", dataIndex: "reward_credits", width: 110 },
  { title: "返利次数", dataIndex: "reward_count", width: 88 },
  { title: "累计返利", dataIndex: "total_reward_amount_yuan", width: 110 },
  { title: "注册时间", dataIndex: "registered_at", width: 170 },
];

const detailActivityColumns = [
  { title: "用户", key: "user", width: "20%" },
  { title: "类型", dataIndex: "activity_type", width: 110 },
  { title: "积分", dataIndex: "credits", width: 80 },
  { title: "金额", dataIndex: "amount_yuan", width: 96 },
  { title: "返利比例", dataIndex: "reward_rate", width: 88 },
  { title: "返利金额", dataIndex: "reward_amount_yuan", width: 100 },
  { title: "第几次", dataIndex: "reward_index", width: 80 },
  { title: "时间", dataIndex: "occurred_at", width: 170 },
];

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function formatYuan(value?: number | null) {
  return value != null ? `¥${Number(value).toFixed(2)}` : "-";
}

function formatRebateStartDate(value?: string | null) {
  return value ? dayjs(value).format("YYYY年M月D日") : "2026年8月19日";
}

function rebateBarWidth(value?: number | null) {
  if (!maxRebateAmount.value) return "0%";
  return `${Math.max(6, Math.round((Number(value || 0) / maxRebateAmount.value) * 100))}%`;
}

function activityTypeLabel(value: string) {
  if (value === "purchase") return "购买订单";
  if (value === "redeem") return "兑换码兑换";
  return value || "-";
}

function promoActivityRowKey(record: AdminUserPromoDashboard["activities"][number], index: number) {
  return `${record.activity_type}-${record.order_no || record.redeem_key || record.user_id}-${index}`;
}

async function load() {
  loading.value = true;
  try {
    dashboard.value = await getAdminPromoStatsDashboard({ month: formatQueryMonth(selectedStatsMonth.value) });
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取白名单推广统计失败");
  } finally {
    loading.value = false;
  }
}

function handleStatsMonthChange(value: Dayjs | string | undefined | null) {
  selectedStatsMonth.value = value && typeof value !== "string" ? value : undefined;
  void load();
}

async function loadUserDetail() {
  if (!detailUserId.value) return;
  detailLoading.value = true;
  try {
    const range = detailFilters.dateRange;
    userDetail.value = await getAdminPromoStatsUserDetail(detailUserId.value, {
      month: range ? undefined : formatQueryMonth(detailFilters.month),
      start_date: formatQueryDate(range?.[0]?.startOf("day")),
      end_date: formatQueryDate(range?.[1]?.endOf("day")),
    });
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取推广详情失败");
  } finally {
    detailLoading.value = false;
  }
}

function resetDetailFilters() {
  detailFilters.month = undefined;
  detailFilters.dateRange = undefined;
}

async function openUserDetail(record: AdminPromoStatsUserItem) {
  detailOpen.value = true;
  detailUserId.value = record.user_id;
  userDetail.value = null;
  resetDetailFilters();
  await loadUserDetail();
}

function handleDetailMonthChange(value: Dayjs | string | undefined | null) {
  const monthValue = value && typeof value !== "string" ? value : undefined;
  detailFilters.month = monthValue;
  detailFilters.dateRange = monthValue
    ? [monthValue.startOf("month"), monthValue.endOf("month")]
    : undefined;
  void loadUserDetail();
}

function handleDetailDateRangeChange(value: [Dayjs, Dayjs] | undefined | null) {
  detailFilters.dateRange = value || undefined;
  if (value?.[0] && value[1]
    && value[0].isSame(value[0].startOf("month"), "day")
    && value[1].isSame(value[1].endOf("month"), "day")
    && value[0].isSame(value[1], "month")) {
    detailFilters.month = value[0].startOf("month");
  } else if (value) {
    detailFilters.month = undefined;
  }
  void loadUserDetail();
}

function handleResetDetailFilters() {
  resetDetailFilters();
  void loadUserDetail();
}

onMounted(() => {
  void load();
});
</script>

<template>
  <div class="warm-page motion-page-enter admin-promo-page">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <GiftOutlined />
        </div>
        <div>
          <div class="warm-page-title">白名单推广统计</div>
          <div class="warm-page-desc">
            统计白名单用户推广码注册、现金返利记账与推广用户消费情况。
            现金返利仅对 {{ formatRebateStartDate(dashboard.summary.start_at) }} 及之后通过推广码注册的用户有效，该日期前注册的推广用户后续新购买不返利。返利金额仅统计，不支持提现。
          </div>
        </div>
      </div>
      <div class="admin-promo-header-actions">
        <a-date-picker
          :value="selectedStatsMonth"
          picker="month"
          :locale="datePickerZhCN"
          format="YYYY-MM"
          placeholder="选择月份"
          :allow-clear="false"
          :disabled-date="disabledFutureMonth"
          @change="handleStatsMonthChange"
        />
        <a-button class="warm-secondary-btn" :loading="loading" @click="load">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
      </div>
    </div>

    <a-spin :spinning="loading">
      <div class="admin-promo-body">
        <div class="admin-promo-stats motion-fade-up" style="--motion-delay: 120ms">
          <div class="warm-card stat-card motion-card-lift">
            <div class="stat-card-head">
              <TeamOutlined />
              <span>推广注册用户</span>
            </div>
            <strong>{{ dashboard.summary.total_referrals }}</strong>
          </div>
          <div class="warm-card stat-card motion-card-lift">
            <div class="stat-card-head">
              <ShareAltOutlined />
              <span>有效推广人</span>
            </div>
            <strong>{{ dashboard.summary.active_promoters }}</strong>
          </div>
          <div class="warm-card stat-card motion-card-lift">
            <div class="stat-card-head">
              <GiftOutlined />
              <span>推广码总数</span>
            </div>
            <strong>{{ dashboard.summary.total_promo_codes }}</strong>
          </div>
          <div class="warm-card stat-card motion-card-lift">
            <div class="stat-card-head">
              <ThunderboltOutlined />
              <span>注册奖励积分</span>
            </div>
            <strong>{{ dashboard.summary.reward_credits }}</strong>
          </div>
        </div>

        <div class="admin-promo-stats secondary motion-fade-up" style="--motion-delay: 160ms">
          <div class="warm-card mini-stat-card motion-card-lift">
            <span>已使用推广码</span>
            <strong>{{ dashboard.summary.used_promo_codes }}</strong>
          </div>
          <div class="warm-card mini-stat-card motion-card-lift">
            <span>白名单用户</span>
            <strong>{{ dashboard.summary.whitelisted_users }}</strong>
          </div>
          <div class="warm-card mini-stat-card motion-card-lift">
            <span>推广用户购买积分</span>
            <strong>{{ dashboard.summary.purchase_credits }}</strong>
          </div>
          <div class="warm-card mini-stat-card motion-card-lift">
            <span>推广用户兑换积分</span>
            <strong>{{ dashboard.summary.redeem_credits }}</strong>
          </div>
          <div class="warm-card mini-stat-card motion-card-lift">
            <span>{{ dashboard.summary.month || "所选月份" }} 返利次数</span>
            <strong>{{ dashboard.summary.month_reward_grant_count || 0 }}</strong>
          </div>
          <div class="warm-card mini-stat-card motion-card-lift">
            <span>{{ dashboard.summary.month || "所选月份" }} 现金返利</span>
            <strong>{{ formatYuan(dashboard.summary.month_reward_amount_yuan || 0) }}</strong>
          </div>
        </div>

        <div class="warm-card admin-promo-chart-card motion-fade-up motion-card-lift" style="--motion-delay: 180ms">
          <div class="chart-card-head">
            <div>
              <div class="section-title">推广返利用户排行</div>
              <p>{{ dashboard.summary.month || "所选月份" }} 按现金返利金额排序，最多展示前 10 名。</p>
            </div>
            <a-tag class="warm-tag">累计 {{ formatYuan(dashboard.summary.total_reward_amount_yuan || 0) }}</a-tag>
          </div>
          <div v-if="rebateRanking.length" class="rebate-ranking-chart">
            <div
              v-for="(item, index) in rebateRanking"
              :key="item.user_id"
              class="rebate-ranking-row"
            >
              <div class="rebate-rank-index">{{ index + 1 }}</div>
              <div class="rebate-rank-user">
                <strong>{{ item.username || item.user_id }}</strong>
                <span>{{ item.email || item.user_id }}</span>
              </div>
              <div class="rebate-rank-bar-wrap">
                <div class="rebate-rank-bar" :style="{ width: rebateBarWidth(item.month_reward_amount_yuan) }" />
              </div>
              <div class="rebate-rank-value">
                <strong>{{ formatYuan(item.month_reward_amount_yuan || 0) }}</strong>
                <span>{{ item.month_reward_grant_count || 0 }} 次</span>
              </div>
            </div>
          </div>
          <a-empty v-else description="所选月份暂无返利数据" />
        </div>

        <div class="warm-card warm-table-card admin-promo-table-card motion-fade-up motion-card-lift" style="--motion-delay: 200ms">
          <div class="section-title">推广人排行</div>
          <a-table
            :columns="userColumns"
            :data-source="dashboard.users"
            row-key="user_id"
            :pagination="{ pageSize: 20 }"
            :scroll="{ x: 1600 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'user'">
                <div class="user-cell">
                  <strong>{{ record.username }}</strong>
                  <span>{{ record.email || record.user_id }}</span>
                </div>
              </template>
              <template v-else-if="column.dataIndex === 'total_reward_amount_yuan'">
                {{ formatYuan(record.total_reward_amount_yuan || 0) }}
              </template>
              <template v-else-if="column.dataIndex === 'month_reward_amount_yuan'">
                {{ formatYuan(record.month_reward_amount_yuan || 0) }}
              </template>
              <template v-else-if="column.dataIndex === 'last_referral_at'">
                {{ formatTime(record.last_referral_at) }}
              </template>
              <template v-else-if="column.key === 'action'">
                <a-button type="link" class="detail-link-btn" @click="openUserDetail(record)">查看详情</a-button>
              </template>
            </template>
          </a-table>
        </div>

        <div class="warm-card warm-table-card admin-promo-table-card motion-fade-up motion-card-lift" style="--motion-delay: 240ms">
          <div class="section-title">最近推广注册</div>
          <a-table
            :columns="referralColumns"
            :data-source="dashboard.recent_referrals"
            row-key="id"
            :pagination="{ pageSize: 20 }"
            :scroll="{ x: 900 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.dataIndex === 'registered_at'">
                {{ formatTime(record.registered_at) }}
              </template>
            </template>
          </a-table>
        </div>
      </div>
    </a-spin>

    <a-drawer
      v-model:open="detailOpen"
      width="1000"
      class="promo-detail-drawer"
      :title="userDetail ? `${userDetail.username} 的推广数据` : '推广数据详情'"
      :destroy-on-close="true"
    >
      <a-spin :spinning="detailLoading">
        <div class="detail-filter-bar">
          <a-date-picker
            :value="detailFilters.month"
            picker="month"
            :locale="datePickerZhCN"
            format="YYYY-MM"
            placeholder="选择月份"
            allow-clear
            :disabled-date="disabledFutureMonth"
            @change="handleDetailMonthChange"
          />
          <a-range-picker
            :value="detailFilters.dateRange"
            :locale="datePickerZhCN"
            format="YYYY-MM-DD"
            :placeholder="['开始日期', '结束日期']"
            allow-clear
            :disabled-date="disabledFutureDate"
            @change="handleDetailDateRangeChange"
          />
          <a-button type="primary" class="warm-primary-btn" @click="loadUserDetail">查询</a-button>
          <a-button class="warm-secondary-btn" @click="handleResetDetailFilters">
            <template #icon><UndoOutlined /></template>
            重置
          </a-button>
        </div>

        <template v-if="userDetail">
          <div class="detail-user-card">
            <div>
              <strong>{{ userDetail.username }}</strong>
              <span>{{ userDetail.user_id }}</span>
            </div>
            <a-tag class="warm-tag">
              {{ hasDetailPeriodFilter ? "筛选期内推广注册" : "推广注册" }}
              {{ userDetail.summary.period_referrals ?? userDetail.summary.total_referrals }}
            </a-tag>
          </div>

          <div class="detail-stat-grid">
            <div class="warm-card mini-stat-card">
              <span>{{ hasDetailPeriodFilter ? "筛选期内推广注册" : "推广注册" }}</span>
              <strong>{{ userDetail.summary.period_referrals ?? userDetail.summary.total_referrals }}</strong>
            </div>
            <div class="warm-card mini-stat-card">
              <span>{{ hasDetailPeriodFilter ? "筛选期内返利次数" : "返利次数" }}</span>
              <strong>{{ userDetail.summary.period_reward_grant_count ?? userDetail.summary.reward_grant_count ?? 0 }}</strong>
            </div>
            <div class="warm-card mini-stat-card">
              <span>{{ hasDetailPeriodFilter ? "筛选期内返利金额" : "返利金额" }}</span>
              <strong>{{ formatYuan(userDetail.summary.period_reward_amount_yuan ?? userDetail.summary.total_reward_amount_yuan ?? 0) }}</strong>
            </div>
            <div class="warm-card mini-stat-card">
              <span>累计现金返利</span>
              <strong>{{ formatYuan(userDetail.summary.total_reward_amount_yuan || 0) }}</strong>
            </div>
            <div class="warm-card mini-stat-card">
              <span>推广码数量</span>
              <strong>{{ userDetail.promo_codes.length }}</strong>
            </div>
          </div>

          <div class="detail-section">
            <div class="section-title">推广码列表</div>
            <a-table
              :columns="detailPromoColumns"
              :data-source="userDetail.promo_codes"
              row-key="id"
              :pagination="{ pageSize: 10 }"
              :scroll="{ x: 700 }"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.dataIndex === 'status'">
                  <a-tag class="warm-tag">{{ record.status === "enabled" ? "启用" : "停用" }}</a-tag>
                </template>
                <template v-else-if="column.dataIndex === 'created_at'">
                  {{ formatTime(record.created_at) }}
                </template>
              </template>
            </a-table>
          </div>

          <div class="detail-section">
            <div class="section-title">{{ hasDetailPeriodFilter ? "筛选期内推广用户" : "推广用户" }}</div>
            <a-table
              :columns="detailReferralColumns"
              :data-source="userDetail.referrals"
              row-key="user_id"
              :pagination="{ pageSize: 10 }"
              :scroll="{ x: 760 }"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'user'">
                  <div class="user-cell">
                    <strong>{{ record.username }}</strong>
                    <span>{{ record.email || record.email_masked || record.user_id }}</span>
                  </div>
                </template>
                <template v-else-if="column.dataIndex === 'total_reward_amount_yuan'">
                  {{ formatYuan(record.total_reward_amount_yuan || 0) }}
                </template>
                <template v-else-if="column.dataIndex === 'registered_at'">
                  {{ formatTime(record.registered_at) }}
                </template>
              </template>
            </a-table>
          </div>

          <div class="detail-section">
            <div class="section-title">{{ hasDetailPeriodFilter ? "筛选期内购买与返利记录" : "推广用户购买与返利记录" }}</div>
            <a-table
              :columns="detailActivityColumns"
              :data-source="userDetail.activities"
              :row-key="promoActivityRowKey"
              :pagination="{ pageSize: 10 }"
              :scroll="{ x: 760 }"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'user'">
                  <div class="user-cell">
                    <strong>{{ record.username }}</strong>
                    <span>{{ record.email_masked || record.user_id }}</span>
                  </div>
                </template>
                <template v-else-if="column.dataIndex === 'activity_type'">
                  <a-tag class="warm-tag">{{ activityTypeLabel(record.activity_type) }}</a-tag>
                </template>
                <template v-else-if="column.dataIndex === 'amount_yuan'">
                  {{ record.amount_yuan != null ? formatYuan(record.amount_yuan) : "-" }}
                </template>
                <template v-else-if="column.dataIndex === 'reward_rate'">
                  {{ record.reward_rate != null ? `${record.reward_rate}%` : "-" }}
                </template>
                <template v-else-if="column.dataIndex === 'reward_amount_yuan'">
                  {{ record.reward_amount_yuan != null ? formatYuan(record.reward_amount_yuan) : "-" }}
                </template>
                <template v-else-if="column.dataIndex === 'occurred_at'">
                  {{ formatTime(record.occurred_at) }}
                </template>
              </template>
            </a-table>
          </div>
        </template>
      </a-spin>
    </a-drawer>
  </div>
</template>

<style scoped lang="scss">
.admin-promo-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding-inline: 14px;
}

.admin-promo-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.admin-promo-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.admin-promo-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 20px;

  &.secondary {
    grid-template-columns: repeat(6, minmax(0, 1fr));
  }
}

.stat-card,
.mini-stat-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;

  span {
    color: var(--theme-text-secondary);
    font-weight: 700;
  }

  strong {
    color: var(--theme-title);
    font-size: 28px;
    line-height: 1;
  }
}

.stat-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;

  :deep(.anticon) {
    flex-shrink: 0;
    color: var(--theme-accent-text);
    font-size: 18px;
  }

  span {
    line-height: 1.3;
  }
}

.mini-stat-card strong {
  font-size: 24px;
}

.section-title {
  margin-bottom: 14px;
  color: var(--theme-title);
  font-size: 16px;
  font-weight: 800;
}

.admin-promo-chart-card {
  display: grid;
  gap: 18px;
  padding: 22px 24px 24px;
}

.chart-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;

  .section-title {
    margin-bottom: 6px;
  }

  p {
    margin: 0;
    color: var(--theme-text-secondary);
    font-size: 13px;
  }
}

.rebate-ranking-chart {
  display: grid;
  gap: 12px;
}

.rebate-ranking-row {
  display: grid;
  grid-template-columns: 36px minmax(150px, 220px) minmax(160px, 1fr) 110px;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.rebate-rank-index {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: var(--theme-pill-bg-strong);
  color: var(--theme-accent-text);
  font-weight: 800;
}

.rebate-rank-user {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;

  strong,
  span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  strong {
    color: var(--theme-title);
  }

  span {
    color: var(--theme-text-secondary);
    font-size: 12px;
  }
}

.rebate-rank-bar-wrap {
  min-width: 0;
  height: 14px;
  border-radius: 999px;
  background: var(--theme-panel-bg-muted);
  overflow: hidden;
}

.rebate-rank-bar {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--theme-accent), var(--theme-accent-strong));
}

.rebate-rank-value {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;

  strong {
    color: var(--theme-title);
  }

  span {
    color: var(--theme-text-secondary);
    font-size: 12px;
  }
}

.admin-promo-table-card {
  padding: 22px 24px 24px;
  overflow: visible;

  :deep(.ant-table-wrapper) {
    overflow: hidden;
    border-radius: 16px;
  }
}

.user-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;

  strong {
    color: var(--theme-title);
  }

  span {
    color: var(--theme-text-secondary);
    font-size: 12px;
    word-break: break-all;
  }
}

.detail-link-btn {
  padding-inline: 0;
  color: var(--theme-accent-text);
  font-weight: 700;
}

.detail-user-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  padding: 16px;
  border-radius: 18px;
  background: var(--theme-panel-bg-strong);
  border: 1px solid var(--theme-panel-border-strong);

  div {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  strong {
    color: var(--theme-title);
    font-size: 18px;
  }

  span {
    color: var(--theme-text-secondary);
  }
}

.detail-filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.detail-stat-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 20px;
}

@media (max-width: 980px) {
  .admin-promo-stats,
  .admin-promo-stats.secondary,
  .detail-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .rebate-ranking-row {
    grid-template-columns: 32px minmax(0, 1fr);
  }

  .rebate-rank-bar-wrap,
  .rebate-rank-value {
    grid-column: 2;
  }

  .rebate-rank-value {
    align-items: flex-start;
  }
}
</style>
