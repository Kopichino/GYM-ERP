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

// ------------------------------------------------------- offers & checkout

export type DiscountType = "percent" | "flat";

export interface Discount {
  id: number;
  code: string;
  description: string;
  discount_type: DiscountType;
  value: string;
  plans: number[];
  plan_names: string[];
  valid_from: string;
  valid_until: string | null;
  max_uses: number | null;
  max_uses_per_member: number;
  is_active: boolean;
  times_used: number;
  created_at: string;
}

export interface CheckoutQuote {
  member: number;
  member_name: string;
  plan: number;
  plan_name: string;
  list_price: string;
  discount_code: string | null;
  discount_label: string | null;
  discount_amount: string;
  total: string;
  /** True when an operator typed the amount instead of taking the computed one. */
  custom_amount: boolean;
  period_start: string;
  period_end: string;
  /** True when the member still has time left, so this stacks on the end. */
  extends_existing: boolean;
}

export interface CheckoutRequest {
  member: number;
  plan: number;
  code?: string;
  /** Overrides the computed total -- for negotiated or part payments. */
  amount?: string;
  method?: string;
  paid_date?: string;
  notes?: string;
}

export async function fetchDiscounts() {
  const res = await api.get<{ results: Discount[] }>("/billing/discounts/");
  return res.data.results;
}

export async function createDiscount(payload: Partial<Discount>) {
  const res = await api.post<Discount>("/billing/discounts/", payload);
  return res.data;
}

export async function updateDiscount(id: number, payload: Partial<Discount>) {
  const res = await api.patch<Discount>(`/billing/discounts/${id}/`, payload);
  return res.data;
}

export async function deleteDiscount(id: number) {
  await api.delete(`/billing/discounts/${id}/`);
}

/** Prices the sale without writing anything. */
export async function quoteCheckout(payload: CheckoutRequest) {
  const res = await api.post<CheckoutQuote>("/billing/checkout/quote/", payload);
  return res.data;
}

export async function commitCheckout(payload: CheckoutRequest) {
  const res = await api.post<CheckoutQuote & { payment: unknown }>("/billing/checkout/", payload);
  return res.data;
}

// ---------------------------------------------------------------- invoices

export interface Invoice {
  id: number;
  number: string;
  issued_on: string;
  payment: number;
  member_name: string;
  plan_name: string;
  amount_paid: string;
  taxable_value: string;
  cgst: string;
  sgst: string;
  igst: string;
  total: string;
  tax_rate: string;
  is_interstate: boolean;
  place_of_supply: string;
}

export async function fetchInvoices(memberId?: number) {
  const res = await api.get<{ results: Invoice[] }>("/invoices/", {
    params: memberId ? { member: memberId } : undefined,
  });
  return res.data.results;
}

/** Opens the PDF in a new tab. The endpoint serves it inline. */
export async function openInvoicePdf(id: number) {
  const res = await api.get(`/invoices/${id}/pdf/`, { responseType: "blob" });
  const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
  window.open(url, "_blank");
  // Revoked on a delay so the new tab has time to read it.
  setTimeout(() => window.URL.revokeObjectURL(url), 60_000);
}

/** Issues the invoice for a payment that predates invoicing. Idempotent. */
export async function issueInvoice(paymentId: number) {
  const res = await api.post<Invoice>("/invoices/issue/", { payment: paymentId });
  return res.data;
}

// -------------------------------------------------------- online payment

export interface OnlineConfig {
  /** False when the gym hasn't set up a gateway; the button stays hidden. */
  enabled: boolean;
  key_id: string;
}

export interface OnlineOrder {
  order_id: string;
  amount: string;
  discount_amount: string;
  plan_name: string;
  key_id: string;
  member_name: string;
  email: string;
}

export async function fetchOnlineConfig() {
  const res = await api.get<OnlineConfig>("/billing/online/config/");
  return res.data;
}

/** The server prices this; anything the browser sends about money is ignored. */
export async function createOnlineOrder(plan: number, code?: string) {
  const res = await api.post<OnlineOrder>("/billing/online/order/", { plan, code });
  return res.data;
}

export async function verifyOnlinePayment(payload: {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}) {
  const res = await api.post("/billing/online/verify/", payload);
  return res.data;
}
