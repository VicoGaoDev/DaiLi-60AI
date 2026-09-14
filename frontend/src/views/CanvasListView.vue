<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { message, Modal } from "ant-design-vue";
import dayjs from "dayjs";
import { useRouter } from "vue-router";
import {
  AppstoreOutlined,
  DeleteOutlined,
  EditOutlined,
  MoreOutlined,
  PlusOutlined,
  SearchOutlined,
} from "@ant-design/icons-vue";
import { createCanvas, deleteCanvas, listCanvases, updateCanvas } from "@/api/canvases";
import { getAdminCanvases, listUserOptions } from "@/api/admin";
import { copyExampleCanvasProject, listExampleCanvasProjects } from "@/api/exampleCanvases";
import AdminUserInfoDialog from "@/components/admin/AdminUserInfoDialog.vue";
import { appendImageTransform, getAvatarImageSrc } from "@/api/images";
import { withApiBaseUrl } from "@/lib/assets";
import { useExpiredResultAsset } from "@/lib/expiredResultAsset";
import type { AdminUser, ExampleCanvasProject, UserCanvasSummary } from "@/types";

const props = withDefaults(defineProps<{
  adminCanvases?: boolean;
}>(), {
  adminCanvases: false,
});

const CANVAS_PAGE_SIZE = 20;
const router = useRouter();
const loading = ref(false);
const loadingMore = ref(false);
const creating = ref(false);
const copyingExampleId = ref<number | null>(null);
const canvases = ref<UserCanvasSummary[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(CANVAS_PAGE_SIZE);
const hasMoreCanvases = ref(false);
const exampleProjects = ref<ExampleCanvasProject[]>([]);
const users = ref<AdminUser[]>([]);
const usersLoading = ref(false);
const canvasSearchKeyword = ref("");
const userFilter = ref<string | undefined>(undefined);
const renameDialogOpen = ref(false);
const renameSaving = ref(false);
const renameTarget = ref<UserCanvasSummary | null>(null);
const renameName = ref("");
const userInfoDialogOpen = ref(false);
const selectedUserInfo = ref<AdminUser | null>(null);
const canvasLoadMoreAnchor = ref<HTMLElement | null>(null);
const isAdminCanvasView = computed(() => props.adminCanvases);
const canvasTotalLabel = computed(() => total.value || canvases.value.length);
const shouldHighlightExampleSection = computed(
  () => !isAdminCanvasView.value && canvases.value.length === 0 && exampleProjects.value.length > 0
);
let canvasReloadTimer: ReturnType<typeof setTimeout> | null = null;
let canvasLoadMoreObserver: IntersectionObserver | null = null;
let canvasRequestSeq = 0;
const expiredResultAsset = useExpiredResultAsset();

function getCanvasPreviewSrc(url?: string) {
  return appendImageTransform(withApiBaseUrl(url || ""), "imageMogr2/format/webp");
}

function handleCanvasPreviewError(event: Event) {
  const image = event.target as HTMLImageElement;
  if (image.dataset.expiredFallback === "true") return;
  image.dataset.expiredFallback = "true";
  image.classList.add("canvas-list-preview-expired");
  image.src = expiredResultAsset.value;
}

function handleCanvasPreviewLoad(event: Event) {
  const image = event.target as HTMLImageElement;
  if (image.currentSrc === expiredResultAsset.value) return;
  delete image.dataset.expiredFallback;
  image.classList.remove("canvas-list-preview-expired");
}

const filteredCanvases = computed(() => canvases.value);

function formatCanvasTime(value?: string | null) {
  if (!value) return "暂无更新";
  const target = dayjs(value);
  const diffDays = dayjs().diff(target, "day");
  if (diffDays <= 0) return "今天";
  if (diffDays < 7) return `${diffDays}天前`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}周前`;
  return target.format("YYYY-MM-DD");
}

async function loadCanvases(options: { reset?: boolean } = {}) {
  const reset = !!options.reset;
  if (!reset && (loading.value || loadingMore.value || !hasMoreCanvases.value)) return;
  const requestPage = reset ? 1 : page.value;
  const requestSeq = ++canvasRequestSeq;
  if (reset) {
    loading.value = true;
  } else {
    loadingMore.value = true;
  }
  try {
    const response = isAdminCanvasView.value
      ? await getAdminCanvases(requestPage, pageSize.value, {
          keyword: canvasSearchKeyword.value.trim() || undefined,
          userId: userFilter.value,
        })
      : await listCanvases(requestPage, pageSize.value, {
          keyword: canvasSearchKeyword.value.trim() || undefined,
        });
    if (requestSeq !== canvasRequestSeq) return;
    canvases.value = reset ? response.items : [...canvases.value, ...response.items];
    total.value = response.total || response.items.length;
    page.value = (response.page || requestPage) + 1;
    pageSize.value = response.page_size || pageSize.value;
    hasMoreCanvases.value = !!response.has_more;
  } catch {
    if (requestSeq !== canvasRequestSeq) return;
    message.error(isAdminCanvasView.value ? "获取用户画布失败" : "获取画布列表失败");
  } finally {
    if (requestSeq === canvasRequestSeq) {
      loading.value = false;
      loadingMore.value = false;
    }
  }
}

async function loadExampleProjects() {
  if (isAdminCanvasView.value) return;
  try {
    exampleProjects.value = (await listExampleCanvasProjects()).items;
  } catch {
    message.error("获取示例项目失败");
  }
}

async function loadAdminUsers() {
  if (!isAdminCanvasView.value || users.value.length || usersLoading.value) return;
  usersLoading.value = true;
  try {
    users.value = await listUserOptions();
  } catch {
    message.error("获取用户列表失败");
  } finally {
    usersLoading.value = false;
  }
}

function handleUserFilterDropdownVisible(open: boolean) {
  if (open) void loadAdminUsers();
}

function setupCanvasLoadMoreObserver(target: HTMLElement | null) {
  canvasLoadMoreObserver?.disconnect();
  canvasLoadMoreObserver = null;
  if (!target) return;
  canvasLoadMoreObserver = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) void loadCanvases();
    },
    { root: null, rootMargin: "0px 0px 260px 0px", threshold: 0.01 }
  );
  canvasLoadMoreObserver.observe(target);
}

function openCanvas(canvas: UserCanvasSummary, options: { onboarding?: boolean } = {}) {
  router.push({
    path: isAdminCanvasView.value ? `/admin/user-canvases/${canvas.project_id}` : `/canvas/${canvas.project_id}`,
    query: options.onboarding ? { onboarding: "1" } : undefined,
  });
}

function findAdminUser(userId?: string) {
  if (!userId) return null;
  return users.value.find((user) => user.id === userId) || null;
}

function openUserInfoDialog(canvas: UserCanvasSummary) {
  if (!isAdminCanvasView.value || !canvas.owner_user_id) return;
  const matchedUser = findAdminUser(canvas.owner_user_id);
  selectedUserInfo.value = matchedUser || {
    id: canvas.owner_user_id,
    username: canvas.owner_username || "未知用户",
    avatar_url: canvas.owner_avatar_url || "",
    role: "user",
    status: "",
    is_whitelisted: false,
    credits: 0,
    consumed_credits: 0,
    created_at: "",
  };
  userInfoDialogOpen.value = true;
}

function filterBySelectedUser(user = selectedUserInfo.value) {
  if (!user?.id) return;
  userFilter.value = user.id;
  userInfoDialogOpen.value = false;
}

async function handleCreateCanvas(options: { onboarding?: boolean } = {}) {
  if (creating.value) return;
  creating.value = true;
  try {
    const canvas = await createCanvas();
    canvases.value = [canvas, ...canvases.value];
    message.success("画布已创建");
    openCanvas(canvas, options);
  } catch {
    message.error("创建画布失败");
  } finally {
    creating.value = false;
  }
}

async function handleCopyExampleProject(example: ExampleCanvasProject) {
  if (copyingExampleId.value) return;
  copyingExampleId.value = example.id;
  try {
    const result = await copyExampleCanvasProject(example.id);
    message.success("示例画布已复制到你的画布");
    openCanvas(result.canvas, { onboarding: true });
  } catch {
    message.error("复制示例画布失败");
  } finally {
    copyingExampleId.value = null;
  }
}

function handleCreateCanvasClick() {
  void handleCreateCanvas();
}

function openRenameDialog(canvas: UserCanvasSummary) {
  renameTarget.value = canvas;
  renameName.value = canvas.name;
  renameDialogOpen.value = true;
}

async function submitRenameCanvas() {
  const target = renameTarget.value;
  if (!target) return;
  const nextName = renameName.value.trim();
  if (!nextName) {
    message.warning("画布名称不能为空");
    return;
  }
  if (nextName === target.name) {
    renameDialogOpen.value = false;
    return;
  }
  renameSaving.value = true;
  try {
    await updateCanvas(target.project_id, { name: nextName });
    message.success("画布已重命名");
    renameDialogOpen.value = false;
    await loadCanvases({ reset: true });
  } catch {
    message.error("重命名失败");
  } finally {
    renameSaving.value = false;
  }
}

function handleDeleteCanvas(canvas: UserCanvasSummary) {
  Modal.confirm({
    title: `删除画布「${canvas.name}」？`,
    content: "删除后，该画布和其中的任务会从画布列表移除。",
    centered: true,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      try {
        await deleteCanvas(canvas.project_id);
        message.success("画布已删除");
        await loadCanvases({ reset: true });
      } catch {
        message.error("删除画布失败");
      }
    },
  });
}

function lockCanvasCardLeaveSize(el: Element) {
  const element = el as HTMLElement;
  const { width, height } = element.getBoundingClientRect();
  element.style.width = `${width}px`;
  element.style.height = `${height}px`;
}

onMounted(async () => {
  await Promise.all([
    loadCanvases({ reset: true }),
    loadExampleProjects(),
  ]);
});

watch([canvasSearchKeyword, userFilter], () => {
  if (canvasReloadTimer) clearTimeout(canvasReloadTimer);
  canvasReloadTimer = setTimeout(() => {
    page.value = 1;
    hasMoreCanvases.value = false;
    void loadCanvases({ reset: true });
  }, 250);
});

watch(canvasLoadMoreAnchor, (target) => {
  setupCanvasLoadMoreObserver(target);
});

onBeforeUnmount(() => {
  if (canvasReloadTimer) clearTimeout(canvasReloadTimer);
  canvasLoadMoreObserver?.disconnect();
});
</script>

<template>
  <div class="warm-page canvas-list-page">
    <div class="canvas-list-topbar">
      <div class="warm-page-heading">
        <div class="warm-page-icon canvas-list-topbar-icon">
          <AppstoreOutlined />
        </div>
        <div>
          <div class="warm-page-title canvas-list-topbar-title">{{ isAdminCanvasView ? "用户画布" : "画布列表" }}</div>
          <div class="warm-page-desc">
            {{ isAdminCanvasView ? "管理员可查看所有用户的画布项目，并进入只读工作台查看画布内容。" : "从示例画布快速起步，或进入你自己的画布继续创作和整理生成任务。" }}
          </div>
        </div>
      </div>
      <div class="canvas-list-topbar-actions">
        <a-select
          v-if="isAdminCanvasView"
          v-model:value="userFilter"
          class="canvas-list-user-filter"
          placeholder="全部用户"
          allow-clear
          show-search
          option-filter-prop="label"
          :loading="usersLoading"
          @dropdownVisibleChange="handleUserFilterDropdownVisible"
        >
          <a-select-option
            v-for="user in users"
            :key="user.id"
            :value="user.id"
            :label="user.username"
          >
            {{ user.username }}
          </a-select-option>
        </a-select>
        <a-input
          v-model:value="canvasSearchKeyword"
          class="canvas-list-search"
          placeholder="搜索画布名称"
          allow-clear
        >
          <template #prefix>
            <SearchOutlined />
          </template>
        </a-input>
        <div class="canvas-list-topbar-meta">
          {{ isAdminCanvasView ? `共 ${canvasTotalLabel} 个画布` : `共 ${canvasTotalLabel} 个画布` }}
        </div>
      </div>
    </div>

    <a-spin :spinning="loading">
      <section class="canvas-section">
        <div v-if="!isAdminCanvasView" class="canvas-section-header">
          <div class="canvas-section-title">我的画布</div>
          <div class="canvas-section-desc">你创建或复制的项目都会出现在这里。</div>
        </div>
        <TransitionGroup
          name="canvas-card-list"
          tag="div"
          class="canvas-list-grid"
          @before-leave="lockCanvasCardLeaveSize"
        >
          <button
            v-if="!isAdminCanvasView"
            key="create"
            class="canvas-list-card canvas-list-card-create warm-card"
            type="button"
            :disabled="creating"
            @click="handleCreateCanvasClick"
          >
            <div class="canvas-list-create-icon">
              <PlusOutlined />
            </div>
            <div class="canvas-list-card-title">新建画布</div>
            <div class="canvas-list-card-desc">创建一个新的无限画布空间</div>
          </button>

          <article
            v-for="canvas in filteredCanvases"
            :key="canvas.project_id"
            class="canvas-list-card warm-card"
            :class="{ 'is-soft-deleted': !!canvas.is_deleted }"
            @click="openCanvas(canvas)"
          >
            <button
              v-if="isAdminCanvasView"
              type="button"
              class="canvas-list-owner-badge"
              :title="canvas.owner_username || '未知用户'"
              @click.stop="openUserInfoDialog(canvas)"
            >
              <a-avatar :size="22" :src="getAvatarImageSrc(canvas.owner_avatar_url) || undefined" class="canvas-list-owner-avatar">
                {{ canvas.owner_username?.charAt(0)?.toUpperCase() }}
              </a-avatar>
              <span class="canvas-list-owner-name">{{ canvas.owner_username || "未知用户" }}</span>
            </button>
            <div v-if="isAdminCanvasView && canvas.is_deleted" class="canvas-list-soft-deleted-badge">
              已软删
            </div>
            <div class="canvas-list-preview" :class="{ empty: !canvas.preview_urls.length }">
              <template v-if="canvas.preview_urls.length">
                <img
                  class="canvas-list-preview-main"
                  :src="getCanvasPreviewSrc(canvas.preview_urls[0])"
                  alt=""
                  @error="handleCanvasPreviewError"
                  @load="handleCanvasPreviewLoad"
                />
                <div class="canvas-list-preview-side">
                  <img
                    v-if="canvas.preview_urls[1]"
                    :src="getCanvasPreviewSrc(canvas.preview_urls[1])"
                    alt=""
                    @error="handleCanvasPreviewError"
                    @load="handleCanvasPreviewLoad"
                  />
                  <img
                    v-if="canvas.preview_urls[2]"
                    :src="getCanvasPreviewSrc(canvas.preview_urls[2])"
                    alt=""
                    @error="handleCanvasPreviewError"
                    @load="handleCanvasPreviewLoad"
                  />
                </div>
              </template>
              <template v-else>
                <div class="canvas-list-preview-skeleton canvas-list-preview-skeleton-main"></div>
                <div class="canvas-list-preview-skeleton-side">
                  <div class="canvas-list-preview-skeleton"></div>
                  <div class="canvas-list-preview-skeleton"></div>
                </div>
              </template>
            </div>

            <div class="canvas-list-card-body">
              <div class="canvas-list-card-heading">
                <div>
                  <div class="canvas-list-card-title">{{ canvas.name }}</div>
                  <div class="canvas-list-card-desc">{{ canvas.node_count }} 个节点 · {{ formatCanvasTime(canvas.updated_at) }}</div>
                </div>
                <a-dropdown v-if="!isAdminCanvasView" trigger="click" @click.stop>
                  <button class="canvas-list-more-btn" type="button" @click.stop>
                    <MoreOutlined />
                  </button>
                  <template #overlay>
                    <a-menu>
                      <a-menu-item key="rename" @click="openRenameDialog(canvas)">
                        <EditOutlined /> 重命名
                      </a-menu-item>
                      <a-menu-item key="delete" danger @click="handleDeleteCanvas(canvas)">
                        <DeleteOutlined /> 删除
                      </a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
              </div>
            </div>
          </article>
        </TransitionGroup>
      </section>

      <div v-if="canvases.length" ref="canvasLoadMoreAnchor" class="canvas-list-load-more">
        <a-spin v-if="loadingMore" size="small" />
        <span v-else-if="!hasMoreCanvases">已加载全部画布</span>
      </div>

      <section
        v-if="!isAdminCanvasView && exampleProjects.length"
        class="canvas-section"
        :class="{ 'canvas-section-highlighted': shouldHighlightExampleSection }"
      >
        <div class="canvas-section-header">
          <div class="canvas-section-title">示例画布</div>
          <div class="canvas-section-desc">
            {{ shouldHighlightExampleSection ? "你还没有自己的画布，先点击下面任意示例画布创建一份开始使用。" : "点击任意示例画布即可复制一份到你的账号下继续编辑。" }}
          </div>
        </div>
        <div class="canvas-list-grid canvas-example-grid">
          <button
            v-for="example in exampleProjects"
            :key="`example-${example.id}`"
            class="canvas-list-card canvas-list-card-example warm-card"
            type="button"
            :disabled="copyingExampleId === example.id"
            @click="handleCopyExampleProject(example)"
          >
            <div class="canvas-list-example-badge">示例</div>
            <div class="canvas-list-preview" :class="{ empty: !example.preview_urls.length }">
              <template v-if="example.preview_urls.length">
                <img
                  class="canvas-list-preview-main"
                  :src="getCanvasPreviewSrc(example.cover_url || example.preview_urls[0])"
                  alt=""
                  @error="handleCanvasPreviewError"
                  @load="handleCanvasPreviewLoad"
                />
                <div class="canvas-list-preview-side">
                  <img
                    v-if="example.preview_urls[1]"
                    :src="getCanvasPreviewSrc(example.preview_urls[1])"
                    alt=""
                    @error="handleCanvasPreviewError"
                    @load="handleCanvasPreviewLoad"
                  />
                  <img
                    v-if="example.preview_urls[2]"
                    :src="getCanvasPreviewSrc(example.preview_urls[2])"
                    alt=""
                    @error="handleCanvasPreviewError"
                    @load="handleCanvasPreviewLoad"
                  />
                </div>
              </template>
              <template v-else>
                <div class="canvas-list-preview-skeleton canvas-list-preview-skeleton-main"></div>
                <div class="canvas-list-preview-skeleton-side">
                  <div class="canvas-list-preview-skeleton"></div>
                  <div class="canvas-list-preview-skeleton"></div>
                </div>
              </template>
            </div>
            <div class="canvas-list-card-body">
              <div class="canvas-list-card-title">{{ example.title }}</div>
              <div class="canvas-list-card-desc">
                {{ example.subtitle || "复制后会为你重新创建画布结构，并直接复用示例图片资源。" }}
              </div>
            </div>
          </button>
        </div>
      </section>
    </a-spin>

    <a-modal
      v-model:open="renameDialogOpen"
      title="重命名画布"
      centered
      :confirm-loading="renameSaving"
      ok-text="保存"
      cancel-text="取消"
      @ok="submitRenameCanvas"
    >
      <a-input
        v-model:value="renameName"
        placeholder="请输入画布名称"
        :maxlength="100"
        show-count
        @press-enter="submitRenameCanvas"
      />
    </a-modal>

    <AdminUserInfoDialog
      v-model:open="userInfoDialogOpen"
      :user="selectedUserInfo"
      show-view-data
      @view-data="filterBySelectedUser"
    />
  </div>
</template>

<style scoped lang="scss">
.canvas-list-page {
  padding-bottom: 42px;
}

.canvas-list-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
}

.canvas-section + .canvas-section {
  margin-top: 40px;
}

.canvas-section-highlighted {
  padding: 18px;
  border: 2px solid rgba(238, 177, 79, 0.6);
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(255, 246, 226, 0.82), rgba(255, 250, 239, 0.48));
  box-shadow: 0 0 0 6px rgba(255, 232, 184, 0.42);
  animation: canvas-section-breathe 2.8s ease-in-out infinite;
}

@keyframes canvas-section-breathe {
  0%,
  100% {
    border-color: rgba(238, 177, 79, 0.52);
    box-shadow:
      0 0 0 4px rgba(255, 232, 184, 0.28),
      0 10px 24px rgba(201, 142, 35, 0.08);
  }

  50% {
    border-color: rgba(238, 177, 79, 0.88);
    box-shadow:
      0 0 0 9px rgba(255, 232, 184, 0.48),
      0 14px 30px rgba(201, 142, 35, 0.12);
  }
}

.canvas-section-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.canvas-section-title {
  color: var(--theme-title);
  font-size: 17px;
  font-weight: 800;
}

.canvas-section-desc {
  color: var(--theme-text-secondary);
  font-size: 13px;
}

.canvas-list-topbar-icon {
  background: linear-gradient(135deg, var(--theme-panel-bg-soft), var(--theme-panel-bg-strong));
  color: var(--theme-accent-text);
}

.canvas-list-topbar-title {
  font-size: 19px;
  line-height: 1.3;
}

.canvas-list-topbar-actions {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}

.canvas-list-load-more {
  display: flex;
  justify-content: center;
  align-items: center;
  margin-top: 28px;
  color: var(--theme-text-tertiary);
  font-size: 13px;
}

.canvas-list-search {
  width: 220px;
}

.canvas-list-user-filter {
  width: 180px;
}

.canvas-list-search :deep(.ant-input-affix-wrapper) {
  border-color: var(--theme-control-border);
}

.canvas-list-topbar-meta {
  color: var(--theme-text-secondary);
  font-size: 13px;
  white-space: nowrap;
}

.canvas-list-grid {
  position: relative;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 18px;
}

.canvas-card-list-move,
.canvas-card-list-enter-active,
.canvas-card-list-leave-active {
  transition:
    transform 0.28s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.22s ease,
    box-shadow 0.18s ease;
}

.canvas-card-list-enter-from,
.canvas-card-list-leave-to {
  opacity: 0;
  transform: scale(0.96) translateY(8px);
}

.canvas-card-list-leave-active {
  position: absolute;
  z-index: 0;
  pointer-events: none;
}

.canvas-list-card {
  aspect-ratio: 1 / 1;
  position: relative;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--theme-panel-border);
  border-radius: 14px;
  padding: 0;
  overflow: hidden;
  background: var(--theme-panel-bg);
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}

.canvas-list-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 18px 42px var(--theme-card-shadow-strong);
}

.canvas-list-card.is-soft-deleted {
  border-color: rgba(180, 92, 78, 0.38);
}

.canvas-list-card-create {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 12px;
  border: 1px dashed var(--theme-panel-border-strong);
  background: var(--theme-panel-bg-soft);
}

.canvas-list-card-example {
  appearance: none;
  border: 1px solid rgba(238, 177, 79, 0.28);
}

.canvas-list-card-example:disabled {
  cursor: wait;
  opacity: 0.78;
}

.canvas-list-example-badge {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 2;
  min-height: 26px;
  padding: 0 10px;
  border: 1px solid rgba(255, 244, 222, 0.45);
  border-radius: 999px;
  background: rgba(35, 27, 20, 0.72);
  color: #fff7eb;
  font-size: 12px;
  font-weight: 800;
  line-height: 24px;
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.18);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.canvas-list-owner-badge {
  appearance: none;
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: calc(100% - 24px);
  height: 34px;
  padding: 0 12px 0 7px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 999px;
  background: rgba(35, 27, 20, 0.74);
  color: #fff7eb;
  cursor: pointer;
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.18);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.canvas-list-owner-avatar {
  flex: 0 0 auto;
  background: var(--theme-accent);
  color: var(--theme-accent-contrast);
}

.canvas-list-owner-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 800;
}

.canvas-list-soft-deleted-badge {
  position: absolute;
  right: 12px;
  bottom: 12px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border: 1px solid rgba(255, 224, 220, 0.22);
  border-radius: 999px;
  background: rgba(166, 60, 47, 0.62);
  color: #fff3ef;
  font-size: 11px;
  font-weight: 800;
  box-shadow: 0 10px 20px rgba(96, 31, 22, 0.22);
}

.canvas-list-card-create:disabled {
  cursor: wait;
  opacity: 0.7;
}

.canvas-list-create-icon {
  width: 54px;
  height: 54px;
  display: grid;
  place-items: center;
  border-radius: 18px;
  margin-bottom: 14px;
  color: var(--theme-accent-text);
  background: var(--theme-control-hover-bg);
  font-size: 24px;
}

.canvas-list-preview {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 74px;
  gap: 3px;
  overflow: hidden;
  border-radius: 13px 13px 0 0;
  background: var(--theme-panel-bg-muted);
}

.canvas-list-preview.empty {
  display: grid;
  grid-template-columns: 1fr 74px;
  gap: 3px;
  background: var(--theme-empty-bg);
}

.canvas-list-preview-skeleton {
  min-width: 0;
  min-height: 0;
  border: 0.5px solid var(--theme-panel-border);
  background: var(--theme-panel-bg);
}

.canvas-list-preview-skeleton-main {
  height: 100%;
}

.canvas-list-preview-skeleton-side {
  display: grid;
  grid-template-rows: 1fr 1fr;
  gap: 3px;
}

.canvas-list-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.canvas-list-preview img.canvas-list-preview-expired {
  object-fit: contain;
  padding: 10px;
  background: var(--theme-empty-bg);
}

.canvas-list-preview-side {
  display: grid;
  grid-template-rows: 1fr 1fr;
  gap: 3px;
}

.canvas-list-card-body {
  flex: 0 0 auto;
  padding: 10px 12px 11px;
}

.canvas-list-card-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.canvas-list-card-title {
  color: var(--theme-title);
  font-size: 14px;
  line-height: 1.35;
  font-weight: 800;
}

.canvas-list-card-desc {
  margin-top: 3px;
  color: var(--theme-text-secondary);
  font-size: 12px;
  line-height: 1.35;
}

.canvas-list-more-btn {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 50%;
  color: var(--theme-text-secondary);
  background: transparent;
  cursor: pointer;
  font-size: 16px;
}

.canvas-list-more-btn:hover {
  background: var(--theme-control-hover-bg);
}

@media (max-width: 720px) {
  .canvas-list-topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .canvas-section-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .canvas-list-topbar-actions {
    width: 100%;
    align-items: stretch;
    flex-direction: column;
  }

  .canvas-list-search {
    width: 100%;
  }
}
</style>
