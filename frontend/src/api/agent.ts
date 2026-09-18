import client from "./client";
import type { AdminRedeemKey, AdminRedeemKeyBatchResult, AgentOverview, CreditLog, RedeemKeyStatus } from "@/types";

export function getAgentOverview(): Promise<AgentOverview> {
  return client.get("/agent/overview");
}

export function getAgentCreditLogs(params?: {
  page?: number;
  page_size?: number;
  user_keyword?: string;
  type?: "allocate" | "agent_pool_deduct";
  redeem_key?: string;
  start_date?: string;
  end_date?: string;
  direction?: "increase" | "decrease";
}): Promise<{ total: number; redeemed_credits: number; items: CreditLog[] }> {
  return client.get("/agent/credit-logs", { params });
}

export function listAgentRedeemKeys(params?: {
  page?: number;
  page_size?: number;
  batch_no?: string;
  redeem_key?: string;
  credit_amount?: number;
  status?: RedeemKeyStatus;
  is_used?: boolean;
  used_by?: string;
  start_date?: string;
  end_date?: string;
}): Promise<{ total: number; items: AdminRedeemKey[] }> {
  return client.get("/agent/redeem-keys", { params });
}

export function createAgentRedeemKeysBatch(count: number, creditAmount: number): Promise<AdminRedeemKeyBatchResult> {
  return client.post("/agent/redeem-keys/batch", { count, credit_amount: creditAmount });
}

export function updateAgentRedeemKeyStatus(id: number, status: RedeemKeyStatus): Promise<AdminRedeemKey> {
  return client.post(`/agent/redeem-keys/${id}/status`, { status });
}

export function updateAgentRedeemKeyLock(id: number, isLocked: boolean): Promise<AdminRedeemKey> {
  return client.post(`/agent/redeem-keys/${id}/lock`, { is_locked: isLocked });
}

export function deleteAgentRedeemKey(id: number): Promise<{ ok: boolean }> {
  return client.delete(`/agent/redeem-keys/${id}`);
}
