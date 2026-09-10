import { create } from "zustand";

export type ConfirmRequest = {
  title: string;
  /** What is actually lost. "5 members will lose this badge", not "Are you sure?". */
  consequence?: string;
  confirmLabel?: string;
  run: () => void;
};

type ConfirmState = {
  pending: ConfirmRequest | null;
  ask: (request: ConfirmRequest) => void;
  cancel: () => void;
  accept: () => void;
};

/**
 * One confirmation dialog for the whole app.
 *
 * A store rather than local state in seventeen components, because the
 * alternative is seventeen `useState` pairs and seventeen `<ConfirmDialog>`
 * elements placed correctly in seventeen JSX trees -- and the eighteenth delete
 * button someone adds quietly skips all of it.
 *
 * This way a call site changes by one line: swap the direct mutate for an
 * `askConfirm`, and the host mounted in the layout does the rest.
 */
export const useConfirmStore = create<ConfirmState>((set, get) => ({
  pending: null,
  ask: (request) => set({ pending: request }),
  cancel: () => set({ pending: null }),
  accept: () => {
    // Read before clearing: `run` is a closure over the row being deleted, and
    // clearing first would drop it.
    const { pending } = get();
    set({ pending: null });
    pending?.run();
  },
}));

/** Ask for confirmation from anywhere, including outside a component. */
export function askConfirm(request: ConfirmRequest) {
  useConfirmStore.getState().ask(request);
}
