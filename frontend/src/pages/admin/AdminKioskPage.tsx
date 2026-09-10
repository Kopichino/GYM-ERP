import { useQuery } from "@tanstack/react-query";
import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";
import { fetchQrToken } from "../../api/attendance";
import { Button, Card, ErrorState, LoadingState } from "../../components/ui";
import { railColor } from "../../lib/theme";

/**
 * The screen at the front desk. It shows a code that changes every minute, so
 * a member has to be standing in front of it to check in -- a photograph of
 * yesterday's code is worthless.
 *
 * Nothing is stored for this: the token is derived from the clock on the
 * server, and this page simply re-asks for the current one.
 */
export default function AdminKioskPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["attendance", "qr-token"],
    queryFn: fetchQrToken,
    // Refetch at half the rotation so the screen is never showing a code that
    // has already rolled past its grace window.
    refetchInterval: (query) => ((query.state.data?.rotate_seconds ?? 60) * 1000) / 2,
    refetchIntervalInBackground: true,
  });

  const [image, setImage] = useState("");
  const frameRef = useRef<HTMLDivElement>(null);

  const scanUrl = data ? `${window.location.origin}/check-in?t=${encodeURIComponent(data.token)}` : "";

  useEffect(() => {
    if (!scanUrl) return;
    let cancelled = false;
    // Deliberately dark-on-white whatever the theme is: a tinted QR against a
    // dark card is the fastest way to make phone cameras give up.
    QRCode.toDataURL(scanUrl, {
      width: 460,
      margin: 2,
      errorCorrectionLevel: "M",
      color: { dark: "#000000", light: "#ffffff" },
    })
      .then((url) => {
        if (!cancelled) setImage(url);
      })
      .catch(() => {
        if (!cancelled) setImage("");
      });
    return () => {
      cancelled = true;
    };
  }, [scanUrl]);

  function goFullScreen() {
    frameRef.current?.requestFullscreen?.();
  }

  return (
    <div className="flex flex-col gap-6">
      <Card accent={railColor(0)}>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              Front desk check-in code
            </h2>
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">
              Members point their phone camera at this. The first scan checks them in, the next one
              checks them out.
            </p>
          </div>
          <Button variant="secondary" onClick={goFullScreen}>
            Full screen
          </Button>
        </div>

        <div
          ref={frameRef}
          className="flex flex-col items-center justify-center gap-5 rounded-lg bg-[var(--color-surface-2)] py-10"
        >
          {isLoading ? (
            <LoadingState label="Fetching the current code..." />
          ) : isError ? (
            <ErrorState />
          ) : image ? (
            <>
              <img
                src={image}
                alt="Check-in QR code"
                className="rounded-lg bg-white p-3 shadow-lg"
                width={460}
                height={460}
              />
              <p className="font-display text-2xl uppercase tracking-[0.2em] text-[var(--color-text)]">
                Scan to check in
              </p>
              <p className="text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
                Code changes every {data?.rotate_seconds ?? 60} seconds
              </p>
            </>
          ) : (
            <LoadingState label="Drawing the code..." />
          )}
        </div>
      </Card>

      <Card accent={railColor(2)}>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          How it works
        </h2>
        <ol className="flex list-decimal flex-col gap-1 pl-5 text-sm text-[var(--color-text-muted)]">
          <li>The member opens their phone camera and points it at the code.</li>
          <li>Their phone opens IRONCORE and records the visit against their own account.</li>
          <li>
            A member who is not signed in on that phone is asked to log in first, then lands back
            here.
          </li>
          <li>
            The code expires within a minute, so a screenshot cannot be used from the car park.
          </li>
        </ol>
      </Card>
    </div>
  );
}
