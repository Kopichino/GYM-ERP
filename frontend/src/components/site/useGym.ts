import { useBranding } from "../../hooks/useBranding";

export interface GymDetails {
  name: string;
  tagline: string;
  /** The address as typed on the Branding page, one entry per line. */
  addressLines: string[];
  phone: string;
  email: string;
  instagramUrl: string;
  whatsappUrl: string;
  website: string;
  hours: { days: string; time: string }[];
}

function lines(text?: string | null) {
  return (text ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

/**
 * The gym's own details for the public website, read from Branding.
 *
 * Everything that identifies one particular gym -- name, address, phone, email,
 * Instagram, opening hours -- comes from the Branding page in the admin portal,
 * so the website changes as soon as an admin saves there. Anything left blank
 * is left off the site rather than filled in with an example: a made-up phone
 * number on a real gym's website is worse than no phone number.
 */
export function useGym(): GymDetails {
  const branding = useBranding();
  const phone = branding?.phone?.trim() ?? "";
  const digits = phone.replace(/\D/g, "");
  const handle = branding?.instagram?.trim() ?? "";

  return {
    name: branding?.name || "IRONCORE",
    tagline: branding?.tagline?.trim() ?? "",
    addressLines: lines(branding?.address),
    phone,
    email: branding?.email?.trim() ?? "",
    instagramUrl: !handle
      ? ""
      : /^https?:\/\//i.test(handle)
        ? handle
        : `https://instagram.com/${handle.replace(/^@/, "")}`,
    // wa.me needs the full international number. A local number without its
    // country code would open a chat with somebody else, so only a number long
    // enough to carry one gets a link.
    whatsappUrl: digits.length >= 11 ? `https://wa.me/${digits}` : "",
    website: branding?.website?.trim() ?? "",
    // "Monday to Friday: 5:30 - 23:00" -- split on the first colon followed by
    // a space, so the colon inside "5:30" is left alone.
    hours: lines(branding?.opening_hours).map((line) => {
      const cut = line.indexOf(": ");
      return cut > 0
        ? { days: line.slice(0, cut).trim(), time: line.slice(cut + 2).trim() }
        : { days: line, time: "" };
    }),
  };
}
