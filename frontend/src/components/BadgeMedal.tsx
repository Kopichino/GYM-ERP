import { TIER_COLOURS, type Badge, type Tier } from "../api/gamification";

/**
 * A badge's artwork, or a stand-in for it.
 *
 * Badges ship without images so the gym can upload its own. Rather than a
 * broken-image icon or a blank square, an unillustrated badge draws a
 * tier-coloured medal with its rung number -- which is enough to tell the tiers
 * apart, and looks deliberate rather than unfinished.
 */
export default function BadgeMedal({
  badge,
  earned,
  size = 56,
}: {
  badge: Badge;
  earned: boolean;
  size?: number;
}) {
  const colour = TIER_COLOURS[badge.tier as Tier] ?? TIER_COLOURS[1];

  if (badge.image) {
    return (
      <img
        src={badge.image}
        alt={badge.name}
        width={size}
        height={size}
        // Locked badges are dimmed and drained rather than hidden: a ladder
        // you cannot see the next rung of is a surprise, not motivation.
        className={`shrink-0 rounded-full object-cover transition-all ${
          earned ? "" : "opacity-40 grayscale"
        }`}
        style={{ width: size, height: size }}
      />
    );
  }

  return (
    <span
      className="relative flex shrink-0 items-center justify-center rounded-full transition-all"
      style={{
        width: size,
        height: size,
        background: earned
          ? `radial-gradient(circle at 30% 25%, ${colour}, ${colour}55)`
          : "var(--color-surface-2)",
        border: `2px solid ${earned ? colour : "var(--color-border)"}`,
        boxShadow: earned ? `0 0 16px -4px ${colour}` : "none",
      }}
      aria-hidden="true"
    >
      <span
        className="font-display leading-none"
        style={{
          fontSize: size * 0.42,
          color: earned ? "#fff" : "var(--color-text-muted)",
        }}
      >
        {badge.tier}
      </span>
    </span>
  );
}
