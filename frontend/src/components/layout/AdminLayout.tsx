import { AnimatePresence, motion } from "framer-motion";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { pageTransition } from "../../lib/motion";
import { PageHeader } from "../ui";

const links = [
  { to: "/admin", label: "Members", end: true },
  { to: "/admin/billing", label: "Billing" },
  { to: "/admin/plans", label: "Plans" },
  { to: "/admin/announcements", label: "Announcements" },
  { to: "/admin/instructors", label: "Instructors" },
  { to: "/admin/schedule", label: "Schedule" },
  { to: "/admin/gallery", label: "Gallery Moderation" },
];

export default function AdminLayout() {
  const location = useLocation();

  return (
    <div>
      <PageHeader title="Admin Dashboard" subtitle="Manage members and gym content." />
      <div className="mb-6 flex flex-wrap gap-1 border-b border-[var(--color-border)] pb-2">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              `rounded-md px-3 py-1.5 text-sm font-medium ${
                isActive
                  ? "bg-[var(--color-accent)] text-white"
                  : "text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
              }`
            }
          >
            {link.label}
          </NavLink>
        ))}
      </div>
      <AnimatePresence mode="wait">
        <motion.div
          key={location.pathname}
          initial="initial"
          animate="animate"
          exit="exit"
          variants={pageTransition}
          transition={{ duration: 0.25, ease: "easeInOut" }}
        >
          <Outlet />
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
