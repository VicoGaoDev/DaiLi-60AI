import client from "./client";
import type { CreativeTemplate, TemplateListResponse, TemplateTag } from "@/types";

export interface TemplatePayload {
  prompt: string;
  model: string;
  reference_images: string[];
  num_images: number;
  size: string;
  resolution: string;
  custom_size: string;
  result_image: string;
  sort_order: number;
  tag_names: string[];
}

export interface TemplateTagPayload {
  name: string;
}

export function listTemplates(page: number = 1, pageSize: number = 20, tagId?: number): Promise<TemplateListResponse> {
  const params: Record<string, unknown> = {};
  params.page = page;
  params.page_size = pageSize;
  if (tagId) params.tag_id = tagId;
  return client.get("/templates", { params });
}

export function listTemplateTags(): Promise<TemplateTag[]> {
  return client.get("/templates/tags");
}

export function createTemplateTag(data: TemplateTagPayload): Promise<TemplateTag> {
  return client.post("/templates/tags", data);
}

export function updateTemplateTag(tagId: number, data: TemplateTagPayload): Promise<TemplateTag> {
  return client.put(`/templates/tags/${tagId}`, data);
}

export function deleteTemplateTag(tagId: number): Promise<void> {
  return client.delete(`/templates/tags/${tagId}`);
}

export function getTemplateDetail(templateId: number): Promise<CreativeTemplate> {
  return client.get(`/templates/${templateId}`);
}

export function listAdminTemplates(): Promise<CreativeTemplate[]> {
  return client.get("/templates/admin/list");
}

export function createTemplateFromTaskImage(imageId: number, data: TemplatePayload): Promise<CreativeTemplate> {
  return client.post("/templates/admin/from-task-image", { ...data, image_id: imageId });
}

export function createTemplate(data: TemplatePayload): Promise<CreativeTemplate> {
  return client.post("/templates", data);
}

export function updateTemplate(templateId: number, data: TemplatePayload): Promise<CreativeTemplate> {
  return client.put(`/templates/${templateId}`, data);
}

export function deleteTemplate(templateId: number): Promise<void> {
  return client.delete(`/templates/${templateId}`);
}
