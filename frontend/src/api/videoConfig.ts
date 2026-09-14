import client from "./client";
import type { VideoGenerationModelOption, VideoTaskSceneConfig } from "@/types";

export function getVideoGenerationModels(): Promise<VideoGenerationModelOption[]> {
  return client.get("/config/video-generation-models");
}

export function getVideoTaskScenes(): Promise<VideoTaskSceneConfig[]> {
  return client.get("/config/video-task-scenes");
}
