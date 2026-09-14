import { ref } from "vue";

import {
  createUserAssetCategory,
  deleteUserAsset,
  deleteUserAssetCategory,
  getUserAssetStats,
  listUserAssetCategories,
  listUserAssets,
  updateUserAsset,
  updateUserAssetCategory,
  uploadUserAssetFile,
} from "@/api/userAssets";
import { getAssetQuotaFullMessage, truncateByAssetQuota } from "@/lib/userAssetQuota";
import type { UserAsset, UserAssetCategory, UserAssetQuota } from "@/types";

export type UserAssetCategoryFilter = "all" | "uncategorized" | number;

function toApiCategoryId(category: UserAssetCategoryFilter): number | undefined {
  if (category === "all") return undefined;
  if (category === "uncategorized") return 0;
  return category;
}

export function useUserAssets() {
  const categories = ref<UserAssetCategory[]>([]);
  const uncategorizedCount = ref(0);
  const assets = ref<UserAsset[]>([]);
  const quota = ref<UserAssetQuota>({ used: 0, limit: 100, remaining: 100 });
  const loading = ref(false);
  const uploading = ref(false);

  async function loadCategories() {
    const res = await listUserAssetCategories();
    categories.value = res.items || [];
    uncategorizedCount.value = Number(res.uncategorized_count || 0);
  }

  async function loadAssets(options?: {
    category?: UserAssetCategoryFilter;
    keyword?: string;
    limit?: number;
  }) {
    const res = await listUserAssets({
      categoryId: toApiCategoryId(options?.category ?? "all"),
      keyword: options?.keyword,
      limit: options?.limit ?? 100,
    });
    assets.value = res.items || [];
    quota.value = res.quota || quota.value;
  }

  async function refresh(options?: {
    category?: UserAssetCategoryFilter;
    keyword?: string;
    limit?: number;
  }) {
    loading.value = true;
    try {
      await Promise.all([
        loadCategories(),
        loadAssets(options),
      ]);
    } finally {
      loading.value = false;
    }
  }

  async function refreshQuota() {
    quota.value = await getUserAssetStats();
  }

  async function createCategory(name: string) {
    const category = await createUserAssetCategory(name);
    await loadCategories();
    return category;
  }

  async function renameCategory(categoryId: number, name: string) {
    const category = await updateUserAssetCategory(categoryId, name);
    await loadCategories();
    return category;
  }

  async function removeCategory(categoryId: number) {
    await deleteUserAssetCategory(categoryId);
    await loadCategories();
  }

  async function removeAsset(assetId: number, options?: {
    category?: UserAssetCategoryFilter;
    keyword?: string;
    limit?: number;
  }) {
    const res = await deleteUserAsset(assetId);
    quota.value = res.quota || quota.value;
    await Promise.all([
      loadCategories(),
      loadAssets(options),
    ]);
  }

  async function removeAssets(assetIds: number[], options?: {
    category?: UserAssetCategoryFilter;
    keyword?: string;
    limit?: number;
  }) {
    if (!assetIds.length) return;
    for (const assetId of assetIds) {
      const res = await deleteUserAsset(assetId);
      quota.value = res.quota || quota.value;
    }
    await Promise.all([
      loadCategories(),
      loadAssets(options),
    ]);
  }

  async function moveAsset(
    assetId: number,
    categoryId: number | null,
    options?: {
      category?: UserAssetCategoryFilter;
      keyword?: string;
      limit?: number;
    },
  ) {
    await updateUserAsset(assetId, { categoryId });
    await Promise.all([
      loadCategories(),
      loadAssets(options),
    ]);
  }

  async function moveAssets(
    assetIds: number[],
    categoryId: number | null,
    options?: {
      category?: UserAssetCategoryFilter;
      keyword?: string;
      limit?: number;
    },
  ) {
    if (!assetIds.length) return;
    for (const assetId of assetIds) {
      await updateUserAsset(assetId, { categoryId });
    }
    await Promise.all([
      loadCategories(),
      loadAssets(options),
    ]);
  }

  async function renameAsset(
    assetId: number,
    fileName: string,
    options?: {
      category?: UserAssetCategoryFilter;
      keyword?: string;
      limit?: number;
    },
  ) {
    await updateUserAsset(assetId, { fileName });
    await Promise.all([
      loadCategories(),
      loadAssets(options),
    ]);
  }

  async function uploadFiles(
    files: File[],
    options?: {
      categoryId?: number | null;
      onItemSuccess?: (asset: UserAsset) => void | Promise<void>;
      onTruncated?: (acceptedCount: number, skippedCount: number, remaining: number) => void;
    },
  ) {
    if (!files.length) return [];

    uploading.value = true;
    const uploadedAssets: UserAsset[] = [];
    try {
      await refreshQuota();
      if (quota.value.remaining <= 0) {
        throw new Error(getAssetQuotaFullMessage(quota.value));
      }

      const { accepted, skipped } = truncateByAssetQuota(files, quota.value.remaining);
      if (skipped > 0) {
        options?.onTruncated?.(accepted.length, skipped, quota.value.remaining);
      }

      for (const file of accepted) {
        if (quota.value.remaining <= 0) break;
        const result = await uploadUserAssetFile(file, { categoryId: options?.categoryId ?? null });
        quota.value = result.quota || quota.value;
        uploadedAssets.push(result.asset);
        await options?.onItemSuccess?.(result.asset);
      }
      return uploadedAssets;
    } finally {
      uploading.value = false;
    }
  }

  return {
    assets,
    categories,
    loading,
    quota,
    refreshQuota,
    refresh,
    loadAssets,
    loadCategories,
    createCategory,
    renameCategory,
    removeCategory,
    removeAsset,
    removeAssets,
    moveAsset,
    moveAssets,
    renameAsset,
    uncategorizedCount,
    uploadFiles,
    uploading,
  };
}
