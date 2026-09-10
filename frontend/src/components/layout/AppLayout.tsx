import { AnimatePresence, motion } from "framer-motion";
import { Outlet, useLocation } from "react-router-dom";
import { pageTransition } from "../../lib/motion";
import ConfirmHost from "../ConfirmHost";
import Navbar from "./Navbar";

export default function AppLayout() {
  const location = useLocation();

  // The admin portal is a different shape from the other two. Member and
  // trainer screens are things you read -- a diet plan, a workout log -- and
  // 6xl keeps the line length comfortable. Admin is a sidebar plus wide tables
  // and a KPI grid, and capping it at 1152px left ~350px of dead space down
  // each side of a normal monitor while the tables scrolled inside a narrow
  // column.
  const isAdmin = location.pathname.startsWith("/admin");

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <Navbar />
      {/* One dialog for every destructive action in the app; see
          store/confirmStore.ts for why it lives here and not per screen. */}
      <ConfirmHost />
      {/* Admin is full-bleed: its sidebar is a rail flush to the left edge, so
          the shell must not centre or pad it. AdminLayout owns the padding for
          its own content column instead. */}
      <main
        className={isAdmin ? "w-full" : "mx-auto max-w-6xl px-4 py-8"}
      >
        <AnimatePresence mode="wait">
          <motion.div
            // Admin gets one key for the whole portal rather than one per page.
            // Keyed on the full path, this outer transition swapped the entire
            // admin shell on every navigation -- remounting the sidebar, which
            // reset its scroll position, so anyone who had scrolled down to
            // reach Branding was thrown back to the top after every click.
            // AdminLayout runs its own transition for the content column, so
            // the page still animates; only the chrome now survives.
            key={isAdmin ? "admin" : location.pathname}
            initial="initial"
            animate="animate"
            exit="exit"
            variants={pageTransition}
            transition={{ duration: 0.25, ease: "easeInOut" }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
