import { motion, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";
import { useRef } from "react";
import { Link } from "react-router-dom";
import { EASE_EXPO, PARALLAX_SPRING } from "./siteMotion";
import { CTA, HERO } from "../../lib/siteContent";
import Barbell from "./Barbell";
import { useGym } from "./useGym";

/** The opening, as a centred poster rather than a split screen.
 *
 * The device the whole page is built on: the dumbbell is not decoration placed
 * near the headline, it is the rule *between* the two lines of the headline.
 * "BUILD MORE THAN", the bar, "MUSCLE." The object is load-bearing in the
 * composition, which is the difference between an illustration dropped onto a
 * layout and a layout drawn around an object.
 *
 * There is no photograph here at all. The hero is type, one rendered object and
 * one light source, which is why it survives being centred: a centred hero goes
 * soft when it is a headline floating in space, not when the centre line has
 * something sitting on it.
 *
 * As the page scrolls the bar tilts, as though it is being racked. The tilt is
 * driven by scroll position through a spring, so it lags the wheel and settles
 * instead of tracking it notch for notch. */
export default function Hero() {
  const reduced = !!useReducedMotion();
  // The line under the headline is the gym's own tagline once it has one.
  const gym = useGym();
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const progress = useSpring(scrollYProgress, PARALLAX_SPRING);

  const barRotate = useTransform(progress, [0, 1], [0, reduced ? 0 : 7]);
  const barY = useTransform(progress, [0, 1], [0, reduced ? 0 : 90]);
  const barScale = useTransform(progress, [0, 1], [1, reduced ? 1 : 1.07]);
  const copyY = useTransform(progress, [0, 1], [0, reduced ? 0 : 46]);
  const copyFade = useTransform(progress, [0, 0.8], [1, reduced ? 1 : 0.12]);

  /** Headline lines ride up from behind their own mask. */
  const line = (delay: number) => ({
    initial: reduced ? false : { y: "106%" },
    animate: { y: "0%" },
    transition: { duration: 1.2, delay, ease: EASE_EXPO },
  });

  return (
    <section
      ref={ref}
      className="relative flex min-h-[100dvh] flex-col items-center justify-center overflow-hidden px-6 pb-16 pt-24 text-center lg:px-10"
    >
      {/* One light source, behind the bar. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(52% 44% at 50% 48%, color-mix(in srgb, var(--color-accent) 22%, transparent), transparent 72%)",
        }}
      />
      {/* Corners pulled down, so the centre reads as lit rather than flat. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(78% 70% at 50% 45%, rgba(10, 9, 9, 0) 40%, rgba(10, 9, 9, 0.88) 100%)",
        }}
      />

      <motion.div
        style={{ y: copyY, opacity: copyFade }}
        className="relative flex w-full max-w-[1100px] flex-col items-center"
      >
        <h1 className="font-display w-full text-[clamp(3rem,9.5vw,7.4rem)] text-[var(--color-text)]">
          <span className="block overflow-hidden pb-[0.06em]">
            <motion.span {...line(0.18)} className="block">
              {HERO.headline[0]}
            </motion.span>
          </span>

          {/* The bar sits in the headline's own flow, between the two lines, so
              the type and the object share one vertical rhythm. */}
          <motion.span
            aria-hidden
            style={{ rotate: barRotate, y: barY, scale: barScale }}
            initial={reduced ? false : { opacity: 0, scaleX: 0.86, rotate: -2.5 }}
            animate={{ opacity: 1, scaleX: 1, rotate: 0 }}
            transition={{ duration: 1.5, delay: 0.42, ease: EASE_EXPO }}
            className="mx-auto my-[0.02em] block w-[min(96%,880px)] origin-center"
          >
            <Barbell uid="hero-bar" className="h-auto w-full" />
          </motion.span>

          <span className="block overflow-hidden pb-[0.06em]">
            <motion.span {...line(0.3)} className="block">
              <span className="text-[var(--color-accent)]">{HERO.headline[1]}</span>
            </motion.span>
          </span>
        </h1>

        <motion.p
          initial={reduced ? false : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.1, delay: 0.72, ease: EASE_EXPO }}
          className="mt-9 max-w-[44ch] text-[15px] leading-[1.7] text-[var(--color-text-muted)] sm:text-base"
        >
          {gym.tagline || HERO.sub}
        </motion.p>

        <motion.div
          initial={reduced ? false : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.1, delay: 0.84, ease: EASE_EXPO }}
          className="mt-10 flex w-full flex-col items-center gap-3 sm:w-auto sm:flex-row"
        >
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
            className="w-full border border-[var(--color-border)] px-9 py-4 text-center text-sm font-bold tracking-wide text-[var(--color-text)] transition-colors duration-300 hover:border-[var(--color-text-muted)] hover:bg-white/[0.04] active:translate-y-px sm:w-auto"
          >
            {CTA.secondary}
          </a>
        </motion.div>
      </motion.div>
    </section>
  );
}
