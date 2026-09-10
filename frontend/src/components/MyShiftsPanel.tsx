import { useQuery } from "@tanstack/react-query";
import { fetchMyShifts } from "../api/shifts";
import { Card, EmptyState, LoadingState } from "./ui";

const hhmm = (t: string) => t.slice(0, 5);

/** A staff member's own upcoming rota. Read-only: the rota is the admin's to
 *  write, and a trainer editing their own shifts would be a different feature
 *  with a different set of rules. */
export default function MyShiftsPanel({ accent }: { accent?: string }) {
  const { data, isLoading } = useQuery({ queryKey: ["shifts", "mine"], queryFn: fetchMyShifts });

  return (
    <Card accent={accent}>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        My shifts
      </h2>
      {isLoading ? (
        <LoadingState />
      ) : !data?.length ? (
        <EmptyState>Nothing on the rota for you yet.</EmptyState>
      ) : (
        <ul className="flex flex-col">
          {data.slice(0, 8).map((shift) => (
            <li
              key={shift.id}
              className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--color-border)] py-2 text-sm last:border-none"
            >
              <span className="text-[var(--color-text)]">
                {new Date(shift.date).toLocaleDateString(undefined, {
                  weekday: "short",
                  day: "numeric",
                  month: "short",
                })}
                <span className="ml-2 text-xs text-[var(--color-text-muted)]">
                  {shift.position_name}
                </span>
              </span>
              <span className="tabular-nums text-[var(--color-text-muted)]">
                {hhmm(shift.start_time)}–{hhmm(shift.end_time)}
                <span className="ml-2 text-xs">{shift.hours}h</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
