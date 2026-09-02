import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { logout } from "../../api/auth";
import { useAuthStore } from "../../store/authStore";

const memberLinks = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/workouts", label: "Workouts" },
  { to: "/exercises", label: "Exercises" },
  { to: "/progress", label: "Progress" },
  { to: "/billing", label: "Billing" },
  { to: "/announcements", label: "Announcements" },
  { to: "/instructors", label: "Instructors" },
  { to: "/schedule", label: "Schedule" },
  { to: "/gallery", label: "Gallery" },
];

const adminLinks = [{ to: "/admin", label: "Admin" }];

function HamburgerIcon({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2}>
      <motion.path
        strokeLinecap="round"
        animate={open ? { d: "M6 6l12 12" } : { d: "M4 7h16" }}
      />
      <motion.path strokeLinecap="round" animate={{ opacity: open ? 0 : 1 }} d="M4 12h16" />
      <motion.path
        strokeLinecap="round"
        animate={open ? { d: "M6 18l12-12" } : { d: "M4 17h16" }}
      />
    </svg>
  );
}

export default function Navbar() {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  async function handleLogout() {
    try {
      await logout();
    } finally {
      clear();
      navigate("/");
    }
  }

  const links = [...memberLinks, ...(user?.is_staff ? adminLinks : [])];

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
      isActive
        ? "bg-[var(--color-accent)] text-white shadow-[0_0_16px_-2px_var(--color-accent)]"
        : "text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
    }`;

  return (
    <header className="sticky top-0 z-40 border-b border-[var(--color-border)] bg-[var(--color-surface)]/90 backdrop-blur">
      <nav className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <span className="font-display text-2xl tracking-wide text-[var(--color-text)]">
          IRON<span className="text-[var(--color-accent)]">CORE</span>
        </span>
        <div className="hidden flex-1 items-center gap-1 overflow-x-auto md:flex">
          {links.map((link) => (
            <NavLink key={link.to} to={link.to} className={linkClass}>
              {link.label}
            </NavLink>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleLogout}
            className="hidden rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-text)] md:block"
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
              {links.map((link) => (
                <NavLink key={link.to} to={link.to} className={linkClass} onClick={() => setMenuOpen(false)}>
                  {link.label}
                </NavLink>
              ))}
              <button
                onClick={() => {
                  setMenuOpen(false);
                  handleLogout();
                }}
                className="mt-2 rounded-md border border-[var(--color-border)] px-3 py-1.5 text-left text-sm text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-text)]"
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
