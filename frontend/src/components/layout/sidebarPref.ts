/**
 * Whether the admin rail was left collapsed.
 *
 * Its own module so the sidebar file exports nothing but components -- mixing
 * the two costs fast refresh during development. Storage access can throw
 * outright in a locked-down browser, so both directions swallow failure: a
 * remembered preference is a convenience, not something worth breaking on.
 */

const STORE_KEY = "ironcore.admin.sidebar";

export function readCollapsed() {
  try {
    return window.localStorage.getItem(STORE_KEY) === "collapsed";
  } catch {
    return false;
  }
}

export function writeCollapsed(collapsed: boolean) {
  try {
    window.localStorage.setItem(STORE_KEY, collapsed ? "collapsed" : "expanded");
  } catch {
    // Ignored on purpose -- see the note above.
  }
}
