<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { message } from "ant-design-vue";
import dayjs from "dayjs";
import { getAdminUserDetail, getCreditLogs as getAdminCreditLogs, listPaymentOrders } from "@/api/admin";
import { getAvatarImageSrc } from "@/api/images";
import type { AdminPaymentOrder, AdminUser, CreditLog } from "@/types";

const props = withDefaults(defineProps<{
  open: boolean;
  user: AdminUser | null;
  showViewData?: boolean;
}>(), {
  showViewData: false,
});

const emit = defineEmits<{
  (event: "update:open", value: boolean): void;
  (event: "view-data", user: AdminUser): void;
}>();

const loading = ref(false);
const redeemLogs = ref<CreditLog[]>([]);
const redeemTotal = ref(0);
const purchaseOrders = ref<AdminPaymentOrder[]>([]);
const purchaseTotal = ref(0);
const loadedUserId = ref("");
const detailedUser = ref<AdminUser | null>(null);

const displayUser = computed(() => detailedUser.value || props.user);
const dialogTitle = computed(() => (displayUser.value ? `用户信息 — ${displayUser.value.username}` : "用户信息"));

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

async function loadUserRecords() {
  const userId = props.user?.id;
  if (!props.open || !userId || loadedUserId.value === userId) return;
  detailedUser.value = null;
  redeemLogs.value = [];
  redeemTotal.value = 0;
  purchaseOrders.value = [];
  purchaseTotal.value = 0;
  loading.value = true;
  try {
    const [userDetail, redeemRes, purchaseRes] = await Promise.all([
      getAdminUserDetail(userId),
      getAdminCreditLogs(1, 5, userId, undefined, undefined, undefined, "redeem"),
      listPaymentOrders({ page: 1, page_size: 5, user: userId, status: "credited" }),
    ]);
    detailedUser.value = userDetail;
    redeemLogs.value = redeemRes.items;
    redeemTotal.value = redeemRes.total;
    purchaseOrders.value = purchaseRes.items;
    purchaseTotal.value = purchaseRes.total;
    loadedUserId.value = userId;
  } catch {
    message.error("获取用户积分记录失败");
  } finally {
    loading.value = false;
  }
}

function closeDialog() {
  emit("update:open", false);
}

function handleViewData() {
  if (!displayUser.value) return;
  emit("view-data", displayUser.value);
}

watch(() => [props.open, props.user?.id], () => {
  void loadUserRecords();
}, { immediate: true });
</script>

<template>
  <a-modal
    :open="open"
    :title="dialogTitle"
    :footer="null"
    :width="560"
    centered
    @cancel="closeDialog"
  >
    <a-spin :spinning="loading">
      <div v-if="displayUser" class="user-info-dialog">
        <div class="user-info-scroll">
          <div class="user-info-header">
            <a-avatar :size="54" :src="getAvatarImageSrc(displayUser.avatar_url) || undefined" class="user-info-avatar">
              {{ displayUser.username?.charAt(0)?.toUpperCase() }}
            </a-avatar>
            <div class="user-info-identity">
              <div class="user-info-name">{{ displayUser.username }}</div>
              <div v-if="displayUser.email" class="user-info-contact">{{ displayUser.email }}</div>
              <div v-if="displayUser.phone" class="user-info-contact">{{ displayUser.phone }}</div>
              <div v-if="!displayUser.email && !displayUser.phone" class="user-info-contact">未绑定邮箱或手机号</div>
              <div class="user-info-id">{{ displayUser.id }}</div>
            </div>
          </div>

          <div class="user-info-stats">
            <div class="user-info-stat-card">
              <span>已使用积分</span>
              <strong>{{ displayUser.consumed_credits || 0 }}</strong>
            </div>
            <div class="user-info-stat-card">
              <span>剩余积分</span>
              <strong>{{ displayUser.credits || 0 }}</strong>
            </div>
            <div class="user-info-stat-card">
              <span>兑换记录</span>
              <strong>{{ redeemTotal }}</strong>
            </div>
            <div class="user-info-stat-card">
              <span>购买记录</span>
              <strong>{{ purchaseTotal }}</strong>
            </div>
          </div>

          <div class="user-info-section">
            <div class="user-info-section-title">最近在线购买记录</div>
            <div v-if="purchaseOrders.length" class="user-redeem-list">
              <div v-for="order in purchaseOrders" :key="order.order_no" class="user-redeem-item">
                <div>
                  <strong>+{{ order.credits }} 积分</strong>
                  <span>{{ order.subject || "积分购买" }} · ¥{{ order.amount_yuan.toFixed(2) }}</span>
                </div>
                <small>{{ formatTime(order.credited_at || order.paid_at || order.created_at) }}</small>
              </div>
            </div>
            <a-empty v-else description="暂无在线购买记录" />
          </div>

          <div class="user-info-section">
            <div class="user-info-section-title">最近积分兑换记录</div>
            <div v-if="redeemLogs.length" class="user-redeem-list">
              <div v-for="log in redeemLogs" :key="log.id" class="user-redeem-item">
                <div>
                  <strong>{{ log.amount > 0 ? `+${log.amount}` : log.amount }} 积分</strong>
                  <span>{{ log.description || "兑换积分" }}</span>
                </div>
                <small>{{ formatTime(log.created_at) }}</small>
              </div>
            </div>
            <a-empty v-else description="暂无积分兑换记录" />
          </div>
        </div>

        <div class="user-info-actions">
          <a-button class="user-info-secondary-btn" @click="closeDialog">
            关闭
          </a-button>
          <a-button v-if="showViewData" type="primary" class="user-info-primary-btn" @click="handleViewData">
            查看数据
          </a-button>
        </div>
      </div>
    </a-spin>
  </a-modal>
</template>

<style scoped lang="scss">
.user-info-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-height: min(68vh, 640px);
}

.user-info-scroll {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.user-info-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 18px;
  background: var(--theme-panel-bg-soft);
  flex-shrink: 0;
}

.user-info-avatar {
  flex: 0 0 auto;
  background: var(--theme-accent);
  color: var(--theme-accent-contrast);
}

.user-info-identity {
  min-width: 0;
}

.user-info-name {
  color: var(--theme-title);
  font-size: 17px;
  font-weight: 800;
}

.user-info-id {
  margin-top: 4px;
  color: var(--theme-text-secondary);
  font-size: 12px;
  word-break: break-all;
}

.user-info-contact {
  margin-top: 4px;
  color: var(--theme-title);
  font-size: 13px;
  word-break: break-all;
}

.user-info-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  flex-shrink: 0;
}

.user-info-stat-card {
  padding: 12px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 16px;
  background: var(--theme-panel-bg);

  span {
    display: block;
    color: var(--theme-text-secondary);
    font-size: 12px;
  }

  strong {
    display: block;
    margin-top: 6px;
    color: var(--theme-title);
    font-size: 20px;
  }
}

.user-info-section-title {
  margin-bottom: 10px;
  color: var(--theme-title);
  font-weight: 800;
}

.user-redeem-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.user-redeem-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 14px;
  background: var(--theme-panel-bg-soft);

  div {
    min-width: 0;
  }

  strong {
    display: block;
    color: #1f9d63;
    font-size: 13px;
  }

  span {
    display: block;
    margin-top: 3px;
    color: var(--theme-title);
    font-size: 12px;
    word-break: break-word;
  }

  small {
    flex: 0 0 auto;
    color: var(--theme-text-secondary);
    font-size: 12px;
    white-space: nowrap;
  }
}

.user-info-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-shrink: 0;
  padding-top: 4px;
}

.user-info-secondary-btn,
.user-info-primary-btn {
  border-radius: 999px;
  font-weight: 700;
}

.user-info-secondary-btn {
  border-color: var(--theme-border);
  background: var(--theme-panel-bg);
  color: var(--theme-title);
}
</style>
