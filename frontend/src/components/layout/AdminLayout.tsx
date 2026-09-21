import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchLeadKeys } from "../../api/leadKeys";
import { useEnquiryReminder } from "../../hooks/useEnquiryReminder";
import { pageTransition } from "../../lib/motion";
import { statusColor } from "../../lib/theme";
import { PageHeader } from "../ui";
import { ADMIN_GROUPS, adminLabelFor } from "./adminNav";
import { SidebarDesktop, SidebarDrawer } from "./Sidebar";
import { readCollapsed, writeCollapsed } from "./sidebarPref";

export default function AdminLayout() {
  const location = useLocation();
  // Polls in the background and raises the desktop notification, so it runs
  // for the whole admin portal rather than only while the tab is open.
  const { due } = useEnquiryReminder(true);
  const dueCount = due?.count ?? 0;

  // A broken website form is silent by nature: the visitor gets an apology and
  // the gym gets nothing, so it is normally found weeks later by noticing that
  // enquiries dried up. Fetched for the whole portal so it shows the moment
  // the admin panel is opened, not only if they happen to visit that screen.
  // Shares the "lead-keys" cache with the Website Form page, so opening it
  // costs no second request.
  const { data: leadKeys } = useQuery({
    queryKey: ["lead-keys"],
    queryFn: fetchLeadKeys,
    staleTime: 5 * 60 * 1000,
  });
  const brokenForms = (leadKeys ?? []).filter(
    (k) => k.is_active && k.failures_since_success > 0 && k.last_failure_reason,
  ).length;

  const badges = {
    "/admin/enquiries": { count: dueCount },
    // Red, not the accent: this is money being lost, not a task to get to.
    "/admin/website-form": { count: brokenForms, tone: statusColor("negative") },
  };

  // Read once at mount rather than synchronised in an effect: the stored
  // preference is the initial value, and from then on this state owns it.
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [drawerOpen, setDrawerOpen] = useState(false);

  function toggle() {
    // The next value is worked out here rather than inside a state updater:
    // React may run an updater more than once, and a write to storage from
    // inside one is a side effect that then runs against different inputs --
    // which had it saving the value it was toggling away from.
    const next = !collapsed;
    setCollapsed(next);
    writeCollapsed(next);
  }

  const header = (
    <div className="mb-6 flex items-center gap-3">
        <button
          onClick={() => setDrawerOpen(true)}
          // Named apart from the top bar's own menu button, which on mobile
          // holds the account actions -- two buttons both called "Open menu"
          // is ambiguous to a screen reader.
          aria-label="Open admin menu"
          className="rounded-md border border-[var(--color-border)] p-2 text-[var(--color-text)] transition-colors hover:border-[var(--color-accent)] lg:hidden"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            className="h-5 w-5"
            aria-hidden="true"
          >
            <path d="M4 6h16M4 12h16M4 18h16" />
          </svg>
          {dueCount > 0 && (
            <span className="sr-only">{dueCount} calls due</span>
          )}
          {brokenForms > 0 && (
            <span className="sr-only">website enquiry form not working</span>
          )}
        </button>
        {/* The section name, not a repeated "Admin Dashboard": the sidebar
            already says which portal this is, so the heading can say which
            page you're on. */}
        <div className="min-w-0 flex-1">
          <PageHeader title={adminLabelFor(location.pathname)} />
        </div>
      </div>
  );

  return (
    <>
      <SidebarDrawer
        groups={ADMIN_GROUPS}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        badges={badges}
      />

      {/* `items-start` so the rail's `sticky` has room to work -- a stretched
          flex child is already full height and never sticks. */}
      <div className="flex items-start">
        <SidebarDesktop
          groups={ADMIN_GROUPS}
          collapsed={collapsed}
          onToggle={toggle}
          badges={badges}
        />

        {/* The shell no longer pads admin routes, so the content column owns
            its own padding. min-w-0 keeps a wide table scrolling inside the
            column rather than stretching the whole layout. */}
        <div className="min-w-0 flex-1 px-4 py-8 lg:px-8">
          {header}
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
      </div>
    </>
  );
}
