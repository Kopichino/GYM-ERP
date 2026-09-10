import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  createSendingDomain,
  deleteSendingDomain,
  fetchSendingDomain,
  requestRecords,
  verifySendingDomain,
} from "../../api/sending";
import DnsRecordCard from "../../components/DnsRecordCard";
import {
  Button,
  Card,
  ErrorState,
  ErrorText,
  ghostButtonClass,
  Input,
  LoadingState,
} from "../../components/ui";
import { statusColor } from "../../lib/theme";
import { askConfirm } from "../../store/confirmStore";

export default function AdminEmailPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    domain: "",
    from_local_part: "no-reply",
    from_name: "",
  });
  const [error, setError] = useState("");

  const { data: identity, isLoading, isError } = useQuery({
    queryKey: ["sending-domain"],
    queryFn: fetchSendingDomain,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["sending-domain"] });

  const fail = (fallback: string) => (err: {
    response?: { data?: Record<string, unknown> };
  }) => {
    const data = err.response?.data;
    const first = data && Object.values(data)[0];
    setError(String(Array.isArray(first) ? first[0] : (first ?? fallback)));
  };

  const create = useMutation({
    mutationFn: () => createSendingDomain(form),
    onSuccess: () => {
      setError("");
      invalidate();
    },
    onError: fail("Could not set that up."),
  });
  const check = useMutation({
    mutationFn: () => verifySendingDomain(identity!.id),
    onSuccess: () => {
      setError("");
      invalidate();
    },
    onError: fail("Could not check those records."),
  });
  const retry = useMutation({
    mutationFn: () => requestRecords(identity!.id),
    onSuccess: () => {
      setError("");
      invalidate();
    },
    onError: fail("The provider could not issue the record."),
  });
  const remove = useMutation({
    mutationFn: () => deleteSendingDomain(identity!.id),
    onSuccess: invalidate,
  });

  if (isLoading) {
    return (
      <Card>
        <LoadingState />
      </Card>
    );
  }
  if (isError) {
    return (
      <Card>
        <ErrorState />
      </Card>
    );
  }

  // Nothing set up yet: ask for the three things, and be clear that member
  // email keeps working in the meantime.
  if (!identity) {
    return (
      <Card accent={statusColor("neutral")}>
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Send email as your own gym
        </h2>
        <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
          Reminders and invoices currently go out from the platform's address.
          Point them at your own domain and members will see your gym in their
          inbox instead. Nothing changes until you have added two DNS records
          and they check out — your email keeps working throughout.
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label
              htmlFor="sending-local"
              className="mb-1 block text-xs text-[var(--color-text-muted)]"
            >
              Send from
            </label>
            <Input
              id="sending-local"
              value={form.from_local_part}
              onChange={(e) =>
                setForm((f) => ({ ...f, from_local_part: e.target.value }))
              }
            />
          </div>
          <div className="sm:col-span-2">
            <label
              htmlFor="sending-domain"
              className="mb-1 block text-xs text-[var(--color-text-muted)]"
            >
              At this domain
            </label>
            <Input
              id="sending-domain"
              value={form.domain}
              onChange={(e) => setForm((f) => ({ ...f, domain: e.target.value }))}
              placeholder="yourgym.com"
            />
          </div>
          <div className="sm:col-span-3">
            <label
              htmlFor="sending-name"
              className="mb-1 block text-xs text-[var(--color-text-muted)]"
            >
              Name shown beside it (optional)
            </label>
            <Input
              id="sending-name"
              value={form.from_name}
              onChange={(e) => setForm((f) => ({ ...f, from_name: e.target.value }))}
              placeholder="Defaults to your gym's name"
            />
          </div>
        </div>

        {form.domain && (
          <p className="mt-3 text-sm text-[var(--color-text-muted)]">
            Members will see mail from{" "}
            <b className="text-[var(--color-text)]">
              {form.from_local_part || "no-reply"}@{form.domain}
            </b>
          </p>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button
            onClick={() => create.mutate()}
            disabled={!form.domain.trim() || create.isPending}
          >
            {create.isPending ? "Setting up..." : "Set up"}
          </Button>
          <ErrorText>{error}</ErrorText>
        </div>
      </Card>
    );
  }

  const live = identity.is_verified;

  return (
    <div className="flex flex-col gap-6">
      <Card accent={live ? statusColor("positive") : statusColor("caution")}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              Sending as
            </h2>
            <p className="mt-1 truncate text-lg text-[var(--color-text)]">
              {identity.from_name || ""} &lt;{identity.from_email}&gt;
            </p>
            <p
              className="mt-1 text-sm"
              style={{ color: live ? statusColor("positive") : statusColor("caution") }}
            >
              {live
                ? "Live — your members see this address."
                : "Not active yet — email still goes out from the platform address."}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {!live && (
              <Button
                variant="success"
                onClick={() => check.mutate()}
                disabled={check.isPending}
                className="px-3 py-1 text-xs"
              >
                {check.isPending ? "Checking..." : "Check records"}
              </Button>
            )}
            <Button
              variant="danger"
              className="px-3 py-1 text-xs"
              onClick={() =>
                askConfirm({
                  title: `Stop sending as ${identity.domain}?`,
                  consequence:
                    "Member email goes back to the platform address. You would need to add the DNS records again to switch back.",
                  confirmLabel: "Remove",
                  run: () => remove.mutate(),
                })
              }
            >
              Remove
            </Button>
          </div>
        </div>
        <ErrorText>{error}</ErrorText>
      </Card>

      {!live && (
        <Card accent={statusColor("neutral")}>
          <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Add these where {identity.domain} is registered
          </h2>
          <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
            Find <b>DNS</b> or <b>DNS records</b> at your registrar and add each
            row below. Press <b>Check records</b> when you are done — changes
            usually appear within a few minutes.
          </p>

          <div className="flex flex-col gap-3">
            {identity.dns_records.map((record) => (
              <DnsRecordCard key={record.purpose ?? record.name} record={record} />
            ))}
          </div>

          {/* The DKIM row only exists once the provider has issued a key. When
              it has not, say why and offer to try again rather than leaving a
              silent gap where a record should be. */}
          {!identity.dns_records.some((r) => r.purpose === "DKIM") && (
            <div className="mt-4 rounded-lg border border-[var(--color-border)] p-4">
              <p className="text-sm text-[var(--color-text)]">
                The signing record has not been issued yet.
              </p>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                {identity.last_error ||
                  "It comes from the email provider and cannot be created here."}
              </p>
              <button
                onClick={() => retry.mutate()}
                className={`${ghostButtonClass} mt-3`}
                disabled={retry.isPending}
              >
                {retry.isPending ? "Asking..." : "Try again"}
              </button>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
