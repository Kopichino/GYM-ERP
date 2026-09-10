import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { fetchMembers } from "../api/admin";
import { commitCheckout, fetchPlans, quoteCheckout, type CheckoutQuote } from "../api/billing";
import { Button, Card, ErrorText, Input, Select } from "./ui";
import { railColor } from "../lib/theme";

const METHODS = [
  { value: "cash", label: "Cash" },
  { value: "upi", label: "UPI" },
  { value: "card", label: "Card" },
  { value: "bank_transfer", label: "Bank transfer" },
  { value: "other", label: "Other" },
];

function Line({ label, value, muted, strong }: { label: string; value: string; muted?: boolean; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <span className={`text-sm ${muted ? "text-[var(--color-text-muted)]" : "text-[var(--color-text)]"}`}>
        {label}
      </span>
      <span
        className={
          strong
            ? "font-display text-2xl text-[var(--color-text)]"
            : `text-sm ${muted ? "text-[var(--color-text-muted)]" : "text-[var(--color-text)]"}`
        }
      >
        {value}
      </span>
    </div>
  );
}

/**
 * Counter-style checkout: pick a member and plan, optionally apply a code, see
 * the total, then take the money.
 *
 * The total shown comes from the server's quote endpoint rather than being
 * worked out here, so the figure on screen is the one that gets charged -- and
 * a code that can't be used is refused before any money moves.
 */
export default function CheckoutPanel() {
  const queryClient = useQueryClient();
  const [member, setMember] = useState<number | "">("");
  const [plan, setPlan] = useState<number | "">("");
  const [code, setCode] = useState("");
  const [method, setMethod] = useState("cash");
  const [notes, setNotes] = useState("");
  // Empty means "charge whatever the plan and code work out to". Typing here
  // takes over, for a price that was negotiated at the desk.
  const [amount, setAmount] = useState("");
  const [quote, setQuote] = useState<CheckoutQuote | null>(null);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  const { data: members } = useQuery({ queryKey: ["admin", "members"], queryFn: fetchMembers });
  const { data: plans } = useQuery({ queryKey: ["plans"], queryFn: fetchPlans });
  const activePlans = plans?.filter((p) => p.is_active) ?? [];

  const ready = member !== "" && plan !== "";

  const priceIt = useMutation({
    mutationFn: () =>
      quoteCheckout({
        member: Number(member),
        plan: Number(plan),
        code: code || undefined,
        amount: amount || undefined,
      }),
    onSuccess: (data) => {
      setQuote(data);
      setError("");
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      setQuote(null);
      setError(err.response?.data?.detail ?? "Could not price that sale.");
    },
  });

  // Re-price whenever the sale changes. Without this the operator could edit
  // the plan after applying a code and charge a stale total.
  useEffect(() => {
    if (!ready) {
      setQuote(null);
      return;
    }
    const id = setTimeout(() => priceIt.mutate(), 250);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [member, plan, code, amount, ready]);

  const charge = useMutation({
    mutationFn: () =>
      commitCheckout({
        member: Number(member),
        plan: Number(plan),
        code: code || undefined,
        amount: amount || undefined,
        method,
        notes,
      }),
    onSuccess: (data) => {
      setDone(`Charged ${data.total} to ${data.member_name}.`);
      setCode("");
      setNotes("");
      setAmount("");
      setQuote(null);
      setMember("");
      setPlan("");
      queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (err: { response?: { data?: { detail?: string } } }) =>
      setError(err.response?.data?.detail ?? "Could not take that payment."),
  });

  return (
    <Card accent={railColor(0)}>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        Checkout
      </h2>

      <div className="flex flex-col gap-3">
        <Select value={member} onChange={(e) => setMember(Number(e.target.value) || "")}>
          <option value="">Select member</option>
          {members?.map((m) => (
            <option key={m.id} value={m.id}>
              {m.username}
            </option>
          ))}
        </Select>

        <Select value={plan} onChange={(e) => setPlan(Number(e.target.value) || "")}>
          <option value="">Select plan</option>
          {activePlans.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} - {p.price} ({p.duration_days}d)
            </option>
          ))}
        </Select>

        <div className="flex gap-3">
          <Input
            placeholder="Offer code (optional)"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            className="flex-1 font-mono"
          />
          <Select value={method} onChange={(e) => setMethod(e.target.value)} className="flex-1">
            {METHODS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </Select>
        </div>

        <div className="flex gap-3">
          <label className="flex-1 text-xs text-[var(--color-text-muted)]">
            Amount to charge
            <Input
              type="number"
              step="0.01"
              min="0"
              placeholder={quote ? quote.list_price : "Plan price"}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="mt-1"
            />
          </label>
          <label className="flex-1 text-xs text-[var(--color-text-muted)]">
            Notes (optional)
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} className="mt-1" />
          </label>
        </div>
        <p className="-mt-1 text-xs text-[var(--color-text-muted)]">
          Leave the amount blank to charge the plan price. Type over it for a
          negotiated or part payment.
        </p>
      </div>

      {/* The bill. Only ever shows figures the server priced. */}
      {quote && (
        <div className="mt-4 border-t border-[var(--color-border)] pt-3">
          <Line label={quote.plan_name} value={quote.list_price} muted />
          {quote.discount_code && (
            <Line
              label={`${quote.discount_code} — ${quote.discount_label}`}
              value={`- ${quote.discount_amount}`}
            />
          )}
          {quote.custom_amount && !quote.discount_code && Number(quote.discount_amount) > 0 && (
            <Line label="Adjusted at the desk" value={`- ${quote.discount_amount}`} />
          )}
          <div className="mt-1 border-t border-[var(--color-border)] pt-2">
            <Line label="Total" value={quote.total} strong />
          </div>
          <p className="mt-2 text-xs text-[var(--color-text-muted)]">
            Covers {new Date(quote.period_start).toLocaleDateString()} to{" "}
            {new Date(quote.period_end).toLocaleDateString()}
            {quote.extends_existing && " — added to the end of their current period"}
          </p>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button
          onClick={() => {
            setDone("");
            charge.mutate();
          }}
          disabled={!ready || !quote || charge.isPending}
        >
          {charge.isPending ? "Taking payment..." : quote ? `Take ${quote.total}` : "Take payment"}
        </Button>
        {priceIt.isPending && (
          <span className="text-xs text-[var(--color-text-muted)]">Pricing...</span>
        )}
        {done && <span className="text-sm" style={{ color: "#22c55e" }}>{done}</span>}
      </div>
      <ErrorText>{error}</ErrorText>
    </Card>
  );
}
