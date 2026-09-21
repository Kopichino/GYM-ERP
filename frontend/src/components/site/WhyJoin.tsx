import { REASONS } from "../../lib/siteContent";
import { BarbellRule } from "./GymMarks";
import Reveal from "./Reveal";

/** Why people stay: a centred statement, then five claims as a ruled ledger.
 *
 * The sticky two-column split this replaces put the argument in a narrow
 * gutter beside the reasons. Centring the statement and letting the reasons run
 * the full measure underneath gives each claim the width to be read in one line
 * of thought, and it puts this section on the same centre axis as the rest of
 * the page.
 *
 * The one section that sits on the raised surface rather than the page black.
 * That tonal step is doing real work: it separates the argument from the floor
 * above and the price list below without a border, a card or a photograph. */
export default function WhyJoin() {
  return (
    <section className="border-y border-[var(--color-border)] bg-[var(--color-surface)] py-24 sm:py-28 lg:py-32">
      <div className="mx-auto w-full max-w-[1400px] px-6 lg:px-10">
        <Reveal>
          <div className="mx-auto flex max-w-[50rem] flex-col items-center text-center">
            <h2 className="font-display text-[clamp(2.2rem,6vw,4.6rem)] text-[var(--color-text)]">
              Most people
              <br />
              quit <span className="text-[var(--color-accent)]">alone.</span>
            </h2>
            <p className="mt-6 max-w-[42ch] text-[15px] leading-[1.8] text-[var(--color-text-muted)]">
              So we built the gym around the things that keep people coming back after the first
              eight weeks, when motivation runs out and habit has to take over.
            </p>
            {/* The one drawn mark that is not the dumbbell, used once. */}
            <BarbellRule className="mt-10 h-8 w-full max-w-xs text-[var(--color-text)]/12" />
          </div>
        </Reveal>

        <ul className="mx-auto mt-16 max-w-[1100px] lg:mt-20">
          {REASONS.map((reason, i) => (
            <Reveal
              key={reason.title}
              as="li"
              delay={i * 0.06}
              className="border-t border-[var(--color-border)] py-7 lg:py-9"
            >
              <div className="grid gap-3 sm:grid-cols-[auto_minmax(0,0.9fr)_minmax(0,1.1fr)] sm:items-start sm:gap-8">
                <span
                  aria-hidden
                  className="font-display hidden text-base text-[var(--color-text-muted)]/55 sm:block sm:pt-1"
                >
                  {String(i + 1).padStart(2, "0")}
                </span>
                <h3 className="font-display text-2xl leading-[0.95] text-[var(--color-text)] sm:text-[1.9rem]">
                  {reason.title}
                </h3>
                <p className="text-[15px] leading-[1.75] text-[var(--color-text-muted)]">
                  {reason.copy}
                </p>
              </div>
            </Reveal>
          ))}
          <li aria-hidden className="border-t border-[var(--color-border)]" />
        </ul>
      </div>
    </section>
  );
}
