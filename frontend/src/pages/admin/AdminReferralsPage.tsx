import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  createReferralProgram,
  fetchReferralPrograms,
  fetchReferrals,
  rewardReferral,
  updateReferralProgram,
  type ReferralProgram,
  type ReferralStatus,
} from "../../api/referrals";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  Input,
  LoadingState,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "../../components/ui";
import { useSubmitOnce } from "../../hooks/useSubmitOnce";
import { serverMessage } from "../../lib/apiError";
import { railColor } from "../../lib/theme";

const STATUS_COLOR: Record<ReferralStatus, string> = {
  pending: "#9494a8",
  signed_up: "#ffb020",
  joined: "#22c55e",
};

const STATUS_LABEL: Record<ReferralStatus, string> = {
  pending: "Not signed up",
  signed_up: "Signed up, unpaid",
  joined: "Joined and paid",
};

const PROGRAMS_QUERY_KEY = ["referrals", "programs"];

/** The reward a brand-new offer starts from, before any offer has been saved. */
const DEFAULT_DAYS = "15";

/** Word for word what the API says about an offer of no days. */
const AT_LEAST_ONE_DAY = "An offer has to give at least 1 free day.";

export default function AdminReferralsPage() {
  const queryClient = useQueryClient();
  // Unsaved edits. Null means "show the offer that is running" -- the form used
  // to start from a hard-coded 15 and an empty message on every visit, so a
  // saved offer looked lost after a reload and the next save wiped its message.
  const [draft, setDraft] = useState<{ days: string; blurb: string } | null>(null);
  const [error, setError] = useState("");
  const submitOnce = useSubmitOnce();

  const { data: referrals, isLoading, isError } = useQuery({
    queryKey: ["referrals", "all"],
    queryFn: fetchReferrals,
  });
  const { data: programs, isLoading: programsLoading } = useQuery({
    queryKey: PROGRAMS_QUERY_KEY,
    queryFn: fetchReferralPrograms,
    // Re-read whenever the page opens. The form shows the running offer, so an
    // offer changed a moment ago -- by another admin -- must not come back from
    // the cache and be saved over the top of that change.
    staleTime: 0,
  });

  const active = programs?.find((p) => p.is_active);
  const days = draft?.days ?? (active ? String(active.reward_days) : DEFAULT_DAYS);
  const blurb = draft?.blurb ?? active?.blurb ?? "";
  // Checked here as well as by the server, so a bad number is explained before Save.
  const daysProblem = !/^\d+$/.test(days)
    ? "Free days has to be a whole number."
    : Number(days) < 1
      ? AT_LEAST_ONE_DAY
      : "";
  const edit = (change: Partial<{ days: string; blurb: string }>) => setDraft({ days, blurb, ...change });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["referrals"] });

  const saveProgram = useMutation({
    // The running offer is edited in place; a new one is created only when none
    // is running. Saving used to create every time, adding a row per save.
    mutationFn: () => {
      const payload = { reward_days: Number(days), blurb };
      return active ? updateReferralProgram(active.id, payload) : createReferralProgram(payload);
    },
    onSuccess: (saved) => {
      // Put the saved offer straight into the list, so the form does not show the
      // old values for a moment while the list reloads.
      queryClient.setQueryData<ReferralProgram[]>(PROGRAMS_QUERY_KEY, (rows = []) => {
        const others = rows
          .filter((p) => p.id !== saved.id)
          .map((p) => (saved.is_active ? { ...p, is_active: false } : p));
        return [saved, ...others];
      });
      setDraft(null);
      setError("");
      invalidate();
    },
    onError: (err) => setError(serverMessage(err, "Could not save that offer.")),
  });

  const pay = useMutation({
    mutationFn: (id: number) => rewardReferral(id),
    onSuccess: () => {
      setError("");
      invalidate();
    },
    onError: (err: { response?: { data?: { detail?: string } } }) =>
      setError(err.response?.data?.detail ?? "Could not grant that reward."),
  });

  const due = referrals?.filter((r) => r.is_rewardable) ?? [];

  return (
    <div className="flex flex-col gap-6">
      <Card accent={railColor(0)}>
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Referral offer
        </h2>
        <p className="mb-4 text-sm text-[var(--color-text-muted)]">
          {active
            ? `Running now: ${active.reward_days} free days per referral.`
            : "No offer is running — members can still share their code, but nothing is owed."}{" "}
          {active ? "Saving changes the offer that is running." : "Saving starts this offer."}
        </p>
        <div className="flex flex-wrap gap-3">
          <label className="text-xs text-[var(--color-text-muted)]">
            Free days
            <Input
              type="number"
              min={1}
              aria-invalid={Boolean(daysProblem)}
              value={days}
              onChange={(e) => edit({ days: e.target.value })}
              className="mt-1 w-28"
            />
          </label>
          <label className="min-w-[240px] flex-1 text-xs text-[var(--color-text-muted)]">
            What members are told
            <Input
              placeholder="Bring a friend, train 15 days on us."
              value={blurb}
              onChange={(e) => edit({ blurb: e.target.value })}
              className="mt-1"
            />
          </label>
          <Button
            onClick={() => submitOnce((settled) => saveProgram.mutate(undefined, { onSettled: settled }))}
            // Not before the offers have loaded: until then the page cannot tell
            // an edit from a first offer, and would start a second one.
            disabled={Boolean(daysProblem) || programsLoading || saveProgram.isPending}
            className="self-end"
          >
            {saveProgram.isPending ? "Saving..." : "Save offer"}
          </Button>
        </div>
        <ErrorText>{daysProblem || error}</ErrorText>
      </Card>

      <Card accent={railColor(4)}>
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {due.length} rewards due
        </h2>
        <p className="mb-4 text-sm text-[var(--color-text-muted)]">
          Granting adds the free days to the referrer's membership as a zero-amount renewal, so
          their expiry moves exactly as it would for a paid one.
        </p>
        {!due.length ? (
          <EmptyState>Nothing owed right now.</EmptyState>
        ) : (
          <ul className="flex flex-col">
            {due.map((r) => (
              <li
                key={r.id}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] py-2 text-sm last:border-none"
              >
                <span className="text-[var(--color-text)]">
                  {r.referrer_name} brought in {r.name}
                </span>
                <Button variant="success" onClick={() => pay.mutate(r.id)} disabled={pay.isPending}>
                  Grant free days
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card accent={railColor(2)}>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {referrals?.length ?? 0} referrals
        </h2>
        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState />
        ) : !referrals?.length ? (
          <EmptyState>No referrals yet.</EmptyState>
        ) : (
          <div className="no-scrollbar overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Referrer</th>
                  <th className={tableHeadCellClass}>Referred</th>
                  <th className={tableHeadCellClass}>Phone</th>
                  <th className={tableHeadCellClass}>Raised</th>
                  <th className={tableHeadCellClass}>Status</th>
                  <th className={tableHeadCellClass}>Reward</th>
                </tr>
              </thead>
              <tbody>
                {referrals.map((r) => (
                  <tr key={r.id} className={tableRowClass}>
                    <td className={tableCellClass}>{r.referrer_name}</td>
                    <td className={tableCellClass}>
                      {r.name}
                      {r.referred_username && (
                        <span className="text-[var(--color-text-muted)]"> ({r.referred_username})</span>
                      )}
                    </td>
                    <td className={tableCellClass}>{r.phone || "-"}</td>
                    <td className={tableCellClass}>
                      {new Date(r.created_at).toLocaleDateString()}
                    </td>
                    <td className={tableCellClass}>
                      <span
                        className="rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
                        style={{
                          background: `${STATUS_COLOR[r.status]}22`,
                          color: STATUS_COLOR[r.status],
                        }}
                      >
                        {STATUS_LABEL[r.status]}
                      </span>
                    </td>
                    <td className={tableCellClass}>
                      {r.reward ? `${r.reward.days_granted} days` : r.is_rewardable ? "Due" : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
