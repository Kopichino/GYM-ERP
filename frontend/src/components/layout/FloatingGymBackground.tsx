import { useEffect, useRef } from "react";

/**
 * The slow field of gym equipment behind the sign-in screens.
 *
 * Decorative only: `aria-hidden`, `pointer-events: none`, and nothing in it
 * knows anything about the form in front of it. It sits between the auth
 * layout's own background and its content, so equipment drifts behind the
 * form column and the brand panel alike without touching either.
 *
 * Three things keep it cheap enough to sit under the app's most-visited page:
 *
 *  * the shapes are one inline SVG sprite, drawn once and referenced by `use`,
 *    so sixty-odd objects cost sixty `<use>` elements rather than sixty copies
 *    of the path data;
 *  * every object moves with a CSS keyframe on `transform` alone -- React
 *    renders the field once and then never touches it again;
 *  * the parallax moves three layer elements, not sixty objects, off one
 *    pointer listener.
 *
 * The layout is generated from a fixed seed rather than `Math.random()`, so the
 * field is the same on every visit. A background that rearranges itself each
 * time the page loads reads as a glitch rather than as atmosphere.
 */

type ShapeName = "dumbbell" | "barbell" | "plate" | "kettlebell" | "handle" | "rack";

/** Depth. 0 is furthest away: smaller movement, dimmer, softly out of focus. */
type Depth = 0 | 1 | 2;

interface Piece {
  shape: ShapeName;
  depth: Depth;
  /** Position as a percentage of the field, so it reflows with the viewport. */
  x: number;
  y: number;
  size: number;
  rotate: number;
  hue: string;
  opacity: number;
  /** Seconds to cross the viewport horizontally, and to cross it vertically. */
  durationX: number;
  durationY: number;
  /** Negative, so each piece starts somewhere along its path rather than in a
   *  corner: this is what scatters the field at load. */
  delayX: number;
  delayY: number;
  /** Seconds for one slow turn. */
  spin: number;
}

/**
 * The gym's own two colours lead, which is what keeps this looking like
 * IRONCORE rather than a generic neon poster -- they are the brand accents, and
 * on a white-labelled install they follow whatever the gym chose. The rest are
 * quieter supporting hues, weighted well below the two brand colours.
 */
const HUES: { value: string; weight: number }[] = [
  { value: "var(--color-accent)", weight: 4 },
  { value: "var(--color-accent-2)", weight: 3 },
  { value: "#4d8dff", weight: 2 }, // electric blue
  { value: "#9b6cff", weight: 2 }, // violet
  { value: "#35d6e6", weight: 1 }, // cyan
  { value: "#3ecf8e", weight: 1 }, // green
  { value: "#e8c06a", weight: 1 }, // warm gold
  { value: "#ff8a3d", weight: 1 }, // orange
];

const SHAPES: ShapeName[] = ["dumbbell", "barbell", "plate", "kettlebell", "handle", "rack"];

/** How many objects each depth carries. Trimmed on small screens in CSS. */
const PER_DEPTH: Record<Depth, number> = { 0: 24, 1: 24, 2: 18 };

/** Small deterministic PRNG, so the field is identical on every load. */
function mulberry32(seed: number) {
  let state = seed;
  return () => {
    state |= 0;
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * How long a piece takes to cross each axis, and where along that journey it
 * starts.
 *
 * The delay is what scatters the field, and it has to be drawn from the piece's
 * *whole* cycle -- one length of the screen and back, so twice the duration.
 * Capping delays at some fixed number of seconds instead leaves every piece in
 * the same stretch of its journey, and the field arrives pooled in one corner
 * rather than spread across the screen.
 *
 * Minutes to cross, not seconds: slow enough to read as still at a glance, and
 * plainly rearranged by the time anyone looks back.
 */
function crossing(random: () => number, pace: number) {
  return {
    durationX: Math.round((150 + random() * 110) * pace),
    durationY: Math.round((120 + random() * 90) * pace),
  };
}

/** A deterministic shuffle, so the two axes are scattered independently. */
function shuffled(count: number, random: () => number) {
  const order = Array.from({ length: count }, (_, index) => index);
  for (let i = count - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }
  return order;
}

function buildField(): Piece[] {
  // Any fixed seed will do; this one simply produced a pleasing scatter.
  const random = mulberry32(0x1c0de);
  const weighted = HUES.flatMap((hue) => Array<string>(hue.weight).fill(hue.value));
  const pieces: Piece[] = [];

  ([0, 1, 2] as Depth[]).forEach((depth) => {
    const count = PER_DEPTH[depth];
    // Where each piece starts is its animation delay, so the delays decide how
    // the field is spread. Drawn at random they clump -- and with a fixed seed
    // one unlucky draw would be every visitor's first impression. Instead each
    // piece takes its own slice of the cycle: one per slice across the screen,
    // shuffled separately per axis so the pieces do not line up on a diagonal,
    // with a jitter inside each slice so the spacing never looks measured.
    const slicesX = shuffled(count, random);
    const slicesY = shuffled(count, random);

    for (let i = 0; i < count; i += 1) {
      // Sizes by depth: the far layer holds the few larger, dimmer, blurred
      // pieces that read as distance; the near layer is small and sharp.
      const size =
        depth === 0
          ? (random() < 0.25 ? 60 + random() * 30 : 22 + random() * 22)
          : depth === 1
            ? 22 + random() * 22
            : 28 + random() * 24;

      // Crossing times, not speeds: a nearer piece takes less time to cross, so
      // it appears to move faster than one further away, which is what sells
      // the depth. The two axes never share a duration, so a piece traces a
      // long angled path around the screen and reverses at each edge instead of
      // running a diagonal back and forth.
      const pace = depth === 0 ? 1.55 : depth === 1 ? 1.2 : 1;
      const { durationX, durationY } = crossing(random, pace);
      // A full cycle is one length of the screen and back, so twice the
      // duration; a phase anywhere in that cycle is a position anywhere on the
      // axis.
      const phaseX = (slicesX[i] + random()) / count;
      const phaseY = (slicesY[i] + random()) / count;

      pieces.push({
        shape: SHAPES[Math.floor(random() * SHAPES.length)],
        depth,
        x: random() * 100,
        y: random() * 100,
        size: Math.round(size),
        rotate: Math.round(random() * 360),
        hue: weighted[Math.floor(random() * weighted.length)],
        opacity:
          depth === 0
            ? 0.07 + random() * 0.04
            : depth === 1
              ? 0.11 + random() * 0.05
              : 0.14 + random() * 0.06,
        durationX,
        durationY,
        delayX: -Math.round(phaseX * durationX * 2),
        delayY: -Math.round(phaseY * durationY * 2),
        spin: Math.round(260 + random() * 220) * (random() < 0.5 ? -1 : 1),
      });
    }
  });

  return pieces;
}

const FIELD = buildField();

/** How far each depth follows the pointer, in px at the extremes. */
const PARALLAX: Record<Depth, number> = { 0: 3, 1: 5, 2: 8 };

export default function FloatingGymBackground() {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = root.current;
    if (!element) return;

    // No parallax for a visitor who asked for less motion, and none on touch,
    // where there is no pointer to follow and the listener would only cost
    // battery.
    const still = window.matchMedia("(prefers-reduced-motion: reduce)");
    const coarse = window.matchMedia("(pointer: coarse)");
    if (still.matches || coarse.matches) return;

    let frame = 0;
    let pending: { x: number; y: number } | null = null;

    const apply = () => {
      frame = 0;
      if (!pending) return;
      // -1..1 from the centre of the viewport. Opposite sign to the pointer, so
      // the field leans away rather than chasing.
      element.style.setProperty("--fgb-x", `${-pending.x}`);
      element.style.setProperty("--fgb-y", `${-pending.y}`);
      pending = null;
    };

    const onPointerMove = (event: PointerEvent) => {
      pending = {
        x: (event.clientX / window.innerWidth) * 2 - 1,
        y: (event.clientY / window.innerHeight) * 2 - 1,
      };
      if (!frame) frame = window.requestAnimationFrame(apply);
    };

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <div ref={root} className="fgb" aria-hidden="true">
      <EquipmentSprite />
      {([0, 1, 2] as Depth[]).map((depth) => (
        <div
          key={depth}
          className="fgb-layer"
          style={{ ["--fgb-depth" as string]: `${PARALLAX[depth]}px` }}
          data-depth={depth}
        >
          {/* Two nested elements per piece, because the bounce is two
              independent journeys: the outer one crosses the screen left to
              right and back, the inner one top to bottom and back, each on its
              own clock. Combined, a piece travels the whole viewport and turns
              at every edge -- and it is still two `transform`s on the
              compositor, with no JavaScript in the loop. */}
          {FIELD.filter((piece) => piece.depth === depth).map((piece, index) => (
            <span
              key={index}
              className="fgb-piece"
              style={
                {
                  "--fgb-size": `${piece.size}px`,
                  "--fgb-duration-x": `${piece.durationX}s`,
                  "--fgb-delay-x": `${piece.delayX}s`,
                } as React.CSSProperties
              }
            >
              <span
                className="fgb-piece-y"
                style={
                  {
                    "--fgb-duration-y": `${piece.durationY}s`,
                    "--fgb-delay-y": `${piece.delayY}s`,
                  } as React.CSSProperties
                }
              >
                <svg
                  viewBox="0 0 48 48"
                  width="100%"
                  height="100%"
                  style={
                    {
                      "--fgb-hue": piece.hue,
                      "--fgb-rotate": `${piece.rotate}deg`,
                      "--fgb-opacity": piece.opacity,
                      "--fgb-spin": `${Math.abs(piece.spin)}s`,
                      animationDirection: piece.spin < 0 ? "reverse" : "normal",
                    } as React.CSSProperties
                  }
                >
                  <use href={`#fgb-${piece.shape}`} />
                </svg>
              </span>
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}

/**
 * The six outlines, defined once.
 *
 * Stroked rather than filled, and drawn in a 48-unit box so the stroke stays
 * proportionally thin at every size. `currentColor` throughout, so a piece's
 * colour is set once on its wrapper and carries into both the stroke and the
 * glow behind it.
 */
function EquipmentSprite() {
  return (
    <svg className="fgb-sprite" aria-hidden="true" focusable="false">
      <defs>
        <g id="fgb-dumbbell">
          <path d="M14 24h20" />
          <rect x="8" y="17" width="6" height="14" rx="2" />
          <rect x="34" y="17" width="6" height="14" rx="2" />
          <rect x="3" y="20" width="5" height="8" rx="2" />
          <rect x="40" y="20" width="5" height="8" rx="2" />
        </g>
        <g id="fgb-barbell">
          <path d="M9 24h30" />
          <rect x="6" y="15" width="4" height="18" rx="1.5" />
          <rect x="38" y="15" width="4" height="18" rx="1.5" />
          <rect x="2" y="19" width="4" height="10" rx="1.5" />
          <rect x="42" y="19" width="4" height="10" rx="1.5" />
        </g>
        <g id="fgb-plate">
          <circle cx="24" cy="24" r="17" />
          <circle cx="24" cy="24" r="6" />
          <path d="M24 7v6M24 35v6M7 24h6M35 24h6" />
        </g>
        <g id="fgb-kettlebell">
          <path d="M18 17a6 6 0 0 1 12 0" />
          <path d="M18 17c-5 3-8 8-8 14a6 6 0 0 0 6 6h16a6 6 0 0 0 6-6c0-6-3-11-8-14" />
        </g>
        <g id="fgb-handle">
          <path d="M24 4v10" />
          <path d="M18 14h12" />
          <path d="M20 14l-4 12a8 8 0 0 0 16 0l-4-12" />
        </g>
        <g id="fgb-rack">
          <path d="M10 6v36M38 6v36" />
          <path d="M10 16h28M10 30h28" />
          <path d="M6 42h8M34 42h8" />
        </g>
      </defs>
    </svg>
  );
}
