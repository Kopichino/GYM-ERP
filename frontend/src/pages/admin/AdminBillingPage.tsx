import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";
import { fetchMembers } from "../../api/admin";
import {
  downloadAdminMemberBillingExcel,
  fetchAdminMemberBilling,
  fetchAdminPayments,
  fetchInvoices,
  issueInvoice,
  openInvoicePdf,
} from "../../api/billing";
import CheckoutPanel from "../../components/CheckoutPanel";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "../../components/ui";
import { fadeUp, staggerContainer } from "../../lib/motion";
import { FALLBACK_STATUS_COLOR, STATUS_COLORS, railColor } from "../../lib/theme";

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

  // Keyed by payment so each ledger row knows whether its invoice exists yet.
  const { data: invoices } = useQuery({
    queryKey: ["invoices", "admin", selectedMemberId],
    queryFn: () => fetchInvoices(selectedMemberId ?? undefined),
  });
  const invoiceByPayment = new Map((invoices ?? []).map((i) => [i.payment, i]));

  const issue = useMutation({
    mutationFn: issueInvoice,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["invoices"] }),
  });

  const selectedMemberName = members?.find((m) => m.id === selectedMemberId)?.username;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 md:grid-cols-2">
        <CheckoutPanel />

        <Card accent={railColor(1)}>
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
            <div className="no-scrollbar max-h-96 overflow-auto">
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

      <Card accent={railColor(2)}>
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
          <div className="no-scrollbar overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Date</th>
                  <th className={tableHeadCellClass}>Member</th>
                  <th className={tableHeadCellClass}>Plan</th>
                  <th className={tableHeadCellClass}>Amount</th>
                  <th className={tableHeadCellClass}>Method</th>
                  <th className={tableHeadCellClass}>Status</th>
                  <th className={tableHeadCellClass}>Invoice</th>
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
                    <td className={tableCellClass}>
                      {invoiceByPayment.has(p.id) ? (
                        <Button
                          variant="secondary"
                          onClick={() => openInvoicePdf(invoiceByPayment.get(p.id)!.id)}
                          className="px-2 py-1 text-xs"
                        >
                          {invoiceByPayment.get(p.id)!.number}
                        </Button>
                      ) : (
                        <Button
                          variant="secondary"
                          onClick={() => issue.mutate(p.id)}
                          disabled={issue.isPending}
                          className="px-2 py-1 text-xs"
                        >
                          Issue
                        </Button>
                      )}
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
