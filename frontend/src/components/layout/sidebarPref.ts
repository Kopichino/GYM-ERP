/**
 * Whether a portal's rail was left collapsed.
 *
 * Its own module so the sidebar file exports nothing but components -- mixing
 * the two costs fast refresh during development. Storage access can throw
 * outright in a locked-down browser, so both directions swallow failure: a
 * remembered preference is a convenience, not something worth breaking on.
 *
 * Kept per portal: the wide tables that make someone collapse the admin rail
 * are not in the member or trainer portals. Admin's key is unchanged, so a
 * preference saved before member and trainer had a rail still applies.
 */

export type Portal = "admin" | "member" | "trainer";

const keyFor = (portal: Portal) => `ironcore.${portal}.sidebar`;

export function readCollapsed(portal: Portal = "admin") {
  try {
    return window.localStorage.getItem(keyFor(portal)) === "collapsed";
  } catch {
    return false;
  }
}

export function writeCollapsed(collapsed: boolean, portal: Portal = "admin") {
  try {
    window.localStorage.setItem(keyFor(portal), collapsed ? "collapsed" : "expanded");
  } catch {
    // Ignored on purpose -- see the note above.
  }
}
