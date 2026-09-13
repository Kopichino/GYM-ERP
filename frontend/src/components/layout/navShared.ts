/**
 * The shape every portal's navigation is described in.
 *
 * Admin, member and trainer menus are one component fed three different lists,
 * so a change to how navigation looks or behaves lands in all three portals at
 * once instead of drifting apart one portal at a time.
 */

export interface PortalLink {
  to: string;
  label: string;
  /** Passed to NavLink so a portal's home doesn't match every child route. */
  end?: boolean;
  /** A 24x24 stroke path from `navIcons`. */
  icon: string;
}

export interface PortalGroup {
  name: string;
  links: PortalLink[];
}

/** The label for a pathname. Longest match wins, so "/admin/billing" resolves
 *  to Billing rather than to the dashboard at "/admin". */
export function labelFor(groups: PortalGroup[], pathname: string, fallback: string) {
  const match = groups
    .flatMap((group) => group.links)
    .filter(
      (link) => pathname === link.to || (!link.end && pathname.startsWith(`${link.to}/`)),
    )
    .sort((a, b) => b.to.length - a.to.length)[0];
  return match?.label ?? fallback;
}
