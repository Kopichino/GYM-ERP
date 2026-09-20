/** A loaded Olympic barbell, drawn to the anatomy of a real bar.
 *
 * HONEST LABEL: still a rendered illustration, not a photograph. There is no
 * image-generation tool wired into this project and no cut-out barbell asset.
 * What makes it read as a real object is anatomy and lighting, not detail count.
 *
 * The anatomy, outward from the middle, is the part most illustrated barbells
 * get wrong:
 *
 *   shaft  ->  knurl zone  ->  collar ring  ->  sleeve  ->  plates  ->  clamp  ->  end cap
 *
 *   - The shaft is thin (28mm on a real bar) and the sleeve is nearly twice its
 *     diameter. A single uniform tube from end to end is the giveaway.
 *   - Knurling exists only where hands and back go: two grip zones and one
 *     centre zone, with smooth steel between them and knurl ring marks at the
 *     boundaries. Knurling the whole bar is the second giveaway.
 *   - Plates load onto the sleeve, largest innermost, and the sleeve stays
 *     visible between the innermost plate and the collar.
 *   - A snap clamp holds the stack on, and the sleeve is capped at the end.
 *
 * Lighting is one source, high and to the left. Every cylinder therefore shares
 * the same specular band at ~30% of its height, tightening as the cylinder gets
 * thinner (the shaft's highlight is narrower than the sleeve's, which is
 * narrower than a plate's). The underside carries a faint warm bounce because
 * the hero sits in red light. The previous version painted a flat red gradient
 * stripe down each plate edge, which is what an outline glow looks like, not
 * what light looks like.
 *
 * If a real cut-out photograph turns up later, swapping it in is a one-line
 * change at the call site: this renders into a plain box and carries no layout.
 *
 * The component is deliberately motionless. Every animation lives at the call
 * site, so the same artwork can be tilted by scroll in the hero and lie still
 * behind the closing panel without two copies existing.
 */

type Props = {
  className?: string;
  /** Unique per instance: SVG gradient ids are document-global, so two barbells
   *  on one page sharing ids would fight over their fills. */
  uid: string;
};

const CENTRE = 450;
const AXIS = 80;

/** Left-hand geometry only; the right side is mirrored about CENTRE. */
const SLEEVE = { x: 88, w: 116, h: 28 };
const COLLAR = { x: 204, w: 12, h: 34 };
const SHAFT = { x: 216, w: 468, h: 15 };
const END_CAP = { x: 84, w: 10, h: 30 };
const CLAMP = { x: 100, w: 16, h: 38 };

/** Largest plate innermost, as they load on a real bar. */
const PLATES = [
  { x: 164, w: 26, h: 122 },
  { x: 140, w: 22, h: 96 },
  { x: 120, w: 18, h: 74 },
];

/** Hands and back only. Everything between these is smooth steel. */
const KNURL_ZONES = [
  { x: 224, w: 92 },
  { x: 404, w: 92 },
];

export default function Barbell({ className = "", uid }: Props) {
  const id = (n: string) => `${uid}-${n}`;
  const mirror = (x: number, w: number) => CENTRE * 2 - x - w;

  /** One cylinder seen edge-on.
   *
   * Two fills over the same rectangle. The vertical gradient is the rim curving
   * away above and below the specular band. The horizontal one darkens both
   * vertical edges, which is the chamfer where the rim meets the flat face, and
   * it doubles as the contact shadow between neighbouring plates, so no separate
   * seam mark is needed.
   *
   * An earlier version drew the bevel as its own hard-edged rectangle. At any
   * real size that reads as a grey bar laid on top of the plate, not as light,
   * which is why the bevel now lives in the gradient stops instead. */
  const cyl = (
    key: string,
    x: number,
    w: number,
    h: number,
    fill: string,
    rx = 2,
  ) => {
    const y = AXIS - h / 2;
    return (
      <g key={key}>
        <rect x={x} y={y} width={w} height={h} rx={rx} fill={fill} />
        <rect x={x} y={y} width={w} height={h} rx={rx} fill={`url(#${id("edge")})`} />
      </g>
    );
  };

  return (
    <svg viewBox="0 0 900 160" aria-hidden className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        {/* Plate: widest cylinder, so the broadest specular band. The last stop
            is the warm bounce from the red light the hero sits in. */}
        <linearGradient id={id("plate")} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#0b0c0d" />
          <stop offset="9%" stopColor="#212429" />
          <stop offset="21%" stopColor="#6b727b" />
          <stop offset="27%" stopColor="#ccd3db" />
          <stop offset="33%" stopColor="#929aa3" />
          <stop offset="45%" stopColor="#474c53" />
          <stop offset="63%" stopColor="#22252a" />
          <stop offset="83%" stopColor="#111215" />
          <stop offset="95%" stopColor="#0a0b0d" />
          <stop offset="100%" stopColor="#331a1c" />
        </linearGradient>

        {/* Chamfer where a cylinder rim meets its flat face. Applied over every
            cylinder, so it also darkens the seam between touching plates. */}
        <linearGradient id={id("edge")} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#000000" stopOpacity="0.6" />
          <stop offset="9%" stopColor="#000000" stopOpacity="0" />
          <stop offset="50%" stopColor="#ffffff" stopOpacity="0.05" />
          <stop offset="91%" stopColor="#000000" stopOpacity="0" />
          <stop offset="100%" stopColor="#000000" stopOpacity="0.6" />
        </linearGradient>

        {/* Sleeve: machined steel, brighter and tighter than cast plate. */}
        <linearGradient id={id("sleeve")} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#232529" />
          <stop offset="18%" stopColor="#6f767f" />
          <stop offset="28%" stopColor="#dfe5ec" />
          <stop offset="36%" stopColor="#858c95" />
          <stop offset="66%" stopColor="#3a3e44" />
          <stop offset="90%" stopColor="#17181b" />
          <stop offset="100%" stopColor="#2a1517" />
        </linearGradient>

        {/* Shaft: thinnest cylinder, so the tightest, brightest highlight. */}
        <linearGradient id={id("shaft")} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#1e2023" />
          <stop offset="20%" stopColor="#8b929b" />
          <stop offset="33%" stopColor="#e2e7ec" />
          <stop offset="46%" stopColor="#8a919a" />
          <stop offset="70%" stopColor="#34383e" />
          <stop offset="92%" stopColor="#141518" />
          <stop offset="100%" stopColor="#281416" />
        </linearGradient>

        {/* Contact shadow: tight and dark under the loaded ends, soft in the
            middle where only the thin shaft is near the ground. */}
        <linearGradient id={id("groundfade")} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#000" stopOpacity="0" />
          <stop offset="12%" stopColor="#000" stopOpacity="0.55" />
          <stop offset="32%" stopColor="#000" stopOpacity="0.16" />
          <stop offset="68%" stopColor="#000" stopOpacity="0.16" />
          <stop offset="88%" stopColor="#000" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#000" stopOpacity="0" />
        </linearGradient>

        {/* Clips the knurl hatching to the shaft so strokes cannot spill. */}
        <clipPath id={id("shaftclip")}>
          <rect x={SHAFT.x} y={AXIS - SHAFT.h / 2} width={SHAFT.w} height={SHAFT.h} rx="2" />
        </clipPath>
      </defs>

      <ellipse cx={CENTRE} cy="149" rx="392" ry="7" fill={`url(#${id("groundfade")})`} />

      {/* Sleeves first: the plates and collars sit on top of them. */}
      {cyl("sl", SLEEVE.x, SLEEVE.w, SLEEVE.h, `url(#${id("sleeve")})`, 3)}
      {cyl("sr", mirror(SLEEVE.x, SLEEVE.w), SLEEVE.w, SLEEVE.h, `url(#${id("sleeve")})`, 3)}

      {/* Shaft, with knurling only where it is gripped. */}
      {cyl("sh", SHAFT.x, SHAFT.w, SHAFT.h, `url(#${id("shaft")})`, 2)}
      <g clipPath={`url(#${id("shaftclip")})`}>
        <g stroke="#05060a" strokeWidth="1.15" opacity="0.42">
          {KNURL_ZONES.flatMap((z) => {
            const zones = [z, { x: mirror(z.x, z.w), w: z.w }];
            return zones.flatMap((zz, zi) =>
              Array.from({ length: Math.round(zz.w / 4.6) }, (_, i) => {
                const x = zz.x + i * 4.6;
                return (
                  <line
                    key={`k${zi}-${z.x}-${i}`}
                    x1={x}
                    y1={AXIS - 8}
                    x2={x - 3.4}
                    y2={AXIS + 8}
                  />
                );
              }),
            );
          })}
        </g>
        {/* Knurl ring marks: the machined bands at each zone boundary. */}
        {[320, 400, 500, 580].map((x) => (
          <rect key={`r${x}`} x={x} y={AXIS - 8} width="1.6" height="16" fill="#05060a" opacity="0.5" />
        ))}
      </g>

      {/* Collar ring: the raised step where the shaft meets the sleeve. */}
      {cyl("cl", COLLAR.x, COLLAR.w, COLLAR.h, `url(#${id("sleeve")})`, 2)}
      {cyl("cr", mirror(COLLAR.x, COLLAR.w), COLLAR.w, COLLAR.h, `url(#${id("sleeve")})`, 2)}

      {/* Plates, then the clamp holding them on, then the sleeve end cap. */}
      {PLATES.map((p, i) => {
        const rxr = mirror(p.x, p.w);
        return (
          <g key={`p${i}`}>
            {cyl(`pl${i}`, p.x, p.w, p.h, `url(#${id("plate")})`, 3)}
            {cyl(`pr${i}`, rxr, p.w, p.h, `url(#${id("plate")})`, 3)}
          </g>
        );
      })}

      {cyl("kl", CLAMP.x, CLAMP.w, CLAMP.h, `url(#${id("sleeve")})`, 2)}
      {cyl("kr", mirror(CLAMP.x, CLAMP.w), CLAMP.w, CLAMP.h, `url(#${id("sleeve")})`, 2)}
      {cyl("el", END_CAP.x, END_CAP.w, END_CAP.h, `url(#${id("plate")})`, 3)}
      {cyl("er", mirror(END_CAP.x, END_CAP.w), END_CAP.w, END_CAP.h, `url(#${id("plate")})`, 3)}
    </svg>
  );
}
