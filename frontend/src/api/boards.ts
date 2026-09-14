import client from "./client";
import dayjs from "dayjs";
import type { UserBoardListResponse, UserBoardSummary } from "@/types";

function normalizeBoardSummary(board: UserBoardSummary): UserBoardSummary {
  return board.is_default ? { ...board, name: "默认分类" } : board;
}

export function getDefaultBoardName() {
  return `新分类-${dayjs().format("YYMMDD")}`;
}

export async function listBoards(options: { includeStats?: boolean; includePreviews?: boolean } = {}): Promise<UserBoardListResponse> {
  const res = await client.get("/boards", {
    params: {
      include_stats: options.includeStats,
      include_previews: options.includePreviews,
    },
  }) as unknown as UserBoardListResponse;
  return {
    items: res.items.map(normalizeBoardSummary),
  };
}

export async function createBoard(name: string = getDefaultBoardName()): Promise<UserBoardSummary> {
  const res = await client.post("/boards", { name }) as unknown as UserBoardSummary;
  return normalizeBoardSummary(res);
}

export async function updateBoard(boardId: number, name: string): Promise<UserBoardSummary> {
  const res = await client.patch(`/boards/${boardId}`, { name }) as unknown as UserBoardSummary;
  return normalizeBoardSummary(res);
}

export function deleteBoard(boardId: number): Promise<void> {
  return client.delete(`/boards/${boardId}`);
}
