import client from "./client";
import type { HistoryFilter, HistoryPinTogglePayload, HistoryPinToggleResponse, UserHistoryResponse } from "@/types";

export function fetchHistory(
  page: number = 1,
  pageSize: number = 20,
  filters: Pick<HistoryFilter, "mode" | "source" | "model" | "prompt" | "status" | "exclude_failed" | "start_date" | "end_date" | "respect_pins" | "include_prompt_reverse" | "board_id" | "board_scope"> = {},
): Promise<UserHistoryResponse> {
  return client.get("/history", {
    params: {
      page,
      page_size: pageSize,
      respect_pins: filters.respect_pins,
      include_prompt_reverse: filters.include_prompt_reverse,
      mode: filters.mode,
      source: filters.source,
      model: filters.model,
      prompt: filters.prompt?.trim() || undefined,
      status: filters.status,
      exclude_failed: filters.exclude_failed || undefined,
      start_date: filters.start_date,
      end_date: filters.end_date,
      board_id: filters.board_id,
      board_scope: filters.board_scope,
    },
  });
}

export function toggleHistoryPin(payload: HistoryPinTogglePayload): Promise<HistoryPinToggleResponse> {
  return client.post("/history/pins/toggle", payload);
}

export function deleteHistoryTask(taskId: string): Promise<void> {
  return client.delete(`/history/tasks/${taskId}`);
}
