<script setup lang="ts">
import { computed } from "vue";
import type { PropType } from "vue";
import type { AdminAnalyticsRedeemRevenue, AdminAnalyticsRedeemRevenueItem } from "@/types";

const props = defineProps({
  data: {
    type: Object as PropType<AdminAnalyticsRedeemRevenue | null>,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  showTitle: {
    type: Boolean,
    default: true,
  },
  title: {
    type: String,
    default: "兑换码营业额",
  },
  countLabel: {
    type: String,
    default: "兑换",
  },
});

const columns = [
  { title: "积分面值", dataIndex: "credit_amount", width: 120 },
  { title: "售价（元）", dataIndex: "unit_price", width: 120 },
  { title: "兑换个数", dataIndex: "used_count", width: 120 },
  { title: "总金额（元）", dataIndex: "total_amount", width: 140 },
];

const tableData = computed(() => props.data?.items ?? []);

function formatMoney(value: number) {
  return value.toFixed(2);
}

function rowKey(record: AdminAnalyticsRedeemRevenueItem) {
  return String(record.credit_amount);
}
</script>

<template>
  <a-spin :spinning="loading">
    <div class="redeem-revenue-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 280ms">
      <div class="redeem-revenue-head">
        <div v-if="showTitle" class="redeem-revenue-head-left">
          <div class="redeem-revenue-title">{{ title }}</div>
          <div v-if="data?.range_label" class="redeem-revenue-range">{{ data.range_label }}</div>
        </div>
        <div v-else-if="data?.range_label" class="redeem-revenue-range-only">{{ data.range_label }}</div>
        <div class="redeem-revenue-head-right">
          <div v-if="$slots['header-extra']" class="redeem-revenue-extra">
            <slot name="header-extra" />
          </div>
          <div v-if="data" class="redeem-revenue-summary">
            <span class="redeem-revenue-chip">{{ countLabel }} {{ data.total_used_count }} 次</span>
            <span class="redeem-revenue-chip redeem-revenue-chip-strong">合计 ¥{{ formatMoney(data.total_amount) }}</span>
          </div>
        </div>
      </div>

      <a-table
        :columns="columns"
        :data-source="tableData"
        :pagination="false"
        :row-key="rowKey"
        size="middle"
        class="redeem-revenue-table admin-mobile-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'credit_amount'">
            {{ record.credit_amount }}
          </template>
          <template v-else-if="column.dataIndex === 'unit_price'">
            {{ record.unit_price > 0 ? formatMoney(record.unit_price) : "-" }}
          </template>
          <template v-else-if="column.dataIndex === 'used_count'">
            {{ record.used_count }}
          </template>
          <template v-else-if="column.dataIndex === 'total_amount'">
            {{ record.total_amount > 0 || record.used_count > 0 ? formatMoney(record.total_amount) : "0.00" }}
          </template>
        </template>
        <template #summary>
          <a-table-summary-row v-if="data">
            <a-table-summary-cell :index="0">合计</a-table-summary-cell>
            <a-table-summary-cell :index="1">-</a-table-summary-cell>
            <a-table-summary-cell :index="2">{{ data.total_used_count }}</a-table-summary-cell>
            <a-table-summary-cell :index="3">¥{{ formatMoney(data.total_amount) }}</a-table-summary-cell>
          </a-table-summary-row>
        </template>
      </a-table>

      <div v-if="$slots['footer-extra']" class="redeem-revenue-footer">
        <slot name="footer-extra" />
      </div>
    </div>
  </a-spin>
</template>

<style scoped lang="scss">
.redeem-revenue-card {
  padding: 16px 18px 10px;
}

.redeem-revenue-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.redeem-revenue-title {
  color: #5d4526;
  font-size: 15px;
  font-weight: 700;
}

.redeem-revenue-range {
  margin-top: 4px;
  color: #8c7458;
  font-size: 12px;
}

.redeem-revenue-range-only {
  color: #8c7458;
  font-size: 13px;
  line-height: 1.5;
}

.redeem-revenue-summary {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.redeem-revenue-head-right {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.redeem-revenue-extra {
  display: flex;
  align-items: center;
}

.redeem-revenue-chip {
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(255, 245, 223, 0.9);
  color: #8c7458;
  font-size: 12px;
  font-weight: 600;
}

.redeem-revenue-chip-strong {
  color: #a05f00;
  background: rgba(255, 196, 91, 0.18);
}

.redeem-revenue-footer {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  margin-top: 12px;
}

.redeem-revenue-table {
  :deep(.ant-table) {
    background: transparent;
  }

  :deep(.ant-table-thead > tr > th) {
    background: rgba(255, 248, 236, 0.92);
    color: #8c7458;
    font-weight: 600;
  }

  :deep(.ant-table-tbody > tr > td),
  :deep(.ant-table-summary > tr > td) {
    color: #5d4526;
  }

  :deep(.ant-table-summary > tr > td) {
    background: rgba(255, 245, 223, 0.72);
    font-weight: 700;
  }
}
</style>
