import { dateRangeProblem, isoDate } from "../../lib/dates";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  fetchAttendanceReport,
  fetchChurn,
  fetchPtPerformance,
  fetchRevenue,
} from "../../api/reports";
import {
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  Input,
  LoadingState,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "../../components/ui";
import { serverMessage } from "../../lib/apiError";
import { railColor } from "../../lib/theme";
import CustomReportBuilder from "../../components/CustomReportBuilder";

const TABS = ["Revenue", "Attendance", "Churn", "PT performance", "Custom"] as const;
type Tab = (typeof TABS)[number];

const GENERIC_ERROR = "Something went wrong. Please try again.";

const daysAgo = (n: number) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return isoDate(d);
};

function Stat({ label, value, colour }: { label: string; value: string; colour?: string }) {
  return (
    <div>
      <p className="font-display text-3xl leading-none" style={{ color: colour ?? "var(--color-text)" }}>
        {value}
      </p>
      <p className="mt-1 text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">{label}</p>
    </div>
  );
}

/** A plain horizontal bar, so a breakdown reads at a glance without pulling in
 *  a charting library for what is essentially a ranked list. */
function BarRow({ label, value, max, suffix = "" }: { label: string; value: number; max: number; suffix?: string }) {
  return (
    <li className="py-2">
      <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
        <span className="text-[var(--color-text)]">{label}</span>
        <span className="text-[var(--color-text-muted)]">
          {value}
          {suffix}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-2)]">
        <div
          className="h-full rounded-full bg-[var(--color-accent)]"
          style={{ width: `${max ? (value / max) * 100 : 0}%` }}
        />
      </div>
    </li>
  );
}

export default function AdminReportsPage() {
  const [tab, setTab] = useState<Tab>("Revenue");
  const [start, setStart] = useState(daysAgo(29));
  const [end, setEnd] = useState(isoDate(new Date()));
  const window_ = { start, end };
  // Caught here and said next to the dates, rather than sent off to be refused
  // and shown as "Something went wrong".
  const rangeProblem = dateRangeProblem(start, end);

  const revenue = useQuery({
    queryKey: ["reports", "revenue", start, end],
    queryFn: () => fetchRevenue(window_),
    enabled: tab === "Revenue" && !rangeProblem,
  });
  const attendance = useQuery({
    queryKey: ["reports", "attendance", start, end],
    queryFn: () => fetchAttendanceReport(window_),
    enabled: tab === "Attendance" && !rangeProblem,
  });
  const churn = useQuery({
    queryKey: ["reports", "churn", start, end],
    queryFn: () => fetchChurn(window_),
    enabled: tab === "Churn" && !rangeProblem,
  });
  const pt = useQuery({
    queryKey: ["reports", "pt", start, end],
    queryFn: () => fetchPtPerformance(window_),
    enabled: tab === "PT performance" && !rangeProblem,
  });

  return (
    <div className="flex flex-col gap-6">
      <Card accent={railColor(0)}>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-wrap gap-1">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  tab === t
                    ? "bg-[var(--color-accent)] text-white"
                    : "text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          {tab !== "Custom" && (
            <div className="flex gap-2">
              <label className="text-xs text-[var(--color-text-muted)]">
                From
                <Input
                  type="date"
                  value={start}
                  max={end || undefined}
                  onChange={(e) => setStart(e.target.value)}
                  className="mt-1"
                />
              </label>
              <label className="text-xs text-[var(--color-text-muted)]">
                To
                <Input
                  type="date"
                  value={end}
                  min={start || undefined}
                  aria-invalid={Boolean(rangeProblem)}
                  onChange={(e) => setEnd(e.target.value)}
                  className="mt-1"
                />
              </label>
            </div>
          )}
        </div>
        {tab !== "Custom" && rangeProblem && (
          <div className="mt-2 flex justify-end">
            <ErrorText>{rangeProblem}</ErrorText>
          </div>
        )}
      </Card>

      {tab === "Revenue" && !rangeProblem && (
        <>
          <Card accent={railColor(1)}>
            {revenue.isLoading ? (
              <LoadingState />
            ) : revenue.isError ? (
              <ErrorState>{serverMessage(revenue.error, GENERIC_ERROR)}</ErrorState>
            ) : revenue.data ? (
              <div className="grid grid-cols-2 gap-5 sm:grid-cols-5">
                <Stat label="Collected" value={revenue.data.collected} colour="#22c55e" />
                <Stat label="Expenses" value={revenue.data.expenses} colour="var(--color-accent)" />
                <Stat label="Net" value={revenue.data.net} />
                <Stat label="Discounts given" value={revenue.data.discounts_given} colour="var(--color-accent-2)" />
                <Stat label="Payments" value={String(revenue.data.payment_count)} />
              </div>
            ) : null}
          </Card>

          {revenue.data && (
            <div className="grid gap-6 lg:grid-cols-2">
              <Card accent={railColor(2)}>
                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                  By plan
                </h3>
                {!revenue.data.by_plan.length ? (
                  <EmptyState>No payments in this window.</EmptyState>
                ) : (
                  <ul className="flex flex-col">
                    {revenue.data.by_plan.map((r) => (
                      <BarRow
                        key={r.plan}
                        label={`${r.plan} (${r.count})`}
                        value={Number(r.total)}
                        max={Math.max(...revenue.data!.by_plan.map((x) => Number(x.total)))}
                      />
                    ))}
                  </ul>
                )}
              </Card>
              <Card accent={railColor(3)}>
                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                  By payment method
                </h3>
                {!revenue.data.by_method.length ? (
                  <EmptyState>Nothing to show.</EmptyState>
                ) : (
                  <ul className="flex flex-col">
                    {revenue.data.by_method.map((r) => (
                      <BarRow
                        key={r.method}
                        label={r.method}
                        value={Number(r.total)}
                        max={Math.max(...revenue.data!.by_method.map((x) => Number(x.total)))}
                      />
                    ))}
                  </ul>
                )}
              </Card>
            </div>
          )}
        </>
      )}

      {tab === "Attendance" && !rangeProblem && (
        <Card accent={railColor(1)}>
          {attendance.isLoading ? (
            <LoadingState />
          ) : attendance.isError ? (
            <ErrorState>{serverMessage(attendance.error, GENERIC_ERROR)}</ErrorState>
          ) : attendance.data ? (
            <>
              <div className="mb-6 grid grid-cols-2 gap-5 sm:grid-cols-4">
                <Stat label="Visits" value={String(attendance.data.total_visits)} />
                <Stat label="Members who came" value={String(attendance.data.unique_members)} />
                <Stat label="Of all members" value={`${attendance.data.participation_pct}%`} colour="#22c55e" />
                <Stat label="Members total" value={String(attendance.data.member_count)} />
              </div>
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                Busiest hours
              </h3>
              {!attendance.data.by_hour.length ? (
                <EmptyState>No check-ins in this window.</EmptyState>
              ) : (
                <ul className="flex flex-col">
                  {attendance.data.by_hour.map((h) => (
                    <BarRow
                      key={h.hour}
                      label={`${String(h.hour).padStart(2, "0")}:00`}
                      value={h.count}
                      max={Math.max(...attendance.data!.by_hour.map((x) => x.count))}
                    />
                  ))}
                </ul>
              )}
            </>
          ) : null}
        </Card>
      )}

      {tab === "Churn" && !rangeProblem && (
        <Card accent={railColor(1)}>
          {churn.isLoading ? (
            <LoadingState />
          ) : churn.isError ? (
            <ErrorState>{serverMessage(churn.error, GENERIC_ERROR)}</ErrorState>
          ) : churn.data ? (
            <>
              <div className="mb-4 grid grid-cols-3 gap-5">
                <Stat label="Churned" value={String(churn.data.churned_count)} colour="var(--color-accent)" />
                <Stat label="Retained" value={String(churn.data.retained_count)} colour="#22c55e" />
                <Stat label="Churn rate" value={`${churn.data.churn_rate_pct}%`} />
              </div>
              {/* Churn has no single agreed meaning, so the report says what it
                  counted rather than leaving the reader to assume. */}
              <p className="mb-4 border-l-2 border-[var(--color-accent-2)] pl-3 text-xs text-[var(--color-text-muted)]">
                {churn.data.definition}
              </p>
              {!churn.data.members.length ? (
                <EmptyState>Nobody lapsed in this window.</EmptyState>
              ) : (
                <div className="no-scrollbar overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-[var(--color-text-muted)]">
                      <tr className={tableHeadRowClass}>
                        <th className={tableHeadCellClass}>Member</th>
                        <th className={tableHeadCellClass}>Last plan</th>
                        <th className={tableHeadCellClass}>Expired</th>
                        <th className={tableHeadCellClass}>Days lapsed</th>
                      </tr>
                    </thead>
                    <tbody>
                      {churn.data.members.map((m) => (
                        <tr key={m.member} className={tableRowClass}>
                          <td className={tableCellClass}>{m.name}</td>
                          <td className={tableCellClass}>{m.last_plan}</td>
                          <td className={tableCellClass}>{new Date(m.expired_on).toLocaleDateString()}</td>
                          <td className={tableCellClass} style={{ color: "var(--color-accent)" }}>
                            {m.days_lapsed}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          ) : null}
        </Card>
      )}

      {tab === "PT performance" && !rangeProblem && (
        <Card accent={railColor(1)}>
          {pt.isLoading ? (
            <LoadingState />
          ) : pt.isError ? (
            <ErrorState>{serverMessage(pt.error, GENERIC_ERROR)}</ErrorState>
          ) : !pt.data?.trainers.length ? (
            <EmptyState>No trainers yet.</EmptyState>
          ) : (
            <div className="no-scrollbar overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-[var(--color-text-muted)]">
                  <tr className={tableHeadRowClass}>
                    <th className={tableHeadCellClass}>Trainer</th>
                    <th className={tableHeadCellClass}>Members</th>
                    <th className={tableHeadCellClass}>Revenue</th>
                    <th className={tableHeadCellClass}>Payments</th>
                    <th className={tableHeadCellClass}>Member visits</th>
                  </tr>
                </thead>
                <tbody>
                  {pt.data.trainers.map((t) => (
                    <tr key={t.trainer} className={tableRowClass}>
                      <td className={tableCellClass}>{t.name}</td>
                      <td className={tableCellClass}>{t.member_count}</td>
                      <td className={tableCellClass}>{t.revenue}</td>
                      <td className={tableCellClass}>{t.payment_count}</td>
                      <td className={tableCellClass}>{t.member_visits}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "Custom" && <CustomReportBuilder />}
    </div>
  );
}
