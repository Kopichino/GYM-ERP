import { useEffect, type CSSProperties } from "react";
import About from "../components/site/About";
import Facilities from "../components/site/Facilities";
import FinalCta from "../components/site/FinalCta";
import Hero from "../components/site/Hero";
import Membership from "../components/site/Membership";
import Programs from "../components/site/Programs";
import SiteFooter from "../components/site/SiteFooter";
import SiteNav from "../components/site/SiteNav";
import Testimonials from "../components/site/Testimonials";
import Ticker from "../components/site/Ticker";
import WhyJoin from "../components/site/WhyJoin";
import { useBranding } from "../hooks/useBranding";

/** Black or white, whichever reads on a filled button in the gym's colour.
 *
 * A gym can pick any accent on the Branding page. White text suits the default
 * red; on an amber or a light green it all but disappears. Buttons are filled
 * with a slightly darkened accent, so the cut-off sits a little above the
 * textbook contrast crossover. */
function readableOn(hex: string | undefined) {
  const match = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex ?? "");
  if (!match) return "#ffffff";
  const full = match[1].length === 3 ? match[1].replace(/./g, (c) => c + c) : match[1];
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(full.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.26 ? "#0b0b10" : "#ffffff";
}

/** The public website, in the order the argument is made:
 *
 *   who we are, what we train, where you train it, why it works, what it costs,
 *   who else is here, and then the ask.
 *
 * It is the gym's own site, not a template: the name or logo, the colour, the
 * address, phone, email, Instagram and opening hours come from the Branding
 * page, and the price list from the Plans page -- so what an admin changes in
 * the portal is what a visitor sees here. The marketing copy and photography in
 * `lib/siteContent.ts` are still placeholders for a gym to replace.
 *
 * The page carries its own look, pinned dark whatever theme the portal is in:
 * the `.site` scope in index.css sets its palette and type, with the accent
 * taken from the gym's brand colour. */
export default function LandingPage() {
  const branding = useBranding();

  // The browser resolves the fragment before React has mounted the sections,
  // so a deep link would otherwise land at the top of the page.
  useEffect(() => {
    const { hash } = window.location;
    if (!hash) return;
    const frame = requestAnimationFrame(() => {
      document.getElementById(hash.slice(1))?.scrollIntoView();
    });
    return () => cancelAnimationFrame(frame);
  }, []);

  // In-page links glide rather than jump. Set on the document only while the
  // website is showing, so the portal keeps instant scrolling -- and never for
  // someone who has asked for less motion.
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const root = document.documentElement;
    const previous = root.style.scrollBehavior;
    root.style.scrollBehavior = "smooth";
    return () => {
      root.style.scrollBehavior = previous;
    };
  }, []);

  return (
    <div
      className="site min-h-screen overflow-x-hidden bg-[var(--color-bg)] text-[var(--color-text)]"
      style={{ "--color-on-accent": readableOn(branding?.accent) } as CSSProperties}
    >
      <SiteNav />
      <main>
        <Hero />
        <About />
        <Ticker />
        <Programs />
        <Facilities />
        <WhyJoin />
        <Membership />
        <Testimonials />
        <FinalCta />
      </main>
      <SiteFooter />
    </div>
  );
}
