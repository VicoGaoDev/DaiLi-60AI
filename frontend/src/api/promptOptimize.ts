import client from "./client";

export function optimizePrompt(data: {
  prompt: string;
  reference_images?: string[];
  style_name: string;
  style_prompt: string;
}, signal?: AbortSignal): Promise<{ prompt: string }> {
  return client.post("/prompt-optimize", data, { signal });
}
