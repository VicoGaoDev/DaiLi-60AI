import client from "./client";
import type {
  CanvasDetail,
  CanvasEdge,
  CanvasGroup,
  CanvasGroupAssignNodesResponse,
  CanvasGroupRemoveNodesResponse,
  CanvasNode,
  CanvasTaskCreateResponse,
  CanvasTaskPayload,
  CanvasVideoTaskPayload,
  UserCanvasListResponse,
  UserCanvasSummary,
} from "@/types";

export function listCanvases(
  page = 1,
  pageSize = 20,
  filters?: { keyword?: string }
): Promise<UserCanvasListResponse> {
  return client.get("/canvases", {
    params: {
      page,
      page_size: pageSize,
      keyword: filters?.keyword || undefined,
    },
  });
}

export function getDefaultCanvasName(date = new Date()): string {
  const year = String(date.getFullYear()).slice(-2);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `新画布-${year}${month}${day}`;
}

export function createCanvas(name: string = getDefaultCanvasName()): Promise<UserCanvasSummary> {
  return client.post("/canvases", { name });
}

export function getCanvas(projectId: string): Promise<CanvasDetail> {
  return client.get(`/canvases/${projectId}`);
}

export function updateCanvas(projectId: string, data: { name?: string; viewport_x?: number; viewport_y?: number; zoom?: number }): Promise<UserCanvasSummary> {
  return client.patch(`/canvases/${projectId}`, data);
}

export function deleteCanvas(projectId: string): Promise<void> {
  return client.delete(`/canvases/${projectId}`);
}

export function updateCanvasViewport(projectId: string, data: { viewport_x: number; viewport_y: number; zoom: number }): Promise<UserCanvasSummary> {
  return client.patch(`/canvases/${projectId}/viewport`, data);
}

export function updateCanvasNode(projectId: string, nodeId: number, data: Partial<Pick<CanvasNode, "x" | "y" | "width" | "height" | "z_index" | "content">>): Promise<CanvasNode> {
  return client.patch(`/canvases/${projectId}/nodes/${nodeId}`, data);
}

export function updateCanvasNodesBatch(projectId: string, nodes: Array<Partial<Pick<CanvasNode, "x" | "y" | "width" | "height" | "z_index" | "content">> & { id: number }>): Promise<{ nodes: CanvasNode[] }> {
  return client.patch(`/canvases/${projectId}/nodes/batch`, { nodes });
}

export function createCanvasGroup(projectId: string, data: {
  name: string;
  color: string;
  node_ids: number[];
  nodes: Array<Partial<Pick<CanvasNode, "x" | "y" | "z_index">> & { id: number }>;
  x: number;
  y: number;
  width: number;
  height: number;
  z_index: number;
}): Promise<{ group: CanvasGroup; nodes: CanvasNode[] }> {
  return client.post(`/canvases/${projectId}/groups`, data);
}

export function updateCanvasGroup(projectId: string, groupId: number, data: Partial<Pick<CanvasGroup, "name" | "color" | "x" | "y" | "width" | "height" | "z_index">>): Promise<CanvasGroup> {
  return client.patch(`/canvases/${projectId}/groups/${groupId}`, data);
}

export function assignCanvasNodesToGroup(projectId: string, groupId: number, nodes: Array<Partial<Pick<CanvasNode, "x" | "y" | "z_index">> & { id: number }>): Promise<CanvasGroupAssignNodesResponse> {
  return client.post(`/canvases/${projectId}/groups/${groupId}/nodes`, { nodes });
}

export function removeCanvasNodesFromGroups(projectId: string, nodes: Array<Partial<Pick<CanvasNode, "x" | "y" | "z_index">> & { id: number }>): Promise<CanvasGroupRemoveNodesResponse> {
  return client.post(`/canvases/${projectId}/groups/nodes/remove`, { nodes });
}

export function deleteCanvasGroup(projectId: string, groupId: number): Promise<void> {
  return client.delete(`/canvases/${projectId}/groups/${groupId}`);
}

export function deleteCanvasNode(projectId: string, nodeId: number): Promise<void> {
  return client.delete(`/canvases/${projectId}/nodes/${nodeId}`);
}

export function updateCanvasEdge(projectId: string, edgeId: number, data: { is_collapsed?: boolean }): Promise<CanvasEdge> {
  return client.patch(`/canvases/${projectId}/edges/${edgeId}`, data);
}

export function createCanvasNode(projectId: string, data: {
  node_type: "text" | "image";
  content?: string;
  image_url?: string;
  x: number;
  y: number;
  width?: number;
  height?: number;
}): Promise<CanvasNode> {
  return client.post(`/canvases/${projectId}/nodes`, data);
}

export function createCanvasTask(projectId: string, data: CanvasTaskPayload): Promise<CanvasTaskCreateResponse> {
  return client.post(`/canvases/${projectId}/tasks`, {
    ...data,
    source: data.source || "web",
  });
}

export function createCanvasVideoTask(projectId: string, data: CanvasVideoTaskPayload): Promise<CanvasTaskCreateResponse> {
  return client.post(`/canvases/${projectId}/video-tasks`, {
    ...data,
    source: data.source || "web",
  });
}
