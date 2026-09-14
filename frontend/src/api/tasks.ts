import client from "./client";
import type { TaskResult } from "@/types";

export interface CreateTaskResponse {
  task_id?: string | null;
  task_ids: string[];
}

export function createTask(data: {
  model?: string;
  source?: "web" | "app" | "api";
  prompt: string;
  num_images: number;
  size: string;
  resolution: string;
  custom_size?: string;
  mode?: "generate" | "inpaint" | "smart_cutout";
  reference_images?: string[];
  source_image?: string;
  mask_image?: string;
  board_id?: number | null;
}): Promise<CreateTaskResponse> {
  return client.post("/tasks", {
    ...data,
    source: data.source || "web",
  });
}

export function getTask(taskId: string): Promise<TaskResult> {
  return client.get(`/tasks/${taskId}`);
}

export function getTasks(taskIds: string[]): Promise<TaskResult[]> {
  const params = new URLSearchParams();
  taskIds.forEach((taskId) => {
    params.append("task_ids", String(taskId));
  });
  return client.get(`/tasks?${params.toString()}`);
}
