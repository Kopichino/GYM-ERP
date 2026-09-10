import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  deleteBadge,
  fetchBadges,
  saveBadge,
  updateBadge,
  TIER_NAMES,
  type Badge,
  type Criterion,
  type Tier,
} from "../../api/gamification";
import { fetchExercises } from "../../api/workouts";
import BadgeMedal from "../../components/BadgeMedal";
import { askConfirm } from "../../store/confirmStore";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  Input,
  LoadingState,
  Select, ghostButtonClass } from "../../components/ui";
import { railColor } from "../../lib/theme";

const CRITERIA: { value: Criterion; label: string }[] = [
  { value: "visits", label: "Total gym visits" },
  { value: "streak", label: "Longest daily streak" },
  { value: "month_streak", label: "Consecutive months trained" },
  { value: "workouts", label: "Workout sessions logged" },
  { value: "sets", label: "Sets logged" },
  { value: "classes", label: "Classes attended" },
  { value: "records", label: "Personal records set" },
  { value: "months", label: "Months as a member" },
  { value: "lift", label: "Heaviest lift on one exercise (kg)" },
];

const LABEL = "mb-1 block text-xs uppercase tracking-wide text-[var(--color-text-muted)]";

/** Uploading artwork for one badge, in place. */
function ArtworkUpload({ badge }: { badge: Badge }) {
  const queryClient = useQueryClient();
  const upload = useMutation({
    mutationFn: (file: File) => {
      const body = new FormData();
      body.append("image", file);
      return updateBadge(badge.id, body);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["badges"] }),
  });

  return (
    <label className={ghostButtonClass}>
      {upload.isPending ? "Uploading..." : badge.image ? "Replace art" : "Add art"}
      <input
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) upload.mutate(file);
        }}
      />
    </label>
  );
}

export default function AdminBadgesPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    code: "",
    name: "",
    description: "",
    tier: "1",
    criterion: "visits" as Criterion,
    exercise: "",
    threshold: "",
  });
  const [error, setError] = useState("");

  const { data: badges, isLoading, isError } = useQuery({
    queryKey: ["badges"],
    queryFn: fetchBadges,
  });
  const { data: exercises } = useQuery({ queryKey: ["exercises"], queryFn: fetchExercises });

  // Only a lift badge names an exercise, and it must -- "100kg" says nothing
  // without saying 100kg of what. The database enforces both halves of that.
  const isLift = form.criterion === "lift";

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["badges"] });

  const add = useMutation({
    mutationFn: () => {
      const body = new FormData();
      Object.entries(form).forEach(([key, value]) => {
        // An empty exercise must be left out rather than sent as "", which the
        // serializer would read as an attempt to set a blank foreign key.
        if (key === "exercise" && (!isLift || !value)) return;
        body.append(key, String(value));
      });
      return saveBadge(body);
    },
    onSuccess: () => {
      setForm({ ...form, code: "", name: "", description: "", threshold: "" });
      setError("");
      invalidate();
    },
    onError: (err: { response?: { data?: Record<string, string[]> } }) => {
      const first = err.response?.data && Object.entries(err.response.data)[0];
      setError(first ? `${first[0]}: ${first[1]}` : "Could not create that badge.");
    },
  });

  const remove = useMutation({ mutationFn: deleteBadge, onSuccess: invalidate });

  // Typed to the shape both Input and the custom Select hand back, rather
  // than a full ChangeEvent -- Select's own handler is deliberately narrower.
  function field(key: keyof typeof form) {
    return (e: { target: { value: string } }) =>
      setForm((f) => ({ ...f, [key]: e.target.value }));
  }

  // Grouped by what they measure, which is how the ladders were designed and
  // how an admin decides whether a threshold is reachable.
  const groups = CRITERIA.map((criterion) => ({
    ...criterion,
    badges: (badges ?? [])
      .filter((b) => b.criterion === criterion.value)
      .sort((a, b) => a.threshold - b.threshold),
  })).filter((group) => group.badges.length > 0);

  return (
    <div className="flex flex-col gap-6">
      <Card accent={railColor(0)}>
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Add a badge
        </h2>
        <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
          Every criterion is something the system already counts, so a badge can never be
          defined against a number nothing measures. Artwork is optional — until you upload
          some, members see a tier-coloured medal.
        </p>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <label htmlFor="badge-name" className={LABEL}>
              Name
            </label>
            <Input id="badge-name" value={form.name} onChange={field("name")} />
          </div>
          <div>
            <label htmlFor="badge-code" className={LABEL}>
              Code
            </label>
            <Input
              id="badge-code"
              placeholder="e.g. visits-100"
              value={form.code}
              onChange={field("code")}
            />
          </div>
          <div>
            <label htmlFor="badge-tier" className={LABEL}>
              Tier
            </label>
            <Select id="badge-tier" value={form.tier} onChange={field("tier")}>
              {([1, 2, 3, 4, 5] as Tier[]).map((tier) => (
                <option key={tier} value={tier}>
                  {tier}. {TIER_NAMES[tier]}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor="badge-criterion" className={LABEL}>
              Measured on
            </label>
            <Select id="badge-criterion" value={form.criterion} onChange={field("criterion")}>
              {CRITERIA.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </Select>
          </div>
          {isLift && (
            <div>
              <label htmlFor="badge-exercise" className={LABEL}>
                Exercise
              </label>
              <Select
                id="badge-exercise"
                value={form.exercise}
                onChange={field("exercise")}
              >
                <option value="">Pick one</option>
                {exercises?.map((ex) => (
                  <option key={ex.id} value={ex.id}>
                    {ex.name}
                  </option>
                ))}
              </Select>
            </div>
          )}
          <div>
            <label htmlFor="badge-threshold" className={LABEL}>
              {isLift ? "Reached at (kg)" : "Reached at"}
            </label>
            <Input
              id="badge-threshold"
              type="number"
              min={1}
              value={form.threshold}
              onChange={field("threshold")}
            />
          </div>
          <div>
            <label htmlFor="badge-description" className={LABEL}>
              Description
            </label>
            <Input
              id="badge-description"
              value={form.description}
              onChange={field("description")}
            />
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button
            onClick={() => add.mutate()}
            disabled={
              !form.name ||
              !form.code ||
              !form.threshold ||
              (isLift && !form.exercise) ||
              add.isPending
            }
          >
            {add.isPending ? "Creating..." : "Create badge"}
          </Button>
          <ErrorText>{error}</ErrorText>
        </div>
      </Card>

      {isLoading ? (
        <Card>
          <LoadingState />
        </Card>
      ) : isError ? (
        <Card>
          <ErrorState />
        </Card>
      ) : !groups.length ? (
        <Card>
          <EmptyState>
            No badges yet. Run <code>manage.py import_badges</code> for a starter ladder, or add
            one above.
          </EmptyState>
        </Card>
      ) : (
        groups.map((group, index) => (
          <Card key={group.value} accent={railColor(index + 1)}>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              {group.label}
            </h2>
            <ul className="flex flex-col">
              {group.badges.map((badge) => (
                <li
                  key={badge.id}
                  className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-[var(--color-border)] py-3 last:border-none"
                >
                  <BadgeMedal badge={badge} earned size={40} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-[var(--color-text)]">
                      {badge.name}
                    </span>
                    <span className="block text-xs text-[var(--color-text-muted)]">
                      {badge.tier_name} · at {badge.threshold}
                      {badge.criterion === "lift"
                        ? `kg on the ${badge.exercise_name}`
                        : ""}{" "}
                      · {badge.awarded_count} awarded
                      {!badge.image && " · no artwork yet"}
                    </span>
                  </span>
                  <ArtworkUpload badge={badge} />
                  <Button
                    variant="danger"
                    onClick={() =>
                      askConfirm({
                        title: `Delete "${badge.name}"?`,
                        // A badge nobody holds is just a definition; one that
                        // has been awarded is member-facing history, and the
                        // count is the fact that decides whether this matters.
                        consequence: badge.awarded_count
                          ? `${badge.awarded_count} member${
                              badge.awarded_count === 1 ? "" : "s"
                            } earned this and will lose it.`
                          : "No members have earned this badge yet.",
                        run: () => remove.mutate(badge.id),
                      })
                    }
                    className="px-3 py-1 text-xs"
                  >
                    Delete
                  </Button>
                </li>
              ))}
            </ul>
          </Card>
        ))
      )}
    </div>
  );
}
