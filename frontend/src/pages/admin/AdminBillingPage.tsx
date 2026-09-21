import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";
import {
  downloadAdminMemberBillingExcel,
  fetchAdminMemberBilling,
  fetchAdminPayments,
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
  Pager,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "../../components/ui";
import { fadeUp, staggerContainer } from "../../lib/motion";
import { PAGE_SIZE } from "../../lib/pagination";
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

interface SelectedMember {
  id: number;
  username: string;
}

export default function AdminBillingPage() {
  const queryClient = useQueryClient();

  // Both lists are paginated by the server, so each keeps its own page, and
  // every count shown comes from the server's total rather than from the rows
  // on screen -- a page of twenty is not a gym of twenty.
  const [membersPage, setMembersPage] = useState(1);
  const {
    data: billing,
    isLoading: billingLoading,
    isError: billingError,
  } = useQuery({
    queryKey: ["billing", "admin", "members", membersPage],
    queryFn: () => fetchAdminMemberBilling(membersPage),
    placeholderData: keepPreviousData,
  });

  const [selectedMember, setSelectedMember] = useState<SelectedMember | null>(null);
  const [ledgerPage, setLedgerPage] = useState(1);
  const {
    data: ledger,
    isLoading: paymentsLoading,
    isError: paymentsError,
  } = useQuery({
    queryKey: ["billing", "admin", "payments", selectedMember?.id ?? null, ledgerPage],
    queryFn: () => fetchAdminPayments(selectedMember?.id, ledgerPage),
    placeholderData: keepPreviousData,
  });
  const payments = ledger?.results;

  // Switching whose payments are shown starts that ledger from its first page.
  function showLedgerFor(member: SelectedMember | null) {
    setSelectedMember(member);
    setLedgerPage(1);
  }

  const issue = useMutation({
    mutationFn: issueInvoice,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["billing", "admin", "payments"] }),
  });

  return (
    <div className="flex flex-col gap-6">
      {/* `grid-cols-1` is what keeps a phone to its own width: without a column
          count below md the one implicit column sizes to its widest content --
          the member table, the checkout pickers -- and the page scrolled sideways. */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <CheckoutPanel />

        <Card accent={railColor(1)}>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              {billing?.count ?? 0} members
            </h2>
            <Button onClick={() => downloadAdminMemberBillingExcel()}>Download as Excel</Button>
          </div>
          {billingLoading ? (
            <LoadingState />
          ) : billingError ? (
            <ErrorState />
          ) : (
            <>
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
                    {billing?.results.map((row) => (
                      <tr
                        key={row.id}
                        onClick={() => showLedgerFor({ id: row.id, username: row.username })}
                        className={`${tableRowClass} cursor-pointer hover:bg-[var(--color-surface-2)] ${
                          selectedMember?.id === row.id ? "bg-[var(--color-surface-2)]" : ""
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
                {billing?.results.length === 0 && <EmptyState>No members yet.</EmptyState>}
              </div>
              <Pager
                page={membersPage}
                pageSize={PAGE_SIZE}
                count={billing?.count ?? 0}
                onPage={setMembersPage}
                noun="members"
              />
            </>
          )}
        </Card>
      </div>

      <Card accent={railColor(2)}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Payments ledger{selectedMember ? ` -- ${selectedMember.username}` : ""}
            {ledger ? ` (${ledger.count})` : ""}
          </h2>
          {selectedMember && (
            <Button variant="secondary" onClick={() => showLedgerFor(null)} className="px-2 py-1 text-xs">
              Show all
            </Button>
          )}
        </div>
        {paymentsLoading ? (
          <LoadingState />
        ) : paymentsError ? (
          <ErrorState />
        ) : payments?.length === 0 ? (
          <EmptyState>No payments recorded yet.</EmptyState>
        ) : (
          <>
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
                <motion.tbody
                  key={`${selectedMember?.id ?? "all"}-${ledgerPage}`}
                  initial="hidden"
                  animate="visible"
                  variants={staggerContainer(0.03)}
                >
                  {payments?.map((p) => {
                    const invoice = p.invoice;
                    return (
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
                          {invoice ? (
                            <Button
                              variant="secondary"
                              onClick={() => openInvoicePdf(invoice.id)}
                              className="px-2 py-1 text-xs"
                            >
                              {invoice.number}
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
                    );
                  })}
                </motion.tbody>
              </table>
            </div>
            <Pager
              page={ledgerPage}
              pageSize={PAGE_SIZE}
              count={ledger?.count ?? 0}
              onPage={setLedgerPage}
              noun="payments"
            />
          </>
        )}
      </Card>
    </div>
  );
}
