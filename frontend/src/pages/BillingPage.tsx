import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { fetchMyPayments, fetchMySubscription } from "../api/billing";
import {
  AnimatedNumber,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "../components/ui";
import { fadeUp, staggerContainer } from "../lib/motion";
import { FALLBACK_STATUS_COLOR, STATUS_COLORS } from "../lib/theme";

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? FALLBACK_STATUS_COLOR;
  return (
    <span
      className="rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide"
      style={{ color, backgroundColor: `${color}22` }}
    >
      {status}
    </span>
  );
}

export default function BillingPage() {
  const {
    data: subscription,
    isLoading: subLoading,
    isError: subError,
  } = useQuery({ queryKey: ["billing", "my-subscription"], queryFn: fetchMySubscription });

  const {
    data: payments,
    isLoading: paymentsLoading,
    isError: paymentsError,
  } = useQuery({ queryKey: ["billing", "my-payments"], queryFn: fetchMyPayments });

  return (
    <div>
      <PageHeader title="Billing" subtitle="Your current plan and payment history." />

      <Card className="mb-6">
        {subLoading ? (
          <LoadingState label="Loading your subscription..." />
        ) : subError ? (
          <ErrorState />
        ) : !subscription?.plan ? (
          <EmptyState>No active subscription yet -- contact the front desk to get started.</EmptyState>
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="flex flex-wrap items-end justify-between gap-6"
          >
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                Current plan
              </h2>
              <p className="font-display text-3xl uppercase tracking-wide text-[var(--color-text)]">
                {subscription.plan.name}
              </p>
              <div className="mt-2">
                <StatusBadge status={subscription.status} />
              </div>
            </div>
            <div className="text-right">
              <p className="font-display text-4xl text-[var(--color-accent)]">
                <AnimatedNumber value={subscription.days_remaining ?? 0} />
              </p>
              <p className="text-xs uppercase tracking-wide text-[var(--color-text-muted)]">Days remaining</p>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                Expires{" "}
                {subscription.period_end ? new Date(subscription.period_end).toLocaleDateString() : "-"}
              </p>
            </div>
          </motion.div>
        )}
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Payment history
        </h2>
        {paymentsLoading ? (
          <LoadingState />
        ) : paymentsError ? (
          <ErrorState />
        ) : payments?.length === 0 ? (
          <EmptyState>No payments recorded yet.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Date</th>
                  <th className={tableHeadCellClass}>Plan</th>
                  <th className={tableHeadCellClass}>Amount</th>
                  <th className={tableHeadCellClass}>Method</th>
                  <th className={tableHeadCellClass}>Status</th>
                  <th className={tableHeadCellClass}>Period</th>
                </tr>
              </thead>
              <motion.tbody initial="hidden" animate="visible" variants={staggerContainer(0.04)}>
                {payments?.map((p) => (
                  <motion.tr key={p.id} variants={fadeUp} className={tableRowClass}>
                    <td className={tableCellClass}>{new Date(p.paid_date).toLocaleDateString()}</td>
                    <td className={tableCellClass}>{p.plan_name}</td>
                    <td className={tableCellClass}>{p.amount}</td>
                    <td className={tableCellClass}>{p.method.replace("_", " ")}</td>
                    <td className={tableCellClass}>
                      <StatusBadge status={p.status} />
                    </td>
                    <td className={tableCellClass}>
                      {new Date(p.period_start).toLocaleDateString()} -{" "}
                      {new Date(p.period_end).toLocaleDateString()}
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
