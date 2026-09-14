<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { message } from "ant-design-vue";
import datePickerZhCN from "ant-design-vue/es/date-picker/locale/zh_CN";
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";
import { getAdminAnalyticsRevenueTimeseries } from "@/api/admin";
import { isSessionExpiredError } from "@/lib/authError";
import type { AdminAnalyticsRevenueTimeseries } from "@/types";
import { getCurrentTheme } from "@/lib/theme";
import { VChart } from "./charting";

function chartLabelColor() {
  return getCurrentTheme() === "midnight" ? "#d8d8d8" : "#8c7458";
}

type RevenueChannel = "total" | "online" | "redeem";

const loading = ref(false);
const chartMonth = ref<Dayjs>(dayjs());
const data = ref<AdminAnalyticsRevenueTimeseries | null>(null);
const channel = ref<RevenueChannel>("total");

const labels = computed(() => data.value?.points.map((item) => item.label) || []);

const channelMeta = computed(() => {
  if (channel.value === "online") {
    return {
      title: "每日在线购买收入",
      desc: "按所选月份逐日对比在线购买金额。",
      badge: "在线购买",
      total: Number(data.value?.total_online_amount || 0),
    };
  }
  if (channel.value === "redeem") {
    return {
      title: "每日兑换码收入",
      desc: "按所选月份逐日对比兑换码金额。",
      badge: "兑换码",
      total: Number(data.value?.total_redeem_amount || 0),
    };
  }
  return {
    title: "每日总收入",
    desc: "按所选月份逐日对比在线购买、兑换码和线下订单收入。",
    badge: "总收入",
    total: Number(data.value?.total_amount || 0),
  };
});

const hasChartData = computed(() => {
  if (!data.value?.points.length) return false;
  return data.value.points.some((item) => {
    if (channel.value === "online") return Number(item.online_amount || 0) !== 0;
    if (channel.value === "redeem") return Number(item.redeem_amount || 0) !== 0;
    return Number(item.total_amount || 0) !== 0;
  });
});

function formatMoney(value?: number) {
  return Number(value || 0).toFixed(2);
}

function barLabelAmount(index: number) {
  const point = data.value?.points[index];
  if (!point) return 0;
  if (channel.value === "online") return Number(point.online_amount || 0);
  if (channel.value === "redeem") return Number(point.redeem_amount || 0);
  return Number(point.total_amount || 0);
}

function topStackKey(item: { online_amount: number; redeem_amount: number; offline_amount: number }) {
  if (channel.value === "online") return Number(item.online_amount || 0) !== 0 ? "online" : null;
  if (channel.value === "redeem") return Number(item.redeem_amount || 0) !== 0 ? "redeem" : null;
  if (Number(item.offline_amount || 0) !== 0) return "offline";
  if (Number(item.redeem_amount || 0) !== 0) return "redeem";
  if (Number(item.online_amount || 0) !== 0) return "online";
  return null;
}

function channelFromLegend(name?: string): RevenueChannel | null {
  if (name === "在线购买") return "online";
  if (name === "兑换码") return "redeem";
  if (name === "线下订单") return "total";
  return null;
}

function handleLegendSelectChanged(params: { name?: string }) {
  const next = channelFromLegend(params.name);
  if (!next) return;
  channel.value = channel.value === next && next !== "total" ? "total" : next;
}

function disableFutureMonth(value: Dayjs) {
  return value.startOf("month").isAfter(dayjs().startOf("month"));
}

function handleMonthChange(value: Dayjs | null) {
  if (!value) return;
  chartMonth.value = value;
  loadChart();
}

async function loadChart() {
  loading.value = true;
  try {
    const month = chartMonth.value;
    const start = month.startOf("month");
    const end = month.isSame(dayjs(), "month") ? dayjs().endOf("day") : month.endOf("month");
    data.value = await getAdminAnalyticsRevenueTimeseries({
      granularity: "day",
      start_date: start.format("YYYY-MM-DDTHH:mm:ss"),
      end_date: end.format("YYYY-MM-DDTHH:mm:ss"),
    });
  } catch (err: unknown) {
    if (isSessionExpiredError(err)) return;
    message.error("获取每日收入数据失败");
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadChart();
});

defineExpose({ reload: loadChart });

const chartOption = computed(() => {
  const moneyAxis = {
    type: "value" as const,
    axisLabel: {
      formatter: (value: number) => `¥${formatMoney(value)}`,
    },
  };
  const legendSelected = {
    在线购买: channel.value === "total" || channel.value === "online",
    兑换码: channel.value === "total" || channel.value === "redeem",
    线下订单: channel.value === "total",
  };

  return {
    color: ["#0E61AC", "#FAF2E0", "#B7A4D6"],
    tooltip: {
      trigger: "axis" as const,
      backgroundColor: "rgba(76, 52, 26, 0.92)",
      borderWidth: 0,
      textStyle: { color: "#fffdf8" },
      formatter: (params: Array<{ dataIndex?: number; axisValue?: string; marker?: string; seriesName?: string }>) => {
        const point = data.value?.points[params[0]?.dataIndex || 0];
        const offlineAmount = Number(point?.offline_amount || 0);
        const rows = [
          { name: "在线购买", value: Number(point?.online_amount || 0), marker: params.find((item) => item.seriesName === "在线购买")?.marker, visible: channel.value === "total" || channel.value === "online" },
          { name: "兑换码", value: Number(point?.redeem_amount || 0), marker: params.find((item) => item.seriesName === "兑换码")?.marker, visible: channel.value === "total" || channel.value === "redeem" },
          { name: "线下订单", value: offlineAmount, marker: params.find((item) => item.seriesName === "线下订单")?.marker, visible: channel.value === "total" },
        ].filter((item) => item.visible);
        const total = channel.value === "online"
          ? Number(point?.online_amount || 0)
          : channel.value === "redeem"
            ? Number(point?.redeem_amount || 0)
            : Number(point?.total_amount || 0);
        return [
          params[0]?.axisValue || "",
          ...rows.map((item) => `${item.marker || ""}${item.name}：¥${formatMoney(item.value)}`),
          `合计：¥${formatMoney(total)}`,
        ].join("<br/>");
      },
    },
    legend: {
      top: 0,
      data: ["在线购买", "兑换码", "线下订单"],
      selected: legendSelected,
    },
    grid: { left: 56, right: 20, top: 56, bottom: 28 },
    xAxis: { type: "category", data: labels.value },
    yAxis: moneyAxis,
    series: [
      {
        name: "在线购买",
        type: "bar",
        stack: "revenue",
        data: data.value?.points.map((item, index) => ({
          value: Number(item.online_amount || 0) || null,
          itemStyle: {
            color: "#0E61AC",
            borderRadius: topStackKey(item) === "online" ? [8, 8, 0, 0] : 0,
          },
          label: {
            show: topStackKey(item) === "online" && barLabelAmount(index) !== 0,
            position: "top",
            color: chartLabelColor(),
            fontSize: 10,
            fontWeight: 600,
            formatter: `¥${formatMoney(barLabelAmount(index))}`,
          },
        })) || [],
      },
      {
        name: "兑换码",
        type: "bar",
        stack: "revenue",
        data: data.value?.points.map((item, index) => ({
          value: Number(item.redeem_amount || 0) || null,
          itemStyle: {
            color: "#FAF2E0",
            borderColor: "#E6D7B8",
            borderWidth: 1,
            borderRadius: topStackKey(item) === "redeem" ? [8, 8, 0, 0] : 0,
          },
          label: {
            show: topStackKey(item) === "redeem" && barLabelAmount(index) !== 0,
            position: "top",
            color: chartLabelColor(),
            fontSize: 10,
            fontWeight: 600,
            formatter: `¥${formatMoney(barLabelAmount(index))}`,
          },
        })) || [],
      },
      {
        name: "线下订单",
        type: "bar",
        stack: "revenue",
        data: data.value?.points.map((item, index) => {
          const amount = Number(item.offline_amount || 0);
          return {
            value: amount === 0 ? null : Math.abs(amount),
            itemStyle: {
              color: amount < 0 ? "#E8A8A8" : "#B7A4D6",
              borderRadius: topStackKey(item) === "offline" ? [8, 8, 0, 0] : 0,
            },
            label: {
              show: topStackKey(item) === "offline" && barLabelAmount(index) !== 0,
              position: "top",
              color: chartLabelColor(),
              fontSize: 10,
              fontWeight: 600,
              formatter: `¥${formatMoney(barLabelAmount(index))}`,
            },
          };
        }) || [],
      },
    ],
  };
});
</script>

<template>
  <a-spin :spinning="loading">
    <div class="revenue-chart-card warm-card motion-card-lift motion-fade-up" style="--motion-delay: 180ms">
      <div class="revenue-chart-head">
        <div>
          <div class="revenue-chart-title">{{ channelMeta.title }}</div>
          <div class="revenue-chart-desc">{{ channelMeta.desc }}</div>
        </div>
        <div class="revenue-chart-actions">
          <a-date-picker
            v-model:value="chartMonth"
            picker="month"
            placeholder="选择月份"
            format="YYYY年M月"
            :locale="datePickerZhCN"
            :allow-clear="false"
            :disabled-date="disableFutureMonth"
            class="revenue-chart-month"
            @change="handleMonthChange"
          />
          <a-radio-group
            v-model:value="channel"
            class="analytics-segmented-group analytics-segmented-group-secondary"
            button-style="solid"
          >
            <a-radio-button value="total">总收入</a-radio-button>
            <a-radio-button value="online">在线购买</a-radio-button>
            <a-radio-button value="redeem">兑换码</a-radio-button>
          </a-radio-group>
          <div class="revenue-chart-summary">
            <span>{{ channelMeta.badge }}</span>
            <strong>¥{{ formatMoney(channelMeta.total) }}</strong>
          </div>
        </div>
      </div>
      <VChart
        v-if="hasChartData"
        class="revenue-chart"
        :option="chartOption"
        :update-options="{ notMerge: true }"
        autoresize
        @legendselectchanged="handleLegendSelectChanged"
      />
      <div v-else class="revenue-chart-empty">
        <a-empty class="warm-empty" description="当前筛选条件下暂无收入数据">
          <template #description>
            <div class="empty-title">当前筛选条件下暂无收入数据</div>
            <div class="empty-desc">切换月份或收入来源后，可查看每日收入对比。</div>
          </template>
        </a-empty>
      </div>
    </div>
  </a-spin>
</template>

<style scoped lang="scss">
.revenue-chart-card {
  padding: 18px 20px 14px;
  min-width: 0;
  overflow: hidden;
}

.revenue-chart-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 10px;
}

.revenue-chart-title {
  font-size: 14px;
  font-weight: 700;
  color: #5d4526;
}

.revenue-chart-desc {
  margin-top: 4px;
  color: #9a805b;
  font-size: 12px;
  line-height: 1.5;
}

.revenue-chart-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.revenue-chart-month {
  width: 132px;
}

.revenue-chart-summary {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--theme-panel-bg-strong);
  color: #a07d49;
  font-size: 12px;
  font-weight: 700;

  strong {
    color: #a05f00;
    font-size: 16px;
  }
}

.revenue-chart {
  height: 280px;
}

.revenue-chart-empty {
  min-height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 28px 20px;
}

.empty-title {
  color: #5d4526;
  font-size: 15px;
  font-weight: 700;
}

.empty-desc {
  margin-top: 6px;
  color: #9a805b;
  font-size: 12px;
}

@media (max-width: 768px) {
  .revenue-chart-card {
    padding: 16px 14px 12px;
  }

  .revenue-chart-head {
    flex-direction: column;
  }

  .revenue-chart-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .revenue-chart-month {
    width: 100%;
  }
}
</style>
