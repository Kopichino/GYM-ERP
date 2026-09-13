import { AnimatePresence, motion } from "framer-motion";
import ThemeToggle from "../ThemeToggle";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { logout } from "../../api/auth";
import { useAuthStore } from "../../store/authStore";
import BrandMark from "../BrandMark";

function HamburgerIcon({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2}>
      {/* `d` is also set statically: framer-motion only supplies it once the
          animation runs, so without this the bars are missing on first paint. */}
      <motion.path
        strokeLinecap="round"
        d="M4 7h16"
        animate={open ? { d: "M6 6l12 12" } : { d: "M4 7h16" }}
      />
      <motion.path strokeLinecap="round" animate={{ opacity: open ? 0 : 1 }} d="M4 12h16" />
      <motion.path
        strokeLinecap="round"
        d="M4 17h16"
        animate={open ? { d: "M6 18l12-12" } : { d: "M4 17h16" }}
      />
    </svg>
  );
}

/**
 * Log out: outlined and faintly tinted, never filled.
 *
 * It is the one action that takes you out of the app, so it should be findable
 * at a glance -- but nothing is destroyed by it, and a solid red button is
 * reserved for things that are. A low-alpha wash of the brand colour reads as
 * "this is the way out" without claiming to be dangerous, and it is the same
 * language a disabled button uses: colour to say which button, weight to say
 * what state.
 */
const LOGOUT_CLASS =
  "rounded-md border border-[#ff3d5a4d] bg-[#ff3d5a0d] px-3 py-1.5 text-sm " +
  "text-[#ff3d5acc] transition-colors hover:border-[var(--color-accent)] " +
  "hover:bg-[#ff3d5a1a] hover:text-[var(--color-text)]";

export default function Navbar() {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const navigate = useNavigate();
  const location = useLocation();
  const isAdmin = location.pathname.startsWith("/admin");
  const [menuOpen, setMenuOpen] = useState(false);

  async function handleLogout() {
    try {
      await logout();
    } finally {
      clear();
      navigate("/");
    }
  }

  // No page links up here for any role. Every portal navigates from its grouped
  // rail on the left, so the top bar is just the brand and the account actions
  // -- a strip of links above the rail would give each page two ways in, and
  // the old strip hid half of them off the right edge. The rail spans the page,
  // so the bar does too wherever there is one.
  const wide = isAdmin || user?.role === "member" || user?.role === "trainer";

  return (
    <header className="sticky top-0 z-40 border-b border-[var(--color-border)] bg-[var(--color-surface)]/90 backdrop-blur">
      {/* Matches the width the page content uses, so the logo and the log-out
          button line up with the columns underneath rather than floating in
          from the edge on the wider admin layout. */}
      <nav
        className={`mx-auto flex items-center justify-between gap-4 px-4 py-3 ${
          wide ? "max-w-[1600px]" : "max-w-6xl"
        }`}
      >
        <BrandMark className="font-display text-2xl tracking-wide text-[var(--color-text)]" />
        <div className="flex items-center gap-2">
          {/* Beside Log out rather than inside the mobile menu: it is a
              display preference, wanted at the moment the screen is the wrong
              brightness, not something to go hunting for. */}
          <ThemeToggle />
          <button
            onClick={handleLogout}
            className={`hidden md:block ${LOGOUT_CLASS}`}
          >
            Log out
          </button>
          <button
            onClick={() => setMenuOpen((o) => !o)}
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            className="rounded-md border border-[var(--color-border)] p-2 text-[var(--color-text)] md:hidden"
          >
            <HamburgerIcon open={menuOpen} />
          </button>
        </div>
      </nav>

      <AnimatePresence>
        {menuOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: "easeInOut" }}
            className="overflow-hidden border-t border-[var(--color-border)] md:hidden"
          >
            <div className="flex flex-col gap-1 px-4 py-3">
              <button
                onClick={() => {
                  setMenuOpen(false);
                  handleLogout();
                }}
                className={`text-left ${LOGOUT_CLASS}`}
              >
                Log out
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
