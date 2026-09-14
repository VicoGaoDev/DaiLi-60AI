import client from "./client";
import type { ChatGenerationModelOption } from "@/types";

export function getChatModels(): Promise<ChatGenerationModelOption[]> {
  return client.get("/config/chat-models");
}
