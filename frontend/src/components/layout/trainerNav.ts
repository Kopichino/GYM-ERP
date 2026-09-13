import { ICONS } from "./navIcons";
import type { PortalGroup } from "./navShared";

/**
 * The trainer portal's navigation, grouped the way the admin's is.
 *
 * Only what a trainer can actually open. Coaching comes first because it is the
 * job -- the members assigned to them, their PT bookings, the classes they run
 * -- and the gym content every role can read sits below it.
 */
export const TRAINER_GROUPS: PortalGroup[] = [
  {
    name: "Overview",
    links: [{ to: "/trainer", label: "Dashboard", end: true, icon: ICONS.gauge }],
  },
  {
    name: "Coaching",
    links: [
      { to: "/trainer/members", label: "My Members", icon: ICONS.members },
      { to: "/trainer/pt", label: "Personal Training", icon: ICONS.stopwatch },
      { to: "/trainer/schedule", label: "My Classes", icon: ICONS.calendar },
    ],
  },
  {
    name: "At the Gym",
    links: [
      { to: "/schedule", label: "Schedule", icon: ICONS.roster },
      { to: "/exercises", label: "Exercises", icon: ICONS.library },
    ],
  },
  {
    name: "Community",
    links: [
      { to: "/announcements", label: "Announcements", icon: ICONS.megaphone },
      { to: "/gallery", label: "Gallery", icon: ICONS.image },
    ],
  },
  {
    name: "Account",
    links: [{ to: "/trainer/profile", label: "My Profile", icon: ICONS.user }],
  },
];
