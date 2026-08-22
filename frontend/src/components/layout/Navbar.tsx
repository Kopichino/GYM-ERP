import { NavLink, useNavigate } from "react-router-dom";
import { logout } from "../../api/auth";
import { useAuthStore } from "../../store/authStore";

const memberLinks = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/workouts", label: "Workouts" },
  { to: "/progress", label: "Progress" },
  { to: "/announcements", label: "Announcements" },
  { to: "/instructors", label: "Instructors" },
  { to: "/schedule", label: "Schedule" },
  { to: "/gallery", label: "Gallery" },
];

const adminLinks = [{ to: "/admin", label: "Admin" }];

export default function Navbar() {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const navigate = useNavigate();

  async function handleLogout() {
    try {
      await logout();
    } finally {
      clear();
      navigate("/");
    }
  }

  const links = [...memberLinks, ...(user?.is_staff ? adminLinks : [])];

  return (
    <header className="sticky top-0 z-40 border-b border-[var(--color-border)] bg-[var(--color-surface)]/90 backdrop-blur">
      <nav className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <span className="text-lg font-bold tracking-tight text-[var(--color-text)]">
          IRON<span className="text-[var(--color-accent)]">CORE</span>
        </span>
        <div className="hidden flex-1 items-center gap-1 overflow-x-auto md:flex">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                `whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
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
        <button
          onClick={handleLogout}
          className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-text)]"
        >
          Log out
        </button>
      </nav>
    </header>
  );
}
