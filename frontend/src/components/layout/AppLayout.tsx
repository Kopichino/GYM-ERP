import { AnimatePresence, motion } from "framer-motion";
import { Outlet, useLocation } from "react-router-dom";
import { pageTransition } from "../../lib/motion";
import { useAuthStore } from "../../store/authStore";
import ConfirmHost from "../ConfirmHost";
import { MEMBER_GROUPS } from "./memberNav";
import Navbar from "./Navbar";
import PortalShell from "./PortalShell";
import { TRAINER_GROUPS } from "./trainerNav";

export default function AppLayout() {
  const location = useLocation();
  const role = useAuthStore((s) => s.user?.role);

  // The admin portal is its own shell under /admin: a sidebar plus wide tables
  // and a KPI grid, and capping it at 1152px left ~350px of dead space down
  // each side of a normal monitor while the tables scrolled inside a narrow
  // column.
  const isAdmin = location.pathname.startsWith("/admin");

  // Member and trainer navigate from the same grouped rail as admin. It wraps
  // every page they can reach -- the shared gym pages (/schedule, /gallery,
  // ...) included -- which is why it is chosen here by role, not by the member
  // or trainer route guard, which only their own pages sit under. An admin who
  // opens one of the shared pages keeps the plain centred column.
  const portal = !isAdmin && (role === "member" || role === "trainer") ? role : null;

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <Navbar />
      {/* One dialog for every destructive action in the app; see
          store/confirmStore.ts for why it lives here and not per screen. */}
      <ConfirmHost />
      {/* Every portal shell is full-bleed: its rail sits flush to the left
          edge, so this must not centre or pad it. Each shell owns the padding
          for its own content column instead. */}
      <main className={isAdmin || portal ? "w-full" : "mx-auto max-w-6xl px-4 py-8"}>
        {portal ? (
          // No outer transition around the portal shell. Keyed on the path it
          // would remount the rail on every click and throw its scroll back to
          // the top -- the bug admin had. The shell animates its own column.
          <PortalShell
            portal={portal}
            groups={portal === "trainer" ? TRAINER_GROUPS : MEMBER_GROUPS}
          />
        ) : (
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
        )}
      </main>
    </div>
  );
}
