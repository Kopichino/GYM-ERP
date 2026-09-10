import { useThemeStore, type ThemeChoice } from "../store/themeStore";

/** 24x24 stroke paths, matching the sidebar's icon set. */
const PATHS: Record<ThemeChoice, string> = {
  // A monitor: "whatever this machine is doing".
  system: "M3 4h18v12H3zM8 20h8M12 16v4",
  light:
    "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10ZM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  dark: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z",
};

const LABEL: Record<ThemeChoice, string> = {
  system: "Match my device",
  light: "Light",
  dark: "Dark",
};

/**
 * One button that cycles system -> light -> dark.
 *
 * A cycle rather than a dropdown because this sits in a navbar that is already
 * crowded on a phone, and the whole interaction is "the app is the wrong
 * brightness, fix it" -- at most two presses away in every case. The icon
 * shows the *current setting*, not the resolved one, so "match my device"
 * stays visible as a distinct state rather than masquerading as whichever of
 * light or dark it happens to be right now.
 */
export default function ThemeToggle({ className = "" }: { className?: string }) {
  const choice = useThemeStore((s) => s.choice);
  const cycle = useThemeStore((s) => s.cycle);

  return (
    <button
      type="button"
      onClick={cycle}
      title={`Theme: ${LABEL[choice]}`}
      aria-label={`Theme: ${LABEL[choice]}. Change it.`}
      className={`rounded-md p-2 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text)] ${className}`}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-[18px] w-[18px]"
        aria-hidden="true"
      >
        <path d={PATHS[choice]} />
      </svg>
    </button>
  );
}
