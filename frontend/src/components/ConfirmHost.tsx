import { useConfirmStore } from "../store/confirmStore";
import ConfirmDialog from "./ConfirmDialog";

/**
 * Mounted once, in the layout. Renders whatever confirmation is pending.
 *
 * Keeping a single instance here is what lets a delete button ask for
 * confirmation without importing a dialog or finding a place in its own JSX to
 * put one.
 */
export default function ConfirmHost() {
  const pending = useConfirmStore((s) => s.pending);
  const cancel = useConfirmStore((s) => s.cancel);
  const accept = useConfirmStore((s) => s.accept);

  return (
    <ConfirmDialog
      open={pending !== null}
      title={pending?.title ?? ""}
      consequence={pending?.consequence}
      confirmLabel={pending?.confirmLabel}
      onConfirm={accept}
      onCancel={cancel}
    />
  );
}
