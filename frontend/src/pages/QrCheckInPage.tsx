import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { scanQr } from "../api/attendance";
import { Button, Card, LoadingState, PageHeader } from "../components/ui";
import { railColor } from "../lib/theme";

/**
 * Where a member's phone lands after scanning the front-desk code.
 *
 * The scan is posted once, automatically -- making someone tap a button after
 * they have already pointed their camera at a screen is one step too many, and
 * the code only lives for a minute.
 */
export default function QrCheckInPage() {
  const [params] = useSearchParams();
  const token = params.get("t") ?? "";
  const queryClient = useQueryClient();

  const scan = useMutation({
    mutationFn: () => scanQr(token),
    onSuccess: () => {
      // The dashboard's "checked in since" banner and the streak calendar both
      // read from these.
      queryClient.invalidateQueries({ queryKey: ["attendance"] });
      queryClient.invalidateQueries({ queryKey: ["checkin"] });
    },
  });

  // React 19 double-invokes effects in development; without this the same code
  // would be posted twice and the member would be checked straight back out.
  const posted = useRef(false);
  const runScan = scan.mutate;
  useEffect(() => {
    if (!token || posted.current) return;
    posted.current = true;
    runScan();
  }, [token, runScan]);

  const detail =
    (scan.error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail ??
    "Something went wrong. Scan the screen again.";

  return (
    <div>
      <PageHeader title="Check in" subtitle="Scanned from the front desk screen." />
      <Card accent={railColor(scan.isSuccess ? 3 : 0)} className="mx-auto max-w-md text-center">
        {!token ? (
          <>
            <p className="font-display text-2xl uppercase tracking-wide text-[var(--color-text)]">
              No code found
            </p>
            <p className="mt-2 text-sm text-[var(--color-text-muted)]">
              Point your camera at the screen at the front desk, then open the link it offers.
            </p>
          </>
        ) : scan.isPending ? (
          <LoadingState label="Recording your visit..." />
        ) : scan.isSuccess ? (
          <>
            <p className="font-display text-4xl uppercase tracking-wide text-[var(--color-accent)]">
              {scan.data.action === "in" ? "You're in" : "See you next time"}
            </p>
            <p className="mt-2 text-sm text-[var(--color-text-muted)]">
              {scan.data.action === "in"
                ? `Checked in at ${new Date(scan.data.record.check_in_time).toLocaleTimeString()}.`
                : scan.data.record.check_out_time
                  ? `Checked out at ${new Date(
                      scan.data.record.check_out_time
                    ).toLocaleTimeString()}.`
                  : "Checked out."}
            </p>
          </>
        ) : (
          <>
            <p className="font-display text-2xl uppercase tracking-wide text-[var(--color-text)]">
              Didn't work
            </p>
            <p className="mt-2 text-sm text-[var(--color-text-muted)]">{detail}</p>
          </>
        )}

        <div className="mt-6">
          <Link to="/dashboard">
            <Button variant="secondary">Go to my dashboard</Button>
          </Link>
        </div>
      </Card>
    </div>
  );
}
