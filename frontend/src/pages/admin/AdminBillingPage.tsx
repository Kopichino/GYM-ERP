import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";
import { fetchMembers } from "../../api/admin";
import {
  downloadAdminMemberBillingExcel,
  fetchAdminMemberBilling,
  fetchAdminPayments,
  fetchPlans,
  recordPayment,
  type PaymentMethod,
} from "../../api/billing";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  LoadingState,
  Select,
  Textarea,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "../../components/ui";
import { fadeUp, staggerContainer } from "../../lib/motion";
import { FALLBACK_STATUS_COLOR, STATUS_COLORS } from "../../lib/theme";

const METHODS: { value: PaymentMethod; label: string }[] = [
  { value: "cash", label: "Cash" },
  { value: "upi", label: "UPI" },
  { value: "bank_transfer", label: "Bank transfer" },
  { value: "card", label: "Card" },
  { value: "other", label: "Other" },
];

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? FALLBACK_STATUS_COLOR;
  return (
    <span
      className="rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide"
      style={{ color, backgroundColor: `${color}22` }}
    >
      {status || "-"}
    </span>
  );
}

export default function AdminBillingPage() {
  const queryClient = useQueryClient();
  const { data: members } = useQuery({ queryKey: ["admin", "members"], queryFn: fetchMembers });
  const { data: plans } = useQuery({ queryKey: ["billing", "plans", "admin"], queryFn: fetchPlans });
  const {
    data: billingRows,
    isLoading: billingLoading,
    isError: billingError,
  } = useQuery({ queryKey: ["billing", "admin", "members"], queryFn: fetchAdminMemberBilling });

  const [selectedMemberId, setSelectedMemberId] = useState<number | null>(null);
  const { data: payments, isLoading: paymentsLoading } = useQuery({
    queryKey: ["billing", "admin", "payments", selectedMemberId],
    queryFn: () => fetchAdminPayments(selectedMemberId ?? undefined),
  });

  const [form, setForm] = useState({
    member: "",
    plan: "",
    amount: "",
    method: "cash" as PaymentMethod,
    paid_date: "",
    notes: "",
  });

  const record = useMutation({
    mutationFn: () =>
      recordPayment({
        member: Number(form.member),
        plan: Number(form.plan),
        amount: form.amount,
        method: form.method,
        paid_date: form.paid_date || undefined,
        notes: form.notes,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["billing"] });
      setForm({ member: "", plan: "", amount: "", method: "cash", paid_date: "", notes: "" });
    },
  });

  const activePlans = plans?.filter((p) => p.is_active) ?? [];
  const selectedMemberName = members?.find((m) => m.id === selectedMemberId)?.username;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Record payment
          </h2>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              record.mutate();
            }}
            className="flex flex-col gap-3"
          >
            <Select
              value={form.member}
              onChange={(e) => setForm((f) => ({ ...f, member: e.target.value }))}
              required
            >
              <option value="">Select member</option>
              {members?.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.username}
                </option>
              ))}
            </Select>
            <Select value={form.plan} onChange={(e) => setForm((f) => ({ ...f, plan: e.target.value }))} required>
              <option value="">Select plan</option>
              {activePlans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} - {p.price} ({p.duration_days}d)
                </option>
              ))}
            </Select>
            <div className="flex gap-3">
              <Input
                type="number"
                step="0.01"
                min="0"
                placeholder="Amount"
                value={form.amount}
                onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
                required
                className="flex-1"
              />
              <Select
                value={form.method}
                onChange={(e) => setForm((f) => ({ ...f, method: e.target.value as PaymentMethod }))}
                className="flex-1"
              >
                {METHODS.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </Select>
            </div>
            <label className="text-xs text-[var(--color-text-muted)]">
              Paid date (defaults to today)
              <Input
                type="date"
                value={form.paid_date}
                onChange={(e) => setForm((f) => ({ ...f, paid_date: e.target.value }))}
                className="mt-1"
              />
            </label>
            <Textarea
              placeholder="Notes (optional)"
              rows={2}
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            />
            <Button type="submit" disabled={record.isPending}>
              {record.isPending ? "Recording..." : "Record payment"}
            </Button>
            {record.isError && (
              <ErrorState>Couldn't record that payment -- check the fields and try again.</ErrorState>
            )}
          </form>
        </Card>

        <Card>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              {billingRows?.length ?? 0} members
            </h2>
            <Button onClick={() => downloadAdminMemberBillingExcel()}>Download as Excel</Button>
          </div>
          {billingLoading ? (
            <LoadingState />
          ) : billingError ? (
            <ErrorState />
          ) : (
            <div className="max-h-96 overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-[var(--color-text-muted)]">
                  <tr className={tableHeadRowClass}>
                    <th className={tableHeadCellClass}>Member</th>
                    <th className={tableHeadCellClass}>Status</th>
                    <th className={tableHeadCellClass}>Plan</th>
                    <th className={tableHeadCellClass}>Expiry</th>
                  </tr>
                </thead>
                <tbody>
                  {billingRows?.map((row) => (
                    <tr
                      key={row.id}
                      onClick={() => setSelectedMemberId(row.id)}
                      className={`${tableRowClass} cursor-pointer hover:bg-[var(--color-surface-2)] ${
                        selectedMemberId === row.id ? "bg-[var(--color-surface-2)]" : ""
                      }`}
                    >
                      <td className={tableCellClass}>{row.username}</td>
                      <td className={tableCellClass}>
                        <StatusBadge status={row.membership_status} />
                      </td>
                      <td className={tableCellClass}>{row.current_plan_name ?? "-"}</td>
                      <td className={tableCellClass}>
                        {row.current_period_end ? new Date(row.current_period_end).toLocaleDateString() : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {billingRows?.length === 0 && <EmptyState>No members yet.</EmptyState>}
            </div>
          )}
        </Card>
      </div>

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Payments ledger{selectedMemberName ? ` -- ${selectedMemberName}` : ""}
          </h2>
          {selectedMemberId && (
            <Button variant="secondary" onClick={() => setSelectedMemberId(null)} className="px-2 py-1 text-xs">
              Show all
            </Button>
          )}
        </div>
        {paymentsLoading ? (
          <LoadingState />
        ) : payments?.length === 0 ? (
          <EmptyState>No payments recorded yet.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Date</th>
                  <th className={tableHeadCellClass}>Member</th>
                  <th className={tableHeadCellClass}>Plan</th>
                  <th className={tableHeadCellClass}>Amount</th>
                  <th className={tableHeadCellClass}>Method</th>
                  <th className={tableHeadCellClass}>Status</th>
                </tr>
              </thead>
              <motion.tbody initial="hidden" animate="visible" variants={staggerContainer(0.03)}>
                {payments?.map((p) => (
                  <motion.tr key={p.id} variants={fadeUp} className={tableRowClass}>
                    <td className={tableCellClass}>{new Date(p.paid_date).toLocaleDateString()}</td>
                    <td className={tableCellClass}>{p.member_username}</td>
                    <td className={tableCellClass}>{p.plan_name}</td>
                    <td className={tableCellClass}>{p.amount}</td>
                    <td className={tableCellClass}>{p.method.replace("_", " ")}</td>
                    <td className={tableCellClass}>
                      <StatusBadge status={p.status} />
                    </td>
                  </motion.tr>
                ))}
              </motion.tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
