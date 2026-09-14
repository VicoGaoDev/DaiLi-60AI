<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { message } from "ant-design-vue";
import { AppstoreOutlined, PictureOutlined, ThunderboltOutlined } from "@ant-design/icons-vue";
import { useRouter } from "vue-router";
import { getGenerationModels } from "@/api/config";
import { getTemplateDetail, listTemplates, listTemplateTags } from "@/api/templates";
import { getPreviewImageSrc } from "@/api/images";
import type { CreativeTemplate, GenerationModelOption, TemplateTag } from "@/types";
import TemplateDetailDialog from "@/components/templates/TemplateDetailDialog.vue";

const router = useRouter();
const TEMPLATE_DRAFT_KEY = "generateDraftFromTemplate";

const page = ref(1);
const pageSize = ref(20);
const loading = ref(false);
const loadingMore = ref(false);
const total = ref(0);
const templates = ref<CreativeTemplate[]>([]);
const generationModels = ref<GenerationModelOption[]>([]);
const tags = ref<TemplateTag[]>([]);
const activeTagId = ref<number | null>(null);
const masonryRef = ref<HTMLElement | null>(null);
const loadMoreAnchor = ref<HTMLElement | null>(null);
let masonryResizeObserver: ResizeObserver | null = null;
let loadMoreObserver: IntersectionObserver | null = null;
const masonryColumnCount = ref(5);
const MASONRY_MIN_COLUMN_WIDTH = 220;
const MASONRY_GAP = 10;
const MASONRY_MAX_COLUMN_COUNT = 12;

const detailOpen = ref(false);
const detailLoading = ref(false);
const detail = ref<CreativeTemplate | null>(null);

const hasMoreTemplates = computed(() => templates.value.length < total.value);
const masonryColumns = computed(() => {
  const columnCount = Math.max(1, masonryColumnCount.value);
  const columns = Array.from({ length: columnCount }, () => [] as Array<{ item: CreativeTemplate; index: number }>);

  templates.value.forEach((item, index) => {
    columns[index % columnCount].push({ item, index });
  });

  return columns;
});

async function loadTags() {
  try {
    tags.value = await listTemplateTags();
  } catch {
    // ignore
  }
}

async function loadTemplates() {
  loading.value = true;
  try {
    const res = await listTemplates(1, pageSize.value, activeTagId.value || undefined);
    templates.value = res.items;
    total.value = res.total;
    page.value = 1;
  } catch {
    message.error("获取创意模版失败");
  } finally {
    loading.value = false;
  }
}

async function loadModels() {
  try {
    generationModels.value = await getGenerationModels();
  } catch {
    generationModels.value = [];
  }
}

async function loadNextTemplatePage() {
  if (loading.value || loadingMore.value || !hasMoreTemplates.value) return;
  loadingMore.value = true;
  try {
    const nextPage = page.value + 1;
    const res = await listTemplates(nextPage, pageSize.value, activeTagId.value || undefined);
    templates.value = [...templates.value, ...res.items];
    total.value = res.total;
    page.value = nextPage;
  } catch {
    message.error("加载更多创意模版失败");
  } finally {
    loadingMore.value = false;
  }
}

function syncMasonryColumnCount() {
  if (typeof window === "undefined") return;
  const width = masonryRef.value?.clientWidth || window.innerWidth;
  const columnCount = Math.floor((width + MASONRY_GAP) / (MASONRY_MIN_COLUMN_WIDTH + MASONRY_GAP));
  masonryColumnCount.value = Math.min(MASONRY_MAX_COLUMN_COUNT, Math.max(1, columnCount));
}

function setupMasonryResizeObserver(target: HTMLElement | null) {
  masonryResizeObserver?.disconnect();
  masonryResizeObserver = null;
  if (!target || typeof ResizeObserver === "undefined") {
    syncMasonryColumnCount();
    return;
  }

  masonryResizeObserver = new ResizeObserver(syncMasonryColumnCount);
  masonryResizeObserver.observe(target);
  syncMasonryColumnCount();
}

function setupLoadMoreObserver(target: HTMLElement | null) {
  loadMoreObserver?.disconnect();
  loadMoreObserver = null;
  if (!target) return;

  loadMoreObserver = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) void loadNextTemplatePage();
    },
    { root: null, rootMargin: "0px 0px 260px 0px", threshold: 0.01 }
  );
  loadMoreObserver.observe(target);
}

async function openDetail(id: number) {
  detailOpen.value = true;
  detailLoading.value = true;
  try {
    detail.value = await getTemplateDetail(id);
  } catch {
    message.error("获取模版详情失败");
    detailOpen.value = false;
  } finally {
    detailLoading.value = false;
  }
}

function useTemplate() {
  if (!detail.value) return;
  localStorage.setItem(
    TEMPLATE_DRAFT_KEY,
    JSON.stringify({
      model: detail.value.model,
      prompt: detail.value.prompt,
      reference_images: detail.value.reference_images,
      num_images: 1,
      size: detail.value.size,
      resolution: detail.value.resolution,
      custom_size: detail.value.custom_size,
    })
  );
  detailOpen.value = false;
  router.push("/generate");
}

function selectTag(tagId: number | null) {
  activeTagId.value = tagId;
  loadTemplates();
}

onMounted(() => {
  loadModels();
  loadTags();
  loadTemplates();
  syncMasonryColumnCount();
  window.addEventListener("resize", syncMasonryColumnCount);
});

onBeforeUnmount(() => {
  masonryResizeObserver?.disconnect();
  masonryResizeObserver = null;
  loadMoreObserver?.disconnect();
  loadMoreObserver = null;
  window.removeEventListener("resize", syncMasonryColumnCount);
});

watch(masonryRef, (target) => {
  setupMasonryResizeObserver(target);
});

watch(loadMoreAnchor, (target) => {
  setupLoadMoreObserver(target);
});
</script>

<template>
  <div class="templates-page warm-page">
    <div class="templates-topbar">
      <div class="warm-page-heading">
        <div class="warm-page-icon templates-topbar-icon">
          <PictureOutlined />
        </div>
        <div>
          <div class="warm-page-title templates-topbar-title">创意模版</div>
          <div class="warm-page-desc">浏览灵感案例，选择喜欢的模版后再进入编辑生成。</div>
        </div>
      </div>
      <div class="templates-topbar-actions">
        <a-button
          class="template-guide-btn"
          href="https://80ai.net/gptimage2-prompt"
          target="_blank"
          rel="noreferrer"
        >
          <template #icon><AppstoreOutlined /></template>
          模版大全
        </a-button>
        <a-button type="primary" class="warm-primary-btn" @click="router.push('/generate')">
          <template #icon><ThunderboltOutlined /></template>
          自定义绘图
        </a-button>
      </div>
    </div>

    <div class="tag-filter">
      <a-tag
        class="filter-tag"
        :class="{ active: activeTagId === null }"
        @click="selectTag(null)"
      >
        全部
      </a-tag>
      <a-tag
        v-for="tag in tags"
        :key="tag.id"
        class="filter-tag"
        :class="{ active: activeTagId === tag.id }"
        @click="selectTag(tag.id)"
      >
        {{ tag.name }}
      </a-tag>
    </div>

    <a-spin :spinning="loading">
      <div v-if="!templates.length && !loading" class="empty-state warm-card">
        <a-empty description="暂无创意模版" />
      </div>

      <div
        v-else
        ref="masonryRef"
        class="masonry"
        :style="{ '--masonry-columns': String(masonryColumnCount) }"
      >
        <TransitionGroup
          v-for="(column, columnIndex) in masonryColumns"
          :key="`masonry-column-${columnIndex}-${masonryColumnCount}`"
          name="template-card"
          tag="div"
          class="masonry-column"
        >
          <div
            v-for="{ item, index } in column"
            :key="item.id"
            class="template-card"
            :style="{ '--template-card-delay': `${Math.min(index, 9) * 45}ms` }"
            @click="openDetail(item.id)"
          >
            <div class="template-cover">
              <img
                v-if="item.result_image"
                :src="getPreviewImageSrc(item.result_image_thumb || item.result_image)"
                alt="模版结果图"
                loading="lazy"
              />
              <div v-else class="template-cover-empty">暂无结果图</div>
              <div class="template-overlay">
                <div class="template-overlay-text">查看详情</div>
              </div>
            </div>
          </div>
        </TransitionGroup>
      </div>
    </a-spin>

    <div v-if="loadingMore" class="templates-load-more-tip">
      <a-spin size="small" />
      <span>正在加载更多模版...</span>
    </div>
    <div v-else-if="templates.length && !hasMoreTemplates" class="templates-load-more-tip templates-load-more-tip-finished">
      已加载全部创意模版
    </div>
    <div
      v-if="templates.length && hasMoreTemplates"
      ref="loadMoreAnchor"
      class="templates-load-more-anchor"
      aria-hidden="true"
    />

    <TemplateDetailDialog
      v-model:open="detailOpen"
      :loading="detailLoading"
      :detail="detail"
      :generation-models="generationModels"
      @use-template="useTemplate"
    />
  </div>
</template>

<style scoped lang="scss">
.templates-page {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  min-height: calc(100vh - 120px);
  animation: templates-page-enter var(--motion-duration-reveal) ease both;
}

@keyframes templates-page-enter {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes templates-fade-up {
  from {
    opacity: 0;
    transform: translate3d(0, 16px, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

@keyframes templates-detail-slide-in {
  from {
    opacity: 0;
    transform: translate3d(20px, 0, 0) scale(0.985);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0) scale(1);
  }
}

.templates-topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
  animation: templates-fade-up var(--motion-duration-reveal) var(--motion-ease-enter) 0.04s both;
}

.templates-topbar-icon {
  width: 38px;
  height: 38px;
  border-radius: 13px;
  font-size: 17px;
}

.templates-topbar-title {
  font-size: 19px;
  line-height: 1.3;
}

.templates-topbar .warm-page-desc {
  font-size: 13px;
  line-height: 1.6;
}

.templates-topbar-actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

:deep(.template-guide-btn) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 36px;
  padding-inline: 14px;
  border-radius: 12px;
  border: 1px solid var(--theme-panel-border-strong) !important;
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-strong)) !important;
  color: var(--theme-accent-text) !important;
  font-size: 13px;
  font-weight: 700;
  box-shadow: 0 10px 22px var(--theme-card-shadow);
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    box-shadow var(--motion-duration-base) var(--motion-ease-soft),
    background var(--motion-duration-base) var(--motion-ease-soft),
    border-color var(--motion-duration-base) var(--motion-ease-soft),
    color var(--motion-duration-base) var(--motion-ease-soft);
}

:deep(.template-guide-btn .ant-btn-icon),
:deep(.template-guide-btn > span) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

:deep(.template-guide-btn:hover),
:deep(.template-guide-btn:focus) {
  color: var(--theme-accent-text-hover) !important;
  border-color: var(--theme-border-strong) !important;
  background: linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-panel-bg-strong)) !important;
  transform: translateY(-1px);
}

:deep(.template-guide-btn:active) {
  transform: scale(0.96);
}

.tag-filter {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 2px 0 6px;
  animation: templates-fade-up var(--motion-duration-reveal-soft) var(--motion-ease-enter) 0.12s both;
}

.filter-tag {
  cursor: pointer;
  border-radius: 999px;
  padding: 6px 12px;
  border-color: var(--theme-pill-border);
  background: var(--theme-pill-bg);
  color: var(--theme-pill-text);
  font-weight: 600;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    box-shadow var(--motion-duration-base) var(--motion-ease-soft),
    background var(--motion-duration-base) var(--motion-ease-soft),
    border-color var(--motion-duration-base) var(--motion-ease-soft),
    color var(--motion-duration-base) var(--motion-ease-soft);

  &:hover {
    transform: translateY(-1px);
    border-color: var(--theme-border-strong);
    background: var(--theme-pill-bg-strong);
    box-shadow: 0 12px 22px var(--theme-pill-shadow);
  }

  &:active {
    transform: scale(0.96);
  }

  &.active {
    color: var(--theme-accent-contrast);
    background: linear-gradient(180deg, var(--theme-accent-strong), var(--theme-accent));
    border-color: var(--theme-border-accent);
    box-shadow: 0 12px 22px var(--theme-shadow-medium);
  }
}

:deep(.ant-spin-nested-loading),
:deep(.ant-spin-container) {
  display: block;
  width: 100%;
  min-width: 0;
}

.masonry {
  display: grid;
  width: 100%;
  box-sizing: border-box;
  grid-template-columns: repeat(var(--masonry-columns), minmax(0, 1fr));
  gap: 10px;
  align-items: start;
}

.masonry-column {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.template-card {
  position: relative;
  width: 100%;
  overflow: hidden;
  border-radius: 16px;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
  cursor: pointer;
  transition:
    transform var(--motion-duration-hover) var(--motion-ease-enter),
    box-shadow var(--motion-duration-hover) var(--motion-ease-soft),
    border-color var(--motion-duration-hover) var(--motion-ease-soft);

  &:hover {
    transform: translateY(-6px);
    border-color: var(--theme-border-strong);
    box-shadow: 0 18px 32px var(--theme-shadow-medium);
  }

  &:active {
    transform: translateY(-2px) scale(0.992);
  }
}

.template-card-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px 14px;
  background: linear-gradient(180deg, rgba(var(--theme-surface-strong-rgb), 0.96), var(--theme-panel-bg-soft));
  border-top: 1px solid var(--theme-border);
}

.template-card-model {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.4;
}

.template-card-prompt {
  color: var(--theme-title);
  font-size: 13px;
  line-height: 1.65;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  min-height: calc(1.65em * 2);
}

.template-card-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.template-cover {
  position: relative;
  overflow: hidden;
  background: var(--theme-panel-bg-soft);

  img {
    width: 100%;
    height: auto;
    display: block;
    transition: transform var(--motion-duration-emphasis) var(--motion-ease-enter);
  }
}

.template-cover-empty,
.detail-result-empty {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
}

.template-cover-empty {
  aspect-ratio: 3 / 4;
}

.template-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, rgba(34, 25, 14, 0.08), rgba(34, 25, 14, 0.56));
  opacity: 0;
  transition: opacity var(--motion-duration-base) var(--motion-ease-soft);

  .template-card:hover & {
    opacity: 1;
  }
}

.template-card:hover .template-cover img {
  transform: scale(1.045);
}

.template-overlay-text {
  padding: 10px 18px;
  border-radius: 999px;
  background: rgba(var(--theme-surface-strong-rgb), 0.92);
  color: var(--theme-accent-text-hover);
  font-size: 14px;
  font-weight: 700;
  transition: transform var(--motion-duration-swift) var(--motion-ease-soft);
}

.template-card:hover .template-overlay-text {
  transform: translateY(-2px);
}

.detail-section + .detail-section {
  margin-top: 18px;
}

.detail-layout {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 20px;
  align-items: start;
  animation: templates-detail-slide-in var(--motion-duration-reveal-slower) var(--motion-ease-enter) both;
}

.detail-left,
.detail-right {
  min-width: 0;
}

.detail-right {
  display: flex;
  flex-direction: column;
}

.detail-floating-actions {
  position: absolute;
  right: 0;
  bottom: 0;
  display: flex;
  gap: 8px;
  padding: 0 2px 2px 0;
}

.detail-primary-action {
  height: 40px;
  padding-inline: 16px;
  border-radius: 14px;
  box-shadow: 0 14px 28px var(--theme-shadow-strong);
}

.detail-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-secondary);
}

.detail-section > .detail-label {
  margin-bottom: 10px;
}

.detail-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.detail-copy-btn {
  height: 30px;
  padding-inline: 10px;
  border-radius: 10px;
  color: var(--theme-link) !important;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover {
    background: var(--theme-panel-bg-strong) !important;
    color: var(--theme-link-hover) !important;
    transform: translateY(-1px);
    box-shadow: 0 10px 20px var(--theme-shadow-soft);
  }

  &:active {
    transform: scale(0.96);
  }
}

.detail-prompt {
  padding: 12px 14px;
  border-radius: 12px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
  color: var(--theme-title);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 210px;
  overflow-y: auto;
  scrollbar-width: thin;
}

.detail-thumb-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.detail-thumb {
  width: 84px;
  height: 84px;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
  cursor: pointer;
  transition:
    transform var(--motion-duration-base) var(--motion-ease-soft),
    box-shadow var(--motion-duration-base) var(--motion-ease-soft),
    border-color var(--motion-duration-base) var(--motion-ease-soft);

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  &:hover {
    transform: translateY(-2px);
    border-color: var(--theme-border-strong);
    box-shadow: 0 16px 24px var(--theme-shadow-soft);
  }
}

.detail-result-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
}

.detail-result-card {
  height: clamp(220px, 36vh, 340px);
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
  cursor: zoom-in;
  transition:
    transform var(--motion-duration-base) var(--motion-ease-soft),
    box-shadow var(--motion-duration-base) var(--motion-ease-soft),
    border-color var(--motion-duration-base) var(--motion-ease-soft);

  img,
  .detail-result-empty {
    width: 100%;
    height: 100%;
  }

  img {
    object-fit: contain;
    display: block;
    background: var(--theme-panel-bg);
    transition: transform var(--motion-duration-hover) var(--motion-ease-soft);
  }

  &:not(.empty):hover {
    transform: translateY(-3px);
    border-color: var(--theme-border-strong);
    box-shadow: 0 16px 28px var(--theme-shadow-medium);
  }

  &:not(.empty):hover img {
    transform: scale(1.015);
  }

  &.single {
    height: clamp(440px, 72vh, 680px);
  }

  &.empty {
    cursor: default;
  }
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
  padding: 12px 14px;
  border-radius: 12px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.8;

  span:not(:last-child)::after {
    content: "｜";
    margin: 0 8px;
    color: #d3b487;
  }
}

.empty-state {
  padding: 72px 0;
  animation: templates-fade-up var(--motion-duration-reveal) var(--motion-ease-enter) 0.2s both;
}

.templates-load-more-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 48px;
  margin: 14px 0 4px;
  color: var(--text-secondary);
  font-size: 13px;
}

.templates-load-more-tip-finished {
  color: var(--text-muted);
}

.templates-load-more-anchor {
  width: 100%;
  height: 2px;
}

:deep(.warm-primary-btn) {
  height: 36px;
  padding-inline: 14px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 700;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    box-shadow var(--motion-duration-base) var(--motion-ease-soft),
    background var(--motion-duration-base) var(--motion-ease-soft);
}

:deep(.warm-primary-btn:hover),
:deep(.warm-primary-btn:focus) {
  transform: translateY(-1px);
}

:deep(.warm-primary-btn:active) {
  transform: scale(0.96);
}

.template-card-enter-active,
.template-card-leave-active {
  transition:
    opacity var(--motion-duration-emphasis) var(--motion-ease-soft),
    transform var(--motion-duration-emphasis-plus) var(--motion-ease-enter);
  transition-delay: var(--template-card-delay, 0ms);
}

.template-card-enter-from,
.template-card-leave-to {
  opacity: 0;
  transform: translate3d(0, 22px, 0) scale(0.985);
}

.template-card-move {
  transition: transform var(--motion-duration-reveal-fast) var(--motion-ease-enter);
}

@media (prefers-reduced-motion: reduce) {
  .templates-page,
  .templates-topbar,
  .tag-filter,
  .empty-state,
  .detail-layout {
    animation: none !important;
  }

  .template-card,
  .template-card-enter-active,
  .template-card-leave-active,
  .template-card-move,
  .template-cover img,
  .template-card-body,
  .template-overlay,
  .template-overlay-text,
  .filter-tag,
  .detail-preview img,
  .detail-refs img,
  :deep(.warm-primary-btn) {
    transition: none !important;
  }
}

@media (max-width: 900px) {
  .masonry {
    gap: 10px;
  }

  .detail-layout {
    grid-template-columns: 1fr;
  }

  .detail-floating-actions {
    position: static;
    justify-content: flex-end;
    margin-top: 14px;
    padding: 0;
  }

  .detail-result-card.single {
    height: clamp(360px, 60vh, 520px);
  }

  .templates-topbar {
    flex-direction: column;
    align-items: stretch;
  }

  .templates-topbar-actions {
    width: 100%;
  }
}

@media (max-width: 640px) {
  .masonry,
  .masonry-column {
    gap: 8px;
  }

  .detail-result-card.single {
    height: clamp(280px, 56vh, 420px);
  }
}

</style>
