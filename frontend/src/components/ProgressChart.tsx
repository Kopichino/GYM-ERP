import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ProgressPoint } from "../api/workouts";

const WEIGHT_COLOR = "var(--color-accent)";
const REPS_COLOR = "var(--color-accent-2)";

/** Pixel headroom so the peak marker clears the top of the plot. Padding is
 *  used rather than inflating the domain, which would push the axis onto
 *  awkward tick values like 92kg instead of a round 80kg. */
const AXIS_PADDING = { top: 14, bottom: 0 };

/**
 * Weight and reps are different quantities on wildly different scales -- a 60kg
 * top set next to 10 reps flattens the reps line onto the axis if both share
 * one Y axis. So each series gets its own axis, tinted to match its line, and
 * the legend/tooltip name the units rather than leaving bare numbers.
 */
export default function ProgressChart({ points }: { points: ProgressPoint[] }) {
  // Whatever unit the member logged most recently labels the axis.
  const unit = points[points.length - 1]?.weight_unit ?? "kg";

  const data = points.map((p) => {
    const date = new Date(p.session__date);
    return {
      label: date.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
      fullDate: date.toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
      }),
      maxWeight: Number(p.max_weight),
      totalReps: p.total_reps,
    };
  });

  const axisTick = { fontSize: 12 };

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          {/* Vertical grid lines add noise when there are only a few sessions. */}
          <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="label"
            stroke="var(--color-text-muted)"
            tick={axisTick}
            tickMargin={8}
            minTickGap={16}
          />
          <YAxis
            yAxisId="weight"
            stroke={WEIGHT_COLOR}
            tick={axisTick}
            width={56}
            // Both axes start at 0 so the two lines can't imply a trend that is
            // really just a cropped axis.
            domain={[0, "auto"]}
            padding={AXIS_PADDING}
            tickFormatter={(value) => `${value}${unit}`}
          />
          <YAxis
            yAxisId="reps"
            orientation="right"
            stroke={REPS_COLOR}
            tick={axisTick}
            width={48}
            allowDecimals={false}
            domain={[0, "auto"]}
            padding={AXIS_PADDING}
          />
          <Tooltip
            cursor={{ stroke: "var(--color-border)", strokeWidth: 1 }}
            contentStyle={{
              background: "var(--color-surface-2)",
              border: "1px solid var(--color-border)",
              borderRadius: 8,
              color: "var(--color-text)",
            }}
            separator=": "
            labelStyle={{ color: "var(--color-text-muted)", marginBottom: 4 }}
            labelFormatter={(_label, payload) => payload?.[0]?.payload?.fullDate ?? ""}
            formatter={(value, name) =>
              name === "Total reps"
                ? [`${value} reps`, name]
                : [`${value} ${unit}`, "Heaviest set"]
            }
          />
          <Legend
            verticalAlign="bottom"
            height={28}
            iconType="plainline"
            wrapperStyle={{ fontSize: 12, color: "var(--color-text-muted)" }}
          />
          <Line
            yAxisId="weight"
            type="monotone"
            dataKey="maxWeight"
            name={`Heaviest set (${unit})`}
            stroke={WEIGHT_COLOR}
            strokeWidth={2}
            // Explicit dots so a member with a single logged session still sees
            // their data instead of an apparently empty chart.
            dot={{ r: 3, strokeWidth: 0, fill: WEIGHT_COLOR }}
            activeDot={{ r: 5 }}
          />
          <Line
            yAxisId="reps"
            type="monotone"
            dataKey="totalReps"
            name="Total reps"
            stroke={REPS_COLOR}
            strokeWidth={2}
            strokeDasharray="4 3"
            dot={{ r: 3, strokeWidth: 0, fill: REPS_COLOR }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
