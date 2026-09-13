import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { pageTransition } from "../../lib/motion";
import type { PortalGroup } from "./navShared";
import { SidebarDesktop, SidebarDrawer } from "./Sidebar";
import { readCollapsed, writeCollapsed, type Portal } from "./sidebarPref";

/**
 * The member and trainer portals, laid out the way admin's is: the grouped rail
 * on the left, the page beside it.
 *
 * No page title here, unlike AdminLayout. Member and trainer pages already open
 * with their own heading -- "Welcome, Arjun" is not something a layout can work
 * out from a URL -- so a second one on top would only repeat it.
 *
 * The reading column stays capped at 6xl inside the wider shell. These pages
 * are things you read, a diet plan or a workout log, and a line running the
 * full width of a monitor beside the rail is harder to follow, not easier.
 */
export default function PortalShell({
  portal,
  groups,
}: {
  portal: Exclude<Portal, "admin">;
  groups: PortalGroup[];
}) {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => readCollapsed(portal));
  const [drawerOpen, setDrawerOpen] = useState(false);

  function toggle() {
    // Worked out outside the state updater, for the reason AdminLayout gives:
    // React may run an updater twice, and a storage write inside one is a side
    // effect running against the wrong input.
    const next = !collapsed;
    setCollapsed(next);
    writeCollapsed(next, portal);
  }

  return (
    <>
      <SidebarDrawer groups={groups} open={drawerOpen} onClose={() => setDrawerOpen(false)} />

      {/* `items-start` so the rail's `sticky` has room to work -- a stretched
          flex child is already full height and never sticks. */}
      <div className="flex items-start">
        <SidebarDesktop groups={groups} collapsed={collapsed} onToggle={toggle} />

        <div className="min-w-0 flex-1 px-4 py-8 lg:px-8">
          <div className="mx-auto max-w-6xl">
            {/* The rail is hidden below `lg`, so this is the way into the menu
                on a phone. Named apart from the top bar's own button, which
                holds the account actions. */}
            <button
              onClick={() => setDrawerOpen(true)}
              aria-label="Open navigation menu"
              className="mb-6 inline-flex items-center gap-2 rounded-md border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-text)] transition-colors hover:border-[var(--color-accent)] lg:hidden"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                className="h-4 w-4"
                aria-hidden="true"
              >
                <path d="M4 6h16M4 12h16M4 18h16" />
              </svg>
              Menu
            </button>

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
      </div>
    </>
  );
}
