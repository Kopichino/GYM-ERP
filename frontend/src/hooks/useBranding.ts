import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { fetchBranding, type Branding } from "../api/branding";

/**
 * Loads the gym's identity and paints its colours onto the document.
 *
 * The two brand hues are written straight onto `:root`, which is where every
 * `var(--color-accent)` in the app already reads from -- so one gym's palette
 * reaches the whole portal without a single component knowing about branding.
 * The dark surfaces are left alone on purpose: they're the product's design,
 * not the gym's, and a light background under light text would be unreadable.
 */
export function useBranding() {
  const { data } = useQuery({
    queryKey: ["branding"],
    queryFn: fetchBranding,
    // The name on the door doesn't change during a session.
    staleTime: 15 * 60 * 1000,
    retry: 1,
  });

  useEffect(() => {
    if (!data) return;
    const root = document.documentElement;
    // Written to `--brand-*`, not straight onto `--color-accent`.
    //
    // Each theme defines `--color-accent: var(--brand-accent, <its default>)`,
    // so a gym's colour still wins everywhere -- including inside the login
    // screen's pinned-dark island, which declares its own accent and would
    // otherwise have overridden an inline value set on <html>. Unbranded, each
    // theme keeps the accent it was designed with.
    root.style.setProperty("--brand-accent", data.accent);
    root.style.setProperty("--brand-accent-2", data.accent_2);
    if (data.name) document.title = data.name;

    // The headline face is fetched only once a gym has actually chosen it,
    // rather than preloading all five for everyone -- four of them would be
    // dead weight on every page load. Bebas Neue is already in index.html as
    // the default, so the common case adds no request at all.
    if (data.display_font && data.display_font !== "Bebas Neue") {
      const id = "branding-display-font";
      const family = data.display_font.replace(/ /g, "+");
      const href = `https://fonts.googleapis.com/css2?family=${family}&display=swap`;
      let link = document.getElementById(id) as HTMLLinkElement | null;
      if (!link) {
        link = document.createElement("link");
        link.id = id;
        link.rel = "stylesheet";
        document.head.appendChild(link);
      }
      // Only touch href when it actually changes: reassigning the same URL
      // makes the browser re-evaluate the sheet and flashes the headings.
      if (link.href !== href) link.href = href;
    }
    // Falls back through to Inter and the system stack if the face is slow or
    // blocked, so a heading is never invisible while waiting on a font.
    root.style.setProperty(
      "--font-display",
      `"${data.display_font || "Bebas Neue"}", "Inter", system-ui, sans-serif`,
    );
  }, [data]);

  return data as Branding | undefined;
}
