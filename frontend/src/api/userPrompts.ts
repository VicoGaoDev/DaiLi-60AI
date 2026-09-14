import client from "./client";
import type {
  UserPrompt,
  UserPromptCategory,
  UserPromptCategoryListResponse,
  UserPromptListResponse,
} from "@/types";

export function listUserPromptCategories(): Promise<UserPromptCategoryListResponse> {
  return client.get("/user-prompts/categories");
}

export function createUserPromptCategory(name: string): Promise<UserPromptCategory> {
  return client.post("/user-prompts/categories", { name });
}

export function updateUserPromptCategory(categoryId: number, name: string): Promise<UserPromptCategory> {
  return client.patch(`/user-prompts/categories/${categoryId}`, { name });
}

export function deleteUserPromptCategory(categoryId: number): Promise<void> {
  return client.delete(`/user-prompts/categories/${categoryId}`);
}

export function listUserPrompts(params?: {
  categoryId?: number | null;
  keyword?: string;
  limit?: number;
}): Promise<UserPromptListResponse> {
  const query: Record<string, any> = {};
  if (typeof params?.categoryId === "number") query.category_id = params.categoryId;
  if (params?.keyword?.trim()) query.keyword = params.keyword.trim();
  if (params?.limit) query.limit = params.limit;
  return client.get("/user-prompts", { params: query });
}

export function createUserPrompt(payload: {
  categoryId?: number | null;
  title: string;
  content: string;
}): Promise<UserPrompt> {
  return client.post("/user-prompts", {
    category_id: payload.categoryId ?? null,
    title: payload.title,
    content: payload.content,
  });
}

export function updateUserPrompt(promptId: number, payload: {
  categoryId?: number | null;
  title?: string;
  content?: string;
}): Promise<UserPrompt> {
  const body: Record<string, any> = {};
  if ("categoryId" in payload) body.category_id = payload.categoryId ?? null;
  if (typeof payload.title !== "undefined") body.title = payload.title;
  if (typeof payload.content !== "undefined") body.content = payload.content;
  return client.patch(`/user-prompts/${promptId}`, body);
}

export function deleteUserPrompt(promptId: number): Promise<{ ok: boolean }> {
  return client.delete(`/user-prompts/${promptId}`);
}
