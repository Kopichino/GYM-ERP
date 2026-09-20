import { DISCIPLINES } from "../../lib/siteContent";

/** The disciplines, running slowly across the seam between the story and the
 * training paths.
 *
 * This is the page's only marquee and it replaces a six-item section that said
 * the same thing at ten times the height. The track holds the list twice and
 * translates exactly -50%, so the loop has no visible cut. Pure CSS: nothing
 * runs in JavaScript while it scrolls, and reduced motion parks it.
 *
 * The band is masked to transparent at both edges so the words arrive and leave
 * rather than being clipped by the viewport. */
export default function Ticker() {
  const track = [...DISCIPLINES, ...DISCIPLINES];
  const edgeFade =
    "linear-gradient(to right, transparent, black 12%, black 88%, transparent)";

  return (
    <div className="select-none border-y border-[var(--color-border)] bg-[var(--color-surface)] py-6">
      <div
        className="flex overflow-hidden"
        style={{ maskImage: edgeFade, WebkitMaskImage: edgeFade }}
      >
        <div className="anim-marquee flex shrink-0 items-center gap-8 pr-8">
          {track.map((item, i) => (
            <div key={`${item}-${i}`} className="flex shrink-0 items-center gap-8">
              <span className="font-display text-xl text-[var(--color-text-muted)] sm:text-2xl">
                {item}
              </span>
              <span aria-hidden className="h-4 w-px shrink-0 bg-[var(--color-accent)]/70" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
