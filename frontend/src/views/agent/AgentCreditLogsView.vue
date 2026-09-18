<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { message } from "ant-design-vue";
import { HistoryOutlined } from "@ant-design/icons-vue";
import { getAgentCreditLogs } from "@/api/agent";
import type { CreditLog } from "@/types";

const loading = ref(false);
const items = ref<CreditLog[]>([]);
const pagination = reactive({ page: 1, pageSize: 20, total: 0 });

async function load() {
  loading.value = true;
  try {
    const res = await getAgentCreditLogs({ page: pagination.page, page_size: pagination.pageSize });
    items.value = res.items;
    pagination.total = res.total;
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取积分池流水失败");
  } finally {
    loading.value = false;
  }
}

function handlePageChange(page: number, pageSize?: number) {
  pagination.page = page;
  if (pageSize) pagination.pageSize = pageSize;
  load();
}

function fmtTime(t?: string | null) {
  return t ? new Date(t).toLocaleString("zh-CN", { hour12: false }) : "-";
}

onMounted(load);
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon"><HistoryOutlined /></div>
        <div>
          <div class="warm-page-title">积分池流水</div>
          <div class="warm-page-desc">只展示代理积分池的管理员充扣和兑换兑付扣减记录。</div>
        </div>
      </div>
    </div>

    <div class="warm-card warm-table-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <a-table :data-source="items" :loading="loading" row-key="id" :pagination="false" :scroll="{ x: 760 }">
        <a-table-column title="时间" data-index="created_at" width="180">
          <template #default="{ record }">{{ fmtTime(record.created_at) }}</template>
        </a-table-column>
        <a-table-column title="变动" data-index="amount" width="100">
          <template #default="{ record }">
            <span :class="record.amount >= 0 ? 'amount-plus' : 'amount-minus'">{{ record.amount > 0 ? `+${record.amount}` : record.amount }}</span>
          </template>
        </a-table-column>
        <a-table-column title="类型" data-index="type" width="140" />
        <a-table-column title="说明" data-index="description" />
        <a-table-column title="操作人" data-index="operator_name" width="140" />
      </a-table>
    </div>

    <div class="warm-pagination">
      <div class="pagination-summary">共 {{ pagination.total }} 条流水</div>
      <a-pagination
        v-if="pagination.total > pagination.pageSize"
        :current="pagination.page"
        :total="pagination.total"
        :page-size="pagination.pageSize"
        show-size-changer
        @change="handlePageChange"
        @showSizeChange="handlePageChange"
      />
    </div>
  </div>
</template>

<style scoped lang="scss">
.amount-plus { color: #389e0d; font-weight: 800; }
.amount-minus { color: #cf1322; font-weight: 800; }
.pagination-summary { color: #8c7458; font-size: 13px; }
</style>
