import { Link } from "react-router-dom";
import { CTA } from "../../lib/siteContent";
import BrandMark from "../BrandMark";
import { EnvelopeSimple, Globe, InstagramLogo, MapPin, Phone, WhatsappLogo } from "./SiteIcons";
import { useGym } from "./useGym";

const NAV = [
  { href: "#about", label: "About" },
  { href: "#programmes", label: "Programmes" },
  { href: "#facilities", label: "Facilities" },
  { href: "#membership", label: "Membership" },
];

const HEADING = "text-[11px] font-bold tracking-[0.16em] text-[var(--color-text)] uppercase";

/** Contact, hours and the way in, read from the gym's Branding page.
 *
 * Every line here is something a real person will act on -- ring the number,
 * walk to the address, turn up at opening time -- so it is never an example.
 * Whatever the gym has not filled in is simply not shown, and the hours and
 * social columns drop out entirely when they would be empty. */
export default function SiteFooter() {
  const gym = useGym();
  const address = gym.addressLines.join(", ");

  const socials = [
    { label: "Instagram", href: gym.instagramUrl, Icon: InstagramLogo },
    { label: "WhatsApp", href: gym.whatsappUrl, Icon: WhatsappLogo },
    { label: "Website", href: gym.website, Icon: Globe },
  ].filter((social) => social.href);

  const hasHours = gym.hours.length > 0;

  return (
    <footer id="contact" className="scroll-mt-20 border-t border-[var(--color-border)]">
      <div className="mx-auto w-full max-w-[1400px] px-6 py-16 lg:px-10 lg:py-20">
        <div
          className={`grid gap-12 ${
            hasHours
              ? "lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,0.8fr)]"
              : "lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,0.8fr)]"
          }`}
        >
          <div>
            <p className="font-display text-3xl text-[var(--color-text)]">
              <BrandMark />
            </p>
            <address className="mt-5 flex flex-col gap-3 text-sm not-italic text-[var(--color-text-muted)]">
              {address && (
                <a
                  href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-start gap-2.5 transition-colors hover:text-[var(--color-text)]"
                >
                  <MapPin size={16} className="mt-0.5 shrink-0" />
                  <span>
                    {gym.addressLines.map((line) => (
                      <span key={line} className="block">
                        {line}
                      </span>
                    ))}
                  </span>
                </a>
              )}
              {gym.phone && (
                <a
                  href={`tel:${gym.phone.replace(/[^\d+]/g, "")}`}
                  className="flex items-center gap-2.5 transition-colors hover:text-[var(--color-text)]"
                >
                  <Phone size={16} className="shrink-0" />
                  {gym.phone}
                </a>
              )}
              {gym.email && (
                <a
                  href={`mailto:${gym.email}`}
                  className="flex items-center gap-2.5 transition-colors hover:text-[var(--color-text)]"
                >
                  <EnvelopeSimple size={16} className="shrink-0" />
                  {gym.email}
                </a>
              )}
            </address>
          </div>

          {hasHours && (
            <div>
              <h2 className={HEADING}>Opening hours</h2>
              <dl className="mt-5 flex flex-col gap-2.5 text-sm">
                {gym.hours.map((slot) => (
                  <div key={`${slot.days}-${slot.time}`} className="flex justify-between gap-4">
                    <dt className="text-[var(--color-text-muted)]">{slot.days}</dt>
                    <dd className="text-right text-[var(--color-text)]">{slot.time}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          <div>
            <h2 className={HEADING}>Explore</h2>
            <ul className="mt-5 flex flex-col gap-2.5 text-sm">
              {NAV.map((item) => (
                <li key={item.href}>
                  <a
                    href={item.href}
                    className="text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text)]"
                  >
                    {item.label}
                  </a>
                </li>
              ))}
              <li>
                <Link
                  to="/login"
                  className="text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text)]"
                >
                  Member log in
                </Link>
              </li>
            </ul>
          </div>

          <div>
            {socials.length > 0 && (
              <>
                <h2 className={HEADING}>Follow</h2>
                <div className="mt-5 flex gap-3">
                  {socials.map(({ label, href, Icon }) => (
                    <a
                      key={label}
                      href={href}
                      aria-label={label}
                      target="_blank"
                      rel="noreferrer"
                      className="flex h-10 w-10 items-center justify-center border border-[var(--color-border)] text-[var(--color-text-muted)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent-soft)]"
                    >
                      <Icon size={18} />
                    </a>
                  ))}
                </div>
              </>
            )}
            <Link
              to="/signup"
              className={`${socials.length > 0 ? "mt-6" : ""} inline-block bg-[var(--color-accent-strong)] px-6 py-3 text-sm font-bold text-[var(--color-on-accent)] transition-colors hover:bg-[var(--color-accent-hover)]`}
            >
              {CTA.primary}
            </Link>
          </div>
        </div>

        <p className="mt-14 border-t border-[var(--color-border)] pt-6 text-xs text-[var(--color-text-muted)]">
          &copy; {new Date().getFullYear()} {gym.name}
          {gym.addressLines.length > 0 ? `, ${gym.addressLines[gym.addressLines.length - 1]}` : ""}.
        </p>
      </div>
    </footer>
  );
}
