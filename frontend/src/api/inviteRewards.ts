import client from "./client";
import type {
  InviteRewardLogListResponse,
  InviteRewardOverviewResponse,
  InviteRewardReferralListResponse,
} from "@/types";

export function getInviteRewardOverview(): Promise<InviteRewardOverviewResponse> {
  return client.get("/auth/invite-rewards/me");
}

export function getInviteRewardReferrals(page = 1, pageSize = 10): Promise<InviteRewardReferralListResponse> {
  return client.get("/auth/invite-rewards/referrals", {
    params: { page, page_size: pageSize },
  });
}

export function getInviteRewardLogs(page = 1, pageSize = 10): Promise<InviteRewardLogListResponse> {
  return client.get("/auth/invite-rewards/logs", {
    params: { page, page_size: pageSize },
  });
}

export function validateInviteCode(code: string): Promise<{ valid: boolean; code: string; platform_name: string }> {
  return client.get("/auth/invite-codes/validate", {
    params: { code },
  });
}
