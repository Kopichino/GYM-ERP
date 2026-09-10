import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef } from "react";
import { Button } from "./ui";

/**
 * A last chance before something is destroyed.
 *
 * Every delete in this app used to fire on the first click -- seventeen of
 * them, each permanently removing a record with no way back. That is fine for
 * an unused draft and not fine for a badge five members have earned.
 *
 * `consequence` is the part that matters. "Are you sure?" tells somebody
 * nothing they did not already know; "5 members will lose this badge" is the
 * fact they need, and it is the caller's job to supply it because only the
 * caller knows what is actually at stake.
 */
export default function ConfirmDialog({
  open,
  title,
  consequence,
  confirmLabel = "Delete",
  onConfirm,
  onCancel,
  pending = false,
}: {
  open: boolean;
  title: string;
  consequence?: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  pending?: boolean;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    // Focus lands on Cancel, not Confirm. A dialog that opens with the
    // destructive button focused turns a stray Enter keypress into a deletion,
    // which is the exact accident this is here to prevent.
    cancelRef.current?.focus();

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          // Clicking the backdrop cancels; clicking the panel must not, or the
          // dialog would close under the pointer on the way to a button.
          onClick={onCancel}
        >
          <motion.div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            aria-describedby={consequence ? "confirm-consequence" : undefined}
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            onClick={(event) => event.stopPropagation()}
            className="w-full max-w-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5"
          >
            <h2
              id="confirm-title"
              className="font-display text-lg uppercase tracking-wide text-[var(--color-text)]"
            >
              {title}
            </h2>
            {consequence && (
              <p
                id="confirm-consequence"
                className="mt-2 text-sm text-[var(--color-text-muted)]"
              >
                {consequence}
              </p>
            )}
            <p className="mt-3 text-xs text-[var(--color-text-muted)]">
              This cannot be undone.
            </p>

            <div className="mt-5 flex justify-end gap-2">
              <Button ref={cancelRef} variant="secondary" onClick={onCancel}>
                Cancel
              </Button>
              <Button variant="danger" onClick={onConfirm} disabled={pending}>
                {pending ? "Deleting..." : confirmLabel}
              </Button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
