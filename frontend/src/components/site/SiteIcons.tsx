import type { ReactNode } from "react";

/** The handful of icons the public site uses, drawn inline.
 *
 * The sections came from a build that used an icon package this app does not
 * install. Eight glyphs do not justify a new dependency, so they live here as
 * plain SVG with the same call signature (`size`, `weight`) the sections already
 * use. `weight` is accepted so those call sites stay as they were, and ignored:
 * every glyph is drawn at one stroke width. */
type IconProps = { size?: number; weight?: string; className?: string };

function Glyph({ size = 20, className = "", children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
    >
      {children}
    </svg>
  );
}

export function ArrowUpRight(props: IconProps) {
  return (
    <Glyph {...props}>
      <path d="M7 17 17 7M8 7h9v9" />
    </Glyph>
  );
}

export function List(props: IconProps) {
  return (
    <Glyph {...props}>
      <path d="M4 6h16M4 12h16M4 18h16" />
    </Glyph>
  );
}

export function X(props: IconProps) {
  return (
    <Glyph {...props}>
      <path d="M6 6l12 12M18 6 6 18" />
    </Glyph>
  );
}

export function MapPin(props: IconProps) {
  return (
    <Glyph {...props}>
      <path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21Z" />
      <circle cx="12" cy="9.5" r="2.5" />
    </Glyph>
  );
}

export function Phone(props: IconProps) {
  return (
    <Glyph {...props}>
      <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2Z" />
    </Glyph>
  );
}

export function EnvelopeSimple(props: IconProps) {
  return (
    <Glyph {...props}>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m3 7 9 6 9-6" />
    </Glyph>
  );
}

export function InstagramLogo(props: IconProps) {
  return (
    <Glyph {...props}>
      <rect x="3" y="3" width="18" height="18" rx="5" />
      <circle cx="12" cy="12" r="4" />
      <path d="M17.5 6.5h.01" />
    </Glyph>
  );
}

export function WhatsappLogo(props: IconProps) {
  return (
    <Glyph {...props}>
      <path d="M3 21l1.7-5A8.5 8.5 0 1 1 8 19.3L3 21Z" />
      <path d="M9 9.5c0 3 2.5 5.5 5.5 5.5l1.2-1.3-1.8-1-1 .8a4 4 0 0 1-2.4-2.4l.8-1-1-1.8L9 9.5Z" />
    </Glyph>
  );
}

export function Globe(props: IconProps) {
  return (
    <Glyph {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" />
    </Glyph>
  );
}
