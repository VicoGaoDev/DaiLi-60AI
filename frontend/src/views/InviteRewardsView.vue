<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import {
  CopyOutlined,
  DownloadOutlined,
  GiftOutlined,
  QrcodeOutlined,
  ShareAltOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  UserAddOutlined,
  CheckCircleOutlined,
  RiseOutlined,
} from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import QRCode from "qrcode";
import dayjs from "dayjs";

import {
  getInviteRewardLogs,
  getInviteRewardOverview,
  getInviteRewardReferrals,
} from "@/api/inviteRewards";
import { copyText as copyToClipboard } from "@/lib/clipboard";
import type {
  InviteRewardLogItem,
  InviteRewardOverviewResponse,
  InviteRewardReferralItem,
} from "@/types";

const INVITE_QR_SIZE = 192;
const INVITE_QR_BRAND_ICON_URL = "/香蕉.svg";
const INVITE_TABLE_PAGE_SIZE = 10;

const loading = ref(false);
const qrCodeDataUrl = ref("");
const overview = ref<InviteRewardOverviewResponse>({
  invite_code: "",
  invite_link: "",
  reward_rate: 15,
  max_reward_count: 3,
  summary: {
    total_referrals: 0,
    today_referrals: 0,
    rewarded_invitees: 0,
    reward_grant_count: 0,
    total_reward_credits: 0,
    today_reward_credits: 0,
  },
});
const referrals = ref<InviteRewardReferralItem[]>([]);
const rewardLogs = ref<InviteRewardLogItem[]>([]);
const referralPage = ref(1);
const referralTotal = ref(0);
const rewardLogPage = ref(1);
const rewardLogTotal = ref(0);

const referralColumns = [
  { title: "用户", key: "user", width: "26%" },
  { title: "已奖励次数", dataIndex: "reward_count", width: 120 },
  { title: "累计奖励积分", dataIndex: "total_reward_credits", width: 140 },
  { title: "最近奖励时间", dataIndex: "last_reward_at", width: 170 },
  { title: "注册时间", dataIndex: "registered_at", width: 170 },
];

const rewardLogColumns = [
  { title: "用户", key: "user", width: "24%" },
  { title: "来源", dataIndex: "source_type", width: 100 },
  { title: "到账积分", dataIndex: "source_credits", width: 100 },
  { title: "奖励积分", dataIndex: "reward_credits", width: 100 },
  { title: "次数", dataIndex: "reward_index", width: 80 },
  { title: "来源编号", dataIndex: "source_id", ellipsis: true },
  { title: "奖励时间", dataIndex: "created_at", width: 170 },
];

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function sourceTypeLabel(value: string) {
  if (value === "payment") return "在线购买";
  if (value === "redeem") return "兑换码";
  return value || "-";
}

async function copyText(text: string, successText: string) {
  if (!text) return;
  try {
    await copyToClipboard(text);
    message.success(successText);
  } catch {
    message.error("复制失败，请重试");
  }
}

function loadImage(src: string) {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`Failed to load image: ${src}`));
    image.src = src;
  });
}

function fillRoundedRect(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
) {
  const maxRadius = Math.min(radius, width / 2, height / 2);
  context.beginPath();
  context.moveTo(x + maxRadius, y);
  context.arcTo(x + width, y, x + width, y + height, maxRadius);
  context.arcTo(x + width, y + height, x, y + height, maxRadius);
  context.arcTo(x, y + height, x, y, maxRadius);
  context.arcTo(x, y, x + width, y, maxRadius);
  context.closePath();
  context.fill();
}

async function drawQrBrand(context: CanvasRenderingContext2D) {
  const badgeSize = 54;
  const badgeX = (INVITE_QR_SIZE - badgeSize) / 2;
  const badgeY = (INVITE_QR_SIZE - badgeSize) / 2;

  context.save();
  context.fillStyle = "#ffffff";
  context.shadowColor = "rgba(15, 23, 42, 0.12)";
  context.shadowBlur = 12;
  context.shadowOffsetY = 3;
  fillRoundedRect(context, badgeX, badgeY, badgeSize, badgeSize, 16);
  context.restore();

  try {
    const icon = await loadImage(INVITE_QR_BRAND_ICON_URL);
    const iconSize = 34;
    const iconX = (INVITE_QR_SIZE - iconSize) / 2;
    const iconY = (INVITE_QR_SIZE - iconSize) / 2;
    context.drawImage(icon, iconX, iconY, iconSize, iconSize);
  } catch {
    context.save();
    context.fillStyle = "#7c8f12";
    context.font = "700 15px Inter, PingFang SC, Microsoft YaHei, sans-serif";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText("80AI", INVITE_QR_SIZE / 2, INVITE_QR_SIZE / 2 + 1);
    context.restore();
  }
}

async function refreshQrCode(link: string) {
  qrCodeDataUrl.value = "";
  if (!link) return;
  const canvas = document.createElement("canvas");
  canvas.width = INVITE_QR_SIZE;
  canvas.height = INVITE_QR_SIZE;
  await QRCode.toCanvas(canvas, link, {
    width: INVITE_QR_SIZE,
    margin: 1,
    errorCorrectionLevel: "H",
  });
  const context = canvas.getContext("2d");
  if (!context) throw new Error("二维码画布初始化失败");
  await drawQrBrand(context);
  qrCodeDataUrl.value = canvas.toDataURL("image/png");
}

async function copyQrCode() {
  if (!qrCodeDataUrl.value) {
    message.warning("二维码还未生成，请稍后重试");
    return;
  }

  if (typeof ClipboardItem === "undefined" || !navigator.clipboard?.write) {
    await copyText(overview.value.invite_link, "当前浏览器不支持复制图片，已复制邀请链接");
    return;
  }

  try {
    const response = await fetch(qrCodeDataUrl.value);
    const blob = await response.blob();
    await navigator.clipboard.write([
      new ClipboardItem({
        [blob.type || "image/png"]: blob,
      }),
    ]);
    message.success("邀请二维码已复制");
  } catch {
    await copyText(overview.value.invite_link, "复制二维码失败，已复制邀请链接");
  }
}

function downloadQrCode() {
  if (!qrCodeDataUrl.value) {
    message.warning("二维码还未生成，请稍后重试");
    return;
  }
  const link = document.createElement("a");
  link.href = qrCodeDataUrl.value;
  link.download = `invite-${overview.value.invite_code || "qrcode"}.png`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

async function loadOverview() {
  overview.value = await getInviteRewardOverview();
}

async function loadReferrals(page = referralPage.value) {
  const response = await getInviteRewardReferrals(page, INVITE_TABLE_PAGE_SIZE);
  referrals.value = response.items;
  referralTotal.value = response.total;
  referralPage.value = response.page || page;
}

async function loadRewardLogs(page = rewardLogPage.value) {
  const response = await getInviteRewardLogs(page, INVITE_TABLE_PAGE_SIZE);
  rewardLogs.value = response.items;
  rewardLogTotal.value = response.total;
  rewardLogPage.value = response.page || page;
}

async function loadData() {
  loading.value = true;
  try {
    await Promise.all([
      loadOverview(),
      loadReferrals(1),
      loadRewardLogs(1),
    ]);
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取邀请奖励数据失败");
  } finally {
    loading.value = false;
  }
}

async function handleReferralTableChange(pagination: { current?: number }) {
  const nextPage = Math.max(1, Number(pagination.current || 1));
  if (nextPage === referralPage.value) return;
  loading.value = true;
  try {
    await loadReferrals(nextPage);
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取推荐好友失败");
  } finally {
    loading.value = false;
  }
}

async function handleRewardLogTableChange(pagination: { current?: number }) {
  const nextPage = Math.max(1, Number(pagination.current || 1));
  if (nextPage === rewardLogPage.value) return;
  loading.value = true;
  try {
    await loadRewardLogs(nextPage);
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取奖励记录失败");
  } finally {
    loading.value = false;
  }
}

watch(
  () => overview.value.invite_link,
  (link) => {
    void refreshQrCode(link);
  },
);

onMounted(() => {
  void loadData();
});
</script>

<template>
  <div class="warm-page motion-page-enter invite-page">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <ShareAltOutlined />
        </div>
        <div>
          <div class="warm-page-title">邀请奖励计划</div>
          <div class="warm-page-desc">分享专属邀请链接，推荐用户在线购买积分后获得积分奖励。</div>
        </div>
      </div>
    </div>

    <a-spin :spinning="loading">
      <div class="invite-page-body">
        <div class="warm-card invite-main-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
          <div class="invite-rule-banner">
            被推荐用户前 {{ overview.max_reward_count }} 次在线购买积分时，邀请人每次获得
            <strong class="invite-rule-rate">{{ overview.reward_rate }}%</strong>
            积分奖励，立即到账。
          </div>

          <div class="invite-main-layout">
            <div class="invite-main-left">
              <div class="invite-guide">
                <div class="invite-guide-title">如何使用</div>
                <ol class="invite-guide-steps">
                  <li>复制<strong>邀请链接</strong>或下载<strong>邀请二维码</strong>发给好友；也可直接分享<strong>邀请码</strong>，好友注册时填写。</li>
                  <li>好友通过链接或扫码打开网站，在注册页完成注册。</li>
                  <li>注册成功后，好友会自动与你建立邀请关联；之后其在线购买积分，你可按规则获得奖励。</li>
                </ol>
                <p class="invite-guide-note">邀请码长期有效，但账号被禁用时邀请关系将无法继续生效。</p>
              </div>

              <div class="invite-summary-grid">
                <div class="invite-summary-item invite-summary-item--col-1">
                  <div class="invite-summary-icon"><TeamOutlined /></div>
                  <span class="invite-summary-label">推荐好友</span>
                  <strong class="invite-summary-value">{{ overview.summary.total_referrals }}</strong>
                </div>
                <div class="invite-summary-item invite-summary-item--col-2">
                  <div class="invite-summary-icon"><CheckCircleOutlined /></div>
                  <span class="invite-summary-label">已奖励用户</span>
                  <strong class="invite-summary-value">{{ overview.summary.rewarded_invitees }}</strong>
                </div>
                <div class="invite-summary-item invite-summary-item--col-3">
                  <div class="invite-summary-icon"><UserAddOutlined /></div>
                  <span class="invite-summary-label">今日推荐好友</span>
                  <strong class="invite-summary-value">{{ overview.summary.today_referrals }}</strong>
                </div>
                <div class="invite-summary-item invite-summary-item--col-1">
                  <div class="invite-summary-icon"><GiftOutlined /></div>
                  <span class="invite-summary-label">奖励次数</span>
                  <strong class="invite-summary-value">{{ overview.summary.reward_grant_count }}</strong>
                </div>
                <div class="invite-summary-item invite-summary-item--col-2">
                  <div class="invite-summary-icon"><ThunderboltOutlined /></div>
                  <span class="invite-summary-label">累计奖励积分</span>
                  <strong class="invite-summary-value">{{ overview.summary.total_reward_credits }}</strong>
                </div>
                <div class="invite-summary-item invite-summary-item--col-3">
                  <div class="invite-summary-icon"><RiseOutlined /></div>
                  <span class="invite-summary-label">今日奖励积分</span>
                  <strong class="invite-summary-value">{{ overview.summary.today_reward_credits }}</strong>
                </div>
              </div>
            </div>

            <div class="invite-main-right">
              <div class="invite-field">
                <span class="invite-field-label">邀请码</span>
                <div class="invite-field-value">
                  <code>{{ overview.invite_code || "-" }}</code>
                  <a-button type="link" class="invite-copy-btn" @click="copyText(overview.invite_code, '邀请码已复制')">
                    <template #icon><CopyOutlined /></template>
                    复制
                  </a-button>
                </div>
              </div>

              <div class="invite-field">
                <span class="invite-field-label">邀请链接</span>
                <div class="invite-field-value invite-link-value">
                  <span>{{ overview.invite_link || "-" }}</span>
                  <a-button type="link" class="invite-copy-btn" @click="copyText(overview.invite_link, '邀请链接已复制')">
                    <template #icon><CopyOutlined /></template>
                    复制
                  </a-button>
                </div>
              </div>

              <div class="invite-qr-block">
                <div class="invite-qr-head">
                  <QrcodeOutlined />
                  <span>邀请二维码</span>
                </div>
                <div class="invite-qr-wrap invite-qr-wrap--clickable" @click="copyQrCode">
                  <img v-if="qrCodeDataUrl" :src="qrCodeDataUrl" alt="邀请二维码">
                  <div v-else class="invite-qr-placeholder">生成中...</div>
                </div>
                <div class="invite-qr-actions">
                  <a-button
                    type="link"
                    class="invite-download-btn"
                    :disabled="!qrCodeDataUrl"
                    @click="copyQrCode"
                  >
                    <template #icon><CopyOutlined /></template>
                    复制二维码
                  </a-button>
                  <a-button
                    type="link"
                    class="invite-download-btn"
                    :disabled="!qrCodeDataUrl"
                    @click="downloadQrCode"
                  >
                    <template #icon><DownloadOutlined /></template>
                    下载二维码
                  </a-button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="warm-card invite-data-card motion-fade-up motion-card-lift" style="--motion-delay: 200ms">
          <div class="invite-data-section">
            <div class="section-title">推荐好友</div>
            <a-table
              :columns="referralColumns"
              :data-source="referrals"
              row-key="user_id"
              :pagination="{ current: referralPage, pageSize: INVITE_TABLE_PAGE_SIZE, total: referralTotal, showSizeChanger: false }"
              :scroll="{ x: 860 }"
              @change="handleReferralTableChange"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'user'">
                  <div class="invite-user-cell">
                    <strong>{{ record.username }}</strong>
                    <span>{{ record.email_masked }}</span>
                  </div>
                </template>
                <template v-else-if="column.dataIndex === 'last_reward_at'">
                  {{ formatTime(record.last_reward_at) }}
                </template>
                <template v-else-if="column.dataIndex === 'registered_at'">
                  {{ formatTime(record.registered_at) }}
                </template>
              </template>
            </a-table>
          </div>

          <div class="invite-data-section">
            <div class="section-title">奖励记录</div>
            <a-table
              :columns="rewardLogColumns"
              :data-source="rewardLogs"
              row-key="id"
              :pagination="{ current: rewardLogPage, pageSize: INVITE_TABLE_PAGE_SIZE, total: rewardLogTotal, showSizeChanger: false }"
              :scroll="{ x: 980 }"
              @change="handleRewardLogTableChange"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'user'">
                  <div class="invite-user-cell">
                    <strong>{{ record.invitee_username }}</strong>
                    <span>{{ record.invitee_email_masked }}</span>
                  </div>
                </template>
                <template v-else-if="column.dataIndex === 'source_type'">
                  <a-tag class="warm-tag">{{ sourceTypeLabel(record.source_type) }}</a-tag>
                </template>
                <template v-else-if="column.dataIndex === 'reward_index'">
                  第 {{ record.reward_index }} 次
                </template>
                <template v-else-if="column.dataIndex === 'created_at'">
                  {{ formatTime(record.created_at) }}
                </template>
              </template>
            </a-table>
          </div>
        </div>
      </div>
    </a-spin>
  </div>
</template>

<style scoped lang="scss">
.invite-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding-inline: 14px;
}

.invite-page-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.invite-main-card,
.invite-data-card {
  padding: 22px 24px 24px;
}

.section-title {
  margin-bottom: 14px;
  color: var(--theme-title);
  font-size: 16px;
  font-weight: 800;
}

.invite-rule-banner {
  padding: 10px 14px;
  border-radius: 14px;
  background: var(--theme-pill-bg-strong);
  color: var(--theme-accent-text);
  font-size: 14px;
  font-weight: 700;
  line-height: 1.6;
}

.invite-rule-rate {
  margin-inline: 2px;
  color: var(--theme-accent-text);
  font-size: 24px;
  font-weight: 900;
  line-height: 1;
}

.invite-main-layout {
  display: grid;
  grid-template-columns: minmax(0, 7fr) minmax(260px, 3fr);
  gap: 24px;
  align-items: start;
  margin-top: 18px;
}

.invite-main-left {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
}

.invite-guide {
  padding: 16px 18px;
  border-radius: 16px;
  background: var(--theme-panel-bg-muted);
  border: 1px solid var(--theme-panel-border);
}

.invite-guide-title {
  margin-bottom: 10px;
  color: var(--theme-title);
  font-size: 15px;
  font-weight: 800;
}

.invite-guide-steps {
  margin: 0;
  padding-left: 20px;
  color: var(--theme-text);
  font-size: 13px;
  line-height: 1.75;

  li + li {
    margin-top: 6px;
  }

  strong {
    color: var(--theme-accent-text);
    font-weight: 700;
  }
}

.invite-guide-note {
  margin: 12px 0 0;
  color: var(--theme-text-secondary);
  font-size: 12px;
  line-height: 1.6;

  strong {
    color: var(--theme-title);
  }
}

.invite-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.invite-summary-item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  min-height: 64px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid transparent;
}

.invite-summary-item--col-1 {
  background: #eef4ff;
  border-color: rgba(74, 127, 212, 0.14);

  .invite-summary-icon {
    background: rgba(255, 255, 255, 0.82);
    color: #4a7fd4;
  }

  .invite-summary-label {
    color: #5b7db8;
  }

  .invite-summary-value {
    color: #2f5ea8;
  }
}

.invite-summary-item--col-2 {
  background: #edf8f0;
  border-color: rgba(61, 154, 101, 0.14);

  .invite-summary-icon {
    background: rgba(255, 255, 255, 0.82);
    color: #3d9a65;
  }

  .invite-summary-label {
    color: #4f8f68;
  }

  .invite-summary-value {
    color: #2f7a4f;
  }
}

.invite-summary-item--col-3 {
  background: #fff3e8;
  border-color: rgba(200, 132, 42, 0.14);

  .invite-summary-icon {
    background: rgba(255, 255, 255, 0.82);
    color: #c8842a;
  }

  .invite-summary-label {
    color: #a9743f;
  }

  .invite-summary-value {
    color: #8f5d1f;
  }
}

.invite-summary-icon {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  color: var(--theme-title);

  :deep(.anticon) {
    font-size: 20px;
  }
}

.invite-summary-label {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
}

.invite-summary-value {
  flex-shrink: 0;
  margin-left: auto;
  font-size: 30px;
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.invite-main-right {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 14px;
  padding: 18px;
  border-radius: 16px;
  background: var(--theme-surface-strong);
  border: 1px solid var(--theme-panel-border);
}

.invite-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.invite-field-label {
  color: var(--theme-text-secondary);
  font-size: 12px;
  font-weight: 700;
  text-align: left;
}

.invite-field-value {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 8px 12px;
  border-radius: 12px;
  background: var(--theme-panel-bg);
  border: 1px solid var(--theme-panel-border);

  code {
    flex: 1;
    min-width: 0;
    color: var(--theme-accent-text);
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-align: left;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  }
}

.invite-link-value span {
  flex: 1;
  min-width: 0;
  color: var(--theme-text);
  font-size: 15px;
  line-height: 1.5;
  text-align: left;
  word-break: break-all;
}

.invite-copy-btn {
  flex-shrink: 0;
  padding-inline: 4px;
  color: var(--theme-accent-text);
  font-weight: 700;
}

.invite-qr-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
  padding: 18px 16px 14px;
  border-radius: 14px;
  background: var(--theme-panel-bg);
  border: 1px solid var(--theme-panel-border);
}

.invite-qr-head {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  color: var(--theme-title);
  font-size: 13px;
  font-weight: 700;

  :deep(.anticon) {
    color: var(--theme-text-secondary);
  }
}

.invite-qr-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 200px;
  height: 200px;
  border-radius: 14px;
  background: #fff;
  border: 1px solid var(--theme-panel-border);

  img {
    width: 192px;
    height: 192px;
  }
}

.invite-qr-wrap--clickable {
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  }
}

.invite-qr-placeholder {
  color: var(--theme-text-secondary);
  font-size: 13px;
}

.invite-qr-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}

.invite-download-btn {
  padding-inline: 0;
  color: var(--theme-accent-text);
  font-weight: 700;
}

.invite-data-section + .invite-data-section {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid var(--theme-panel-border);
}

.invite-data-card {
  overflow: visible;

  :deep(.ant-table-wrapper) {
    overflow: hidden;
    border-radius: 16px;
  }
}

.invite-user-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;

  strong {
    color: var(--theme-title);
  }

  span {
    color: var(--theme-text-secondary);
    font-size: 12px;
  }
}

@media (max-width: 900px) {
  .invite-main-layout {
    grid-template-columns: 1fr;
  }

  .invite-main-right {
    order: -1;
  }

  .invite-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .invite-summary-value {
    font-size: 24px;
  }
}

html[data-theme="midnight"] {
  .invite-summary-item--col-1 {
    background: color-mix(in srgb, #4a7fd4 18%, var(--theme-panel-bg));
  }

  .invite-summary-item--col-2 {
    background: color-mix(in srgb, #3d9a65 18%, var(--theme-panel-bg));
  }

  .invite-summary-item--col-3 {
    background: color-mix(in srgb, #c8842a 18%, var(--theme-panel-bg));
  }

  .invite-summary-item--col-1 .invite-summary-label,
  .invite-summary-item--col-1 .invite-summary-value {
    color: #9db8e8;
  }

  .invite-summary-item--col-2 .invite-summary-label,
  .invite-summary-item--col-2 .invite-summary-value {
    color: #8fd0a8;
  }

  .invite-summary-item--col-3 .invite-summary-label,
  .invite-summary-item--col-3 .invite-summary-value {
    color: #e0b57a;
  }
}
</style>
