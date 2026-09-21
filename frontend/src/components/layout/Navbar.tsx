import ThemeToggle from "../ThemeToggle";
import { useLocation, useNavigate } from "react-router-dom";
import { logout } from "../../api/auth";
import { useAuthStore } from "../../store/authStore";
import BrandMark from "../BrandMark";

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
          {/* Up here beside Log out rather than in a menu: it is a display
              preference, wanted at the moment the screen is the wrong
              brightness, not something to go hunting for. */}
          <ThemeToggle />
          {/* Log out, as itself, at every width. Phones used to get a hamburger
              whose only item was Log out, sitting beside the portal's own
              navigation button: two menu buttons, one of which opened almost
              nothing. */}
          <button onClick={handleLogout} className={LOGOUT_CLASS}>
            Log out
          </button>
        </div>
      </nav>
    </header>
  );
}
