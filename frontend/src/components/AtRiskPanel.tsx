import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchAtRisk, type AtRiskMember, type RiskBand } from "../api/crm";
import { Button, Card, EmptyState, ErrorState, LoadingState } from "./ui";

const BAND_COLOUR: Record<RiskBand, string> = {
  quiet: "#ff3d5a",
  cooling: "#ffb020",
};

function Row({ member }: { member: AtRiskMember }) {
  const colour = BAND_COLOUR[member.band];
  const gap = member.never_visited
    ? "never been in"
    : member.days_since_visit === 1
      ? "in yesterday"
      : `${member.days_since_visit} days`;

  return (
    <li className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-[var(--color-border)] py-2 text-sm last:border-none">
      <span className="flex min-w-0 items-center gap-2">
        <span
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ background: colour }}
          aria-hidden="true"
        />
        <span className="min-w-0">
          <span className="block truncate text-[var(--color-text)]">
            {member.full_name || member.username}
          </span>
          {member.trainer && (
            <span className="block text-[11px] text-[var(--color-text-muted)]">
              with {member.trainer}
            </span>
          )}
        </span>
      </span>

      <span className="flex shrink-0 items-center gap-4">
        <span className="text-right">
          <span className="block tabular-nums" style={{ color: colour }}>
            {gap}
          </span>
          {/* Someone about to lose their membership turns a "we miss you" call
              into a renewal conversation, so it is worth seeing here. */}
          {member.days_left !== null && member.days_left <= 14 && (
            <span className="block text-[11px] text-[var(--color-text-muted)]">
              {member.days_left < 0
                ? "membership expired"
                : `expires in ${member.days_left}d`}
            </span>
          )}
        </span>
        {member.phone && (
          <a
            href={`tel:${member.phone.replace(/\s/g, "")}`}
            className="shrink-0 text-xs text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-accent)]"
          >
            Call
          </a>
        )}
      </span>
    </li>
  );
}

/**
 * Members who have stopped turning up.
 *
 * Two bands rather than one flag: someone six days quiet needs a different
 * message from someone gone a month, and lumping them together means the
 * urgent ones get lost. Longest absence sorts first, which is the order
 * somebody actually works a call list in.
 */
export default function AtRiskPanel({ accent = "#ff3d5a" }: { accent?: string }) {
  const [showAll, setShowAll] = useState(false);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["at-risk"],
    queryFn: fetchAtRisk,
  });

  const rows = data?.results ?? [];
  const shown = showAll ? rows : rows.slice(0, 6);

  return (
    <Card accent={accent}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Not been in lately
        </h2>
        {data && rows.length > 0 && (
          <span className="text-xs text-[var(--color-text-muted)]">
            <b style={{ color: BAND_COLOUR.quiet }}>{data.quiet_count}</b> quiet ·{" "}
            <b style={{ color: BAND_COLOUR.cooling }}>{data.cooling_count}</b> cooling off
          </span>
        )}
      </div>

      {isLoading ? (
        <LoadingState />
      ) : isError ? (
        <ErrorState />
      ) : !rows.length ? (
        <EmptyState>
          Everyone has been in recently. Nothing to chase.
        </EmptyState>
      ) : (
        <>
          <ul className="flex flex-col">
            {shown.map((member) => (
              <Row key={member.id} member={member} />
            ))}
          </ul>
          {rows.length > shown.length && (
            <Button
              variant="secondary"
              onClick={() => setShowAll(true)}
              className="mt-3 px-3 py-1 text-xs"
            >
              Show all {rows.length}
            </Button>
          )}
          {data && (
            <p className="mt-3 text-[11px] text-[var(--color-text-muted)]">
              Quiet after {data.quiet_days} days, cooling off after {data.cooling_days}.
              New members are left alone for their first {data.grace_days}.
            </p>
          )}
        </>
      )}
    </Card>
  );
}
