import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchPublicPlans, type PublicPlan } from "../../api/site";
import { CTA } from "../../lib/siteContent";
import Reveal from "./Reveal";

const COUNT_WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight"];

/** Static class names per column count: Tailwind only generates classes it can
 * find written out in full, so a computed `lg:grid-cols-${n}` would never exist. */
const COLUMNS: Record<number, string> = {
  1: "lg:mx-auto lg:max-w-md",
  2: "lg:grid-cols-2 lg:divide-x lg:divide-y-0",
  3: "lg:grid-cols-3 lg:divide-x lg:divide-y-0",
};
const MANY_COLUMNS = "lg:grid-cols-4 lg:divide-x lg:divide-y-0";

function rupees(value: number) {
  return value.toLocaleString("en-IN", { maximumFractionDigits: Number.isInteger(value) ? 0 : 2 });
}

/** The billing period in words, from the plan's length in days. */
function cadence(days: number) {
  if (days === 1) return "per day";
  if (days === 7) return "per week";
  if (days >= 28 && days <= 31) return "per month";
  if (days >= 84 && days <= 93) return "per quarter";
  if (days >= 180 && days <= 186) return "per six months";
  if (days >= 360 && days <= 366) return "per year";
  return `for ${days} days`;
}

/** What a longer plan comes to per month, which is the figure people compare. */
function perMonth(plan: PublicPlan) {
  if (plan.duration_days < 45) return "";
  const monthly = Math.round((Number(plan.price) / plan.duration_days) * 30);
  return `Works out to ₹${rupees(monthly)} a month.`;
}

/** The plan's description, one feature per line, as the admin typed it. */
function features(plan: PublicPlan) {
  const listed = plan.description
    .split(/\r?\n/)
    .map((line) => line.replace(/^[\s\-*•]+/, "").trim())
    .filter(Boolean);
  return listed.length ? listed : [`${plan.duration_days} days of full access`, "Member app and check in"];
}

/** The plan that costs least per day, when there is a clear winner. */
function bestValueId(plans: PublicPlan[]) {
  if (plans.length < 2) return null;
  const rates = plans
    .map((plan) => ({ id: plan.id, rate: Number(plan.price) / plan.duration_days }))
    .sort((a, b) => a.rate - b.rate);
  return rates[0].rate < rates[1].rate ? rates[0].id : null;
}

/** Shortest to longest, with the featured plan moved to the middle column when
 * there is one, so it lands in the centre of the panel at desktop. */
function arrange(plans: PublicPlan[], featured: number | null) {
  const byLength = [...plans].sort(
    (a, b) => a.duration_days - b.duration_days || Number(a.price) - Number(b.price),
  );
  if (featured === null || byLength.length % 2 === 0) return byLength;
  const star = byLength.filter((plan) => plan.id === featured);
  const rest = byLength.filter((plan) => plan.id !== featured);
  const middle = Math.floor(byLength.length / 2);
  return [...rest.slice(0, middle), ...star, ...rest.slice(middle)];
}

/** The price list, read live from the gym's own plans.
 *
 * These are the plans an admin keeps on the Plans page -- the same rows the
 * front desk charges against -- so a price changed there is the price on the
 * website on the next visit. Nothing here is typed in twice. Retired plans are
 * left off, and the "best value" mark and per-month figures are worked out
 * from the prices rather than claimed.
 *
 * Laid out to be compared rather than admired: one bordered panel divided by
 * hairlines, so the columns read as one price list and the eye can run across a
 * row instead of hopping between boxes. */
export default function Membership() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["public-plans"],
    queryFn: fetchPublicPlans,
    // Fetched fresh on every visit. This is the price list, and it has to agree
    // with the front desk the moment an admin changes it.
    staleTime: 0,
  });

  const featured = bestValueId(data ?? []);
  const plans = arrange(data ?? [], featured);
  const count = plans.length;
  const heading =
    count > 0 && count < COUNT_WORDS.length
      ? `One floor. ${COUNT_WORDS[count]} ${count === 1 ? "way" : "ways"} in.`
      : "One floor. Every way in.";

  return (
    <section id="membership" className="scroll-mt-20 pt-24 pb-20 sm:pt-28 sm:pb-24 lg:pt-32 lg:pb-24">
      <div className="mx-auto w-full max-w-[1400px] px-6 lg:px-10">
        <Reveal>
          <div className="mx-auto max-w-[50rem] text-center">
            <h2 className="font-display text-[clamp(2.2rem,6vw,4.6rem)] text-[var(--color-text)]">
              {heading}
            </h2>
            <p className="mx-auto mt-6 max-w-[50ch] text-[15px] leading-[1.75] text-[var(--color-text-muted)]">
              Every plan comes with the member app: check in at the door, log your training and
              watch your progress.
            </p>
          </div>
        </Reveal>

        {isLoading ? (
          <div
            aria-label="Loading membership plans"
            className="mt-14 grid divide-y divide-[var(--color-border)] border border-[var(--color-border)] lg:mt-20 lg:grid-cols-3 lg:divide-x lg:divide-y-0"
          >
            {[0, 1, 2].map((slot) => (
              <div key={slot} className="flex animate-pulse flex-col gap-5 p-7 lg:p-9">
                <div className="h-6 w-28 bg-[var(--color-surface-2)]" />
                <div className="h-12 w-40 bg-[var(--color-surface-2)]" />
                <div className="h-24 w-full bg-[var(--color-surface-2)]" />
              </div>
            ))}
          </div>
        ) : isError || count === 0 ? (
          <Reveal delay={0.08}>
            <div className="mt-14 flex flex-col items-center gap-6 border border-[var(--color-border)] p-10 text-center lg:mt-20">
              <p className="max-w-[46ch] text-[15px] leading-[1.75] text-[var(--color-text-muted)]">
                {isError
                  ? "Prices could not be loaded just now. Book a visit and we will walk you through every plan."
                  : "Plans are being updated. Book a visit and we will walk you through the options."}
              </p>
              <a
                href="#contact"
                className="border border-[var(--color-border)] px-9 py-4 text-sm font-bold tracking-wide text-[var(--color-text)] transition-colors duration-300 hover:border-[var(--color-text-muted)]"
              >
                {CTA.secondary}
              </a>
            </div>
          </Reveal>
        ) : (
          <Reveal delay={0.08}>
            <div
              className={`mt-14 grid divide-y divide-[var(--color-border)] border border-[var(--color-border)] lg:mt-20 ${
                COLUMNS[count] ?? MANY_COLUMNS
              }`}
            >
              {plans.map((plan) => {
                const isFeatured = plan.id === featured;
                const note = perMonth(plan);
                return (
                  <div
                    key={plan.id}
                    className={`relative flex flex-col p-7 lg:p-9 ${
                      isFeatured ? "bg-[var(--color-surface-2)]" : ""
                    }`}
                  >
                    {isFeatured && (
                      <span aria-hidden className="absolute inset-x-0 top-0 h-0.5 bg-[var(--color-accent)]" />
                    )}

                    <div className="flex items-baseline justify-between gap-4">
                      <h3 className="font-display text-2xl text-[var(--color-text)]">{plan.name}</h3>
                      {isFeatured && (
                        <span className="text-[11px] font-bold tracking-[0.14em] text-[var(--color-accent-soft)] uppercase">
                          Best value
                        </span>
                      )}
                    </div>

                    <p className="mt-7 flex flex-wrap items-baseline gap-2">
                      <span className="font-display text-[clamp(2.6rem,4.4vw,3.6rem)] text-[var(--color-text)]">
                        {/* Body face on purpose: the display face has no rupee
                            glyph and falls back mid-number without it. */}
                        <span
                          className="align-baseline text-[0.42em] text-[var(--color-text-muted)]"
                          style={{ fontFamily: "var(--font-sans)" }}
                        >
                          &#8377;
                        </span>
                        {rupees(Number(plan.price))}
                      </span>
                      <span className="text-[13px] text-[var(--color-text-muted)]">
                        {cadence(plan.duration_days)}
                      </span>
                    </p>
                    {/* Kept at a fixed height when empty, so the feature rows of
                        neighbouring plans still start level. */}
                    <p className="mt-2 min-h-[1.25rem] text-[13px] text-[var(--color-text-muted)]">{note}</p>

                    {/* Ruled rows rather than a bulleted list, so the same line
                        of two neighbouring plans sits at the same height. */}
                    <ul className="mt-8 flex flex-1 flex-col divide-y divide-[var(--color-border)]/70 border-t border-[var(--color-border)]/70">
                      {features(plan).map((feature) => (
                        <li key={feature} className="py-3 text-[14px] text-[var(--color-text)]">
                          {feature}
                        </li>
                      ))}
                    </ul>

                    <Link
                      to="/signup"
                      className={`mt-9 py-4 text-center text-sm font-bold tracking-wide transition-colors duration-300 active:translate-y-px ${
                        isFeatured
                          ? "bg-[var(--color-accent-strong)] text-[var(--color-on-accent)] hover:bg-[var(--color-accent-hover)]"
                          : "border border-[var(--color-border)] text-[var(--color-text)] hover:border-[var(--color-text-muted)] hover:bg-white/[0.04]"
                      }`}
                    >
                      {CTA.primary}
                    </Link>
                  </div>
                );
              })}
            </div>
          </Reveal>
        )}
      </div>
    </section>
  );
}
