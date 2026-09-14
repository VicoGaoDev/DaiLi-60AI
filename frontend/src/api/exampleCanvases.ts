import client from "./client";
import type {
  ExampleCanvasCopyResponse,
  ExampleCanvasProject,
  ExampleCanvasProjectCreatePayload,
  ExampleCanvasProjectListResponse,
  ExampleCanvasProjectUpdatePayload,
} from "@/types";

export function listExampleCanvasProjects(): Promise<ExampleCanvasProjectListResponse> {
  return client.get("/canvases/example-projects");
}

export function copyExampleCanvasProject(exampleId: number): Promise<ExampleCanvasCopyResponse> {
  return client.post(`/canvases/example-projects/${exampleId}/copy`);
}

export function listAdminExampleCanvasProjects(): Promise<ExampleCanvasProjectListResponse> {
  return client.get("/admin/example-canvases");
}

export function createAdminExampleCanvasProject(payload: ExampleCanvasProjectCreatePayload): Promise<ExampleCanvasProject> {
  return client.post("/admin/example-canvases", payload);
}

export function updateAdminExampleCanvasProject(
  exampleId: number,
  payload: ExampleCanvasProjectUpdatePayload,
): Promise<ExampleCanvasProject> {
  return client.put(`/admin/example-canvases/${exampleId}`, payload);
}

export function deleteAdminExampleCanvasProject(exampleId: number): Promise<void> {
  return client.delete(`/admin/example-canvases/${exampleId}`);
}
