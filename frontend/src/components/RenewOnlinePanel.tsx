import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  createOnlineOrder,
  fetchOnlineConfig,
  fetchPlans,
  verifyOnlinePayment,
} from "../api/billing";
import { useBranding } from "../hooks/useBranding";
import { Button, Card, ErrorText, Input, Select } from "./ui";
import { railColor } from "../lib/theme";

const CHECKOUT_SRC = "https://checkout.razorpay.com/v1/checkout.js";

interface RazorpayResponse {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

interface RazorpayOptions {
  key: string;
  order_id: string;
  name: string;
  description: string;
  prefill: { name: string; email: string };
  theme: { color: string };
  handler: (response: RazorpayResponse) => void;
  modal?: { ondismiss: () => void };
}

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayOptions) => { open: () => void };
  }
}

/** Loads Razorpay's widget on first use rather than on every page load. */
function loadCheckout() {
  if (window.Razorpay) return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${CHECKOUT_SRC}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("blocked")));
      return;
    }
    const script = document.createElement("script");
    script.src = CHECKOUT_SRC;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("blocked"));
    document.body.appendChild(script);
  });
}

/**
 * Self-service renewal by UPI or card.
 *
 * The browser never says what anything costs: it asks the server to open an
 * order, opens Razorpay's widget against that order id, and hands the signed
 * result back for the server to verify. If the member closes the tab midway,
 * Razorpay's webhook settles it instead.
 */
export default function RenewOnlinePanel() {
  const queryClient = useQueryClient();
  // The gym's own name is what a member should see on the payment sheet.
  const branding = useBranding();
  const gymName = branding?.name || "IRONCORE";
  const [planId, setPlanId] = useState<number | "">("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const { data: config } = useQuery({
    queryKey: ["billing", "online-config"],
    queryFn: fetchOnlineConfig,
  });
  const { data: plans } = useQuery({ queryKey: ["plans"], queryFn: fetchPlans });

  const confirm = useMutation({
    mutationFn: verifyOnlinePayment,
    onSuccess: () => {
      setDone(true);
      setError("");
      queryClient.invalidateQueries({ queryKey: ["billing"] });
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
    },
    onError: () =>
      setError(
        "We couldn't confirm that payment. If money left your account it will be applied " +
          "automatically — check back in a few minutes before trying again."
      ),
  });

  async function pay() {
    if (!planId) return;
    setError("");
    setDone(false);
    setBusy(true);
    try {
      await loadCheckout();
      const order = await createOnlineOrder(Number(planId), code || undefined);
      const razorpay = new window.Razorpay!({
        key: order.key_id,
        order_id: order.order_id,
        name: gymName,
        description: `${order.plan_name} membership`,
        prefill: { name: order.member_name, email: order.email },
        // Razorpay's sheet is the gym's, not ours.
        theme: { color: branding?.accent || "#ff3d5a" },
        handler: (response) => confirm.mutate(response),
        modal: { ondismiss: () => setBusy(false) },
      });
      razorpay.open();
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail;
      setError(detail ?? "Could not start the payment. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  // Nothing to offer if the gym hasn't connected a gateway.
  if (!config?.enabled) return null;

  return (
    <Card accent={railColor(4)} className="mb-6">
      <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        Renew online
      </h2>
      <p className="mb-4 text-sm text-[var(--color-text-muted)]">
        Pay by UPI, card or netbanking. If you still have days left, the new period starts when
        this one ends — nothing you've paid for is lost.
      </p>

      <div className="flex flex-wrap gap-3">
        <Select
          value={planId}
          onChange={(e) => setPlanId(Number(e.target.value) || "")}
          className="max-w-[240px]"
        >
          <option value="">Choose a plan</option>
          {plans?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} — {p.price}
            </option>
          ))}
        </Select>
        <Input
          placeholder="Offer code (optional)"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          className="max-w-[180px]"
        />
        <Button onClick={pay} disabled={!planId || busy || confirm.isPending}>
          {confirm.isPending ? "Confirming..." : busy ? "Opening..." : "Pay now"}
        </Button>
      </div>

      {done && (
        <p className="mt-3 text-sm" style={{ color: "#22c55e" }}>
          Payment received — your membership has been extended.
        </p>
      )}
      <ErrorText>{error}</ErrorText>
    </Card>
  );
}
