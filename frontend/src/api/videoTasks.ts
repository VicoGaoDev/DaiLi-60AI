import client from "./client";
import type { VideoTaskResult } from "@/types";

export interface CreateVideoTaskResponse {
  task_id: string;
}

export function createVideoTask(data: {
  model: string;
  source?: "web" | "app" | "api";
  generation_mode: "text_to_video" | "image_to_video" | "first_last_frame";
  prompt: string;
  duration_seconds: number;
  aspect_ratio: string;
  resolution: string;
  reference_images?: string[];
}): Promise<CreateVideoTaskResponse> {
  return client.post("/video-tasks/submit", {
    ...data,
    source: data.source || "web",
  });
}

export function getVideoTask(taskId: string): Promise<VideoTaskResult> {
  return client.get(`/video-tasks/${taskId}`);
}

export function getVideoTasks(taskIds: string[], limit?: number): Promise<VideoTaskResult[]> {
  const params = new URLSearchParams();
  taskIds.forEach((taskId) => {
    params.append("task_ids", String(taskId));
  });
  if (!taskIds.length && typeof limit === "number") {
    params.append("limit", String(limit));
  }
  const query = params.toString();
  return client.get(query ? `/video-tasks?${query}` : "/video-tasks");
}

export function deleteVideoTask(taskId: string): Promise<void> {
  return client.delete(`/video-tasks/${taskId}`);
}
