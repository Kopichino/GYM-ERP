import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchKpis, fetchOccupancy } from "../../api/reports";
import AtRiskPanel from "../../components/AtRiskPanel";
import OccupancyHeatmap from "../../components/OccupancyHeatmap";
import {
  Card,
  ErrorState,
  Input,
  LoadingState,
} from "../../components/ui";
import { isoDaysFromNow, todayIso } from "../../lib/dates";
import { railColor, statusColor, thresholdStatus } from "../../lib/theme";

/** A headline number with the sentence that says what it counts. */
function Metric({
  value,
  label,
  hint,
  accent,
  definition,
}: {
  value: string | number;
  label: string;
  hint?: string;
  accent: string;
  definition?: string;
}) {
  return (
    <Card accent={accent}>
      <p className="font-display text-4xl leading-none" style={{ color: accent }}>
        {value}
      </p>
      <p className="mt-1 text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
        {label}
      </p>
      {hint && <p className="mt-1 text-xs text-[var(--color-text)]">{hint}</p>}
      {definition && (
        <p className="mt-2 border-t border-[var(--color-border)] pt-2 text-[11px] leading-snug text-[var(--color-text-muted)]">
          {definition}
        </p>
      )}
    </Card>
  );
}

export default function AdminOverviewPage() {
  const [from, setFrom] = useState(isoDaysFromNow(-29));
  const [to, setTo] = useState(todayIso());

  const { data: kpis, isLoading, isError } = useQuery({
    queryKey: ["kpis", from, to],
    queryFn: () => fetchKpis({ start: from, end: to }),
  });
  const { data: occupancy } = useQuery({
    queryKey: ["occupancy", from, to],
    // Eight weeks regardless of the KPI window: a heatmap of one week is
    // noise, and the pattern is what makes it worth looking at.
    queryFn: () => fetchOccupancy({ start: isoDaysFromNow(-55), end: todayIso() }),
  });

  const money = (value: string) => Number(value).toLocaleString(undefined, {
    maximumFractionDigits: 0,
  });

  return (
    <div className="flex flex-col gap-6">
      <Card accent={railColor(0)}>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              How the gym is doing
            </h2>
            <p className="mt-1 max-w-prose text-sm text-[var(--color-text-muted)]">
              Every figure here is worked out from payments, check-ins and bookings when you open
              the page — there is no month-end job to run and nothing cached that can disagree
              with the ledger.
            </p>
          </div>
          <div className="flex gap-2">
            <label className="text-xs text-[var(--color-text-muted)]">
              From
              <Input
                type="date"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
                className="mt-1"
              />
            </label>
            <label className="text-xs text-[var(--color-text-muted)]">
              To
              <Input
                type="date"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                className="mt-1"
              />
            </label>
          </div>
        </div>
      </Card>

      {isLoading ? (
        <Card>
          <LoadingState />
        </Card>
      ) : isError || !kpis ? (
        <Card>
          <ErrorState />
        </Card>
      ) : (
        <>
          <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
            <Metric
              value={money(kpis.mrr)}
              label="Monthly recurring revenue"
              accent={statusColor("neutral")}
              definition={kpis.definitions.mrr}
            />
            <Metric
              value={money(kpis.arpm)}
              label="Average revenue per member"
              accent={statusColor("neutral")}
              definition={kpis.definitions.arpm}
            />
            <Metric
              value={kpis.active_members}
              label="Active members"
              hint={
                kpis.paused_members > 0 ? `${kpis.paused_members} on hold` : undefined
              }
              accent={statusColor("positive")}
            />
            <Metric
              value={`${kpis.churn.rate}%`}
              label="Churn"
              hint={`${kpis.churn.lapsed} of ${kpis.churn.considered} lapsed`}
              accent={statusColor(
                thresholdStatus(kpis.churn.rate, { good: 2, bad: 10 })
              )}
              definition={kpis.definitions.churn}
            />
            <Metric
              value={`${kpis.pt.rate}%`}
              label="PT utilisation"
              hint={`${kpis.pt.booked_hours}h booked of ${kpis.pt.offered_hours}h offered`}
              accent={statusColor(
                thresholdStatus(kpis.pt.rate, { good: 60, bad: 25, lowerIsBetter: false })
              )}
              definition={kpis.definitions.pt}
            />
            <Metric
              value={`${kpis.classes.rate}%`}
              label="Class fill rate"
              hint={`${kpis.classes.booked} of ${kpis.classes.seats} seats across ${kpis.classes.sessions} classes`}
              accent={statusColor(
                thresholdStatus(kpis.classes.rate, { good: 70, bad: 30, lowerIsBetter: false })
              )}
              definition={kpis.definitions.classes}
            />
          </div>

          <div className="grid gap-6 sm:grid-cols-2">
            <Metric
              value={money(kpis.collected)}
              label="Collected in this window"
              accent={statusColor("neutral")}
            />
            <Metric
              value={kpis.visits}
              label="Visits in this window"
              accent={statusColor("neutral")}
            />
          </div>
        </>
      )}

      <Card accent={railColor(1)}>
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          When the gym is busy
        </h2>
        <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
          The last eight weeks of check-ins, by day and hour — members and walk-in guests
          together, since both are through the same door.
        </p>
        {!occupancy ? <LoadingState /> : <OccupancyHeatmap data={occupancy} />}
      </Card>

      {/* Caution by meaning, not by position: these are members who need
          a call, which is the definition of needs-attention. */}
      <AtRiskPanel accent={statusColor("caution")} />
    </div>
  );
}
