import { ICONS } from "./navIcons";
import type { PortalGroup } from "./navShared";

/**
 * The member portal's navigation, grouped the way the admin's is.
 *
 * Only what a member can actually open: their own training and account, plus
 * the gym content every signed-in role can read. The groups follow what someone
 * comes to the app to do -- train, come in, keep up with the gym, sort out
 * their membership -- rather than the order the pages happened to be built in.
 */
export const MEMBER_GROUPS: PortalGroup[] = [
  {
    name: "Overview",
    links: [{ to: "/dashboard", label: "Dashboard", icon: ICONS.gauge }],
  },
  {
    name: "Training",
    links: [
      { to: "/workouts", label: "Workouts", icon: ICONS.dumbbell },
      { to: "/split", label: "My Split", icon: ICONS.layers },
      { to: "/diet", label: "My Diet", icon: ICONS.bowl },
      { to: "/exercises", label: "Exercises", icon: ICONS.library },
      { to: "/progress", label: "Progress", icon: ICONS.chart },
    ],
  },
  {
    name: "At the Gym",
    links: [
      { to: "/schedule", label: "Schedule", icon: ICONS.calendar },
      { to: "/book-trainer", label: "Book a Trainer", icon: ICONS.stopwatch },
    ],
  },
  {
    name: "Community",
    links: [
      { to: "/announcements", label: "Announcements", icon: ICONS.megaphone },
      { to: "/gallery", label: "Gallery", icon: ICONS.image },
      { to: "/achievements", label: "Achievements", icon: ICONS.medal },
      { to: "/referrals", label: "Refer a Friend", icon: ICONS.share },
    ],
  },
  {
    name: "Account",
    links: [
      { to: "/billing", label: "Billing", icon: ICONS.card },
      { to: "/profile", label: "Profile", icon: ICONS.user },
    ],
  },
];
