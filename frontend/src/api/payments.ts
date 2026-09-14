import client from "./client";
import type { CreatePaymentOrderResult, PaymentOrder, PaymentPlan } from "@/types";

export function listPaymentPlans(): Promise<{ items: PaymentPlan[] }> {
  return client.get("/payment/plans");
}

export function createPaymentOrder(planKey: string): Promise<CreatePaymentOrderResult> {
  return client.post("/payment/orders", { plan_key: planKey });
}

export function getPaymentOrder(orderNo: string): Promise<PaymentOrder> {
  return client.get(`/payment/orders/${orderNo}`);
}

export function getPaymentOrderResult(orderNo: string, token: string): Promise<PaymentOrder> {
  return client.get(`/payment/orders/${orderNo}/result`, { params: { token } });
}
