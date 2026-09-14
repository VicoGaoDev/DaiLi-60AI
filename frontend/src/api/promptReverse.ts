import client from "./client";

export function reversePrompt(image_url: string): Promise<{ prompt: string }> {
  return client.post("/prompt-reverse", { image_url });
}
