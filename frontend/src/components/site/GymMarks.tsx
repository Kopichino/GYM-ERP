/** The one piece of gym hardware drawn as SVG on the whole site.
 *
 * There used to be two, including a weight plate rotating slowly behind a
 * section. A mark that spins forever is decoration announcing itself, so it
 * went. What is left is a single loaded bar used once, as a rule, which is the
 * amount of drawn ornament a page like this can carry without starting to look
 * like clip art. */

type MarkProps = { className?: string };

/** A loaded bar, used once as a section rule instead of a plain hairline. */
export function BarbellRule({ className = "" }: MarkProps) {
  const plates = [
    { x: 52, w: 10, y: 10, h: 60 },
    { x: 38, w: 8, y: 20, h: 40 },
    { x: 26, w: 6, y: 28, h: 24 },
  ];
  return (
    <svg viewBox="0 0 480 80" aria-hidden className={className} fill="currentColor">
      <rect x="16" y="36" width="70" height="8" opacity="0.55" />
      <rect x="394" y="36" width="70" height="8" opacity="0.55" />
      <rect x="86" y="38" width="308" height="4" opacity="0.85" />
      <rect x="88" y="32" width="7" height="16" />
      <rect x="385" y="32" width="7" height="16" />
      {plates.map((p) => (
        <rect key={`l${p.x}`} x={p.x} y={p.y} width={p.w} height={p.h} />
      ))}
      {plates.map((p) => (
        <rect key={`r${p.x}`} x={480 - p.x - p.w} y={p.y} width={p.w} height={p.h} />
      ))}
    </svg>
  );
}
