<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { BarChartOutlined, PictureOutlined, VideoCameraOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import { useRouter } from "vue-router";
import { getStats, getVideoStats } from "@/api/admin";
import { isSessionExpiredError } from "@/lib/authError";
import type { AdminStats, VideoStats } from "@/types";

type OverviewCard = {
  key: string;
  label: string;
  value: number;
  desc: string;
  color: string;
};

const imageLoading = ref(false);
const videoLoading = ref(false);
const imageStats = ref<AdminStats | null>(null);
const videoStats = ref<VideoStats | null>(null);
const router = useRouter();

const imageOverviewStats = computed<OverviewCard[]>(() => {
  if (!imageStats.value) return [];
  return [
    {
      key: "total_tasks",
      label: "所有时间总任务数",
      value: imageStats.value.total_tasks,
      desc: "累计发起的全部图片任务数量（含提示词反推）",
      color: "#1890ff",
    },
    {
      key: "total_credit_cost",
      label: "所有时间总积分消耗",
      value: imageStats.value.total_credit_cost,
      desc: "累计图片任务实际扣减的积分总量（含提示词反推）",
      color: "#722ed1",
    },
    {
      key: "total_remain_credits",
      label: "所有用户剩余积分总和",
      value: imageStats.value.total_remain_credits,
      desc: "当前系统内非超级管理员用户的可用积分合计",
      color: "#eb2f96",
    },
    {
      key: "active_users",
      label: "近 7 天活跃用户",
      value: imageStats.value.active_users,
      desc: "按最近 7 天内发起图片任务或提示词反推计算",
      color: "#13c2c2",
    },
    {
      key: "total_users",
      label: "总用户数",
      value: imageStats.value.total_users,
      desc: "当前系统内非超级管理员用户",
      color: "#fa8c16",
    },
  ];
});

const videoOverviewStats = computed<OverviewCard[]>(() => {
  if (!videoStats.value) return [];
  return [
    {
      key: "total_tasks",
      label: "累计视频任务数",
      value: videoStats.value.total_tasks,
      desc: "全量用户已提交的视频任务总数",
      color: "#1890ff",
    },
    {
      key: "total_credit_cost",
      label: "累计视频积分消耗",
      value: videoStats.value.total_credit_cost,
      desc: "视频任务实际消耗的积分总量",
      color: "#722ed1",
    },
    {
      key: "total_users",
      label: "累计视频用户数",
      value: videoStats.value.total_users,
      desc: "至少提交过一次视频任务的用户数",
      color: "#fa8c16",
    },
    {
      key: "active_users",
      label: "近 7 天视频活跃用户",
      value: videoStats.value.active_users,
      desc: "最近 7 天内提交过视频任务的用户数",
      color: "#13c2c2",
    },
    {
      key: "success_tasks",
      label: "累计成功视频任务",
      value: videoStats.value.success_tasks,
      desc: "状态为成功的视频任务总数",
      color: "#52c41a",
    },
    {
      key: "failed_tasks",
      label: "累计失败视频任务",
      value: videoStats.value.failed_tasks,
      desc: "状态为失败的视频任务总数",
      color: "#ff4d4f",
    },
  ];
});

async function loadImageStats() {
  imageLoading.value = true;
  try {
    imageStats.value = await getStats();
  } catch (err: any) {
    if (isSessionExpiredError(err)) return;
    message.error("获取图片固定概览失败");
  } finally {
    imageLoading.value = false;
  }
}

async function loadVideoStatsData() {
  videoLoading.value = true;
  try {
    videoStats.value = await getVideoStats();
  } catch (err: any) {
    if (isSessionExpiredError(err)) return;
    message.error("获取视频固定概览失败");
  } finally {
    videoLoading.value = false;
  }
}

onMounted(() => {
  void Promise.all([loadImageStats(), loadVideoStatsData()]);
});

function goImageDashboard() {
  router.push("/admin/image-dashboard");
}

function goVideoDashboard() {
  router.push("/admin/video-dashboard");
}
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <BarChartOutlined />
        </div>
        <div>
          <div class="warm-page-title">数据总览</div>
          <div class="warm-page-desc">统一查看图片与视频的固定概览统计，不受页面筛选条件影响。</div>
        </div>
      </div>
    </div>

    <section class="dashboard-section">
      <div class="section-title-row">
        <div class="section-title-wrap">
          <h3 class="section-title">
            <PictureOutlined />
            <span>图片固定概览</span>
          </h3>
          <span class="section-tip">这一组为图片累计口径统计。</span>
        </div>
        <a-button class="analytics-action-btn analytics-action-btn-secondary detail-entry-btn" @click="goImageDashboard">
          查看详细数据
        </a-button>
      </div>
      <a-spin :spinning="imageLoading">
        <div class="overview-grid">
          <div
            v-for="(item, index) in imageOverviewStats"
            :key="item.key"
            class="overview-card warm-card motion-card-lift motion-fade-up"
            :style="{ '--motion-delay': `${120 + Math.min(index, 5) * 40}ms` }"
          >
            <div class="overview-card-head">
              <span class="overview-card-label">{{ item.label }}</span>
              <span class="overview-card-dot" :style="{ background: item.color }" />
            </div>
            <div class="overview-card-value" :style="{ color: item.color }">{{ item.value }}</div>
            <div class="overview-card-desc">{{ item.desc }}</div>
          </div>
        </div>
      </a-spin>
    </section>

    <section class="dashboard-section">
      <div class="section-title-row">
        <div class="section-title-wrap">
          <h3 class="section-title">
            <VideoCameraOutlined />
            <span>视频固定概览</span>
          </h3>
          <span class="section-tip">这一组为视频累计口径统计。</span>
        </div>
        <a-button class="analytics-action-btn analytics-action-btn-secondary detail-entry-btn" @click="goVideoDashboard">
          查看详细数据
        </a-button>
      </div>
      <a-spin :spinning="videoLoading">
        <div class="overview-grid">
          <div
            v-for="(item, index) in videoOverviewStats"
            :key="item.key"
            class="overview-card warm-card motion-card-lift motion-fade-up"
            :style="{ '--motion-delay': `${160 + Math.min(index, 5) * 40}ms` }"
          >
            <div class="overview-card-head">
              <span class="overview-card-label">{{ item.label }}</span>
              <span class="overview-card-dot" :style="{ background: item.color }" />
            </div>
            <div class="overview-card-value" :style="{ color: item.color }">{{ item.value }}</div>
            <div class="overview-card-desc">{{ item.desc }}</div>
          </div>
        </div>
      </a-spin>
    </section>
  </div>
</template>

<style scoped lang="scss">
.dashboard-section + .dashboard-section {
  margin-top: 18px;
}

.dashboard-section {
  padding-top: 2px;
}

.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.section-title-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: #5d4526;
  font-size: 18px;
  font-weight: 700;
}

.section-tip {
  color: #9a805b;
  font-size: 12px;
  line-height: 1.5;
}

.detail-entry-btn {
  flex-shrink: 0;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}

.overview-card {
  min-height: 116px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  justify-content: space-between;
}

.overview-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.overview-card-label {
  color: #8c7458;
  font-size: 13px;
  font-weight: 700;
}

.overview-card-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  box-shadow: 0 0 0 4px rgba(255, 193, 90, 0.14);
}

.overview-card-value {
  font-size: 30px;
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.overview-card-desc {
  color: #9a805b;
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 768px) {
  .section-title-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .section-title-wrap {
    align-items: flex-start;
    flex-direction: column;
    gap: 6px;
  }

  .detail-entry-btn {
    width: 100%;
  }
}
</style>
