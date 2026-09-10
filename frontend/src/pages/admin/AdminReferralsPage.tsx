import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  createReferralProgram,
  fetchReferralPrograms,
  fetchReferrals,
  rewardReferral,
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

export default function AdminReferralsPage() {
  const queryClient = useQueryClient();
  const [days, setDays] = useState("15");
  const [blurb, setBlurb] = useState("");
  const [error, setError] = useState("");

  const { data: referrals, isLoading, isError } = useQuery({
    queryKey: ["referrals", "all"],
    queryFn: fetchReferrals,
  });
  const { data: programs } = useQuery({
    queryKey: ["referrals", "programs"],
    queryFn: fetchReferralPrograms,
  });

  const active = programs?.find((p) => p.is_active);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["referrals"] });

  const saveProgram = useMutation({
    mutationFn: () => createReferralProgram({ reward_days: Number(days), blurb }),
    onSuccess: () => {
      setError("");
      invalidate();
    },
    onError: () => setError("Could not save that offer."),
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
          Saving a new offer replaces the current one.
        </p>
        <div className="flex flex-wrap gap-3">
          <label className="text-xs text-[var(--color-text-muted)]">
            Free days
            <Input
              type="number"
              min={1}
              value={days}
              onChange={(e) => setDays(e.target.value)}
              className="mt-1 w-28"
            />
          </label>
          <label className="min-w-[240px] flex-1 text-xs text-[var(--color-text-muted)]">
            What members are told
            <Input
              placeholder="Bring a friend, train 15 days on us."
              value={blurb}
              onChange={(e) => setBlurb(e.target.value)}
              className="mt-1"
            />
          </label>
          <Button
            onClick={() => saveProgram.mutate()}
            disabled={!days || saveProgram.isPending}
            className="self-end"
          >
            {saveProgram.isPending ? "Saving..." : "Save offer"}
          </Button>
        </div>
        <ErrorText>{error}</ErrorText>
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
