import client from "./client";
import type { UserApiKey, UserApiKeyStatus } from "@/types";

export function listUserApiKeys(): Promise<{ items: UserApiKey[] }> {
  return client.get("/user-api-keys");
}

export function createUserApiKey(payload: {
  key_name?: string;
  expire_time?: string | null;
}): Promise<UserApiKey> {
  return client.post("/user-api-keys", payload);
}

export function updateUserApiKey(
  id: number,
  payload: {
    key_name?: string;
    status?: UserApiKeyStatus;
    expire_time?: string | null;
  }
): Promise<UserApiKey> {
  return client.patch(`/user-api-keys/${id}`, payload);
}

export function deleteUserApiKey(id: number): Promise<{ ok: boolean }> {
  return client.delete(`/user-api-keys/${id}`);
}
