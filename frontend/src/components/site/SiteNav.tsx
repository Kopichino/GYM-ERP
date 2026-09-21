import { AnimatePresence, motion, useMotionValueEvent, useScroll } from "framer-motion";
import { useState } from "react";
import { Link } from "react-router-dom";
import { CTA } from "../../lib/siteContent";
import { homePathFor, useAuthStore } from "../../store/authStore";
import BrandMark from "../BrandMark";
import { List, X } from "./SiteIcons";

const LINKS = [
  { href: "#about", label: "About" },
  { href: "#programmes", label: "Programmes" },
  { href: "#facilities", label: "Facilities" },
  { href: "#membership", label: "Membership" },
  { href: "#contact", label: "Contact" },
];

/** Site header. Transparent over the hero, then a solid blurred bar once the
 * visitor scrolls past it. One row at every width above `lg`, 68px tall.
 *
 * The wordmark is the gym's own -- its name or uploaded logo, from Branding --
 * and the right-hand side knows whether the visitor is already signed in: a
 * member landing on the website gets a way back into the app, not a sign-up
 * button. */
export default function SiteNav() {
  const { scrollY } = useScroll();
  const [solid, setSolid] = useState(false);
  const [open, setOpen] = useState(false);
  const user = useAuthStore((s) => s.user);

  useMotionValueEvent(scrollY, "change", (y) => {
    const next = y > 32;
    setSolid((prev) => (prev === next ? prev : next));
  });

  const primary = user
    ? { to: homePathFor(user), label: "Open the app" }
    : { to: "/signup", label: CTA.primary };

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-colors duration-300 ${
        solid
          ? "border-b border-[var(--color-border)] bg-[var(--color-bg)]/90 backdrop-blur-md"
          : "border-b border-transparent"
      }`}
    >
      {!solid && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-28 bg-gradient-to-b from-[var(--color-bg)]/85 to-transparent"
        />
      )}

      <nav className="mx-auto flex h-[68px] w-full max-w-[1400px] items-center justify-between px-6 lg:px-10">
        <Link
          to="/"
          className="font-display text-2xl text-[var(--color-text)]"
          style={{ letterSpacing: "0.02em" }}
        >
          <BrandMark />
        </Link>

        <div className="hidden items-center gap-9 lg:flex">
          {LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="group relative py-1 text-[13px] font-medium text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text)]"
            >
              {link.label}
              <span className="absolute -bottom-0.5 left-0 h-px w-full origin-left scale-x-0 bg-[var(--color-accent)] transition-transform duration-[450ms] ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:scale-x-100" />
            </a>
          ))}
        </div>

        <div className="flex items-center gap-5">
          {!user && (
            <Link
              to="/login"
              className="hidden text-[13px] font-medium text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text)] sm:block"
            >
              Log in
            </Link>
          )}
          <Link
            to={primary.to}
            className="hidden bg-[var(--color-accent-strong)] px-5 py-2.5 text-[13px] font-bold tracking-wide text-[var(--color-on-accent)] transition-colors duration-200 hover:bg-[var(--color-accent-hover)] active:scale-[0.98] sm:block"
          >
            {primary.label}
          </Link>
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            className="p-1.5 text-[var(--color-text)] lg:hidden"
          >
            {open ? <X size={22} weight="bold" /> : <List size={22} weight="bold" />}
          </button>
        </div>
      </nav>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden border-t border-[var(--color-border)] bg-[var(--color-bg)] lg:hidden"
          >
            <div className="flex flex-col px-6 py-4">
              {LINKS.map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  onClick={() => setOpen(false)}
                  className="font-display border-b border-[var(--color-border)] py-4 text-2xl text-[var(--color-text)] last:border-b-0"
                >
                  {link.label}
                </a>
              ))}
              <Link
                to={primary.to}
                onClick={() => setOpen(false)}
                className="mt-5 bg-[var(--color-accent-strong)] px-5 py-3.5 text-center text-sm font-bold text-[var(--color-on-accent)]"
              >
                {primary.label}
              </Link>
              {!user && (
                <Link
                  to="/login"
                  onClick={() => setOpen(false)}
                  className="mt-3 pb-2 text-center text-xs text-[var(--color-text-muted)]"
                >
                  Member log in
                </Link>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
