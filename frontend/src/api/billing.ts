import { api } from "../lib/api";

export interface Plan {
  id: number;
  name: string;
  price: string;
  duration_days: number;
  description: string;
  is_active: boolean;
}

export type PaymentMethod = "cash" | "upi" | "bank_transfer" | "card" | "other";
export type PaymentStatus = "completed" | "pending" | "failed" | "refunded";

export interface Payment {
  id: number;
  member: number;
  member_username: string;
  plan: number;
  plan_name: string;
  amount: string;
  method: PaymentMethod;
  status: PaymentStatus;
  paid_date: string;
  period_start: string;
  period_end: string;
  notes: string;
  recorded_by: number | null;
  external_reference: string;
  gateway: string;
  created_at: string;
}

export interface MyPayment {
  id: number;
  plan_name: string;
  amount: string;
  method: PaymentMethod;
  status: PaymentStatus;
  paid_date: string;
  period_start: string;
  period_end: string;
}

export interface MySubscription {
  plan: { id: number; name: string; price: string } | null;
  status: string;
  period_start: string | null;
  period_end: string | null;
  days_remaining: number | null;
}

export interface AdminMemberBilling {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  membership_status: string;
  current_plan_name: string | null;
  current_period_end: string | null;
  last_payment_date: string | null;
  last_payment_amount: string | null;
}

export async function fetchPlans() {
  const res = await api.get<{ results: Plan[] }>("/billing/plans/");
  return res.data.results;
}

export async function createPlan(payload: Omit<Plan, "id">) {
  const res = await api.post<Plan>("/billing/plans/", payload);
  return res.data;
}

export async function updatePlan(id: number, payload: Partial<Omit<Plan, "id">>) {
  const res = await api.patch<Plan>(`/billing/plans/${id}/`, payload);
  return res.data;
}

export async function deletePlan(id: number) {
  await api.delete(`/billing/plans/${id}/`);
}

export async function fetchMySubscription() {
  const res = await api.get<MySubscription>("/billing/my-subscription/");
  return res.data;
}

export async function fetchMyPayments() {
  const res = await api.get<{ results: MyPayment[] }>("/billing/my-payments/");
  return res.data.results;
}

export async function fetchAdminMemberBilling() {
  const res = await api.get<{ results: AdminMemberBilling[] }>("/billing/admin/members/");
  return res.data.results;
}

export async function downloadAdminMemberBillingExcel() {
  const res = await api.get("/billing/admin/members/export/", { responseType: "blob" });
  const url = window.URL.createObjectURL(new Blob([res.data]));
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", "gym_billing.xlsx");
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export async function fetchAdminPayments(memberId?: number) {
  const res = await api.get<{ results: Payment[] }>("/billing/admin/payments/", {
    params: memberId ? { member: memberId } : undefined,
  });
  return res.data.results;
}

export interface RecordPaymentPayload {
  member: number;
  plan: number;
  amount: string;
  method: PaymentMethod;
  paid_date?: string;
  notes?: string;
}

export async function recordPayment(payload: RecordPaymentPayload) {
  const res = await api.post<Payment>("/billing/admin/payments/", payload);
  return res.data;
}

export async function deletePayment(id: number) {
  await api.delete(`/billing/admin/payments/${id}/`);
}
