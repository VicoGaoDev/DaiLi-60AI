<script setup lang="ts">
import { ref, onMounted, reactive, computed, watch } from "vue";
import { message, Modal } from "ant-design-vue";
import { CopyOutlined, PlusOutlined, TeamOutlined, WalletOutlined, SearchOutlined, UndoOutlined } from "@ant-design/icons-vue";
import {
  listUsers,
  createUser,
  updateUserStatus,
  updateUserRole,
  updateUserWhitelist,
  resetUserPassword,
  allocateCredits,
  resetUserCredits,
  getUserPromoDashboard,
} from "@/api/admin";
import UserCreditLogsDialog from "@/components/admin/UserCreditLogsDialog.vue";
import AdminUserInfoDialog from "@/components/admin/AdminUserInfoDialog.vue";
import { getAvatarImageSrc } from "@/api/images";
import { useAuthStore } from "@/stores/auth";
import type { AdminUser, AdminUserPromoDashboard } from "@/types";

const auth = useAuthStore();
const isSuperAdmin = computed(() => auth.isSuperAdmin);

const users = ref<AdminUser[]>([]);
const totalUsers = ref(0);
const firstAdminId = ref<string | null>(null);
const whitelistedTotal = ref(0);
const loading = ref(false);
const modalOpen = ref(false);
const creating = ref(false);
const form = reactive({ username: "", password: "", role: "user" });
const filters = reactive({
  username: "",
  status: undefined as "active" | "disabled" | undefined,
  whitelist: undefined as boolean | undefined,
  sort: "created_at_desc" as "created_at_desc" | "credits_desc" | "consumed_credits_desc",
});

const resetPwdOpen = ref(false);
const resetPwdLoading = ref(false);
const resetTarget = ref<AdminUser | null>(null);
const resetForm = reactive({ newPassword: "" });

const creditsOpen = ref(false);
const creditsLoading = ref(false);
const creditsTarget = ref<AdminUser | null>(null);
const creditsForm = reactive({ amount: 0, description: "" });
const whitelistOpen = ref(false);
const whitelistKeyword = ref("");
const whitelistLoadingId = ref<string | null>(null);
const whitelistUsers = ref<AdminUser[]>([]);
const whitelistLoading = ref(false);
const whitelistPage = ref(1);
const whitelistPageSize = 20;
const whitelistTotal = ref(0);
const promoDashboardOpen = ref(false);
const promoDashboardLoading = ref(false);
const promoDashboard = ref<AdminUserPromoDashboard | null>(null);
const creditLogsOpen = ref(false);
const creditLogsTarget = ref<AdminUser | null>(null);
const userInfoOpen = ref(false);
const userInfoTarget = ref<AdminUser | null>(null);
const currentPage = ref(1);
const pageSize = 30;
let filterDebounceTimer: number | null = null;
let whitelistDebounceTimer: number | null = null;

const columns = [
  { title: "ID", dataIndex: "id", width: 58 },
  { title: "用户", dataIndex: "username", width: 212 },
  { title: "角色", dataIndex: "role", width: 88 },
  { title: "剩余积分", dataIndex: "credits", width: 92 },
  { title: "已消耗积分", dataIndex: "consumed_credits", width: 108 },
  { title: "状态", dataIndex: "status", width: 82 },
  { title: "创建时间", dataIndex: "created_at", width: 154 },
  { title: "操作", key: "action", width: 400 },
];

const currentRangeSummary = computed(() => {
  const total = totalUsers.value;
  if (!total) return "当前第 0-0 条 / 共 0 条";
  const start = (currentPage.value - 1) * pageSize + 1;
  const end = Math.min(currentPage.value * pageSize, total);
  return `当前第 ${start}-${end} 条 / 共 ${total} 条`;
});

const filteredWhitelistUsers = computed(() => {
  return whitelistUsers.value;
});

const whitelistedCount = computed(() => whitelistedTotal.value);

async function load(page = currentPage.value) {
  loading.value = true;
  try {
    const response = await listUsers(page, pageSize, {
      keyword: filters.username,
      status: filters.status,
      whitelist: filters.whitelist,
      sort: filters.sort,
    });
    users.value = response.items;
    totalUsers.value = response.total;
    currentPage.value = response.page || page;
    firstAdminId.value = response.first_admin_id || null;
    whitelistedTotal.value = response.whitelisted_total || 0;
  }
  catch { message.error("获取用户列表失败"); }
  finally { loading.value = false; }
}
onMounted(load);

watch(() => [filters.username, filters.status, filters.whitelist, filters.sort], () => {
  currentPage.value = 1;
  if (filterDebounceTimer) window.clearTimeout(filterDebounceTimer);
  filterDebounceTimer = window.setTimeout(() => {
    void load(1);
  }, 250);
});

watch(whitelistOpen, (open) => {
  if (!open) return;
  whitelistPage.value = 1;
  void loadWhitelistUsers(1);
});

watch(whitelistKeyword, () => {
  if (!whitelistOpen.value) return;
  whitelistPage.value = 1;
  if (whitelistDebounceTimer) window.clearTimeout(whitelistDebounceTimer);
  whitelistDebounceTimer = window.setTimeout(() => {
    void loadWhitelistUsers(1);
  }, 250);
});

async function handleCreate() {
  if (!form.username || !form.password) { message.warning("请填写完整"); return; }
  creating.value = true;
  try {
    await createUser({ username: form.username, password: form.password, role: form.role });
    message.success("创建成功");
    modalOpen.value = false;
    form.username = ""; form.password = ""; form.role = "user";
    await load(1);
  } catch (err: any) { message.error(err.response?.data?.detail || "创建失败"); }
  finally { creating.value = false; }
}

function toggleStatus(u: AdminUser) {
  const next = u.status === "active" ? "disabled" : "active";
  const label = next === "disabled" ? "禁用" : "启用";
  Modal.confirm({
    title: `确认${label}用户 "${u.username}" ？`,
    centered: true,
    async onOk() {
      await updateUserStatus(u.id, next);
      message.success(`${label}成功`);
      await Promise.all([
        load(),
        whitelistOpen.value ? loadWhitelistUsers() : Promise.resolve(),
      ]);
    },
  });
}

function toggleRole(u: AdminUser) {
  const next = u.role === "admin" ? "user" : "admin";
  const label = next === "admin" ? "设为管理员" : "取消管理员";
  Modal.confirm({
    title: `确认${label} "${u.username}" ？`,
    centered: true,
    async onOk() {
      await updateUserRole(u.id, next);
      message.success(`${label}成功`);
      await Promise.all([
        load(),
        whitelistOpen.value ? loadWhitelistUsers() : Promise.resolve(),
      ]);
    },
  });
}

function openResetPwd(u: AdminUser) {
  resetTarget.value = u;
  resetForm.newPassword = "";
  resetPwdOpen.value = true;
}

async function handleResetPwd() {
  if (!resetTarget.value) return;
  if (!resetForm.newPassword || resetForm.newPassword.length < 6) {
    message.warning("新密码至少6位");
    return;
  }
  resetPwdLoading.value = true;
  try {
    await resetUserPassword(resetTarget.value.id, resetForm.newPassword);
    message.success(`已重置 "${resetTarget.value.username}" 的密码`);
    resetPwdOpen.value = false;
  } catch (err: any) {
    message.error(err.response?.data?.detail || "重置失败");
  } finally {
    resetPwdLoading.value = false;
  }
}

function openCredits(u: AdminUser) {
  creditsTarget.value = u;
  creditsForm.amount = 0;
  creditsForm.description = "";
  creditsOpen.value = true;
}

function openCreditLogs(u: AdminUser) {
  creditLogsTarget.value = u;
  creditLogsOpen.value = true;
}

function openUserInfo(u: AdminUser) {
  userInfoTarget.value = u;
  userInfoOpen.value = true;
}

async function handleAllocateCredits() {
  if (!creditsTarget.value || creditsForm.amount === 0) {
    message.warning("请输入有效的积分数量");
    return;
  }
  if (!creditsForm.description.trim()) {
    message.warning("请填写备注说明");
    return;
  }
  creditsLoading.value = true;
  try {
    await allocateCredits(creditsTarget.value.id, creditsForm.amount, creditsForm.description.trim());
    message.success("积分分配成功");
    creditsOpen.value = false;
    await Promise.all([
      load(),
      whitelistOpen.value ? loadWhitelistUsers() : Promise.resolve(),
    ]);
  } catch (err: any) {
    message.error(err.response?.data?.detail || "分配失败");
  } finally {
    creditsLoading.value = false;
  }
}

function handleResetCredits(user: AdminUser) {
  Modal.confirm({
    title: `确认将 "${user.username}" 的积分清零？`,
    content: `当前剩余积分为 ${user.credits}，清零后会写入积分日志。`,
    okText: "确认清零",
    okButtonProps: { danger: true },
    centered: true,
    async onOk() {
      try {
        await resetUserCredits(user.id);
        message.success("积分已清零");
        await Promise.all([
          load(),
          whitelistOpen.value ? loadWhitelistUsers() : Promise.resolve(),
        ]);
      } catch (err: any) {
        message.error(err.response?.data?.detail || "积分清零失败");
      }
    },
  });
}

async function handleToggleWhitelist(user: AdminUser) {
  whitelistLoadingId.value = user.id;
  const next = !user.is_whitelisted;
  try {
    await updateUserWhitelist(user.id, next);
    message.success(next ? "已加入白名单" : "已移出白名单");
    await Promise.all([
      load(),
      whitelistOpen.value ? loadWhitelistUsers() : Promise.resolve(),
    ]);
  } catch (err: any) {
    message.error(err.response?.data?.detail || "白名单更新失败");
  } finally {
    whitelistLoadingId.value = null;
  }
}

async function openPromoDashboard(user: AdminUser) {
  promoDashboardOpen.value = true;
  promoDashboardLoading.value = true;
  promoDashboard.value = null;
  try {
    promoDashboard.value = await getUserPromoDashboard(user.id);
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取推广数据失败");
    promoDashboardOpen.value = false;
  } finally {
    promoDashboardLoading.value = false;
  }
}

function isFirstAdmin(u: AdminUser) {
  return !!firstAdminId.value && firstAdminId.value === u.id;
}

function resetFilters() {
  filters.username = "";
  filters.status = undefined;
  filters.whitelist = undefined;
  filters.sort = "created_at_desc";
  currentPage.value = 1;
  void load(1);
}

function handlePageChange(page: number) {
  void load(page);
}

async function loadWhitelistUsers(page = whitelistPage.value) {
  whitelistLoading.value = true;
  try {
    const response = await listUsers(page, whitelistPageSize, {
      keyword: whitelistKeyword.value,
      sort: "created_at_desc",
    });
    whitelistUsers.value = response.items;
    whitelistTotal.value = response.total;
    whitelistPage.value = response.page || page;
    whitelistedTotal.value = response.whitelisted_total || 0;
  } catch {
    message.error("获取白名单用户列表失败");
  } finally {
    whitelistLoading.value = false;
  }
}

function handleWhitelistPageChange(page: number) {
  void loadWhitelistUsers(page);
}

function formatUserId(id?: string) {
  if (!id) return "-";
  if (id.length <= 8) return id;
  return `${id.slice(0, 4)}...${id.slice(-4)}`;
}

async function copyUserId(id: string) {
  try {
    await navigator.clipboard.writeText(id);
    message.success("内容已复制");
  } catch {
    message.error("复制失败，请重试");
  }
}

function fmtTime(t: string) { return t ? new Date(t).toLocaleString("zh-CN") : "-"; }

function promoActivityRowKey(record: {
  user_id: string;
  activity_type: string;
  occurred_at?: string | null;
  order_no?: string;
  redeem_key?: string;
}) {
  return `${record.user_id}-${record.activity_type}-${record.occurred_at || ""}-${record.order_no || record.redeem_key || ""}`;
}
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <TeamOutlined />
        </div>
        <div>
          <div class="warm-page-title">用户管理</div>
          <div class="warm-page-desc">管理员可创建普通用户、管理白名单、分配积分、禁用账号与积分清零，超级管理员可额外管理权限。</div>
        </div>
      </div>
      <div class="header-actions">
        <a-button class="filter-reset-btn" @click="whitelistOpen = true">
          白名单用户
        </a-button>
        <a-button type="primary" class="warm-primary-btn" @click="modalOpen = true">
          <template #icon><PlusOutlined /></template>
          新增用户
        </a-button>
      </div>
    </div>

    <div class="warm-card filter-bar motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
      <a-input
        v-model:value="filters.username"
        allow-clear
        placeholder="按用户名或邮箱筛选"
        class="filter-input warm-input"
      >
        <template #prefix><SearchOutlined /></template>
      </a-input>
      <a-select
        v-model:value="filters.status"
        allow-clear
        placeholder="用户状态"
        class="filter-select warm-select"
      >
        <a-select-option value="active">正常</a-select-option>
        <a-select-option value="disabled">禁用</a-select-option>
      </a-select>
      <a-select
        v-model:value="filters.whitelist"
        allow-clear
        placeholder="白名单筛选"
        class="filter-select warm-select"
      >
        <a-select-option :value="true">白名单用户</a-select-option>
        <a-select-option :value="false">非白名单用户</a-select-option>
      </a-select>
      <a-select
        v-model:value="filters.sort"
        class="filter-select warm-select"
      >
        <a-select-option value="created_at_desc">创建时间（默认）</a-select-option>
        <a-select-option value="credits_desc">剩余积分（从高到低）</a-select-option>
        <a-select-option value="consumed_credits_desc">消耗积分（从高到低）</a-select-option>
      </a-select>
      <a-button class="filter-reset-btn" @click="resetFilters">
        <template #icon><UndoOutlined /></template>
        重置
      </a-button>
      <div class="filter-result-count">{{ currentRangeSummary }}</div>
    </div>

    <div class="warm-card warm-table-card motion-fade-up motion-card-lift" style="--motion-delay: 200ms">
      <a-table
        :columns="columns"
        :data-source="users"
        :loading="loading"
        row-key="id"
        :pagination="false"
        :scroll="{ x: 1280 }"
        class="admin-mobile-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'id'">
            <div class="id-cell">
              <a-tooltip :title="record.id">
                <span class="id-text">{{ formatUserId(record.id) }}</span>
              </a-tooltip>
              <a-button type="text" size="small" class="id-copy-btn" @click="copyUserId(record.id)">
                <template #icon><CopyOutlined /></template>
              </a-button>
            </div>
          </template>
          <template v-if="column.dataIndex === 'username'">
            <div class="user-cell">
              <button type="button" class="table-avatar-btn" @click="openUserInfo(record)">
                <a-avatar :size="34" :src="getAvatarImageSrc(record.avatar_url) || undefined" class="table-avatar">
                  {{ record.username?.charAt(0)?.toUpperCase() }}
                </a-avatar>
              </button>
              <div class="user-cell-meta">
                <span class="user-cell-name">{{ record.username }}</span>
                <span v-if="record.email || record.phone" class="user-cell-sub">{{ record.email || record.phone }}</span>
              </div>
            </div>
          </template>
          <template v-else-if="column.dataIndex === 'role'">
            <a-tag class="warm-tag" :class="record.role === 'admin' ? 'warm-tag-role-admin' : 'warm-tag-role-user'">
              {{ record.role === "admin" ? "管理员" : "普通用户" }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'consumed_credits'">
            <span style="font-weight: 700; color: #cf1322">{{ record.consumed_credits ?? 0 }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'credits'">
            <span style="font-weight: 700; color: var(--theme-accent-text)">{{ record.credits }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <a-badge :status="record.status === 'active' ? 'success' : 'error'" />
            {{ record.status === "active" ? "正常" : "禁用" }}
          </template>
          <template v-else-if="column.dataIndex === 'created_at'">
            {{ fmtTime(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <div class="table-actions">
              <a-button type="link" size="small" class="user-action-btn user-action-btn-primary" @click="openCredits(record)">
                <template #icon><WalletOutlined /></template>
                分配积分
              </a-button>
              <a-button
                type="link"
                size="small"
                class="user-action-btn user-action-btn-secondary"
                @click="openCreditLogs(record)"
              >
                积分明细
              </a-button>
              <a-button
                v-if="record.is_whitelisted"
                type="link"
                size="small"
                class="user-action-btn user-action-btn-secondary"
                @click="openPromoDashboard(record)"
              >
                推广数据
              </a-button>
              <a-button
                type="link"
                size="small"
                class="user-action-btn user-action-btn-danger"
                :danger="true"
                :disabled="record.credits <= 0"
                @click="handleResetCredits(record)"
              >
                积分清零
              </a-button>
              <a-button
                type="link"
                size="small"
                class="user-action-btn"
                :class="record.status === 'active' ? 'user-action-btn-danger' : 'user-action-btn-secondary'"
                :danger="record.status === 'active'"
                :disabled="isFirstAdmin(record) && record.status === 'active'"
                @click="toggleStatus(record)"
              >
                {{ record.status === "active" ? "禁用" : "启用" }}
              </a-button>
              <template v-if="isSuperAdmin">
                <a-button
                  type="link"
                  size="small"
                  class="user-action-btn user-action-btn-secondary"
                  :disabled="isFirstAdmin(record)"
                  @click="toggleRole(record)"
                >
                  {{ record.role === "admin" ? "取消管理员" : "设为管理员" }}
                </a-button>
                <a-button type="link" size="small" class="user-action-btn user-action-btn-secondary" @click="openResetPwd(record)">
                  重置密码
                </a-button>
              </template>
            </div>
          </template>
        </template>
      </a-table>
    </div>

    <div class="warm-pagination">
      <div class="pagination-summary">{{ currentRangeSummary }}</div>
      <a-pagination
        v-if="totalUsers > pageSize"
        :current="currentPage"
        :total="totalUsers"
        :page-size="pageSize"
        show-less-items
        @change="handlePageChange"
      />
    </div>

    <!-- Create user modal -->
    <a-modal
      v-model:open="modalOpen"
      title="新增用户"
      :confirm-loading="creating"
      :ok-button-props="{ class: 'warm-primary-btn' }"
      :cancel-button-props="{ class: 'warm-secondary-btn' }"
      ok-text="创建"
      cancel-text="取消"
      centered
      :width="440"
      @ok="handleCreate"
    >
      <a-form layout="vertical" style="margin-top: 16px">
        <a-form-item label="用户名">
          <a-input v-model:value="form.username" class="warm-input" placeholder="请输入用户名" />
        </a-form-item>
        <a-form-item label="密码">
          <a-input-password v-model:value="form.password" class="warm-input" placeholder="至少6位" />
        </a-form-item>
        <a-form-item v-if="isSuperAdmin" label="角色" style="margin-bottom: 0">
          <a-radio-group v-model:value="form.role" class="warm-radio-group">
            <a-radio value="user">普通用户</a-radio>
            <a-radio value="admin">管理员</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item v-else label="角色" style="margin-bottom: 0">
          <a-input value="普通用户" class="warm-input" disabled />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Reset password modal (superadmin only) -->
    <a-modal
      v-model:open="resetPwdOpen"
      :title="`重置密码 — ${resetTarget?.username}`"
      :confirm-loading="resetPwdLoading"
      :ok-button-props="{ class: 'warm-primary-btn' }"
      :cancel-button-props="{ class: 'warm-secondary-btn' }"
      ok-text="确认重置"
      cancel-text="取消"
      centered
      :width="440"
      @ok="handleResetPwd"
    >
      <a-form layout="vertical" style="margin-top: 16px">
        <a-form-item label="新密码" style="margin-bottom: 0">
          <a-input-password v-model:value="resetForm.newPassword" class="warm-input" placeholder="至少6位" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Allocate credits modal -->
    <a-modal
      v-model:open="creditsOpen"
      :title="`分配积分 — ${creditsTarget?.username}`"
      :confirm-loading="creditsLoading"
      :ok-button-props="{ class: 'warm-primary-btn' }"
      :cancel-button-props="{ class: 'warm-secondary-btn' }"
      ok-text="确认"
      cancel-text="取消"
      centered
      :width="440"
      @ok="handleAllocateCredits"
    >
      <a-form layout="vertical" style="margin-top: 16px">
        <a-form-item label="积分数量（正数充值，负数扣减）">
          <a-input-number v-model:value="creditsForm.amount" class="warm-input-number" placeholder="请输入积分数量" />
        </a-form-item>
        <a-form-item label="备注说明" style="margin-bottom: 0">
          <a-input v-model:value="creditsForm.description" class="warm-input" placeholder="请输入备注说明" />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="whitelistOpen"
      title="白名单用户"
      :footer="null"
      centered
      :width="720"
    >
      <div class="whitelist-dialog">
        <div class="whitelist-toolbar">
          <a-input
            v-model:value="whitelistKeyword"
            allow-clear
            placeholder="筛选用户名"
            class="whitelist-search warm-input"
          >
            <template #prefix><SearchOutlined /></template>
          </a-input>
          <div class="whitelist-summary">
            当前白名单 <span>{{ whitelistedCount }}</span> 人
          </div>
        </div>

        <div class="whitelist-list" v-if="!whitelistLoading">
          <div v-for="user in filteredWhitelistUsers" :key="user.id" class="whitelist-item">
            <div class="user-cell">
              <a-avatar :size="36" :src="getAvatarImageSrc(user.avatar_url) || undefined" class="table-avatar">
                {{ user.username?.charAt(0)?.toUpperCase() }}
              </a-avatar>
              <div class="whitelist-user-meta">
                <div class="user-cell-name">
                  {{ user.username }}
                  <a-tag v-if="user.is_whitelisted" class="warm-tag warm-tag-whitelist">白名单</a-tag>
                </div>
                <div class="whitelist-user-sub">
                  {{ user.email || user.phone || "未绑定邮箱或手机号" }} · {{ user.role === "admin" ? "管理员" : "普通用户" }} · 积分 {{ user.credits }}
                </div>
              </div>
            </div>
            <a-button
              :type="user.is_whitelisted ? 'default' : 'primary'"
              :loading="whitelistLoadingId === user.id"
              class="whitelist-action-btn"
              :class="user.is_whitelisted ? 'whitelist-action-btn-secondary' : 'whitelist-action-btn-primary'"
              @click="handleToggleWhitelist(user)"
            >
              {{ user.is_whitelisted ? "移出白名单" : "加入白名单" }}
            </a-button>
          </div>
        </div>
        <a-spin v-else />
        <div class="warm-pagination">
          <div class="pagination-summary">
            {{
              whitelistTotal
                ? `当前第 ${(whitelistPage - 1) * whitelistPageSize + 1}-${Math.min(whitelistPage * whitelistPageSize, whitelistTotal)} 条 / 共 ${whitelistTotal} 条`
                : "当前第 0-0 条 / 共 0 条"
            }}
          </div>
          <a-pagination
            v-if="whitelistTotal > whitelistPageSize"
            :current="whitelistPage"
            :total="whitelistTotal"
            :page-size="whitelistPageSize"
            show-less-items
            @change="handleWhitelistPageChange"
          />
        </div>
      </div>
    </a-modal>

    <UserCreditLogsDialog v-model:open="creditLogsOpen" :user="creditLogsTarget" />
    <AdminUserInfoDialog v-model:open="userInfoOpen" :user="userInfoTarget" />

    <a-modal
      v-model:open="promoDashboardOpen"
      :title="`推广数据 - ${promoDashboard?.username || ''}`"
      :footer="null"
      centered
      :width="1020"
    >
      <a-spin :spinning="promoDashboardLoading">
        <div v-if="promoDashboard" class="promo-dashboard">
          <div class="promo-dashboard-stats">
            <div class="promo-stat-card">
              <span>推广注册人数</span>
              <strong>{{ promoDashboard.summary.total_referrals }}</strong>
            </div>
            <div class="promo-stat-card">
              <span>已使用推广码数</span>
              <strong>{{ promoDashboard.summary.used_code_count }}</strong>
            </div>
            <div class="promo-stat-card">
              <span>奖励发放人数</span>
              <strong>{{ promoDashboard.summary.rewarded_registrations }}</strong>
            </div>
            <div class="promo-stat-card">
              <span>累计现金返利</span>
              <strong>{{ promoDashboard.summary.total_reward_amount_yuan != null ? `¥${Number(promoDashboard.summary.total_reward_amount_yuan).toFixed(2)}` : "¥0.00" }}</strong>
            </div>
          </div>

          <div class="promo-dashboard-section">
            <div class="promo-dashboard-title">推广码列表</div>
            <a-table
              :data-source="promoDashboard.promo_codes"
              :pagination="false"
              row-key="id"
              size="small"
              :scroll="{ x: 700 }"
            >
              <a-table-column title="推广码" data-index="code" width="160" />
              <a-table-column title="平台" data-index="platform_name" width="180" />
              <a-table-column title="使用人数" data-index="referral_count" width="100" />
              <a-table-column title="状态" data-index="status" width="100" />
              <a-table-column title="创建时间" data-index="created_at" width="180">
                <template #default="{ record }">
                  {{ fmtTime(record.created_at) }}
                </template>
              </a-table-column>
            </a-table>
          </div>

          <div class="promo-dashboard-section">
            <div class="promo-dashboard-title">推广用户列表</div>
            <a-table
              :data-source="promoDashboard.referrals"
              :pagination="false"
              row-key="user_id"
              size="small"
              :scroll="{ x: 860 }"
            >
              <a-table-column title="用户" data-index="username" width="140" />
              <a-table-column title="邮箱" data-index="email_masked" width="220" />
              <a-table-column title="推广码" data-index="promo_code" width="140" />
              <a-table-column title="来源平台" data-index="platform_name" width="160" />
              <a-table-column title="注册奖励积分" data-index="reward_credits" width="110" />
              <a-table-column title="返利次数" data-index="reward_count" width="88" />
              <a-table-column title="累计返利" data-index="total_reward_amount_yuan" width="110">
                <template #default="{ record }">
                  {{ record.total_reward_amount_yuan != null ? `¥${Number(record.total_reward_amount_yuan).toFixed(2)}` : "¥0.00" }}
                </template>
              </a-table-column>
              <a-table-column title="注册时间" data-index="registered_at" width="180">
                <template #default="{ record }">
                  {{ fmtTime(record.registered_at) }}
                </template>
              </a-table-column>
            </a-table>
          </div>

          <div class="promo-dashboard-section">
            <div class="promo-dashboard-title">推广用户积分记录</div>
            <a-table
              :data-source="promoDashboard.activities"
              :pagination="false"
              :row-key="promoActivityRowKey"
              size="small"
              table-layout="fixed"
              class="promo-dashboard-activity-table"
            >
              <a-table-column title="用户" key="user" width="22%">
                <template #default="{ record }">
                  <div class="promo-user-cell">
                    <span class="promo-user-name">{{ record.username || "-" }}</span>
                    <span v-if="record.email_masked" class="promo-user-email">{{ record.email_masked }}</span>
                  </div>
                </template>
              </a-table-column>
              <a-table-column title="类型" data-index="activity_type" width="100">
                <template #default="{ record }">
                  {{ record.activity_type === "purchase" ? "购买订单" : "兑换码兑换" }}
                </template>
              </a-table-column>
              <a-table-column title="积分" data-index="credits" width="72" />
              <a-table-column title="金额" data-index="amount_yuan" width="96">
                <template #default="{ record }">
                  {{ record.amount_yuan != null ? `¥${record.amount_yuan.toFixed(2)}` : "-" }}
                </template>
              </a-table-column>
              <a-table-column title="返利比例" data-index="reward_rate" width="88">
                <template #default="{ record }">
                  {{ record.reward_rate != null ? `${record.reward_rate}%` : "-" }}
                </template>
              </a-table-column>
              <a-table-column title="返利金额" data-index="reward_amount_yuan" width="100">
                <template #default="{ record }">
                  {{ record.reward_amount_yuan != null ? `¥${Number(record.reward_amount_yuan).toFixed(2)}` : "-" }}
                </template>
              </a-table-column>
              <a-table-column title="订单号/兑换码" ellipsis>
                <template #default="{ record }">
                  {{ record.order_no || record.redeem_key || "-" }}
                </template>
              </a-table-column>
              <a-table-column title="发生时间" data-index="occurred_at" width="168">
                <template #default="{ record }">
                  {{ fmtTime(record.occurred_at) }}
                </template>
              </a-table-column>
            </a-table>
          </div>
        </div>
      </a-spin>
    </a-modal>
  </div>
</template>

<style scoped lang="scss">
.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.filter-input {
  width: 220px;
}

.filter-select {
  width: 180px;
}

.filter-reset-btn {
  height: 36px;
  border-radius: 12px;
  border: 1px solid var(--theme-control-border-strong) !important;
  background: var(--theme-control-bg) !important;
  color: var(--theme-accent-text) !important;

  &:hover {
    border-color: var(--theme-border-strong) !important;
    background: var(--theme-control-hover-bg) !important;
    color: var(--theme-accent-text-hover) !important;
  }
}

.filter-result-count {
  margin-left: auto;
  color: #8c7458;
  font-size: 14px;
  white-space: nowrap;

  span {
    color: #b26c04;
    font-weight: 700;
  }
}

.pagination-summary {
  color: #8c7458;
  font-size: 13px;
  white-space: nowrap;
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-cell-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.table-avatar {
  background: var(--theme-accent);
  color: var(--theme-accent-contrast);
  font-weight: 700;
}

.table-avatar-btn {
  display: inline-flex;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 50%;
  transition: transform 0.15s ease, box-shadow 0.15s ease;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 10px rgba(177, 109, 16, 0.18);
  }

  &:focus-visible {
    outline: 2px solid var(--theme-accent);
    outline-offset: 2px;
  }
}

.user-cell-name {
  color: var(--theme-title);
  font-weight: 700;
}

.user-cell-sub {
  color: #8c7458;
  font-size: 12px;
  word-break: break-all;
}

.id-cell {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  max-width: 100%;
}

.id-text {
  color: #8c7458;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.id-copy-btn {
  width: 24px;
  min-width: 24px;
  height: 24px;
  padding: 0 !important;
  color: #b16d10 !important;
}

.table-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  max-width: 400px;
}

.user-action-btn {
  height: 30px;
  padding-inline: 6px;
  border-radius: 9px;
  font-weight: 600;
  font-size: 12px;
  margin: 0;
}

.user-action-btn.user-action-btn-primary {
  color: var(--theme-accent-text) !important;
  background: var(--theme-panel-bg-strong) !important;
}

.user-action-btn.user-action-btn-secondary {
  color: var(--theme-accent-text) !important;
  background: var(--theme-panel-bg-soft) !important;
}

.user-action-btn.user-action-btn-danger {
  color: #d6574b !important;
  background: #fff1ef !important;
}

.user-action-btn:hover,
.user-action-btn:focus {
  opacity: 0.92;
}

.warm-tag {
  border-radius: 999px;
  border-width: 1px;
  font-weight: 600;
}

.warm-tag-role-admin {
  color: var(--theme-accent-text);
  background: var(--theme-panel-bg-strong);
  border-color: var(--theme-panel-border-strong);
}

.promo-dashboard {
  display: grid;
  gap: 18px;
}

.promo-dashboard-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.promo-stat-card {
  padding: 16px;
  border-radius: 16px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
  display: grid;
  gap: 8px;

  span {
    color: var(--text-secondary);
    font-size: 13px;
  }

  strong {
    color: var(--theme-title);
    font-size: 28px;
    line-height: 1;
  }
}

.promo-dashboard-section {
  display: grid;
  gap: 12px;
}

.promo-user-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.promo-user-name {
  color: #4c341a;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.promo-user-email {
  color: #8c7458;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.promo-dashboard-activity-table {
  :deep(.ant-table) {
    table-layout: fixed;
  }
}

.promo-dashboard-title {
  color: #4c341a;
  font-size: 16px;
  font-weight: 700;
}

.warm-tag-role-user {
  color: var(--theme-accent-text);
  background: var(--theme-panel-bg-soft);
  border-color: var(--theme-panel-border-strong);
}

.warm-tag-whitelist {
  color: var(--theme-accent-text-hover);
  background: var(--theme-panel-bg-strong);
  border-color: var(--theme-border-strong);
}

.warm-tag-muted {
  color: var(--text-secondary);
  background: var(--theme-empty-bg);
  border-color: var(--theme-panel-border);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .warm-page .warm-tag-role-admin,
html:is([data-theme="dark"], [data-theme="midnight"]) .warm-page .warm-tag-role-user,
html:is([data-theme="dark"], [data-theme="midnight"]) .warm-page .warm-tag-whitelist,
html:is([data-theme="dark"], [data-theme="midnight"]) .warm-page .warm-tag-muted {
  background: var(--theme-panel-bg) !important;
  border-color: var(--theme-panel-border) !important;
  color: var(--text-secondary) !important;
  box-shadow: none !important;
}

html[data-theme="midnight"] .warm-page .warm-tag-role-admin,
html[data-theme="midnight"] .warm-page .warm-tag-role-user,
html[data-theme="midnight"] .warm-page .warm-tag-whitelist,
html[data-theme="midnight"] .warm-page .warm-tag-muted {
  background: var(--theme-tag-bg) !important;
  border-color: var(--theme-pill-border) !important;
  color: var(--theme-title) !important;
}

.whitelist-dialog {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 12px;
}

.whitelist-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.whitelist-search {
  width: 240px;
}

.whitelist-summary {
  color: #8c7458;
  font-size: 14px;

  span {
    color: #b26c04;
    font-weight: 700;
  }
}

.whitelist-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 420px;
  overflow: auto;
  padding-right: 4px;
}

.whitelist-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(240, 223, 190, 0.95);
  background: linear-gradient(180deg, rgba(255, 250, 240, 0.88), rgba(255, 255, 255, 0.82));
}

.whitelist-user-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.whitelist-user-sub {
  color: #8c7458;
  font-size: 12px;
}

.whitelist-action-btn {
  flex-shrink: 0;
  min-width: 104px;
  border-radius: 12px;
}

.whitelist-action-btn-primary {
  border-color: var(--theme-accent) !important;
  background: var(--theme-accent) !important;
  color: var(--theme-accent-contrast) !important;
}

.whitelist-action-btn-primary:hover,
.whitelist-action-btn-primary:focus {
  border-color: var(--theme-accent-strong) !important;
  background: var(--theme-accent-strong) !important;
  color: var(--theme-accent-contrast) !important;
}

.whitelist-action-btn-secondary {
  border-color: var(--theme-panel-border-strong) !important;
  background: var(--theme-panel-bg-strong) !important;
  color: var(--theme-accent-text) !important;
}

.whitelist-action-btn-secondary:hover,
.whitelist-action-btn-secondary:focus {
  border-color: var(--theme-border-strong) !important;
  background: var(--theme-control-hover-bg) !important;
  color: var(--theme-accent-text-hover) !important;
}

:deep(.ant-badge-status-text) {
  color: var(--theme-title);
  font-weight: 600;
}

:deep(.admin-mobile-table .ant-table-thead > tr > th) {
  padding: 11px 12px;
  white-space: nowrap;
}

:deep(.admin-mobile-table .ant-table-tbody > tr > td) {
  padding: 8px 12px;
}

@media (max-width: 768px) {
  :deep(.admin-mobile-table .ant-table-content) {
    overflow-x: auto !important;
  }

  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-input,
  .filter-select {
    width: 100%;
  }

  .header-actions,
  .whitelist-toolbar,
  .whitelist-item {
    flex-direction: column;
    align-items: stretch;
  }

  .whitelist-search {
    width: 100%;
  }

  .filter-result-count {
    margin-left: 0;
  }
}
</style>
