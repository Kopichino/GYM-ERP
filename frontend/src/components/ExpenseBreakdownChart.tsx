import { useState } from "react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer } from "recharts";
import { RAIL_COLORS } from "../lib/theme";

interface Slice {
  category: string;
  total: string;
}

/**
 * Where the month's money went.
 *
 * A donut rather than a full pie so the period's total can sit in the middle --
 * the two questions an owner asks looking at this ("how much, and on what?")
 * then have one answer each in one place.
 *
 * There is deliberately no floating tooltip: one following the cursor lands on
 * top of the centre total whenever the pointer crosses the hole, which left two
 * numbers overlapping each other. Hovering a slice writes that slice into the
 * middle instead, which is the same information in the space already reserved
 * for it.
 *
 * Categories keep the app's existing rail palette rather than gaining a second
 * colour vocabulary, and the order is whatever the API returned (largest
 * first), so the biggest slice always draws in the brand accent.
 */
export default function ExpenseBreakdownChart({ slices }: { slices: Slice[] }) {
  const [active, setActive] = useState<number | null>(null);

  const data = slices
    .map((s) => ({ name: s.category, value: Number(s.total) }))
    // A zero-value slice draws nothing but still claims a legend entry and a
    // colour, which makes the palette look wrong for no benefit.
    .filter((s) => s.value > 0);

  const total = data.reduce((sum, s) => sum + s.value, 0);
  const money = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 0 });

  if (!data.length) return null;

  const focused = active !== null ? data[active] : null;
  const share = focused && total ? Math.round((focused.value / total) * 100) : 0;

  return (
    // Reset on leaving the whole chart, not per sector: moving from one slice
    // to the next fires a leave before the next enter, which would blink the
    // centre back to the total on every crossing.
    <div className="relative h-64 w-full" onMouseLeave={() => setActive(null)}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius="55%"
            outerRadius="80%"
            paddingAngle={2}
            // The gap between slices reads as a gap, not a hairline, against
            // the dark card.
            stroke="var(--color-surface)"
            strokeWidth={2}
            isAnimationActive={false}
            onMouseEnter={(_, index) => setActive(index)}
          >
            {data.map((slice, index) => (
              <Cell
                key={slice.name}
                fill={RAIL_COLORS[index % RAIL_COLORS.length]}
                // Dimming the rest is what tells you which slice the centre is
                // reporting, now that nothing floats next to the cursor.
                opacity={active === null || active === index ? 1 : 0.35}
                style={{ transition: "opacity 150ms", cursor: "pointer" }}
              />
            ))}
          </Pie>
          <Legend
            verticalAlign="bottom"
            height={30}
            iconType="circle"
            wrapperStyle={{ fontSize: 12, color: "var(--color-text-muted)" }}
          />
        </PieChart>
      </ResponsiveContainer>

      {/* Centred in the donut. `pointer-events-none` so it never swallows a
          hover meant for the slice behind it. */}
      <div className="pointer-events-none absolute inset-0 bottom-8 flex flex-col items-center justify-center px-8 text-center">
        <p
          className="font-display text-3xl leading-none"
          style={{
            color: focused
              ? RAIL_COLORS[(active as number) % RAIL_COLORS.length]
              : "var(--color-text)",
          }}
        >
          {money(focused ? focused.value : total)}
        </p>
        <p className="mt-0.5 max-w-full truncate text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
          {focused ? `${focused.name} · ${share}%` : "Total spent"}
        </p>
      </div>
    </div>
  );
}
