<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { message } from "ant-design-vue";

import { getMe } from "@/api/auth";
import { getPaymentOrder, getPaymentOrderResult } from "@/api/payments";
import { useAuthStore } from "@/stores/auth";
import type { PaymentOrder } from "@/types";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const loading = ref(false);
const order = ref<PaymentOrder | null>(null);
const notFound = ref(false);
let pollTimer: number | null = null;

const orderNo = computed(() => String(route.query.order_no || "").trim());
const paymentToken = computed(() => String(route.query.payment_token || "").trim());
const statusText = computed(() => {
  if (!order.value) return "正在查询订单状态";
  if (order.value.status === "pending_pay") return "订单待支付";
  if (order.value.status === "paid") return "支付成功，积分处理中";
  if (order.value.status === "credited") return "积分已到账";
  if (order.value.status === "closed") return "订单已关闭";
  if (order.value.status === "failed") return "支付失败";
  return "订单创建中";
});

function clearPollTimer() {
  if (!pollTimer) return;
  window.clearTimeout(pollTimer);
  pollTimer = null;
}

async function fetchOrderStatus() {
  if (!paymentToken.value) {
    return getPaymentOrder(orderNo.value);
  }
  try {
    return await getPaymentOrderResult(orderNo.value, paymentToken.value);
  } catch (err) {
    if (auth.isLoggedIn) {
      return getPaymentOrder(orderNo.value);
    }
    throw err;
  }
}

async function syncOrder(showError = true) {
  if (!orderNo.value) {
    notFound.value = true;
    return;
  }
  loading.value = true;
  try {
    order.value = await fetchOrderStatus();
    notFound.value = false;
    if (order.value.status === "credited") {
      if (auth.isLoggedIn) {
        try {
          auth.updateUser(await getMe());
        } catch {
          // ignore refresh errors, result page can still show success
        }
      }
      clearPollTimer();
      return;
    }
    if (order.value.status === "pending_pay" || order.value.status === "paid") {
      clearPollTimer();
      pollTimer = window.setTimeout(() => {
        void syncOrder(false);
      }, 2500);
      return;
    }
    clearPollTimer();
  } catch (err: any) {
    if (err?.response?.status === 404) {
      notFound.value = true;
      clearPollTimer();
      return;
    }
    if (showError) {
      message.error(err?.response?.data?.detail || "查询订单失败");
    }
  } finally {
    loading.value = false;
  }
}

function goBack() {
  router.push("/");
}

function goCreditLogs() {
  router.push("/credit-logs");
}

onMounted(() => {
  void syncOrder();
});

onBeforeUnmount(() => {
  clearPollTimer();
});
</script>

<template>
  <div class="payment-result-page warm-page motion-page-enter">
    <section class="payment-result-card">
      <h2>支付结果</h2>
      <p v-if="notFound" class="payment-result-desc">未找到对应订单，请返回后重试。</p>
      <template v-else>
        <p class="payment-result-desc">{{ statusText }}</p>
        <div v-if="order" class="payment-result-summary">
          <div><span>订单号</span><strong>{{ order.order_no }}</strong></div>
          <div><span>套餐</span><strong>{{ order.subject }}</strong></div>
          <div><span>积分</span><strong>{{ order.credits }}</strong></div>
          <div><span>状态</span><strong>{{ order.status }}</strong></div>
        </div>
      </template>
      <div class="payment-result-actions">
        <a-button class="warm-secondary-btn" @click="goBack">返回首页</a-button>
        <a-button type="primary" class="warm-primary-btn" :loading="loading" @click="goCreditLogs">
          查看积分明细
        </a-button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.payment-result-page {
  display: flex;
  justify-content: center;
  padding: 48px 16px;
}

.payment-result-card {
  width: min(100%, 560px);
  padding: 28px;
  border-radius: 24px;
  background: var(--theme-card-bg, #fff);
  box-shadow: 0 18px 50px rgba(24, 24, 24, 0.08);
}

.payment-result-card h2 {
  margin: 0 0 12px;
  font-size: 24px;
}

.payment-result-desc {
  margin: 0 0 18px;
  color: var(--theme-text-secondary);
}

.payment-result-summary {
  display: grid;
  gap: 12px;
  margin-bottom: 24px;
}

.payment-result-summary div {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border-radius: 14px;
  background: var(--theme-background-soft, rgba(0, 0, 0, 0.03));
}

.payment-result-summary span {
  color: var(--theme-text-secondary);
}

.payment-result-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
