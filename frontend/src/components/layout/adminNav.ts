/**
 * The admin portal's navigation, grouped.
 *
 * Nineteen destinations in one flat strip meant the last few were only
 * reachable by scrolling, and nothing told you that Expenses and Commissions
 * are the same kind of job. Grouping is the point of the sidebar; the groups
 * below are the actual jobs a gym runs, not an alphabetical tidy-up.
 */

import { ICONS } from "./navIcons";
import { labelFor, type PortalGroup } from "./navShared";

export const ADMIN_GROUPS: PortalGroup[] = [
  {
    name: "Overview",
    links: [{ to: "/admin", label: "Dashboard", end: true, icon: ICONS.gauge }],
  },
  {
    name: "People",
    links: [
      { to: "/admin/members", label: "Members", icon: ICONS.members },
      { to: "/admin/trainers", label: "Trainers", icon: ICONS.trainers },
      { to: "/admin/enquiries", label: "Enquiries", icon: ICONS.phone },
      { to: "/admin/referrals", label: "Referrals", icon: ICONS.share },
      { to: "/admin/retention", label: "Retention", icon: ICONS.heartbeat },
      { to: "/admin/feedback", label: "Feedback", icon: ICONS.speech },
    ],
  },
  {
    name: "Money",
    links: [
      { to: "/admin/billing", label: "Billing", icon: ICONS.card },
      { to: "/admin/plans", label: "Plans", icon: ICONS.layers },
      { to: "/admin/offers", label: "Offers", icon: ICONS.tag },
      { to: "/admin/day-passes", label: "Day Passes", icon: ICONS.ticket },
      { to: "/admin/expenses", label: "Expenses", icon: ICONS.receipt },
      { to: "/admin/reports", label: "Reports", icon: ICONS.chart },
    ],
  },
  {
    name: "Operations",
    links: [
      { to: "/admin/kiosk", label: "Check-in QR", icon: ICONS.qr },
      { to: "/admin/devices", label: "Devices", icon: ICONS.device },
      { to: "/admin/schedule", label: "Schedule", icon: ICONS.calendar },
      { to: "/admin/shifts", label: "Staff Rota", icon: ICONS.roster },
      { to: "/admin/import", label: "Import Data", icon: ICONS.upload },
    ],
  },
  {
    name: "Content",
    links: [
      { to: "/admin/announcements", label: "Announcements", icon: ICONS.megaphone },
      { to: "/admin/gallery", label: "Gallery Moderation", icon: ICONS.image },
      { to: "/admin/badges", label: "Badges", icon: ICONS.medal },
      { to: "/admin/whatsapp", label: "WhatsApp", icon: ICONS.chat },
    ],
  },
  {
    name: "Setup",
    links: [
      { to: "/admin/branding", label: "Branding", icon: ICONS.palette },
      { to: "/admin/domains", label: "Web Address", icon: ICONS.device },
      { to: "/admin/email", label: "Email Address", icon: ICONS.speech },
      { to: "/admin/website-form", label: "Website Form", icon: ICONS.form },
    ],
  },
];

/** The page title for a pathname inside the admin portal. */
export function adminLabelFor(pathname: string) {
  return labelFor(ADMIN_GROUPS, pathname, "Admin Dashboard");
}
