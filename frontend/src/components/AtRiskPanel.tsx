import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchAtRisk, type AtRiskMember, type RiskBand } from "../api/crm";
import { Button, Card, EmptyState, ErrorState, ghostButtonClass, LoadingState } from "./ui";

const BAND_COLOUR: Record<RiskBand, string> = {
  quiet: "#ff3d5a",
  cooling: "#ffb020",
};

/**
 * Reveals the number rather than trying to dial it.
 *
 * This was a bare `tel:` link, and a `tel:` link on a desktop browser with no
 * calling app does nothing at all -- which is exactly where the front desk
 * works this list. Showing the number lets them dial it on whatever phone is
 * in their hand. The revealed number stays a `tel:` link, so on a phone it
 * still dials in one tap.
 *
 * A member with no number on file says so, rather than simply having no
 * button -- a missing button reads as a broken page, not as missing data.
 */
function CallAction({ member }: { member: AtRiskMember }) {
  const [shown, setShown] = useState(false);
  const [copied, setCopied] = useState(false);
  const name = member.full_name || member.username;

  if (!member.phone) {
    return (
      <span className="shrink-0 text-xs text-[var(--color-text-muted)] opacity-70">
        No phone on file
      </span>
    );
  }

  if (!shown) {
    return (
      <button
        type="button"
        onClick={() => setShown(true)}
        className={`shrink-0 ${ghostButtonClass}`}
        aria-label={`Show ${name}'s phone number`}
      >
        Call
      </button>
    );
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(member.phone);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Blocked in some contexts. The number is on screen and selectable.
    }
  }

  return (
    <span className="flex shrink-0 items-center gap-2">
      <a
        href={`tel:${member.phone.replace(/\s/g, "")}`}
        className="font-semibold tabular-nums text-[var(--color-text)] transition-colors hover:text-[var(--color-accent)]"
      >
        {member.phone}
      </a>
      {/* Named for whose number it is. A list of several members otherwise has
          a row of buttons that all read "Copy", and a screen reader cannot
          tell one member's from the next. */}
      <button
        type="button"
        onClick={copy}
        aria-label={`${copied ? "Copied" : "Copy"} ${name}'s phone number`}
        className={ghostButtonClass}
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </span>
  );
}

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
        <CallAction member={member} />
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
