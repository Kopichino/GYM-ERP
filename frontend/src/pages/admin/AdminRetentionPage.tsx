import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  fetchRetentionPolicies,
  saveRetentionPolicy,
  type RetentionPolicy,
} from "../../api/crm";
import AtRiskPanel from "../../components/AtRiskPanel";
import { Button, Card, ErrorState, ErrorText, Input, LoadingState } from "../../components/ui";
import { railColor } from "../../lib/theme";

const LABEL = "mb-1 block text-xs uppercase tracking-wide text-[var(--color-text-muted)]";

/**
 * The thresholds form, seeded from the server through `useState` and remounted
 * on a `key` when the saved policy changes -- the same pattern the branding
 * page uses, so server data is an initial value rather than a copy that has to
 * be kept in step by an effect.
 */
function PolicyForm({ current }: { current?: RetentionPolicy }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    quiet_days: String(current?.quiet_days ?? 10),
    cooling_days: String(current?.cooling_days ?? 5),
    grace_days: String(current?.grace_days ?? 7),
  });
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const save = useMutation({
    mutationFn: () =>
      saveRetentionPolicy({
        quiet_days: Number(form.quiet_days),
        cooling_days: Number(form.cooling_days),
        grace_days: Number(form.grace_days),
      }),
    onSuccess: () => {
      setError("");
      setSaved(true);
      // The at-risk list is derived from these, so it has to be re-read.
      queryClient.invalidateQueries({ queryKey: ["at-risk"] });
      queryClient.invalidateQueries({ queryKey: ["retention"] });
    },
    onError: (err: { response?: { data?: Record<string, string[]> } }) => {
      const first = err.response?.data && Object.entries(err.response.data)[0];
      setSaved(false);
      setError(first ? `${first[1]}` : "Could not save that.");
    },
  });

  function field(key: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      setSaved(false);
      setForm((f) => ({ ...f, [key]: e.target.value }));
    };
  }

  return (
    <Card accent={railColor(1)}>
      <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        What counts as gone quiet
      </h2>
      <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
        Nobody is flagged in the database — the list above is worked out from check-in history
        every time it is opened, so changing these numbers changes it immediately and a member
        who walks in tonight is off it by morning.
      </p>

      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <label htmlFor="quiet-days" className={LABEL}>
            Quiet after
          </label>
          <Input
            id="quiet-days"
            type="number"
            min={1}
            value={form.quiet_days}
            onChange={field("quiet_days")}
          />
        </div>
        <div>
          <label htmlFor="cooling-days" className={LABEL}>
            Cooling off after
          </label>
          <Input
            id="cooling-days"
            type="number"
            min={1}
            value={form.cooling_days}
            onChange={field("cooling_days")}
          />
        </div>
        <div>
          <label htmlFor="grace-days" className={LABEL}>
            Leave new members
          </label>
          <Input
            id="grace-days"
            type="number"
            min={0}
            value={form.grace_days}
            onChange={field("grace_days")}
          />
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Saving..." : "Save thresholds"}
        </Button>
        {saved && (
          <span className="text-sm" style={{ color: "#22c55e" }}>
            Saved — the list above now uses these.
          </span>
        )}
        <ErrorText>{error}</ErrorText>
      </div>
    </Card>
  );
}

export default function AdminRetentionPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["retention", "policies"],
    queryFn: fetchRetentionPolicies,
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

  const current = data?.find((p) => p.is_active);

  return (
    <div className="flex flex-col gap-6">
      <AtRiskPanel accent={railColor(0)} />
      <PolicyForm key={current?.updated_at ?? "default"} current={current} />
    </div>
  );
}
