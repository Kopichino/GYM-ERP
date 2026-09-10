import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { fetchDueEnquiries } from "../api/crm";

const STORAGE_KEY = "ironcore.enquiry-reminder";
/** Re-check while the tab is open, so a callback that becomes due mid-shift
 *  still surfaces without a reload. */
const POLL_MS = 5 * 60 * 1000;

function alreadyNotifiedToday(date: string) {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === date;
  } catch {
    // Private windows and blocked site data throw on access; the banner is
    // the real reminder, so failing to dedupe is not worth breaking over.
    return false;
  }
}

function rememberNotified(date: string) {
  try {
    window.localStorage.setItem(STORAGE_KEY, date);
  } catch {
    /* ignore */
  }
}

/**
 * Watches for enquiries whose callback date has arrived.
 *
 * Two levels of reminder: the returned data drives an always-visible banner in
 * the admin portal, and — if the admin allows it — a desktop notification fires
 * once per day so it lands even when the tab is in the background. Anything
 * that must reach them with the app *closed* needs email or push, which is a
 * separate piece of infrastructure.
 */
export function useEnquiryReminder(enabled: boolean) {
  const [permission, setPermission] = useState<NotificationPermission>(
    typeof Notification === "undefined" ? "denied" : Notification.permission
  );

  const { data } = useQuery({
    queryKey: ["enquiries", "due"],
    queryFn: fetchDueEnquiries,
    enabled,
    refetchInterval: POLL_MS,
  });

  useEffect(() => {
    if (!data || data.count === 0) return;
    if (typeof Notification === "undefined" || permission !== "granted") return;
    if (alreadyNotifiedToday(data.date)) return;

    const names = data.results.slice(0, 3).map((e) => e.name).join(", ");
    const extra = data.count > 3 ? ` and ${data.count - 3} more` : "";
    new Notification(
      data.count === 1 ? "1 call to make today" : `${data.count} calls to make today`,
      {
        body: `${names}${extra}`,
        tag: "ironcore-enquiries",
      }
    );
    rememberNotified(data.date);
  }, [data, permission]);

  async function requestPermission() {
    if (typeof Notification === "undefined") return;
    setPermission(await Notification.requestPermission());
  }

  return {
    due: data,
    permission,
    requestPermission,
    canAsk: typeof Notification !== "undefined" && permission === "default",
  };
}
