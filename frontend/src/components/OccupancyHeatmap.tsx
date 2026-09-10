import { useState } from "react";
import type { Occupancy } from "../api/reports";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Gyms are shut in the small hours; showing them makes the busy part smaller
 *  for no information. Anything outside this that has visits widens the range
 *  automatically, so a 24-hour gym still reads correctly. */
const DEFAULT_FROM = 5;
const DEFAULT_TO = 23;

function hourLabel(hour: number) {
  if (hour === 0) return "12a";
  if (hour === 12) return "12p";
  return hour < 12 ? `${hour}a` : `${hour - 12}p`;
}

/**
 * Visits by weekday and hour.
 *
 * Colour is scaled against the busiest single cell rather than a fixed ceiling,
 * so a quiet gym's pattern is as readable as a busy one's -- the question this
 * answers is "when is *my* gym busy", not "how do I compare to a benchmark".
 */
export default function OccupancyHeatmap({ data }: { data: Occupancy }) {
  const [hovered, setHovered] = useState<{ day: number; hour: number } | null>(null);

  const active = data.grid.flatMap((row) =>
    row.map((count, hour) => (count > 0 ? hour : -1))
  ).filter((hour) => hour >= 0);

  const from = Math.min(DEFAULT_FROM, ...(active.length ? active : [DEFAULT_FROM]));
  const to = Math.max(DEFAULT_TO, ...(active.length ? active : [DEFAULT_TO]));
  const hours = Array.from({ length: to - from + 1 }, (_, i) => from + i);

  const peak = data.peak || 1;
  const cell = (count: number) => {
    if (!count) return { background: "var(--color-surface-2)" };
    // Floored at 0.18 so a single visit is still visible rather than
    // indistinguishable from an empty hour.
    const intensity = 0.18 + (count / peak) * 0.82;
    return { background: `color-mix(in srgb, var(--color-accent) ${intensity * 100}%, transparent)` };
  };

  const focus = hovered ? data.grid[hovered.day][hovered.hour] : null;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        {/* Both numbers used to sit either side of a middot -- "106 visits ·
            busiest Mon at 1p with 7" -- which read as a single phrase, as
            though 106 were the count for that one hour. They are a total and a
            single cell, so each now carries its own unit and the busiest hour
            says it is one of the 106. */}
        <p className="text-sm text-[var(--color-text-muted)]">
          <b className="text-[var(--color-text)]">{data.total_visits}</b> visits in total.{" "}
          {data.busiest ? (
            <>
              Busiest hour: {WEEKDAYS[data.busiest.weekday]}{" "}
              {hourLabel(data.busiest.hour)}, with{" "}
              <b className="text-[var(--color-text)]">{data.busiest.visits}</b> of them.
            </>
          ) : (
            "Nothing recorded in this window."
          )}
        </p>
        {hovered && (
          <p className="text-sm text-[var(--color-text)]">
            {WEEKDAYS[hovered.day]} {hourLabel(hovered.hour)} —{" "}
            <b>{focus}</b> {focus === 1 ? "visit" : "visits"}
          </p>
        )}
      </div>

      <div className="no-scrollbar overflow-x-auto" onMouseLeave={() => setHovered(null)}>
        <table className="border-separate border-spacing-[2px]">
          <thead>
            <tr>
              <th />
              {hours.map((hour) => (
                <th
                  key={hour}
                  className="pb-1 text-[9px] font-normal text-[var(--color-text-muted)]"
                >
                  {/* Every third hour, so the labels do not collide. */}
                  {hour % 3 === 0 ? hourLabel(hour) : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {WEEKDAYS.map((label, day) => (
              <tr key={label}>
                <th className="pr-2 text-right text-[10px] font-normal uppercase tracking-wide text-[var(--color-text-muted)]">
                  {label}
                </th>
                {hours.map((hour) => {
                  const count = data.grid[day][hour];
                  return (
                    <td key={hour} className="p-0">
                      <div
                        onMouseEnter={() => setHovered({ day, hour })}
                        title={`${label} ${hourLabel(hour)}: ${count} visit${count === 1 ? "" : "s"}`}
                        className="h-5 w-5 rounded-[3px] transition-transform hover:scale-110"
                        style={cell(count)}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
