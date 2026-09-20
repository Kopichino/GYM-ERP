import { TESTIMONIALS } from "../../lib/siteContent";
import Reveal from "./Reveal";

/** Three members, three short quotes, and no faces.
 *
 * The portraits are gone. They were three more images earning very little: at
 * 40px, greyscale, on a page that had already spent its image budget, a stock
 * headshot adds a stock headshot. What carries a testimonial is the sentence
 * and the number underneath it, so the number is what gets the red.
 *
 * The hierarchy is scale, not layout: one quote set large on the centre axis,
 * two set small beneath it. That keeps the section on the page's centre line
 * while still refusing to be three matched panels in a row. */
export default function Testimonials() {
  const [lead, ...rest] = TESTIMONIALS;

  return (
    <section className="pt-16 pb-24 sm:pt-20 sm:pb-28 lg:pt-24 lg:pb-32">
      <div className="mx-auto w-full max-w-[1400px] px-6 lg:px-10">
        <Reveal>
          <h2 className="font-display mx-auto max-w-[22ch] text-center text-[clamp(2.2rem,6vw,4.6rem)] text-[var(--color-text)]">
            The people on the floor
          </h2>
        </Reveal>

        <Reveal delay={0.06}>
          <figure className="mx-auto mt-14 max-w-[44rem] text-center lg:mt-20">
            {/* Set in the body face. The display face is uppercase by
                definition, and a quote in caps stops being something a person
                said and starts being a slogan. */}
            <blockquote className="text-[clamp(1.5rem,3.4vw,2.6rem)] font-medium leading-[1.25] tracking-[-0.02em] text-[var(--color-text)]">
              {lead.quote}
            </blockquote>
            <figcaption className="mt-7">
              <span className="block text-sm font-bold text-[var(--color-text)]">{lead.name}</span>
              <span className="mt-1 block text-[12px] text-[var(--color-text-muted)]">
                {lead.since}
              </span>
              <span className="mt-2 block text-[13px] text-[var(--color-accent-soft)]">
                {lead.result}
              </span>
            </figcaption>
          </figure>
        </Reveal>

        <div className="mx-auto mt-16 grid max-w-[900px] gap-10 sm:grid-cols-2 sm:gap-14 lg:mt-20">
          {rest.map((person, i) => (
            <Reveal key={person.name} delay={0.1 + i * 0.08}>
              <figure className="border-t border-[var(--color-border)] pt-6">
                <blockquote className="text-[15px] leading-[1.7] text-[var(--color-text)]">
                  {person.quote}
                </blockquote>
                <figcaption className="mt-5">
                  <span className="block text-[13px] font-bold text-[var(--color-text)]">
                    {person.name}
                  </span>
                  <span className="mt-1 block text-[12px] text-[var(--color-accent-soft)]">
                    {person.result}
                  </span>
                </figcaption>
              </figure>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
