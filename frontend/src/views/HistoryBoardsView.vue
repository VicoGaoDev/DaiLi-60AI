<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
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
  ThunderboltOutlined,
} from "@ant-design/icons-vue";
import { createBoard, deleteBoard, listBoards, updateBoard } from "@/api/boards";
import { boardKeyFromId, GENERATE_BOARD_KEY, writeStoredBoardKey } from "@/lib/boardPreference";
import { useExpiredResultAsset } from "@/lib/expiredResultAsset";
import type { UserBoardSummary } from "@/types";

const router = useRouter();
const loading = ref(false);
const creating = ref(false);
const boards = ref<UserBoardSummary[]>([]);
const boardSearchKeyword = ref("");
const renameDialogOpen = ref(false);
const renameSaving = ref(false);
const renameTarget = ref<UserBoardSummary | null>(null);
const renameName = ref("");
const expiredPreviewAsset = useExpiredResultAsset();

const userBoards = computed(() => boards.value.filter((board) => !board.is_default));
const filteredBoards = computed(() => {
  const keyword = boardSearchKeyword.value.trim().toLowerCase();
  if (!keyword) return boards.value;
  return boards.value.filter((board) => board.name.toLowerCase().includes(keyword));
});

function formatBoardTime(value?: string | null) {
  if (!value) return "暂无更新";
  const target = dayjs(value);
  const diffDays = dayjs().diff(target, "day");
  if (diffDays <= 0) return "今天";
  if (diffDays < 7) return `${diffDays}天前`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}周前`;
  return target.format("YYYY-MM-DD");
}

async function loadBoards() {
  loading.value = true;
  try {
    boards.value = (await listBoards({ includeStats: true, includePreviews: false })).items;
    void loadBoardPreviews();
  } catch {
    message.error("获取分类失败");
  } finally {
    loading.value = false;
  }
}

async function loadBoardPreviews() {
  try {
    const previewBoards = (await listBoards({ includeStats: true, includePreviews: true })).items;
    const previewMap = new Map(previewBoards.map((board) => [boardKeyFromId(board.id), board]));
    boards.value = boards.value.map((board) => ({
      ...board,
      preview_urls: previewMap.get(boardKeyFromId(board.id))?.preview_urls || board.preview_urls,
    }));
  } catch {
    // Preview loading is best-effort; the page is already usable with names and counts.
  }
}

function openBoard(board: UserBoardSummary) {
  const key = boardKeyFromId(board.id);
  router.push(key === "default" ? "/history/board/default" : `/history/board/${board.id}`);
}

async function handleCreateBoard() {
  if (creating.value) return;
  creating.value = true;
  try {
    const board = await createBoard();
    const defaultBoards = boards.value.filter((item) => item.is_default);
    const customBoards = boards.value.filter((item) => !item.is_default && item.id !== board.id);
    boards.value = [...defaultBoards, board, ...customBoards];
    message.success("分类已创建");
  } catch {
    message.error("创建分类失败");
  } finally {
    creating.value = false;
  }
}

function openRenameDialog(board: UserBoardSummary) {
  if (board.is_default || typeof board.id !== "number") return;
  renameTarget.value = board;
  renameName.value = board.name;
  renameDialogOpen.value = true;
}

async function submitRenameBoard() {
  const target = renameTarget.value;
  if (!target || typeof target.id !== "number") return;
  const nextName = renameName.value.trim();
  if (!nextName) {
    message.warning("分类名称不能为空");
    return;
  }
  if (nextName === target.name) {
    renameDialogOpen.value = false;
    return;
  }
  renameSaving.value = true;
  try {
    await updateBoard(target.id, nextName);
    message.success("分类已重命名");
    renameDialogOpen.value = false;
    await loadBoards();
  } catch {
    message.error("重命名失败");
  } finally {
    renameSaving.value = false;
  }
}

function goGenerateWithBoard(board: UserBoardSummary) {
  writeStoredBoardKey(GENERATE_BOARD_KEY, boardKeyFromId(board.id));
  router.push("/generate");
}

function handleDeleteBoard(board: UserBoardSummary) {
  if (board.is_default || typeof board.id !== "number") return;
  Modal.confirm({
    title: `删除分类「${board.name}」？`,
    content: "删除后，该分类下的任务会回到默认分类。",
    centered: true,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      try {
        await deleteBoard(board.id as number);
        message.success("分类已删除");
        await loadBoards();
      } catch {
        message.error("删除分类失败");
      }
    },
  });
}

function lockBoardCardLeaveSize(el: Element) {
  const element = el as HTMLElement;
  const { width, height } = element.getBoundingClientRect();
  element.style.width = `${width}px`;
  element.style.height = `${height}px`;
}

function handleBoardPreviewError(event: Event) {
  const image = event.target as HTMLImageElement;
  if (image.dataset.expiredFallback === "true") return;
  image.dataset.expiredFallback = "true";
  image.classList.add("board-preview-expired");
  image.src = expiredPreviewAsset.value;
}

onMounted(loadBoards);
</script>

<template>
  <div class="warm-page board-page">
    <div class="board-topbar">
      <div class="warm-page-heading">
        <div class="warm-page-icon board-topbar-icon">
          <AppstoreOutlined />
        </div>
        <div>
          <div class="warm-page-title board-topbar-title">我的分类</div>
          <div class="warm-page-desc">按分类整理生成结果，点击分类查看其中的历史图片。</div>
        </div>
      </div>
      <div class="board-topbar-actions">
        <a-input
          v-model:value="boardSearchKeyword"
          class="board-search"
          placeholder="搜索分类名称"
          allow-clear
        >
          <template #prefix>
            <SearchOutlined />
          </template>
        </a-input>
        <div class="board-topbar-meta">
          共 {{ userBoards.length }} 个自定义分类
        </div>
      </div>
    </div>

    <a-spin :spinning="loading">
      <TransitionGroup
        name="board-card-list"
        tag="div"
        class="board-grid"
        @before-leave="lockBoardCardLeaveSize"
      >
        <button
          key="create"
          class="board-card board-card-create warm-card"
          type="button"
          :disabled="creating"
          @click="handleCreateBoard"
        >
          <div class="board-create-icon">
            <PlusOutlined />
          </div>
          <div class="board-card-title">新建分类</div>
          <div class="board-card-desc">创建一个新的图片收纳空间</div>
        </button>

        <article
          v-for="board in filteredBoards"
          :key="boardKeyFromId(board.id)"
          class="board-card warm-card"
          @click="openBoard(board)"
        >
          <div class="board-preview" :class="{ empty: !board.preview_urls.length }">
            <template v-if="board.preview_urls.length">
              <img class="board-preview-main" :src="board.preview_urls[0]" alt="" @error="handleBoardPreviewError" />
              <div class="board-preview-side">
                <img v-if="board.preview_urls[1]" :src="board.preview_urls[1]" alt="" @error="handleBoardPreviewError" />
                <img v-if="board.preview_urls[2]" :src="board.preview_urls[2]" alt="" @error="handleBoardPreviewError" />
              </div>
            </template>
            <template v-else>
              <div class="board-preview-skeleton board-preview-skeleton-main"></div>
              <div class="board-preview-skeleton-side">
                <div class="board-preview-skeleton"></div>
                <div class="board-preview-skeleton"></div>
              </div>
            </template>
          </div>

          <div class="board-card-body">
            <div class="board-card-heading">
              <div>
                <div class="board-card-title">{{ board.name }}</div>
                <div class="board-card-desc">{{ board.asset_count }} 图片 · {{ formatBoardTime(board.updated_at) }}</div>
              </div>
              <a-dropdown trigger="click" @click.stop>
                <button class="board-more-btn" type="button" @click.stop>
                  <MoreOutlined />
                </button>
                <template #overlay>
                  <a-menu>
                    <a-menu-item key="generate" @click="goGenerateWithBoard(board)">
                      <ThunderboltOutlined /> 前往生图
                    </a-menu-item>
                    <a-menu-item v-if="!board.is_default" key="rename" @click="openRenameDialog(board)">
                      <EditOutlined /> 重命名
                    </a-menu-item>
                    <a-menu-item v-if="!board.is_default" key="delete" danger @click="handleDeleteBoard(board)">
                      <DeleteOutlined /> 删除
                    </a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
            </div>
          </div>
        </article>
      </TransitionGroup>
    </a-spin>

    <a-modal
      v-model:open="renameDialogOpen"
      title="重命名分类"
      centered
      :confirm-loading="renameSaving"
      ok-text="保存"
      cancel-text="取消"
      @ok="submitRenameBoard"
    >
      <a-input
        v-model:value="renameName"
        placeholder="请输入分类名称"
        :maxlength="100"
        show-count
        @press-enter="submitRenameBoard"
      />
    </a-modal>
  </div>
</template>

<style scoped lang="scss">
.board-page {
  padding-bottom: 42px;
}

.board-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
}

.board-topbar-icon {
  background: linear-gradient(135deg, var(--theme-panel-bg-soft), var(--theme-panel-bg-strong));
  color: var(--theme-accent-text);
}

.board-topbar-title {
  font-size: 19px;
  line-height: 1.3;
}

.board-topbar-actions {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}

.board-search {
  width: 220px;
}

.board-search :deep(.ant-input-affix-wrapper) {
  border-color: var(--theme-control-border);
}

.board-topbar-meta {
  color: var(--theme-text-secondary);
  font-size: 13px;
  white-space: nowrap;
}

.board-grid {
  position: relative;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 18px;
}

.board-card-list-move,
.board-card-list-enter-active,
.board-card-list-leave-active {
  transition:
    transform 0.28s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.22s ease,
    box-shadow 0.18s ease;
}

.board-card-list-enter-from,
.board-card-list-leave-to {
  opacity: 0;
  transform: scale(0.96) translateY(8px);
}

.board-card-list-leave-active {
  position: absolute;
  z-index: 0;
  pointer-events: none;
}

.board-card {
  aspect-ratio: 1 / 1;
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

.board-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 18px 42px var(--theme-card-shadow-strong);
}

.board-card-create {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 12px;
  border: 1px dashed var(--theme-panel-border-strong);
  background: var(--theme-panel-bg-soft);
}

.board-card-create:disabled {
  cursor: wait;
  opacity: 0.7;
}

.board-create-icon {
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

.board-preview {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 74px;
  gap: 3px;
  overflow: hidden;
  border-radius: 13px 13px 0 0;
  background: var(--theme-panel-bg-muted);
}

.board-preview.empty {
  display: grid;
  grid-template-columns: 1fr 74px;
  gap: 3px;
  background: var(--theme-empty-bg);
}

.board-preview-skeleton {
  min-width: 0;
  min-height: 0;
  border: 0.5px solid var(--theme-panel-border);
  background: var(--theme-panel-bg);
}

.board-preview-skeleton-main {
  height: 100%;
}

.board-preview-skeleton-side {
  display: grid;
  grid-template-rows: 1fr 1fr;
  gap: 3px;
}

.board-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.board-preview img.board-preview-expired {
  object-fit: contain;
  padding: 12px;
  background: var(--theme-empty-bg);
}

.board-preview-side {
  display: grid;
  grid-template-rows: 1fr 1fr;
  gap: 3px;
}

.board-card-body {
  flex: 0 0 auto;
  padding: 10px 12px 11px;
}

.board-card-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.board-card-title {
  color: var(--theme-title);
  font-size: 14px;
  line-height: 1.35;
  font-weight: 800;
}

.board-card-desc {
  margin-top: 3px;
  color: var(--theme-text-secondary);
  font-size: 12px;
  line-height: 1.35;
}

.board-more-btn {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 50%;
  color: var(--theme-text-secondary);
  background: transparent;
  cursor: pointer;
  font-size: 16px;
}

.board-more-btn:hover {
  background: var(--theme-control-hover-bg);
}

@media (max-width: 720px) {
  .board-topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .board-topbar-actions {
    width: 100%;
    align-items: stretch;
    flex-direction: column;
  }

  .board-search {
    width: 100%;
  }
}
</style>
