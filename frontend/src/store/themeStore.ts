import { create } from "zustand";

export type ThemeChoice = "system" | "light" | "dark";

const STORAGE_KEY = "ironcore.theme";

/**
 * Three states, not two.
 *
 * "System" is a real choice and the right default: someone whose laptop turns
 * dark at sunset expects the app to follow. Collapsing it into a boolean would
 * mean the first visit guesses, and guessing wrong on a bright phone in a gym
 * is worse than asking the OS.
 */
function read(): ThemeChoice {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") {
      return stored;
    }
  } catch {
    // Private mode, or storage blocked. The default is a fine answer.
  }
  return "system";
}

function prefersDark() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-color-scheme: dark)").matches
  );
}

/** What a choice actually resolves to right now. */
export function resolve(choice: ThemeChoice): "light" | "dark" {
  if (choice === "system") return prefersDark() ? "dark" : "light";
  return choice;
}

/**
 * Paint the choice onto <html>.
 *
 * `data-theme` is always written, even for "system" -- the CSS keys off the
 * attribute alone, so leaving it off during a system preference would mean
 * light mode was unreachable for anyone whose OS is dark.
 *
 * `color-scheme` is what makes the browser's own furniture agree: form
 * controls, the scrollbar, and the flash of background before React mounts.
 * Without it a light theme still gets dark native selects.
 */
export function apply(choice: ThemeChoice) {
  const resolved = resolve(choice);
  const root = document.documentElement;
  root.setAttribute("data-theme", resolved);
  root.style.colorScheme = resolved;
}

type ThemeState = {
  choice: ThemeChoice;
  /** What is on screen, so components can show the right icon. */
  resolved: "light" | "dark";
  set: (choice: ThemeChoice) => void;
  /** Cycles through the three, which is what a single button can offer. */
  cycle: () => void;
};

export const useThemeStore = create<ThemeState>((set, get) => ({
  choice: read(),
  resolved: resolve(read()),
  set: (choice) => {
    try {
      localStorage.setItem(STORAGE_KEY, choice);
    } catch {
      // Not being able to remember it is not a reason to refuse the change.
    }
    apply(choice);
    set({ choice, resolved: resolve(choice) });
  },
  cycle: () => {
    const order: ThemeChoice[] = ["system", "light", "dark"];
    const next = order[(order.indexOf(get().choice) + 1) % order.length];
    get().set(next);
  },
}));

/**
 * Follow the OS while the choice is "system".
 *
 * Called once at startup. Without it, switching the laptop to dark at sunset
 * leaves an app that only catches up on reload.
 */
export function watchSystemTheme() {
  const media = window.matchMedia?.("(prefers-color-scheme: dark)");
  if (!media) return;

  const onChange = () => {
    const { choice } = useThemeStore.getState();
    if (choice !== "system") return;
    apply(choice);
    useThemeStore.setState({ resolved: resolve(choice) });
  };

  media.addEventListener("change", onChange);
}
