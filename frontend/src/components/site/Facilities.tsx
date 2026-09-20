import { motion, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";
import { useRef } from "react";
import { FLOOR } from "../../lib/siteContent";
import Reveal from "./Reveal";

/** The gym itself: one photograph, edge to edge, and the floor named in type.
 *
 * The previous version of this section was six photographs in an asymmetric
 * grid with a caption under each one. It was the single biggest source of
 * clutter on the page: six crops, six headings, six bodies, all fighting at the
 * same size. One large image carries the room better than six small ones, and
 * the six spaces are worth more as a fast index you can read in one pass.
 *
 * This is also the only section that breaks the page's measure and runs the
 * full width of the viewport, which is what gives the scroll a change of
 * pressure rather than another block inside the same column. */
export default function Facilities() {
  const reduced = !!useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });

  const progress = useSpring(scrollYProgress, { stiffness: 80, damping: 30, mass: 0.6 });
  const y = useTransform(progress, [0, 1], ["-6%", reduced ? "-6%" : "6%"]);

  return (
    <section id="facilities" className="scroll-mt-20 pt-16 pb-24 sm:pt-20 sm:pb-28 lg:pt-24 lg:pb-32">
      {/* Full-bleed plate. The image runs taller than its frame so it has room
          to drift without ever exposing an edge. */}
      <div ref={ref} className="relative isolate h-[58vh] min-h-[380px] overflow-hidden lg:h-[70vh]">
        <motion.img
          src={FLOOR.image}
          alt={FLOOR.alt}
          loading="lazy"
          style={{ y }}
          className="absolute inset-0 -z-10 h-[118%] w-full object-cover contrast-[1.05] saturate-[0.7]"
        />
        <div className="absolute inset-0 -z-10 bg-gradient-to-t from-[var(--color-bg)] via-[var(--color-bg)]/45 to-[var(--color-bg)]/25" />

        <div className="mx-auto flex h-full w-full max-w-[1400px] items-end justify-center px-6 pb-10 lg:px-10 lg:pb-14">
          <Reveal>
            <h2 className="font-display max-w-[20ch] text-center text-[clamp(2.2rem,6.2vw,4.8rem)] text-[var(--color-text)]">
              {FLOOR.headline.map((line, i) => (
                <span key={line} className="block">
                  {i === 1 ? <span className="text-[var(--color-accent)]">{line}</span> : line}
                </span>
              ))}
            </h2>
          </Reveal>
        </div>
      </div>

      <div className="mx-auto w-full max-w-[1400px] px-6 lg:px-10">
        <Reveal>
          <p className="mx-auto mt-12 max-w-[58ch] text-center text-[15px] leading-[1.8] text-[var(--color-text-muted)] lg:mt-16">
            {FLOOR.sub}
          </p>
        </Reveal>

        {/* Six spaces as an index. A rule above each entry and nothing else:
            no boxes, no icons, no photograph per line. */}
        <dl className="mt-12 grid gap-x-10 gap-y-9 sm:grid-cols-2 lg:mt-16 lg:grid-cols-3 lg:gap-x-14">
          {FLOOR.spaces.map((space, i) => (
            <Reveal key={space.title} delay={(i % 3) * 0.07}>
              <div className="border-t border-[var(--color-border)] pt-5">
                <dt className="font-display text-[1.35rem] text-[var(--color-text)]">
                  {space.title}
                </dt>
                <dd className="mt-2 max-w-[34ch] text-[14px] leading-relaxed text-[var(--color-text-muted)]">
                  {space.copy}
                </dd>
              </div>
            </Reveal>
          ))}
        </dl>
      </div>
    </section>
  );
}
