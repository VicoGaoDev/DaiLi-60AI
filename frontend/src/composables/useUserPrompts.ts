import { ref } from "vue";

import {
  createUserPrompt,
  createUserPromptCategory,
  deleteUserPrompt,
  deleteUserPromptCategory,
  listUserPromptCategories,
  listUserPrompts,
  updateUserPrompt,
  updateUserPromptCategory,
} from "@/api/userPrompts";
import type { UserPrompt, UserPromptCategory } from "@/types";

export type UserPromptCategoryFilter = "all" | "uncategorized" | number;

function toApiCategoryId(category: UserPromptCategoryFilter): number | undefined {
  if (category === "all") return undefined;
  if (category === "uncategorized") return 0;
  return category;
}

export function useUserPrompts() {
  const categories = ref<UserPromptCategory[]>([]);
  const uncategorizedCount = ref(0);
  const prompts = ref<UserPrompt[]>([]);
  const total = ref(0);
  const loading = ref(false);
  const saving = ref(false);

  async function loadCategories() {
    const res = await listUserPromptCategories();
    categories.value = res.items || [];
    uncategorizedCount.value = Number(res.uncategorized_count || 0);
  }

  async function loadPrompts(options?: {
    category?: UserPromptCategoryFilter;
    keyword?: string;
    limit?: number;
  }) {
    const res = await listUserPrompts({
      categoryId: toApiCategoryId(options?.category ?? "all"),
      keyword: options?.keyword,
      limit: options?.limit ?? 100,
    });
    prompts.value = res.items || [];
    total.value = Number(res.total || 0);
  }

  async function refresh(options?: {
    category?: UserPromptCategoryFilter;
    keyword?: string;
    limit?: number;
  }) {
    loading.value = true;
    try {
      await Promise.all([
        loadCategories(),
        loadPrompts(options),
      ]);
    } finally {
      loading.value = false;
    }
  }

  async function createCategory(name: string) {
    const category = await createUserPromptCategory(name);
    await loadCategories();
    return category;
  }

  async function renameCategory(categoryId: number, name: string) {
    const category = await updateUserPromptCategory(categoryId, name);
    await loadCategories();
    return category;
  }

  async function removeCategory(categoryId: number) {
    await deleteUserPromptCategory(categoryId);
    await loadCategories();
  }

  async function createPrompt(payload: {
    categoryId?: number | null;
    title: string;
    content: string;
  }, options?: {
    category?: UserPromptCategoryFilter;
    keyword?: string;
    limit?: number;
  }) {
    saving.value = true;
    try {
      const prompt = await createUserPrompt(payload);
      await Promise.all([
        loadCategories(),
        loadPrompts(options),
      ]);
      return prompt;
    } finally {
      saving.value = false;
    }
  }

  async function editPrompt(
    promptId: number,
    payload: {
      categoryId?: number | null;
      title?: string;
      content?: string;
    },
    options?: {
      category?: UserPromptCategoryFilter;
      keyword?: string;
      limit?: number;
    },
  ) {
    saving.value = true;
    try {
      const prompt = await updateUserPrompt(promptId, payload);
      await Promise.all([
        loadCategories(),
        loadPrompts(options),
      ]);
      return prompt;
    } finally {
      saving.value = false;
    }
  }

  async function removePrompt(
    promptId: number,
    options?: {
      category?: UserPromptCategoryFilter;
      keyword?: string;
      limit?: number;
    },
  ) {
    await deleteUserPrompt(promptId);
    await Promise.all([
      loadCategories(),
      loadPrompts(options),
    ]);
  }

  async function removePrompts(
    promptIds: number[],
    options?: {
      category?: UserPromptCategoryFilter;
      keyword?: string;
      limit?: number;
    },
  ) {
    if (!promptIds.length) return;
    await Promise.all(promptIds.map((promptId) => deleteUserPrompt(promptId)));
    await Promise.all([
      loadCategories(),
      loadPrompts(options),
    ]);
  }

  async function movePrompts(
    promptIds: number[],
    categoryId: number | null,
    options?: {
      category?: UserPromptCategoryFilter;
      keyword?: string;
      limit?: number;
    },
  ) {
    if (!promptIds.length) return;
    await Promise.all(promptIds.map((promptId) => updateUserPrompt(promptId, { categoryId })));
    await Promise.all([
      loadCategories(),
      loadPrompts(options),
    ]);
  }

  return {
    categories,
    uncategorizedCount,
    prompts,
    total,
    loading,
    saving,
    refresh,
    loadCategories,
    loadPrompts,
    createCategory,
    renameCategory,
    removeCategory,
    createPrompt,
    editPrompt,
    removePrompt,
    removePrompts,
    movePrompts,
  };
}
