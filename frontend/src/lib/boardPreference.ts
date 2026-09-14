import type { BoardKey, UserBoardSummary } from "@/types";

export const GENERATE_BOARD_KEY = "generateBoardKey";
export const DEFAULT_BOARD_KEY: BoardKey = "default";

export function boardKeyFromId(id: number | null | undefined): BoardKey {
  return typeof id === "number" ? `board:${id}` : DEFAULT_BOARD_KEY;
}

export function boardIdFromKey(key: BoardKey): number | null {
  if (key === DEFAULT_BOARD_KEY) return null;
  const id = Number(key.replace("board:", ""));
  return Number.isFinite(id) ? id : null;
}

export function readStoredBoardKey(storageKey: string, boards: UserBoardSummary[], fallback: BoardKey = DEFAULT_BOARD_KEY): BoardKey {
  if (typeof window === "undefined") return fallback;
  const raw = window.localStorage.getItem(storageKey) as BoardKey | null;
  if (!raw) return fallback;
  if (raw === DEFAULT_BOARD_KEY) return raw;
  const boardId = boardIdFromKey(raw);
  return boards.some((board) => board.id === boardId) ? raw : fallback;
}

export function writeStoredBoardKey(storageKey: string, key: BoardKey) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(storageKey, key);
}
