<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import dayjs from "dayjs";
import { CheckSquareOutlined, DeleteOutlined, FolderAddOutlined, FolderOpenOutlined, MoreOutlined, PictureOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons-vue";
import { Modal, message } from "ant-design-vue";

import { getPreviewImageSrc } from "@/api/images";
import { useUserAssets, type UserAssetCategoryFilter } from "@/composables/useUserAssets";
import { getAssetQuotaFullMessage, getAssetQuotaTruncatedMessage, isAssetQuotaFull as checkAssetQuotaFull } from "@/lib/userAssetQuota";
import { USER_ASSET_DRAG_MIME, encodeDraggedUserAsset } from "@/lib/userAssetDrag";
import type { UserAsset } from "@/types";

const props = withDefaults(defineProps<{
  open: boolean;
  title?: string;
  enableDrag?: boolean;
  initialCategory?: UserAssetCategoryFilter;
  mask?: boolean;
  showInsertToCanvas?: boolean;
}>(), {
  title: "我的素材",
  enableDrag: false,
  initialCategory: "all",
  mask: true,
  showInsertToCanvas: false,
});

const emit = defineEmits<{
  "update:open": [value: boolean];
  "select-asset": [asset: UserAsset];
  "select-assets": [assets: UserAsset[]];
  "insert-asset": [asset: UserAsset];
  "insert-assets": [assets: UserAsset[]];
}>();

const {
  assets,
  categories,
  loading,
  quota,
  refresh,
  createCategory,
  moveAssets,
  renameAsset,
  removeAsset,
  removeAssets,
  removeCategory,
  renameCategory,
  uncategorizedCount,
  uploadFiles,
  uploading,
} = useUserAssets();

const fileInputRef = ref<HTMLInputElement | null>(null);
const keyword = ref("");
const activeCategory = ref<UserAssetCategoryFilter>(props.initialCategory);
const previewVisible = ref(false);
const previewSrc = ref("");
const categoryNameDialogOpen = ref(false);
const categoryNameDialogSaving = ref(false);
const categoryNameDialogMode = ref<"create" | "rename">("create");
const categoryNameDialogValue = ref("");
const categoryDialogOpen = ref(false);
const categoryDialogSaving = ref(false);
const categoryDialogAssetIds = ref<number[]>([]);
const categoryDialogValue = ref<number | "uncategorized">("uncategorized");
const assetNameDialogOpen = ref(false);
const assetNameDialogSaving = ref(false);
const assetNameDialogAsset = ref<UserAsset | null>(null);
const assetNameDialogValue = ref("");
const batchMode = ref(false);
const batchDeleting = ref(false);
const selectedAssetIds = ref<number[]>([]);
const assetMainRef = ref<HTMLElement | null>(null);
const assetDragActive = ref(false);

const categoryTabs = computed(() => [
  { key: "all" as const, label: "全部", count: quota.value.used },
  { key: "uncategorized" as const, label: "未分类", count: uncategorizedCount.value },
  ...categories.value.map((item) => ({
    key: item.id as UserAssetCategoryFilter,
    label: item.name,
    count: item.asset_count,
  })),
]);

const assetQuotaFull = computed(() => checkAssetQuotaFull(quota.value));
const allVisibleAssetIds = computed(() => assets.value.map((asset) => asset.id));
const selectedCount = computed(() => selectedAssetIds.value.length);
const allVisibleSelected = computed(() => (
  allVisibleAssetIds.value.length > 0
  && allVisibleAssetIds.value.every((id) => selectedAssetIds.value.includes(id))
));
const categoryDialogTitle = computed(() => (
  categoryDialogAssetIds.value.length > 1 ? "批量修改分类" : "修改分类"
));

watch(() => props.open, (open) => {
  if (!open) return;
  void refresh({
    category: activeCategory.value,
    keyword: keyword.value,
    limit: 120,
  }).catch((err: any) => {
    message.error(err?.response?.data?.detail || "获取我的素材失败");
  });
}, { immediate: true });

watch(() => props.initialCategory, (value) => {
  activeCategory.value = value;
});

watch(() => props.open, (open) => {
  if (open) return;
  batchMode.value = false;
  selectedAssetIds.value = [];
  resetAssetDragState();
});

watch(assets, (nextAssets) => {
  const visibleIds = new Set(nextAssets.map((asset) => asset.id));
  selectedAssetIds.value = selectedAssetIds.value.filter((id) => visibleIds.has(id));
  if (!nextAssets.length) {
    batchMode.value = false;
  }
});

function closeDialog() {
  emit("update:open", false);
}

async function reloadAssets() {
  try {
    await refresh({
      category: activeCategory.value,
      keyword: keyword.value,
      limit: 120,
    });
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "刷新我的素材失败");
  }
}

async function changeCategory(category: UserAssetCategoryFilter) {
  activeCategory.value = category;
  await reloadAssets();
}

async function handleSearch() {
  await reloadAssets();
}

function toggleBatchMode() {
  batchMode.value = !batchMode.value;
  if (!batchMode.value) {
    selectedAssetIds.value = [];
  }
}

function handleSelectAssetChange(assetId: number, checked: boolean) {
  if (checked) {
    if (!selectedAssetIds.value.includes(assetId)) {
      selectedAssetIds.value = [...selectedAssetIds.value, assetId];
    }
    return;
  }
  selectedAssetIds.value = selectedAssetIds.value.filter((id) => id !== assetId);
}

function toggleSelectAllAssets() {
  if (allVisibleSelected.value) {
    selectedAssetIds.value = [];
    return;
  }
  selectedAssetIds.value = [...allVisibleAssetIds.value];
}

function clearAssetSelection() {
  selectedAssetIds.value = [];
}

function toggleAssetSelection(assetId: number) {
  handleSelectAssetChange(assetId, !selectedAssetIds.value.includes(assetId));
}

function openPreview(asset: UserAsset) {
  previewSrc.value = getPreviewImageSrc(asset.image_url || asset.thumb_url);
  previewVisible.value = true;
}

function handleAssetThumbClick(asset: UserAsset) {
  if (batchMode.value) {
    toggleAssetSelection(asset.id);
    return;
  }
  openPreview(asset);
}

function formatAssetDate(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD") : "-";
}

function triggerUpload() {
  if (assetQuotaFull.value) {
    message.warning(getAssetQuotaFullMessage(quota.value));
    return;
  }
  fileInputRef.value?.click();
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  input.value = "";
  if (!files.length) return;

  try {
    const uploaded = await uploadFiles(files, {
      categoryId: typeof activeCategory.value === "number" ? activeCategory.value : null,
      onTruncated: (acceptedCount, _skippedCount, remaining) => {
        message.warning(getAssetQuotaTruncatedMessage(acceptedCount, remaining));
      },
    });
    await reloadAssets();
    if (uploaded.length) {
      message.success(`成功上传 ${uploaded.length} 个素材`);
    }
  } catch (err: any) {
    message.error(err?.response?.data?.detail || err?.message || "上传素材失败");
  }
}

function resetAssetDragState() {
  assetDragActive.value = false;
}

function isPointInsideAssetMain(clientX: number, clientY: number) {
  const element = assetMainRef.value;
  if (!element) return false;
  const rect = element.getBoundingClientRect();
  return clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom;
}

function getFileExtension(fileName: string) {
  const normalized = (fileName || "").trim().toLowerCase();
  const parts = normalized.split(".");
  return parts.length > 1 ? parts.pop() || "" : "";
}

function isImageUploadFile(file: File) {
  if ((file.type || "").toLowerCase().startsWith("image/")) return true;
  return ["jpg", "jpeg", "png", "webp", "gif"].includes(getFileExtension(file.name));
}

async function uploadDraggedAssetFiles(files: File[]) {
  try {
    const uploaded = await uploadFiles(files, {
      categoryId: typeof activeCategory.value === "number" ? activeCategory.value : null,
      onTruncated: (acceptedCount, _skippedCount, remaining) => {
        message.warning(getAssetQuotaTruncatedMessage(acceptedCount, remaining));
      },
    });
    await reloadAssets();
    if (uploaded.length) {
      message.success(`成功上传 ${uploaded.length} 个素材`);
    }
  } catch (err: any) {
    message.error(err?.response?.data?.detail || err?.message || "上传素材失败");
  }
}

function confirmDraggedAssetUpload(files: File[]) {
  const imageFiles = files.filter(isImageUploadFile);
  const skippedCount = files.length - imageFiles.length;
  if (!imageFiles.length) {
    message.warning("请拖拽图片文件上传");
    return;
  }

  Modal.confirm({
    title: "上传素材",
    content: `检测到 ${imageFiles.length} 个图片文件${skippedCount ? `，将跳过 ${skippedCount} 个非图片文件` : ""}，确认上传吗？`,
    okText: "确认上传",
    cancelText: "取消",
    async onOk() {
      await uploadDraggedAssetFiles(imageFiles);
    },
  });
}

function showAssetDragOverlay(event: DragEvent) {
  if (!props.open || !event.dataTransfer) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "copy";
  assetDragActive.value = true;
}

function handleAssetMainDragEnter(event: DragEvent) {
  showAssetDragOverlay(event);
}

function handleAssetMainDragOver(event: DragEvent) {
  showAssetDragOverlay(event);
}

function handleAssetMainDragLeave(event: DragEvent) {
  if (!props.open) return;
  const nextTarget = event.relatedTarget as Node | null;
  if (nextTarget && assetMainRef.value?.contains(nextTarget)) return;
  resetAssetDragState();
}

function handleAssetMainDrop(event: DragEvent) {
  if (!props.open || !event.dataTransfer) return;
  event.preventDefault();
  event.stopPropagation();
  const files = Array.from(event.dataTransfer.files || []);
  resetAssetDragState();
  if (!files.length) return;
  confirmDraggedAssetUpload(files);
}

function handleDocumentAssetDragOver(event: DragEvent) {
  if (!props.open || !event.dataTransfer) return;
  const inside = isPointInsideAssetMain(event.clientX, event.clientY);
  assetDragActive.value = inside;
  if (!inside) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "copy";
}

function handleDocumentAssetDrop(event: DragEvent) {
  if (!props.open || !event.dataTransfer) {
    resetAssetDragState();
    return;
  }
  const inside = isPointInsideAssetMain(event.clientX, event.clientY);
  if (!inside) {
    resetAssetDragState();
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  const files = Array.from(event.dataTransfer.files || []);
  resetAssetDragState();
  if (!files.length) return;
  confirmDraggedAssetUpload(files);
}

function handleDocumentAssetDragLeave(event: DragEvent) {
  if (!props.open) return;
  if (event.clientX <= 0 || event.clientY <= 0 || event.clientX >= window.innerWidth || event.clientY >= window.innerHeight) {
    resetAssetDragState();
  }
}

function handleDocumentAssetDragEnd() {
  resetAssetDragState();
}

onMounted(() => {
  document.addEventListener("dragover", handleDocumentAssetDragOver, true);
  document.addEventListener("drop", handleDocumentAssetDrop, true);
  document.addEventListener("dragleave", handleDocumentAssetDragLeave, true);
  document.addEventListener("dragend", handleDocumentAssetDragEnd, true);
});

onBeforeUnmount(() => {
  document.removeEventListener("dragover", handleDocumentAssetDragOver, true);
  document.removeEventListener("drop", handleDocumentAssetDrop, true);
  document.removeEventListener("dragleave", handleDocumentAssetDragLeave, true);
  document.removeEventListener("dragend", handleDocumentAssetDragEnd, true);
});

async function handleCreateCategory() {
  categoryNameDialogMode.value = "create";
  categoryNameDialogValue.value = "";
  categoryNameDialogOpen.value = true;
}

async function handleRenameCategory() {
  if (typeof activeCategory.value !== "number") return;
  const current = categories.value.find((item) => item.id === activeCategory.value);
  categoryNameDialogMode.value = "rename";
  categoryNameDialogValue.value = current?.name || "";
  categoryNameDialogOpen.value = true;
}

function handleDeleteCategory() {
  if (typeof activeCategory.value !== "number") return;
  const categoryId = activeCategory.value;
  Modal.confirm({
    title: "删除分类",
    content: "删除分类不会删除素材，但分类下仍有素材时不可删除。",
    okText: "删除",
    cancelText: "取消",
    async onOk() {
      try {
        await removeCategory(categoryId);
        activeCategory.value = "all";
        await reloadAssets();
        message.success("分类已删除");
      } catch (err: any) {
        message.error(err?.response?.data?.detail || "删除分类失败");
      }
    },
  });
}

function handleDeleteAsset(asset: UserAsset) {
  Modal.confirm({
    title: "删除素材",
    content: "删除后会同步删除云端 COS 对象，并立即释放额度。",
    okText: "删除",
    cancelText: "取消",
    async onOk() {
      try {
        await removeAsset(asset.id, {
          category: activeCategory.value,
          keyword: keyword.value,
          limit: 120,
        });
        message.success("素材已删除");
      } catch (err: any) {
        message.error(err?.response?.data?.detail || "删除素材失败");
      }
    },
  });
}

function handleBatchDeleteAssets() {
  if (!selectedAssetIds.value.length) {
    message.warning("请先选择要删除的素材");
    return;
  }
  const ids = [...selectedAssetIds.value];
  Modal.confirm({
    title: "批量删除素材",
    content: `确定删除已选中的 ${ids.length} 个素材吗？删除后会同步删除云端 COS 对象，并立即释放额度。`,
    okText: "删除",
    cancelText: "取消",
    async onOk() {
      batchDeleting.value = true;
      try {
        await removeAssets(ids, {
          category: activeCategory.value,
          keyword: keyword.value,
          limit: 120,
        });
        selectedAssetIds.value = [];
        message.success(`已删除 ${ids.length} 个素材`);
      } catch (err: any) {
        message.error(err?.response?.data?.detail || "批量删除素材失败");
      } finally {
        batchDeleting.value = false;
      }
    },
  });
}

function handleSelectAsset(asset: UserAsset) {
  emit("select-asset", asset);
}

function handleBatchSelectAssets() {
  if (!selectedAssetIds.value.length) {
    message.warning("请先选择素材");
    return;
  }
  const selectedIdSet = new Set(selectedAssetIds.value);
  const selectedAssets = assets.value.filter((asset) => selectedIdSet.has(asset.id));
  if (!selectedAssets.length) {
    message.warning("请先选择素材");
    return;
  }
  emit("select-assets", selectedAssets);
}

function handleInsertAsset(asset: UserAsset) {
  emit("insert-asset", asset);
}

function handleBatchInsertAssets() {
  if (!selectedAssetIds.value.length) {
    message.warning("请先选择素材");
    return;
  }
  const selectedIdSet = new Set(selectedAssetIds.value);
  const selectedAssets = assets.value.filter((asset) => selectedIdSet.has(asset.id));
  if (!selectedAssets.length) {
    message.warning("请先选择素材");
    return;
  }
  emit("insert-assets", selectedAssets);
}

function openAssetNameDialog(asset: UserAsset) {
  assetNameDialogAsset.value = asset;
  assetNameDialogValue.value = asset.file_name || "";
  assetNameDialogOpen.value = true;
}

async function submitAssetNameDialog() {
  const asset = assetNameDialogAsset.value;
  const nextName = assetNameDialogValue.value.trim();
  if (!asset) return;
  if (!nextName) {
    message.warning("请输入素材名称");
    return;
  }
  if (nextName === (asset.file_name || "").trim()) {
    assetNameDialogOpen.value = false;
    return;
  }
  assetNameDialogSaving.value = true;
  try {
    await renameAsset(asset.id, nextName, {
      category: activeCategory.value,
      keyword: keyword.value,
      limit: 120,
    });
    assetNameDialogOpen.value = false;
    message.success("素材名称已更新");
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "更新素材名称失败");
  } finally {
    assetNameDialogSaving.value = false;
  }
}

async function submitCategoryNameDialog() {
  const name = categoryNameDialogValue.value.trim();
  if (!name) {
    message.warning("请输入分类名称");
    return;
  }
  categoryNameDialogSaving.value = true;
  try {
    if (categoryNameDialogMode.value === "create") {
      const category = await createCategory(name);
      activeCategory.value = category.id;
      await reloadAssets();
      message.success("分类已创建");
    } else {
      if (typeof activeCategory.value !== "number") return;
      await renameCategory(activeCategory.value, name);
      await reloadAssets();
      message.success("分类已重命名");
    }
    categoryNameDialogOpen.value = false;
  } catch (err: any) {
    message.error(err?.response?.data?.detail || (categoryNameDialogMode.value === "create" ? "创建分类失败" : "重命名分类失败"));
  } finally {
    categoryNameDialogSaving.value = false;
  }
}

function openCategoryDialog(asset: UserAsset) {
  categoryDialogAssetIds.value = [asset.id];
  categoryDialogValue.value = asset.category_id ?? "uncategorized";
  categoryDialogOpen.value = true;
}

function openBatchCategoryDialog() {
  if (!selectedAssetIds.value.length) {
    message.warning("请先选择要修改分类的素材");
    return;
  }
  categoryDialogAssetIds.value = [...selectedAssetIds.value];
  categoryDialogValue.value = typeof activeCategory.value === "number" ? activeCategory.value : "uncategorized";
  categoryDialogOpen.value = true;
}

async function submitCategoryDialog() {
  const ids = [...categoryDialogAssetIds.value];
  if (!ids.length) return;
  const nextCategoryId = categoryDialogValue.value === "uncategorized" ? null : categoryDialogValue.value;
  if (ids.length === 1) {
    const asset = assets.value.find((item) => item.id === ids[0]);
    if (asset && (asset.category_id ?? null) === nextCategoryId) {
      categoryDialogOpen.value = false;
      return;
    }
  }
  categoryDialogSaving.value = true;
  try {
    await moveAssets(ids, nextCategoryId, {
      category: activeCategory.value,
      keyword: keyword.value,
      limit: 120,
    });
    categoryDialogOpen.value = false;
    if (ids.length > 1) {
      selectedAssetIds.value = [];
      message.success(`已更新 ${ids.length} 个素材的分类`);
    } else {
      message.success("素材分类已更新");
    }
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "更新素材分类失败");
  } finally {
    categoryDialogSaving.value = false;
  }
}

function handleAssetDragStart(event: DragEvent, asset: UserAsset) {
  if (!props.enableDrag || !event.dataTransfer) return;
  event.dataTransfer.effectAllowed = "copy";
  event.dataTransfer.setData(USER_ASSET_DRAG_MIME, encodeDraggedUserAsset(asset));
  event.dataTransfer.setData("text/plain", asset.image_url || "");
  if (asset.thumb_url || asset.image_url) {
    const img = new Image();
    img.src = getPreviewImageSrc(asset.thumb_url || asset.image_url);
    event.dataTransfer.setDragImage(img, 36, 36);
  }
}
</script>

<template>
  <a-modal
    :open="open"
    :footer="null"
    :width="1120"
    :mask="mask"
    centered
    wrap-class-name="asset-library-modal-wrap"
    @update:open="emit('update:open', $event)"
    @cancel="closeDialog"
  >
    <template #title>
      <div class="asset-modal-header">
        <div class="asset-modal-header-left">
          <div class="asset-modal-header-title">{{ title }}</div>
          <div class="asset-quota-pill">素材额度 {{ quota.used }} / {{ quota.limit }}</div>
        </div>
        <div class="asset-modal-header-right">
          <div class="asset-search">
            <a-input
              v-model:value="keyword"
              allow-clear
              placeholder="搜索素材名称"
              @press-enter="handleSearch"
            />
            <button type="button" class="asset-search-btn" aria-label="搜索素材" @click="handleSearch">
              <SearchOutlined />
            </button>
          </div>
        </div>
        <div class="asset-toolbar-right">
          <a-button type="text" :class="{ 'asset-batch-toggle-active': batchMode }" @click="toggleBatchMode">
            <template #icon><CheckSquareOutlined /></template>
            {{ batchMode ? "退出批量" : "批量管理" }}
          </a-button>
          <a-button :loading="loading" @click="reloadAssets">
            <template #icon><ReloadOutlined /></template>
            刷新
          </a-button>
          <a-button type="primary" :loading="uploading" :disabled="assetQuotaFull" @click="triggerUpload">
            <template #icon><PictureOutlined /></template>
            上传素材
          </a-button>
        </div>
      </div>
    </template>
    <div class="asset-picker">
      <aside class="asset-sidebar">
        <div class="asset-sidebar-header">
          <div class="asset-sidebar-title">分类</div>
          <div class="asset-sidebar-actions">
            <button type="button" class="asset-side-icon-btn" title="新建分类" @click="handleCreateCategory">
              <FolderAddOutlined />
            </button>
            <button
              v-if="typeof activeCategory === 'number'"
              type="button"
              class="asset-side-icon-btn"
              title="重命名分类"
              @click="handleRenameCategory"
            >
              <FolderOpenOutlined />
            </button>
            <button
              v-if="typeof activeCategory === 'number'"
              type="button"
              class="asset-side-icon-btn danger"
              title="删除分类"
              @click="handleDeleteCategory"
            >
              <DeleteOutlined />
            </button>
          </div>
        </div>
        <div class="asset-category-list">
          <button
            v-for="item in categoryTabs"
            :key="String(item.key)"
            type="button"
            class="asset-category-btn"
            :class="{ active: activeCategory === item.key }"
            @click="changeCategory(item.key)"
          >
            <span>{{ item.label }}</span>
            <span>{{ item.count }}</span>
          </button>
        </div>
      </aside>

      <section
        ref="assetMainRef"
        class="asset-main"
        @dragenter="handleAssetMainDragEnter"
        @dragover="handleAssetMainDragOver"
        @dragleave="handleAssetMainDragLeave"
        @drop="handleAssetMainDrop"
      >
        <input ref="fileInputRef" type="file" accept="image/*" multiple hidden @change="handleFileChange" />
        <div class="asset-content-shell">
          <div v-if="!assetQuotaFull" class="asset-drop-hint">支持拖拽上传素材</div>
          <div v-if="assetDragActive" class="asset-drop-overlay">
            <div class="asset-drop-overlay-text">松开即可上传素材</div>
          </div>
          <div v-if="batchMode && assets.length" class="asset-batch-bar">
            <div class="asset-batch-summary">
              已选 {{ selectedCount }} 项 / 当前 {{ allVisibleAssetIds.length }} 项
            </div>
            <div class="asset-batch-actions">
              <a-button size="small" @click="toggleSelectAllAssets">
                {{ allVisibleSelected ? "取消全选" : "全选" }}
              </a-button>
              <a-button size="small" :disabled="!selectedCount" @click="clearAssetSelection">
                清空
              </a-button>
              <a-button size="small" type="primary" :disabled="!selectedCount" @click="handleBatchSelectAssets">
                添加到参考图
              </a-button>
              <a-button
                v-if="showInsertToCanvas"
                size="small"
                :disabled="!selectedCount"
                @click="handleBatchInsertAssets"
              >
                批量添加到画布
              </a-button>
              <a-button size="small" :disabled="!selectedCount" @click="openBatchCategoryDialog">
                批量修改分类
              </a-button>
              <a-button size="small" danger :loading="batchDeleting" :disabled="!selectedCount" @click="handleBatchDeleteAssets">
                批量删除
              </a-button>
            </div>
          </div>
          <div v-if="loading" class="asset-loading-mask">
            <a-spin />
          </div>
          <div class="asset-content">
            <div v-if="assets.length" class="asset-grid">
              <div
                v-for="asset in assets"
                :key="asset.id"
                class="asset-card"
                :class="{ 'asset-card-selected': selectedAssetIds.includes(asset.id) }"
                :draggable="enableDrag"
                @dragstart="handleAssetDragStart($event, asset)"
              >
                <div v-if="batchMode" class="asset-card-check" @click.stop>
                  <a-checkbox
                    :checked="selectedAssetIds.includes(asset.id)"
                    @update:checked="handleSelectAssetChange(asset.id, $event)"
                  />
                </div>
                <div class="asset-card-media">
                  <div class="asset-card-thumb" :class="{ 'batch-selectable': batchMode }" @click="handleAssetThumbClick(asset)">
                    <img :src="getPreviewImageSrc(asset.thumb_url || asset.image_url)" :alt="asset.file_name" loading="lazy" />
                  </div>
                  <div class="asset-card-actions">
                    <button type="button" class="asset-card-action asset-card-action-primary" @click.stop="handleSelectAsset(asset)">
                      作为参考图
                    </button>
                    <button
                      v-if="showInsertToCanvas"
                      type="button"
                      class="asset-card-action"
                      @click.stop="handleInsertAsset(asset)"
                    >
                      添加到画布
                    </button>
                  </div>
                </div>
                <div class="asset-card-name" :title="asset.file_name">{{ asset.file_name }}</div>
                <div class="asset-card-meta-row">
                  <div class="asset-card-date">{{ formatAssetDate(asset.completed_at || asset.created_at) }}</div>
                  <a-dropdown :trigger="['click']">
                    <button type="button" class="asset-card-more-btn" @click.stop>
                      <MoreOutlined />
                    </button>
                    <template #overlay>
                      <a-menu>
                        <a-menu-item key="change-category" @click="openCategoryDialog(asset)">
                          修改分类
                        </a-menu-item>
                        <a-menu-item key="rename-asset" @click="openAssetNameDialog(asset)">
                          修改名称
                        </a-menu-item>
                        <a-menu-item key="delete-asset" danger @click="handleDeleteAsset(asset)">
                          删除
                        </a-menu-item>
                      </a-menu>
                    </template>
                  </a-dropdown>
                </div>
              </div>
            </div>
            <div v-else class="asset-empty">
              <div class="asset-empty-title">暂无素材</div>
              <div class="asset-empty-desc">
                上传到我的素材的图片会
                <strong class="asset-empty-desc-emphasis">永久保存</strong>
                ，可在画布页、AI 生图页和 AI 视频页复用。每个用户最多可保存 100 个素材。
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </a-modal>

  <div v-if="previewVisible" style="display: none">
    <a-image
      :src="previewSrc"
      :preview="{ visible: previewVisible, onVisibleChange: (v: boolean) => (previewVisible = v) }"
    />
  </div>

  <a-modal
    v-model:open="categoryDialogOpen"
    :title="categoryDialogTitle"
    centered
    ok-text="保存"
    cancel-text="取消"
    :confirm-loading="categoryDialogSaving"
    @ok="submitCategoryDialog"
  >
    <div v-if="categoryDialogAssetIds.length > 1" class="asset-category-dialog-hint">
      将已选 {{ categoryDialogAssetIds.length }} 项移动到：
    </div>
    <a-select v-model:value="categoryDialogValue" class="asset-category-dialog-select">
      <a-select-option value="uncategorized">未分类</a-select-option>
      <a-select-option v-for="item in categories" :key="item.id" :value="item.id">
        {{ item.name }}
      </a-select-option>
    </a-select>
  </a-modal>

  <a-modal
    v-model:open="categoryNameDialogOpen"
    :title="categoryNameDialogMode === 'create' ? '新建分类' : '重命名分类'"
    centered
    ok-text="保存"
    cancel-text="取消"
    :confirm-loading="categoryNameDialogSaving"
    @ok="submitCategoryNameDialog"
  >
    <a-input
      v-model:value="categoryNameDialogValue"
      :maxlength="100"
      show-count
      placeholder="请输入分类名称"
      @press-enter="submitCategoryNameDialog"
    />
  </a-modal>
  <a-modal
    v-model:open="assetNameDialogOpen"
    title="修改名称"
    centered
    ok-text="保存"
    cancel-text="取消"
    :confirm-loading="assetNameDialogSaving"
    @ok="submitAssetNameDialog"
  >
    <a-input
      v-model:value="assetNameDialogValue"
      :maxlength="255"
      show-count
      placeholder="请输入素材名称"
      @press-enter="submitAssetNameDialog"
    />
  </a-modal>
</template>

<style scoped lang="scss">
.asset-picker {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 18px;
  height: 620px;
  max-height: calc(100vh - 220px);
  min-height: 0;
}

.asset-sidebar {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--theme-panel-border);
  border-radius: 18px;
  padding: 14px;
  background: var(--theme-panel-bg-soft);
  min-height: 0;
}

.asset-sidebar-header,
.asset-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.asset-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-right: 16px;
}

.asset-modal-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.asset-modal-header-title {
  flex-shrink: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.asset-modal-header-right {
  display: flex;
  align-items: center;
  min-width: 0;
  flex: 1;
  justify-content: flex-end;
}

.asset-sidebar-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--theme-title);
}

.asset-sidebar-actions,
.asset-toolbar-right,
.asset-toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.asset-side-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 10px;
  border: 1px solid var(--theme-control-border);
  background: var(--theme-control-bg);
  color: var(--theme-accent-text);
  cursor: pointer;
}

.asset-side-icon-btn.danger {
  color: #d25959;
}

.asset-category-list {
  margin-top: 14px;
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: var(--theme-border-strong) var(--theme-panel-bg-muted);
}

.asset-category-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid transparent;
  background: var(--theme-control-bg);
  color: var(--theme-title);
  cursor: pointer;
}

.asset-category-btn.active {
  border-color: var(--theme-accent);
  background: var(--theme-control-hover-bg);
  color: var(--theme-accent-text);
}

.asset-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.asset-content-shell {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  margin-top: 0;
  min-height: 0;
  overflow: hidden;
}

.asset-drop-hint {
  position: absolute;
  right: 14px;
  bottom: 10px;
  z-index: 2;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.4;
  pointer-events: none;
  user-select: none;
}

.asset-drop-overlay {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: grid;
  place-items: center;
  border: 2px dashed var(--theme-border-strong);
  border-radius: 18px;
  background: color-mix(in srgb, var(--theme-page-base) 88%, transparent);
  pointer-events: none;
}

.asset-drop-overlay-text {
  padding: 10px 16px;
  border-radius: 999px;
  background: var(--theme-surface-strong);
  color: var(--theme-accent-text);
  font-size: 14px;
  font-weight: 700;
  box-shadow: 0 12px 26px var(--theme-shadow-medium);
}

.asset-batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  padding: 10px 14px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 14px;
  background: var(--theme-panel-bg-strong);
}

.asset-batch-summary {
  color: var(--theme-accent-text);
  font-size: 13px;
  font-weight: 600;
}

.asset-batch-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.asset-loading-mask {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: grid;
  place-items: center;
  border-radius: 18px;
  background: color-mix(in srgb, var(--theme-page-base) 48%, transparent);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  pointer-events: none;
}

.asset-content {
  width: 100%;
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
  overflow-x: hidden;
  overflow-y: scroll;
  padding: 0 4px 4px 0;
  scrollbar-width: thin;
  scrollbar-color: var(--theme-border-strong) var(--theme-panel-bg-muted);
}

.asset-content::-webkit-scrollbar,
.asset-category-list::-webkit-scrollbar {
  width: 8px;
}

.asset-content::-webkit-scrollbar-track,
.asset-category-list::-webkit-scrollbar-track {
  border-radius: 999px;
  background: var(--theme-panel-bg-muted);
}

.asset-content::-webkit-scrollbar-thumb,
.asset-category-list::-webkit-scrollbar-thumb {
  border-radius: 999px;
  border: 2px solid var(--theme-panel-bg-muted);
  background: var(--theme-border-strong);
}

.asset-content::-webkit-scrollbar-thumb:hover,
.asset-category-list::-webkit-scrollbar-thumb:hover {
  background: var(--theme-accent);
}

.asset-search {
  display: flex;
  align-items: stretch;
  width: 280px;
  min-height: 38px;
  border-radius: 999px;
  overflow: hidden;
  border: 1px solid var(--theme-control-border);
  background: var(--theme-control-bg);
  box-shadow: 0 8px 18px var(--theme-shadow-soft);
  transition:
    border-color var(--motion-duration-fast, 0.18s) var(--motion-ease-soft, ease),
    box-shadow var(--motion-duration-fast, 0.18s) var(--motion-ease-soft, ease);
}

.asset-search:hover,
.asset-search:focus-within {
  border-color: var(--theme-border-strong);
  box-shadow: 0 10px 22px var(--theme-shadow-medium);
}

.asset-search :deep(.ant-input-affix-wrapper) {
  flex: 1;
  min-width: 0;
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  border-radius: 0 !important;
  padding-inline: 14px 8px;
}

.asset-search :deep(.ant-input) {
  color: var(--theme-title);
}

.asset-search :deep(.ant-input::placeholder) {
  color: var(--text-muted);
}

.asset-search :deep(.ant-input-clear-icon) {
  color: var(--text-muted);
}

.asset-search :deep(.ant-input-clear-icon:hover) {
  color: var(--theme-accent-text);
}

.asset-search-btn {
  flex-shrink: 0;
  width: 42px;
  border: none;
  border-left: 1px solid var(--theme-control-border);
  background: var(--theme-control-hover-bg);
  color: var(--theme-accent-text);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition:
    background var(--motion-duration-fast, 0.18s) var(--motion-ease-soft, ease),
    color var(--motion-duration-fast, 0.18s) var(--motion-ease-soft, ease);
}

.asset-search-btn :deep(.anticon) {
  font-size: 15px;
}

.asset-search-btn:hover,
.asset-search-btn:focus {
  background: var(--theme-panel-bg-strong);
  color: var(--theme-accent-text-hover);
}

.asset-batch-toggle-active {
  color: var(--theme-accent-text);
  background: var(--theme-control-hover-bg);
}

.asset-quota-pill {
  padding: 8px 12px;
  border-radius: 999px;
  background: var(--theme-pill-bg);
  color: var(--theme-pill-text);
  font-size: 13px;
  font-weight: 600;
}

.asset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  align-content: start;
  gap: 14px;
  min-height: 100%;
}

.asset-card {
  position: relative;
  overflow: hidden;
  border-radius: 18px;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-surface-strong);
  box-shadow: 0 12px 28px var(--theme-shadow-soft);
  transition:
    transform var(--motion-duration-hover, 0.22s) var(--motion-ease-enter, ease),
    box-shadow var(--motion-duration-hover, 0.22s) var(--motion-ease-soft, ease),
    border-color var(--motion-duration-fast, 0.18s) var(--motion-ease-soft, ease);
}

.asset-card-selected {
  border-color: var(--theme-accent);
  box-shadow: 0 18px 34px var(--theme-shadow-medium);
}

.asset-card-check {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 3;
  line-height: 1;
}

.asset-card:hover,
.asset-card:focus-within {
  transform: translateY(-3px);
  border-color: var(--theme-border-strong);
  box-shadow: 0 18px 34px var(--theme-shadow-medium);
}

.asset-card-media {
  position: relative;
}

.asset-card-thumb {
  aspect-ratio: 1 / 1;
  cursor: zoom-in;
  background: var(--theme-panel-bg-muted);
  overflow: hidden;
}

.asset-card-thumb.batch-selectable {
  cursor: pointer;
}

.asset-card-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform var(--motion-duration-emphasis, 0.28s) var(--motion-ease-enter, ease);
}

.asset-card:hover .asset-card-thumb img,
.asset-card:focus-within .asset-card-thumb img {
  transform: scale(1.03);
}

.asset-card-actions {
  position: absolute;
  right: 12px;
  bottom: 12px;
  left: 12px;
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  opacity: 0;
  transform: translateY(8px);
  pointer-events: none;
  transition:
    opacity var(--motion-duration-fast, 0.18s) var(--motion-ease-soft, ease),
    transform var(--motion-duration-fast, 0.18s) var(--motion-ease-soft, ease);
}

.asset-card:hover .asset-card-actions,
.asset-card:focus-within .asset-card-actions {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

.asset-card-action {
  height: 34px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid rgba(255, 240, 214, 0.18);
  background: rgba(76, 52, 26, 0.58);
  color: #fff7ea;
  box-shadow: 0 10px 20px rgba(34, 22, 10, 0.22);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition:
    color var(--motion-duration-fast, 0.18s) var(--motion-ease-soft, ease),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast, 0.18s) var(--motion-ease-soft, ease),
    transform var(--motion-duration-press) var(--motion-ease-soft);
}

.asset-card-action:hover,
.asset-card-action:focus {
  background: rgba(76, 52, 26, 0.78);
  border-color: rgba(255, 240, 214, 0.26);
  color: #fffdfa;
  box-shadow: 0 14px 26px rgba(34, 22, 10, 0.28);
  transform: translateY(-1px);
}

.asset-card-action-primary {
  background: rgba(121, 80, 26, 0.64);
  color: #fff4d8;
}

.asset-card-action-primary:hover,
.asset-card-action-primary:focus {
  background: rgba(143, 94, 30, 0.82);
  color: #fffaf0;
}

.asset-card-action-danger {
  border-color: rgba(255, 214, 209, 0.18);
  background: rgba(180, 58, 43, 0.88);
  color: #fff5f2;
  box-shadow: 0 10px 22px rgba(140, 40, 28, 0.24);
}

.asset-card-action-danger:hover,
.asset-card-action-danger:focus {
  background: rgba(201, 73, 60, 0.98);
  border-color: rgba(255, 224, 220, 0.24);
  color: #fff7f5;
  box-shadow: 0 14px 26px rgba(140, 40, 28, 0.34);
}

.asset-card-name,
.asset-card-meta-row {
  padding-inline: 10px;
}

.asset-card-name {
  margin-top: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-card-meta-row {
  margin-top: 2px;
  padding-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.asset-card-date {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.2;
}

.asset-card-more-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--theme-control-border);
  border-radius: 999px;
  background: var(--theme-control-bg);
  color: var(--text-secondary);
  cursor: pointer;
  transition:
    background var(--motion-duration-fast, 0.18s) var(--motion-ease-soft, ease),
    border-color var(--motion-duration-fast, 0.18s) var(--motion-ease-soft, ease),
    color var(--motion-duration-fast, 0.18s) var(--motion-ease-soft, ease),
    transform var(--motion-duration-press, 0.16s) var(--motion-ease-soft, ease);
}

.asset-card-more-btn:hover,
.asset-card-more-btn:focus {
  background: var(--theme-control-hover-bg);
  border-color: var(--theme-border-strong);
  color: var(--theme-accent-text);
  transform: translateY(-1px);
}

.asset-card-more-btn :deep(.anticon) {
  font-size: 16px;
}

.asset-category-dialog-select {
  width: 100%;
}

.asset-category-dialog-hint {
  margin-bottom: 10px;
  color: var(--theme-accent-text);
  font-size: 13px;
}

.asset-category-dialog-select :deep(.ant-select-selector) {
  border-radius: 12px !important;
  min-height: 40px !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-card {
  background: var(--theme-panel-bg-soft);
  border-color: var(--theme-panel-border);
  box-shadow: 0 12px 28px var(--theme-shadow-soft);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-card-action {
  background: rgba(46, 38, 28, 0.72);
  border-color: rgba(255, 240, 214, 0.12);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-card-action:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .asset-card-action:focus {
  background: rgba(64, 53, 39, 0.86);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-card-more-btn {
  background: var(--theme-panel-bg);
  border-color: var(--theme-panel-border);
  color: var(--text-secondary);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-card-more-btn:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .asset-card-more-btn:focus {
  background: var(--theme-control-hover-bg);
  border-color: var(--theme-border-strong);
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-search {
  background: var(--theme-panel-bg);
  border-color: var(--theme-panel-border);
  box-shadow: 0 10px 20px rgba(0, 0, 0, 0.16);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-search:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .asset-search:focus-within {
  border-color: var(--theme-border-strong);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-search :deep(.ant-input),
html:is([data-theme="dark"], [data-theme="midnight"]) .asset-search :deep(.ant-input-affix-wrapper) {
  color: var(--theme-title) !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-search :deep(.ant-input::placeholder) {
  color: var(--theme-text-secondary);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-search-btn {
  background: linear-gradient(180deg, rgba(61, 49, 31, 0.96), rgba(46, 37, 24, 0.96));
  border-left-color: rgba(214, 168, 84, 0.28);
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-search-btn:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .asset-search-btn:focus {
  background: linear-gradient(180deg, rgba(78, 62, 38, 0.98), rgba(58, 46, 29, 0.98));
  color: var(--theme-accent-text);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-sidebar {
  background: var(--theme-panel-bg-soft);
  border-color: var(--theme-panel-border);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-sidebar-title {
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-side-icon-btn {
  background: var(--theme-panel-bg);
  border-color: var(--theme-panel-border);
  color: var(--theme-text-secondary);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-side-icon-btn:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .asset-side-icon-btn:focus {
  background: var(--theme-control-hover-bg);
  border-color: var(--theme-border-strong);
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-side-icon-btn.danger {
  color: #de8f84;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-category-btn {
  background: var(--theme-panel-bg);
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-category-btn.active {
  background: var(--theme-panel-bg-strong);
  border-color: var(--theme-panel-border-strong);
  color: var(--theme-accent-text);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-drop-hint {
  color: var(--theme-text-secondary);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-drop-overlay {
  background: rgba(var(--theme-surface-strong-rgb), 0.82);
  border-color: rgba(255, 187, 77, 0.56);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-drop-overlay-text {
  background: var(--theme-panel-bg-strong);
  color: var(--theme-title);
  box-shadow: 0 12px 26px rgba(0, 0, 0, 0.28);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-batch-bar {
  background: var(--theme-panel-bg-soft);
  border-color: var(--theme-panel-border);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-batch-summary {
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-loading-mask {
  background: rgba(var(--theme-surface-strong-rgb), 0.42);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-quota-pill {
  background: var(--theme-panel-bg-strong);
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-toolbar-right :deep(.ant-btn-text) {
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-batch-toggle-active {
  background: var(--theme-control-hover-bg);
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-card-thumb {
  background: var(--theme-panel-bg-muted);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-card-name {
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-category-dialog-hint {
  color: var(--theme-text-secondary);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-empty {
  color: var(--theme-text-secondary);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .asset-empty-title {
  color: var(--theme-title);
}

.asset-empty {
  display: grid;
  place-items: center;
  min-height: 100%;
  text-align: center;
  color: var(--text-secondary);
}

.asset-empty-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.asset-empty-desc {
  max-width: 420px;
  margin-top: 8px;
  line-height: 1.6;
}

.asset-empty-desc-emphasis {
  margin: 0 2px;
  color: var(--theme-title);
  font-size: 1.2em;
  font-weight: 800;
}

@media (max-width: 960px) {
  .asset-picker {
    grid-template-columns: 1fr;
    height: auto;
    max-height: none;
  }

  .asset-modal-header {
    flex-direction: column;
    align-items: stretch;
    padding-right: 0;
  }

  .asset-modal-header-left,
  .asset-modal-header-right,
  .asset-toolbar-right {
    width: 100%;
    flex-wrap: wrap;
  }

  .asset-batch-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .asset-search {
    width: 100%;
  }

  .asset-category-list {
    overflow: visible;
    padding-right: 0;
  }

  .asset-content {
    height: auto;
    min-height: auto;
    overflow: visible;
    padding-right: 0;
  }
}
</style>
