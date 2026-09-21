import { AnimatePresence, motion } from "framer-motion";
import { NavLink } from "react-router-dom";
import type { PortalGroup, PortalLink } from "./navShared";
import { railColor } from "../../lib/theme";

function Icon({ path, className = "" }: { path: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`h-[18px] w-[18px] shrink-0 ${className}`}
      aria-hidden="true"
    >
      <path d={path} />
    </svg>
  );
}

function Item({
  link,
  colour,
  collapsed,
  badge,
  badgeTone,
  onNavigate,
}: {
  link: PortalLink;
  colour: string;
  collapsed: boolean;
  badge?: number;
  /** Accent for a count, danger for a fault. Same shape, different meaning. */
  badgeTone?: string;
  onNavigate?: () => void;
}) {
  return (
    <NavLink
      to={link.to}
      end={link.end}
      onClick={onNavigate}
      // The label is the accessible name when collapsed, and the native
      // tooltip when hovering the icon rail.
      title={collapsed ? link.label : undefined}
      aria-label={collapsed ? link.label : undefined}
      className={({ isActive }) =>
        `group relative flex items-center gap-2.5 rounded-md py-1.5 text-sm transition-colors ${
          collapsed ? "justify-center px-2" : "px-2.5"
        } ${
          isActive
            ? "font-semibold text-[var(--color-text)]"
            : "text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
        }`
      }
      style={({ isActive }) =>
        isActive
          ? { background: `${colour}22`, boxShadow: `inset 2px 0 0 ${colour}` }
          : undefined
      }
    >
      {({ isActive }) => (
        <>
          <Icon path={link.icon} className={isActive ? "" : "opacity-70"} />
          {!collapsed && <span className="min-w-0 flex-1 truncate">{link.label}</span>}
          {badge !== undefined && badge > 0 && (
            <span
              className={`rounded-full text-[10px] font-bold leading-none text-white ${
                collapsed
                  ? "absolute right-1 top-1 h-4 min-w-4 px-1 pt-[3px] text-center"
                  : "px-1.5 py-0.5"
              }`}
              style={{ background: badgeTone ?? "var(--color-accent)" }}
            >
              {badge}
            </span>
          )}
        </>
      )}
    </NavLink>
  );
}

export interface NavBadge {
  count: number;
  tone?: string;
}

function Nav({
  groups,
  collapsed,
  badges,
  onNavigate,
}: {
  groups: PortalGroup[];
  collapsed: boolean;
  badges: Record<string, NavBadge>;
  onNavigate?: () => void;
}) {
  return (
    <nav className="flex flex-col gap-4">
      {groups.map((group, groupIndex) => (
        <div key={group.name}>
          {collapsed ? (
            // A rule instead of a heading: the grouping still reads, without a
            // word of text that wouldn't fit anyway.
            groupIndex > 0 && (
              <div className="mx-2 mb-2 h-px bg-[var(--color-border)]" aria-hidden="true" />
            )
          ) : (
            <p className="mb-1 px-2.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-muted)] opacity-70">
              {group.name}
            </p>
          )}
          <div className="flex flex-col gap-0.5">
            {group.links.map((link) => (
              <Item
                key={link.to}
                link={link}
                colour={railColor(groupIndex)}
                collapsed={collapsed}
                // Badges follow you around the portal rather than
                // living on the page they refer to -- a warning you have to go
                // looking for is not a warning.
                badge={badges[link.to]?.count}
                badgeTone={badges[link.to]?.tone}
                onNavigate={onNavigate}
              />
            ))}
          </div>
        </div>
      ))}
    </nav>
  );
}

/**
 * A portal's navigation -- admin, member or trainer, each fed its own groups.
 *
 * A column rather than a strip because vertical space is the cheap axis here:
 * every destination fits at once, grouped, with no scrolling. The collapse
 * toggle trades the labels for page width and is remembered, so it stays
 * collapsed for someone who works in wide tables all day -- but nothing is
 * hidden behind a click by default.
 *
 * Member and trainer used to get a single scrolling tab strip across the top,
 * which hid half their pages off the right edge and grouped nothing. All three
 * portals are now navigated the same way.
 */
export function SidebarDesktop({
  groups,
  collapsed,
  onToggle,
  badges = {},
}: {
  groups: PortalGroup[];
  collapsed: boolean;
  onToggle: () => void;
  badges?: Record<string, NavBadge>;
}) {
  return (
    <aside
      // A rail, not a floating card. `sticky` with a full viewport height and
      // `self-start` pins it below the navbar and keeps it there, while leaving
      // it in normal flow so the content column sits beside it without any
      // margin arithmetic. As a card with `top-20` it visibly travelled down
      // the page as you scrolled, which read as the menu chasing you.
      className="sticky top-[57px] hidden h-[calc(100vh-57px)] shrink-0 self-start border-r border-[var(--color-border)] bg-[var(--color-surface)] transition-[width] duration-200 lg:block"
      style={{ width: collapsed ? 56 : 208 }}
    >
      {/* Scrolled internally: a rail taller than the screen would otherwise
          clip its last group off the bottom with no way to reach it. */}
      <div className="no-scrollbar h-full overflow-y-auto p-2">
        <button
          onClick={onToggle}
          aria-label={collapsed ? "Expand menu" : "Collapse menu"}
          title={collapsed ? "Expand menu" : "Collapse menu"}
          className={`mb-3 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text)] ${
            collapsed ? "justify-center" : ""
          }`}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            className="h-4 w-4 shrink-0"
            aria-hidden="true"
          >
            <path d="M4 6h16M4 12h16M4 18h16" />
          </svg>
          {!collapsed && <span className="flex-1 text-left">Menu</span>}
          {!collapsed && (
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-4 w-4"
              aria-hidden="true"
            >
              <path d="m15 18-6-6 6-6" />
            </svg>
          )}
        </button>
        <Nav groups={groups} collapsed={collapsed} badges={badges} />
      </div>
    </aside>
  );
}

/** Below `lg` the same nav slides in over the page -- which is where a
 *  hamburger genuinely earns its keep. */
export function SidebarDrawer({
  groups,
  open,
  onClose,
  badges = {},
}: {
  groups: PortalGroup[];
  open: boolean;
  onClose: () => void;
  badges?: Record<string, NavBadge>;
}) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          />
          <motion.div
            initial={{ x: -260 }}
            animate={{ x: 0 }}
            exit={{ x: -260 }}
            transition={{ type: "spring", stiffness: 400, damping: 36 }}
            className="no-scrollbar fixed inset-y-0 left-0 z-50 w-60 overflow-y-auto border-r border-[var(--color-border)] bg-[var(--color-surface)] p-3 lg:hidden"
          >
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                Menu
              </span>
              <button
                onClick={onClose}
                aria-label="Close menu"
                className="rounded-md p-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
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
                  <path d="M6 6l12 12M18 6 6 18" />
                </svg>
              </button>
            </div>
            {/* Closing on pick: leaving it open over the page you just asked
                for is the classic drawer annoyance. */}
            <Nav groups={groups} collapsed={false} badges={badges} onNavigate={onClose} />
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
