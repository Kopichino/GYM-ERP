import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { resetUserMfa } from "../api/users";
import { statusColor, tint } from "../lib/theme";
import { askConfirm } from "../store/confirmStore";
import { ghostButtonClass } from "./ui";

const PILL = "inline-block rounded-full px-2 py-1 text-[11px] font-semibold leading-none";

/**
 * Whether someone has two-step sign-in set up, and the way back in for a person
 * who has lost their phone and their recovery codes.
 *
 * "Not set up" is not a fault. With two-step sign-in required, it means they
 * have not signed in since it was switched on, and will set it up when they do.
 */
export default function MfaResetCell({
  userId,
  name,
  hasMfa,
}: {
  userId: number;
  name: string;
  hasMfa: boolean;
}) {
  const queryClient = useQueryClient();
  const [done, setDone] = useState(false);

  const reset = useMutation({
    mutationFn: () => resetUserMfa(userId),
    onSuccess: () => {
      setDone(true);
      queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
  });

  const tone = statusColor(hasMfa ? "positive" : "neutral");

  return (
    <span className="flex items-center gap-2 whitespace-nowrap">
      <span className={PILL} style={{ color: tone, background: tint(tone) }}>
        {hasMfa ? "On" : "Not set up"}
      </span>
      {done && (
        <span className="text-xs" style={{ color: statusColor("positive") }}>
          Reset done
        </span>
      )}
      {reset.isError && <span className="text-xs text-red-400">Could not reset</span>}
      {hasMfa && (
        <button
          type="button"
          disabled={reset.isPending}
          onClick={() =>
            askConfirm({
              title: `Reset two-step sign-in for ${name}?`,
              consequence:
                "Their authenticator app and recovery codes stop working, and they are signed out everywhere. They set it up again the next time they sign in.",
              confirmLabel: "Reset",
              run: () => reset.mutate(),
            })
          }
          className={ghostButtonClass}
        >
          Reset
        </button>
      )}
    </span>
  );
}
