import type { ReactNode } from "react";
import { useBranding } from "../../hooks/useBranding";
import BrandMark from "../BrandMark";

/** A barbell, drawn rather than illustrated: it scales cleanly, costs nothing
 *  to load, and takes the gym's own accent colour so a white-labelled install
 *  doesn't end up with someone else's brand in its artwork. */
function Barbell({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 200 80" className={className} aria-hidden="true">
      <g fill="currentColor">
        <rect x="44" y="37" width="112" height="6" rx="3" />
        <rect x="56" y="29" width="8" height="22" rx="2" />
        <rect x="136" y="29" width="8" height="22" rx="2" />
        <rect x="30" y="17" width="16" height="46" rx="5" />
        <rect x="154" y="17" width="16" height="46" rx="5" />
        <rect x="16" y="27" width="10" height="26" rx="3" opacity="0.6" />
        <rect x="174" y="27" width="10" height="26" rx="3" opacity="0.6" />
      </g>
    </svg>
  );
}

const SELLING_POINTS = [
  "Log every set and watch the numbers move",
  "Book classes and check in with a scan",
  "Your plan, your macros, your progress",
];

const JOINING_STEPS = [
  { title: "Create your account", body: "Takes a minute. You are logged in the moment it saves." },
  { title: "Pick a plan at the desk", body: "Your membership starts the day it is paid, not the day you signed up." },
  { title: "Scan in and start logging", body: "Your card is on your phone. Tap it at the door and train." },
];

export type AuthVariant = "login" | "signup";

/**
 * The shell behind logging in and signing up.
 *
 * The two pages share a vocabulary -- same palette, same type, same drawn
 * artwork -- but are laid out as mirror images of each other, and that is
 * deliberate. Landing on the wrong one of two near-identical dark forms is a
 * genuinely common way to get stuck, so the halves swap sides, the accent
 * stripe moves to the other edge, and the two panels carry different content:
 * *coming back* on one, *what happens next* on the other. A member can tell
 * which page they are on before reading a word of it.
 *
 * The brand half is drawn with CSS and one inline SVG rather than an image or
 * the landing page's 3D scene -- these are the most-visited pages in the app
 * and should not pull a megabyte of Three.js to show a background.
 *
 * Below `lg` the brand panel drops away on both and the form takes the full
 * width, which is the only sensible thing to do with a split layout on a phone.
 */
export default function AuthLayout({
  variant,
  title,
  subtitle,
  children,
  footer,
}: {
  variant: AuthVariant;
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  const branding = useBranding();
  const isSignup = variant === "signup";

  // Login leads with the brand crimson; signup leads with amber. Both colours
  // are already in the palette, so this shifts the weight rather than
  // introducing a second design.
  const lead = isSignup ? "var(--color-accent-2)" : "var(--color-accent)";
  const trail = isSignup ? "var(--color-accent)" : "var(--color-accent-2)";

  // The explicit order matters: the other two halves are ordered so they can
  // swap sides, and an unordered flex child defaults to 0, which threw the
  // stripe back to the left edge on signup no matter where it sat in the JSX.
  const stripe = (
    <div
      className={`hidden w-2 shrink-0 lg:block ${isSignup ? "lg:order-3" : ""}`}
      style={{ background: `linear-gradient(180deg, ${lead}, ${trail})` }}
    />
  );

  const form = (
    <div
      className={`flex w-full flex-col bg-[var(--color-surface)] px-6 py-8 sm:px-10 lg:w-[44%] lg:max-w-[560px] ${
        isSignup ? "lg:order-2" : ""
      }`}
    >
      <BrandMark className="font-display text-2xl tracking-wide text-[var(--color-text)]" />

      {/* Login is centred in whatever space is left; signup is top-aligned,
          because a six-field form centred on a short screen ends up with its
          submit button below the fold. */}
      <div className={`flex flex-1 py-8 ${isSignup ? "items-start pt-10" : "items-center"}`}>
        <div className="w-full max-w-sm">
          <h1
            className="font-display text-4xl uppercase tracking-wide"
            style={{ color: isSignup ? lead : "var(--color-text)" }}
          >
            {title}
          </h1>
          <p className="mb-6 mt-1 text-sm text-[var(--color-text-muted)]">{subtitle}</p>
          {children}
        </div>
      </div>

      <div className="text-sm text-[var(--color-text-muted)]">{footer}</div>
    </div>
  );

  const brand = (
    <div
      className={`relative hidden flex-1 overflow-hidden lg:block ${
        isSignup ? "lg:order-1" : ""
      }`}
    >
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: isSignup
            ? [
                // Signup: one warm glow rising from the bottom-left and a dot
                // grid, so the texture reads as different at a glance from
                // login's diagonal hatch.
                `radial-gradient(ellipse 75% 55% at 15% 95%, color-mix(in srgb, ${lead} 20%, transparent), transparent 62%)`,
                `radial-gradient(ellipse 55% 45% at 85% 5%, color-mix(in srgb, ${trail} 14%, transparent), transparent 60%)`,
                "radial-gradient(var(--texture) 1px, transparent 1px)",
              ].join(",")
            : [
                `radial-gradient(ellipse 70% 50% at 20% 10%, color-mix(in srgb, ${lead} 22%, transparent), transparent 60%)`,
                `radial-gradient(ellipse 60% 45% at 90% 80%, color-mix(in srgb, ${trail} 16%, transparent), transparent 60%)`,
                "repeating-linear-gradient(135deg, var(--texture-faint) 0 2px, transparent 2px 14px)",
              ].join(","),
          backgroundSize: isSignup ? "auto, auto, 22px 22px" : undefined,
        }}
      />

      <div className="relative flex h-full flex-col justify-center px-12 xl:px-16">
        {isSignup ? (
          <SignupAside gymName={branding?.name || "IRONCORE"} accent={lead} />
        ) : (
          <LoginAside tagline={branding?.tagline || "Train hard. Track everything."} />
        )}
      </div>
    </div>
  );

  return (
    // Always dark, whatever the app theme is set to.
    //
    // These two screens are a designed piece rather than a surface: the lit
    // gradient, the diagonal texture and the brand stripe all read as a photo
    // studio at night, and none of it survives being flipped to white. Pinning
    // is honest about that -- it is not that light mode is unfinished here, it
    // is that this page has one look.
    //
    // A scoped island rather than forcing the document theme: writing to <html>
    // would fight the store, flash on navigation, and leave the app in the
    // wrong theme if someone closed the tab on the login screen. `colorScheme`
    // comes along so the native form controls are dark too.
    <div
      data-theme="dark"
      style={{ colorScheme: "dark" }}
      className="flex min-h-screen bg-[var(--color-bg)] text-[var(--color-text)]"
    >
      {/* The stripe sits on the outer edge of the form half, so it moves from
          the far left on login to the far right on signup. */}
      {!isSignup && stripe}
      {form}
      {brand}
      {isSignup && stripe}
    </div>
  );
}

/** Coming back: the promise, stated once, with what the app does for you. */
function LoginAside({ tagline }: { tagline: string }) {
  return (
    <>
      <Barbell className="mb-8 h-20 w-48 text-[var(--color-accent)]" />

      <p className="max-w-md font-display text-5xl uppercase leading-[1.05] tracking-wide text-[var(--color-text)]">
        {tagline}
      </p>

      <ul className="mt-8 flex max-w-md flex-col gap-3">
        {SELLING_POINTS.map((point) => (
          <li
            key={point}
            className="flex items-start gap-3 text-sm text-[var(--color-text-muted)]"
          >
            <span
              className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
              style={{ background: "var(--color-accent)" }}
            />
            {point}
          </li>
        ))}
      </ul>
    </>
  );
}

/**
 * Joining: what actually happens after the form, in order.
 *
 * Numbered steps rather than selling points, because someone on this page has
 * already decided -- what they do not know is what comes next, and the honest
 * answer includes "your membership starts when it is paid", which is exactly
 * the rule the billing ledger enforces.
 */
function SignupAside({ gymName, accent }: { gymName: string; accent: string }) {
  return (
    <>
      {/* A membership card rather than the barbell: it is the thing being
          created on the other half of the screen. */}
      <div
        className="mb-10 w-[300px] rounded-xl border p-5"
        style={{
          borderColor: "var(--color-border)",
          background:
            "linear-gradient(150deg, var(--color-surface-2), var(--color-surface))",
          boxShadow: `0 18px 50px -20px color-mix(in srgb, ${accent} 45%, transparent)`,
        }}
      >
        <div className="flex items-start justify-between">
          <span className="font-display text-xl tracking-wide text-[var(--color-text)]">
            {gymName}
          </span>
          <span
            className="rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
            style={{ background: accent, color: "var(--color-on-accent)" }}
          >
            Member
          </span>
        </div>

        <div className="mt-8 flex items-end justify-between">
          <div>
            <p className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
              Your name here
            </p>
            <p className="mt-0.5 font-display text-2xl tracking-wide text-[var(--color-text)]">
              — — — —
            </p>
          </div>
          {/* A suggestion of the check-in QR, not a real one. */}
          <div className="grid h-12 w-12 grid-cols-4 grid-rows-4 gap-[2px] opacity-70">
            {Array.from({ length: 16 }, (_, i) => (
              <span
                key={i}
                className="rounded-[1px]"
                style={{
                  background:
                    [0, 1, 2, 4, 6, 8, 9, 11, 13, 14].includes(i)
                      ? "var(--color-text)"
                      : "transparent",
                }}
              />
            ))}
          </div>
        </div>
      </div>

      <ol className="flex max-w-md flex-col gap-5">
        {JOINING_STEPS.map((step, index) => (
          <li key={step.title} className="flex gap-4">
            <span
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border font-display text-sm"
              style={{ borderColor: accent, color: accent }}
            >
              {index + 1}
            </span>
            <span>
              <span className="block text-sm font-semibold text-[var(--color-text)]">
                {step.title}
              </span>
              <span className="block text-sm text-[var(--color-text-muted)]">{step.body}</span>
            </span>
          </li>
        ))}
      </ol>
    </>
  );
}
