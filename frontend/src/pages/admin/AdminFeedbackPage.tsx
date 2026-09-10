import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  deleteSurvey,
  fetchNps,
  fetchSurveys,
  saveSurvey,
  type Survey,
  type Trigger,
} from "../../api/feedback";
import {
  Button,
  Card,
  EmptyState,
  ErrorText,
  Input,
  LoadingState,
  PageHeader,
  Select, ghostButtonClass } from "../../components/ui";
import { railColor } from "../../lib/theme";

const LABEL = "mb-1 block text-xs uppercase tracking-wide text-[var(--color-text-muted)]";

const TRIGGERS: { value: Trigger; label: string }[] = [
  { value: "post_checkin", label: "After a visit" },
  { value: "post_pt", label: "After a PT session" },
  { value: "manual", label: "Any time" },
];

const BANDS = [
  { key: "promoters", label: "Promoters", range: "9–10", color: "#22c55e" },
  { key: "passives", label: "Passives", range: "7–8", color: "#ffb020" },
  { key: "detractors", label: "Detractors", range: "0–6", color: "#ff3d5a" },
] as const;

/** Green above 0, red below — the sign is the whole point of an NPS. */
function npsColor(value: number | null) {
  if (value === null) return "var(--color-text-muted)";
  if (value >= 50) return "#22c55e";
  if (value >= 0) return "#ffb020";
  return "#ff3d5a";
}

/** Pixels either side of the baseline in the trend chart. */
const BAR_MAX = 72;

const monthLabel = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { month: "short" });

export default function AdminFeedbackPage() {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState({
    title: "",
    question: "How likely are you to recommend us to a friend?",
    trigger: "post_checkin" as Trigger,
    cooldown_days: 90,
  });
  const [error, setError] = useState("");

  const { data: nps, isLoading } = useQuery({ queryKey: ["nps"], queryFn: () => fetchNps() });
  const { data: surveys } = useQuery({ queryKey: ["surveys"], queryFn: fetchSurveys });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["surveys"] });
    queryClient.invalidateQueries({ queryKey: ["nps"] });
  };

  const create = useMutation({
    mutationFn: () => saveSurvey(draft),
    onSuccess: () => {
      setDraft({ ...draft, title: "" });
      setError("");
      invalidate();
    },
    onError: (err: { response?: { data?: { detail?: string } } }) =>
      setError(err.response?.data?.detail ?? "Could not save that survey."),
  });

  const toggle = useMutation({
    mutationFn: (survey: Survey) =>
      saveSurvey({ id: survey.id, is_active: !survey.is_active }),
    onSuccess: () => {
      setError("");
      invalidate();
    },
    onError: (err: { response?: { data?: { detail?: string } } }) =>
      setError(err.response?.data?.detail ?? "Could not change that survey."),
  });

  const remove = useMutation({ mutationFn: deleteSurvey, onSuccess: invalidate });

  // Scaled against the biggest month rather than a fixed 100, so a gym sitting
  // steadily around +30 still shows a readable shape.
  const trendPeak = Math.max(1, ...(nps?.trend ?? []).map((m) => Math.abs(m.nps ?? 0)));

  return (
    <div>
      <PageHeader
        title="Member feedback"
        subtitle="One question, asked at the right moment, scored the standard way."
      />

      <div className="mb-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <Card accent={railColor(0)}>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Net promoter score
          </h2>
          {isLoading || !nps ? (
            <LoadingState />
          ) : nps.responses === 0 ? (
            <EmptyState>
              Nobody has answered yet. Switch on a survey below and it starts asking.
            </EmptyState>
          ) : (
            <>
              <p
                className="font-display text-6xl leading-none"
                style={{ color: npsColor(nps.nps) }}
              >
                {nps.nps! > 0 ? "+" : ""}
                {nps.nps}
              </p>
              <p className="mt-1 text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
                from {nps.responses} {nps.responses === 1 ? "answer" : "answers"} · average{" "}
                {nps.average}
              </p>

              {/* One stacked bar rather than three numbers: the split between
                  the bands is the thing worth seeing. */}
              <div className="mt-4 flex h-3 overflow-hidden rounded-full">
                {BANDS.map((band) => {
                  const count = nps[band.key];
                  if (!count) return null;
                  return (
                    <div
                      key={band.key}
                      style={{
                        width: `${(count * 100) / nps.responses}%`,
                        background: band.color,
                      }}
                      title={`${band.label}: ${count}`}
                    />
                  );
                })}
              </div>
              <ul className="mt-3 flex flex-col gap-1">
                {BANDS.map((band) => (
                  <li
                    key={band.key}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="flex items-center gap-2 text-[var(--color-text-muted)]">
                      <span
                        className="h-2 w-2 rounded-full"
                        style={{ background: band.color }}
                      />
                      {band.label}{" "}
                      <span className="text-[11px] tabular-nums">({band.range})</span>
                    </span>
                    <b className="tabular-nums text-[var(--color-text)]">{nps[band.key]}</b>
                  </li>
                ))}
              </ul>
              <p className="mt-3 border-t border-[var(--color-border)] pt-2 text-[11px] leading-snug text-[var(--color-text-muted)]">
                {nps.definition}
              </p>
            </>
          )}
        </Card>

        <Card accent={railColor(1)}>
          <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Last six months
          </h2>
          <p className="mb-4 text-sm text-[var(--color-text-muted)]">
            A falling score is worth acting on well before it turns into cancellations.
          </p>
          {!nps ? (
            <LoadingState />
          ) : (
            <div className="flex items-end gap-3">
              {nps.trend.map((month) => {
                const value = month.nps;
                // Floored at 3px for a month that was actually measured, so a
                // score of exactly 0 reads as "we asked, and it came out zero"
                // rather than looking identical to a month nobody answered.
                const height =
                  value === null
                    ? 0
                    : Math.max(3, (Math.abs(value) / trendPeak) * BAR_MAX);
                return (
                  <div key={month.month} className="flex flex-1 flex-col items-center gap-1">
                    <span className="text-[11px] tabular-nums text-[var(--color-text-muted)]">
                      {value === null ? "—" : value}
                    </span>
                    {/* Equal room above and below the baseline: a -60 month has
                        to look as bad as a +60 month looks good, which a
                        shorter negative half would quietly undersell. */}
                    <div className="flex w-full flex-col justify-end" style={{ height: BAR_MAX }}>
                      {value !== null && value >= 0 && (
                        <div
                          className="w-full rounded-t"
                          style={{ height: `${height}px`, background: npsColor(value) }}
                        />
                      )}
                    </div>
                    <div className="h-px w-full bg-[var(--color-border)]" />
                    <div className="flex w-full flex-col justify-start" style={{ height: BAR_MAX }}>
                      {value !== null && value < 0 && (
                        <div
                          className="w-full rounded-b"
                          style={{ height: `${height}px`, background: npsColor(value) }}
                        />
                      )}
                    </div>
                    <span className="text-[11px] uppercase text-[var(--color-text-muted)]">
                      {monthLabel(month.month)}
                    </span>
                    <span className="text-[10px] tabular-nums text-[var(--color-text-muted)]">
                      {month.responses || ""}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      {nps && nps.detractor_comments.length > 0 && (
        <Card accent="#ff3d5a" className="mb-6">
          <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            What the unhappy ones said
          </h2>
          <p className="mb-3 text-sm text-[var(--color-text-muted)]">
            The only part of a survey that tells you what to change. A score says something
            is wrong; these say what.
          </p>
          <ul className="flex flex-col">
            {nps.detractor_comments.map((row) => (
              <li
                key={row.id}
                className="flex gap-3 border-b border-[var(--color-border)] py-2 text-sm last:border-none"
              >
                <span
                  className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded text-xs font-bold"
                  style={{ background: "var(--color-accent)", color: "var(--color-on-accent)" }}
                >
                  {row.score}
                </span>
                <span className="min-w-0">
                  <span className="block text-[var(--color-text)]">{row.comment}</span>
                  <span className="block text-xs text-[var(--color-text-muted)]">
                    {row.member} · {new Date(row.created_at).toLocaleDateString()}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card accent={railColor(4)}>
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Surveys
        </h2>
        <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
          One live survey per moment. A member is asked once and then left alone for the
          cooldown, so the prompt stays something people read rather than dismiss.
        </p>

        <div className="flex flex-wrap gap-2">
          <div className="min-w-[150px] flex-1">
            <label htmlFor="survey-title" className={LABEL}>
              Name
            </label>
            <Input
              id="survey-title"
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              placeholder="After the gym"
            />
          </div>
          <div className="min-w-[220px] flex-[2]">
            <label htmlFor="survey-question" className={LABEL}>
              Question
            </label>
            <Input
              id="survey-question"
              value={draft.question}
              onChange={(e) => setDraft({ ...draft, question: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="survey-trigger" className={LABEL}>
              Asked
            </label>
            <Select
              id="survey-trigger"
              value={draft.trigger}
              onChange={(e) => setDraft({ ...draft, trigger: e.target.value as Trigger })}
            >
              {TRIGGERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor="survey-cooldown" className={LABEL}>
              Cooldown (days)
            </label>
            <Input
              id="survey-cooldown"
              type="number"
              min={0}
              value={draft.cooldown_days}
              onChange={(e) =>
                setDraft({ ...draft, cooldown_days: Number(e.target.value) })
              }
              className="w-[110px]"
            />
          </div>
          <Button
            onClick={() => create.mutate()}
            disabled={!draft.title.trim() || create.isPending}
            className="self-end"
          >
            Add
          </Button>
        </div>
        <ErrorText>{error}</ErrorText>

        <div className="mt-4 border-t border-[var(--color-border)] pt-3">
          {!surveys?.length ? (
            <EmptyState>No surveys yet.</EmptyState>
          ) : (
            <ul className="flex flex-col">
              {surveys.map((survey) => (
                <li
                  key={survey.id}
                  className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] py-2 text-sm last:border-none"
                >
                  <span className="min-w-0">
                    <span className="block text-[var(--color-text)]">
                      {survey.title}
                      <span
                        className="ml-2 text-[11px] font-semibold uppercase tracking-wide"
                        style={{ color: survey.is_active ? "#22c55e" : "#9494a8" }}
                      >
                        {survey.is_active ? "Live" : "Off"}
                      </span>
                    </span>
                    <span className="block text-xs text-[var(--color-text-muted)]">
                      {survey.trigger_name} · every {survey.cooldown_days} days ·{" "}
                      {survey.response_count}{" "}
                      {survey.response_count === 1 ? "answer" : "answers"}
                    </span>
                  </span>
                  <span className="flex gap-2">
                    <Button
                      variant="secondary"
                      onClick={() => toggle.mutate(survey)}
                      className="px-3 py-1 text-xs"
                    >
                      {survey.is_active ? "Switch off" : "Switch on"}
                    </Button>
                    <button
                      onClick={() => remove.mutate(survey.id)}
                      className={ghostButtonClass}
                    >
                      Delete
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>
    </div>
  );
}
