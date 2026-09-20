import { motion, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";
import { useRef } from "react";
import { Link } from "react-router-dom";
import { PARALLAX_SPRING } from "./siteMotion";
import { CTA, FINAL_CTA } from "../../lib/siteContent";
import Barbell from "./Barbell";
import Reveal from "./Reveal";

/** The closing statement. The page opens and closes on the same object.
 *
 * The bar returns here, but it is doing a different job: in the hero it is a
 * crisp rule holding the headline apart, and here it is a large, dim mass lying
 * behind the type, tilted and drifting. Same object, opposite role, which reads
 * as a bookend rather than as the same section twice.
 *
 * It also tilts the other way. Small thing, but the eye notices the symmetry
 * even when it does not notice why. */
export default function FinalCta() {
  const reduced = !!useReducedMotion();
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });

  const progress = useSpring(scrollYProgress, PARALLAX_SPRING);
  const y = useTransform(progress, [0, 1], ["-7%", reduced ? "-7%" : "7%"]);
  const barRotate = useTransform(progress, [0, 1], [reduced ? -9 : -14, reduced ? -9 : -4]);
  const barY = useTransform(progress, [0, 1], [reduced ? 0 : 60, reduced ? 0 : -60]);

  return (
    <section ref={ref} className="relative isolate overflow-hidden">
      <motion.img
        src={FINAL_CTA.image}
        alt={FINAL_CTA.alt}
        loading="lazy"
        style={{ y }}
        className="absolute inset-0 -z-30 h-[120%] w-full object-cover contrast-[1.1] saturate-[0.55] brightness-[0.45]"
      />
      <div className="absolute inset-0 -z-20 bg-[var(--color-bg)]/78" />

      {/* The bar, lying behind the type. */}
      <motion.div
        aria-hidden
        style={{ rotate: barRotate, y: barY }}
        className="pointer-events-none absolute inset-x-0 top-1/2 -z-10 mx-auto w-[min(150%,1500px)] -translate-y-1/2 opacity-[0.13]"
      >
        <Barbell uid="cta-bar" className="h-auto w-full" />
      </motion.div>

      {/* A bloom of the gym's own colour from the lower left, and a fade at the top so the section
          arrives out of the page rather than starting at a hard edge. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          backgroundImage:
            "radial-gradient(70% 60% at 12% 92%, color-mix(in srgb, var(--color-accent) 26%, transparent), transparent 68%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-32 bg-gradient-to-b from-[var(--color-bg)] to-transparent"
      />

      <div className="mx-auto w-full max-w-[1400px] px-6 py-32 text-center sm:py-40 lg:px-10 lg:py-56">
        <Reveal className="mx-auto max-w-4xl">
          <h2 className="font-display text-[clamp(3rem,9vw,7.6rem)] text-[var(--color-text)]">
            {FINAL_CTA.headline.map((line, i) => (
              <span key={line} className="block">
                {i === 1 ? <span className="text-[var(--color-accent)]">{line}</span> : line}
              </span>
            ))}
          </h2>
          <p className="mx-auto mt-8 max-w-[46ch] text-base leading-[1.7] text-[var(--color-text)]/75">
            {FINAL_CTA.sub}
          </p>

          <div className="mt-11 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
            <Link
              to="/signup"
              className="group relative w-full overflow-hidden bg-[var(--color-accent-strong)] px-9 py-4 text-center text-sm font-bold tracking-wide text-[var(--color-on-accent)] transition-transform duration-300 active:translate-y-px sm:w-auto"
            >
              <span
                aria-hidden
                className="absolute inset-0 origin-left scale-x-0 bg-[var(--color-accent-hover)] transition-transform duration-[450ms] ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:scale-x-100"
              />
              <span className="relative">{CTA.primary}</span>
            </Link>
            <a
              href="#contact"
              className="w-full border border-[var(--color-text)]/30 bg-[var(--color-bg)]/50 px-9 py-4 text-center text-sm font-bold tracking-wide text-[var(--color-text)] backdrop-blur-sm transition-colors duration-300 hover:border-[var(--color-text)]/70 active:translate-y-px sm:w-auto"
            >
              {CTA.secondary}
            </a>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
