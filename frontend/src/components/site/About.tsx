import { ABOUT } from "../../lib/siteContent";
import CountUp from "./CountUp";
import Reveal from "./Reveal";
import { useGym } from "./useGym";

/** Who we are. No photograph anywhere in this section, on purpose.
 *
 * The hero has just spent a full viewport on a picture. Following it with more
 * pictures is how a page starts to feel like a gallery instead of an argument,
 * so this section is carried entirely by type: one large statement across the
 * full measure, a rule, then the story on the left against three figures
 * stacked on the right. The figures are the visual. */
export default function About() {
  const gym = useGym();

  return (
    <section id="about" className="scroll-mt-20 pb-24 pt-20 sm:pb-28 sm:pt-24 lg:pb-32 lg:pt-28">
      <div className="mx-auto w-full max-w-[1400px] px-6 lg:px-10">
        <Reveal>
          <h2 className="font-display mx-auto max-w-[18ch] text-center text-[clamp(2.4rem,7vw,5.6rem)] text-[var(--color-text)]">
            {/* No accent in this section. It follows the most saturated
                moment on the page, and the red means more if it stops. */}
            {ABOUT.headline.map((l) => (
              <span key={l} className="block">
                {l}
              </span>
            ))}
          </h2>
        </Reveal>

        <Reveal delay={0.06}>
          <div className="mt-14 h-px w-full bg-[var(--color-border)] lg:mt-20" />
        </Reveal>

        <div className="grid gap-14 pt-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)] lg:gap-24 lg:pt-16">
          <div>
            {/* Spacing keys off the index, not `first:`. Each paragraph sits in
                its own Reveal wrapper, so every one of them is a first-child and
                position-based selectors silently match all of them. */}
            {ABOUT.body(gym.name).map((paragraph, i) => (
              <Reveal key={i} delay={0.08 + i * 0.07}>
                <p
                  className={`max-w-[58ch] text-[15px] leading-[1.8] text-[var(--color-text-muted)] ${
                    i === 0 ? "" : "mt-6"
                  }`}
                >
                  {paragraph}
                </p>
              </Reveal>
            ))}
          </div>

          {/* Three figures stacked rather than sat in a row. Stacked, each one
              gets its own line of the page and reads as a claim; in a row they
              turn into a strip of statistics nobody looks at.

              Number and label sit together on the left of a narrow column. Held
              apart by `justify-between` across the full column they stopped
              reading as one fact and became a figure with an unrelated caption
              floating opposite it. */}
          <dl className="w-full max-w-[22rem] lg:ml-auto lg:pt-1.5">
            {ABOUT.stats.map((stat, i) => (
              <Reveal key={stat.label} delay={0.12 + i * 0.08}>
                <div
                  className={`flex items-baseline gap-5 sm:py-7 ${
                    i === 0 ? "" : "border-t border-[var(--color-border)] py-6"
                  }`}
                >
                  <dt className="font-display min-w-[2.2em] text-[clamp(2.6rem,5.5vw,4rem)] leading-none text-[var(--color-text)]">
                    <CountUp to={stat.to} suffix={stat.suffix} />
                  </dt>
                  <dd className="max-w-[16ch] text-[13px] leading-snug text-[var(--color-text-muted)]">
                    {stat.label}
                  </dd>
                </div>
              </Reveal>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}
