import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { Link } from "react-router-dom";
import { EASE_SOFT } from "./siteMotion";
import { PROGRAMS } from "../../lib/siteContent";
import Reveal from "./Reveal";
import { ArrowUpRight } from "./SiteIcons";

/** Four training paths as a typographic index against a single frame.
 *
 * This used to be four photographic cards on a rail, which meant four large
 * images competing at once and a section that looked like every other section.
 * Here the paths are the content and the photography is reduced to one frame
 * that changes as you move down the list, so the visitor reads names and
 * durations first and sees a picture of whichever one they are considering.
 *
 * Pointing at a row and tabbing to it both drive the frame, so the image is not
 * information the keyboard is locked out of. Below `lg` the frame is dropped
 * entirely rather than stacked: on a phone it would be four full-width
 * photographs to scroll past, which is exactly the weight this section was
 * redesigned to lose. */
export default function Programs() {
  const reduced = !!useReducedMotion();
  const [active, setActive] = useState(0);

  return (
    <section id="programmes" className="scroll-mt-20 pt-24 pb-20 sm:pt-28 sm:pb-24 lg:pt-32 lg:pb-24">
      <div className="mx-auto w-full max-w-[1400px] px-6 lg:px-10">
        <Reveal>
          <div className="mx-auto max-w-[54rem] text-center">
            <h2 className="font-display text-[clamp(2.2rem,6vw,4.6rem)] text-[var(--color-text)]">
              Pick the path.
              <br />
              We write the block.
            </h2>
            <p className="mx-auto mt-6 max-w-[50ch] text-[15px] leading-[1.75] text-[var(--color-text-muted)]">
              Every path opens with an assessment and closes with a retest. Your coach adjusts the
              block as the numbers come in.
            </p>
          </div>
        </Reveal>

        <div className="mt-14 grid gap-12 lg:mt-20 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] lg:gap-16">
          <ul>
            {PROGRAMS.map((program, i) => (
              <Reveal as="li" key={program.title} delay={i * 0.07}>
                <Link
                  to="/signup"
                  onMouseEnter={() => setActive(i)}
                  onFocus={() => setActive(i)}
                  className="group relative block border-t border-[var(--color-border)] py-7 lg:py-8"
                >
                  {/* The active row draws its own rule across the hairline
                      above it. One red mark, and it moves with the reader. */}
                  <span
                    aria-hidden
                    className="absolute inset-x-0 top-0 h-px origin-left bg-[var(--color-accent)] transition-transform duration-[550ms] ease-[cubic-bezier(0.22,1,0.36,1)]"
                    style={{ transform: `scaleX(${active === i ? 1 : 0})` }}
                  />

                  <div className="flex items-start gap-5 sm:gap-8">
                    <span className="mt-1.5 shrink-0 text-[12px] font-bold tracking-[0.12em] text-[var(--color-accent-soft)] uppercase">
                      {program.weeks}
                    </span>

                    <div className="min-w-0 flex-1 transition-transform duration-[550ms] ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:translate-x-1.5 group-focus-visible:translate-x-1.5">
                      <h3 className="font-display text-[clamp(1.5rem,2.6vw,2.2rem)] text-[var(--color-text)]">
                        {program.title}
                      </h3>
                      <p className="mt-2.5 max-w-[42ch] text-[14px] leading-relaxed text-[var(--color-text-muted)]">
                        {program.copy}
                      </p>
                    </div>

                    <ArrowUpRight
                      size={20}
                      weight="bold"
                      aria-hidden
                      className="mt-1 shrink-0 text-[var(--color-text-muted)] opacity-0 transition-all duration-[550ms] ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-[var(--color-accent-soft)] group-hover:opacity-100 group-focus-visible:opacity-100"
                    />
                  </div>
                </Link>
              </Reveal>
            ))}
            <li aria-hidden className="border-t border-[var(--color-border)]" />
          </ul>

          {/* One frame, four states. Sticky so it stays with the list. */}
          <Reveal delay={0.1} className="hidden lg:block">
            <div
              aria-hidden
              className="sticky top-28 aspect-[4/5] overflow-hidden bg-[var(--color-surface)]"
            >
              {PROGRAMS.map((program, i) => (
                <motion.img
                  key={program.title}
                  src={program.image}
                  alt=""
                  loading="lazy"
                  initial={false}
                  animate={{
                    opacity: active === i ? 1 : 0,
                    scale: reduced || active === i ? 1 : 1.05,
                  }}
                  transition={{ duration: reduced ? 0 : 0.9, ease: EASE_SOFT }}
                  className="absolute inset-0 h-full w-full object-cover contrast-[1.05] saturate-[0.75]"
                />
              ))}
              {/* Grades the frame into the page so it is not a bright rectangle
                  floating on black. */}
              <div className="absolute inset-0 bg-gradient-to-t from-[var(--color-bg)]/55 via-transparent to-transparent" />
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
