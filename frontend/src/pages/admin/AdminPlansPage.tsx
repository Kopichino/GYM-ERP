import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createPlan, deletePlan, fetchPlans, updatePlan, type Plan } from "../../api/billing";
import { Button, Card, EmptyState, ErrorState, Input, LoadingState, Textarea } from "../../components/ui";
import { useSubmitOnce } from "../../hooks/useSubmitOnce";
import { railColor } from "../../lib/theme";
import { askConfirm } from "../../store/confirmStore";

const PLANS_QUERY_KEY = ["billing", "plans", "admin"];
/** The price list on the public website (components/site/Membership). */
const PUBLIC_PLANS_QUERY_KEY = ["public-plans"];

/**
 * Every cached list of plans: this page's, the till's picker and the other plan
 * pickers (all under "plans"), and the website's price list. A change here --
 * a new price, or a plan retired -- has to reach all of them, or the till goes
 * on offering a plan that has just been taken off sale.
 */
function refreshPlanLists(queryClient: QueryClient) {
  for (const queryKey of [PLANS_QUERY_KEY, ["plans"], PUBLIC_PLANS_QUERY_KEY]) {
    queryClient.invalidateQueries({ queryKey });
  }
}

/**
 * The server's own reason a save was refused -- "A plan with this name already
 * exists." -- or `fallback` when it gave none.
 */
function refusal(error: unknown, fallback: string) {
  const data = (error as { response?: { data?: Record<string, unknown> } } | null)?.response?.data;
  const first = data ? Object.values(data)[0] : undefined;
  const message = Array.isArray(first) ? first[0] : first;
  return typeof message === "string" && message ? message : fallback;
}

/**
 * One plan in the list, editable in place.
 *
 * Changing a price here changes it for the next sale and on the public
 * website's price list straight away. Payments already recorded keep the amount
 * that was actually charged -- each payment stores its own amount -- so an edit
 * never rewrites anyone's history.
 */
function PlanRow({
  plan,
  onToggle,
  onDelete,
}: {
  plan: Plan;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const submitOnce = useSubmitOnce();
  const [draft, setDraft] = useState({
    name: plan.name,
    price: plan.price,
    duration_days: String(plan.duration_days),
    description: plan.description,
  });

  const save = useMutation({
    mutationFn: () =>
      updatePlan(plan.id, {
        name: draft.name,
        price: draft.price,
        duration_days: Number(draft.duration_days),
        description: draft.description,
      }),
    onSuccess: () => {
      setEditing(false);
      refreshPlanLists(queryClient);
    },
  });

  function startEditing() {
    // Seeded from the plan as it is now, not as it was when the row mounted.
    setDraft({
      name: plan.name,
      price: plan.price,
      duration_days: String(plan.duration_days),
      description: plan.description,
    });
    save.reset();
    setEditing(true);
  }

  if (editing) {
    return (
      <li className="border-b border-[var(--color-border)] py-3 last:border-none">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submitOnce((settled) => save.mutate(undefined, { onSettled: settled }));
          }}
          className="flex flex-col gap-2"
        >
          <Input
            aria-label="Plan name"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            required
          />
          <div className="flex gap-2">
            <Input
              aria-label="Price"
              type="number"
              step="0.01"
              min="0"
              value={draft.price}
              onChange={(e) => setDraft({ ...draft, price: e.target.value })}
              required
            />
            <Input
              aria-label="Duration (days)"
              type="number"
              min="1"
              value={draft.duration_days}
              onChange={(e) => setDraft({ ...draft, duration_days: e.target.value })}
              required
            />
          </div>
          <Textarea
            aria-label="Features, one per line"
            placeholder={"Features, one per line (optional). Shown on your website's price list."}
            rows={3}
            value={draft.description}
            onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          />
          <p className="text-xs text-[var(--color-text-muted)]">
            New sales and your website use the new details straight away. Payments already recorded
            keep what was charged.
          </p>
          {save.isError && (
            <ErrorState>
              {refusal(save.error, "Couldn't save those changes -- check the fields and try again.")}
            </ErrorState>
          )}
          <div className="flex gap-2">
            <Button type="submit" disabled={save.isPending} className="px-3 py-1 text-xs">
              {save.isPending ? "Saving..." : "Save"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setEditing(false)}
              className="px-3 py-1 text-xs"
            >
              Cancel
            </Button>
          </div>
        </form>
      </li>
    );
  }

  return (
    <li className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] py-2 last:border-none">
      <div className="min-w-0">
        <span
          className={`text-sm ${
            plan.is_active ? "text-[var(--color-text)]" : "text-[var(--color-text-muted)] line-through"
          }`}
        >
          {plan.name}
        </span>
        <p className="text-xs text-[var(--color-text-muted)]">
          &#8377;{plan.price} - {plan.duration_days} days
        </p>
      </div>
      <div className="flex shrink-0 gap-2">
        <Button variant="secondary" onClick={startEditing} className="px-2 py-1 text-xs">
          Edit
        </Button>
        <Button variant="secondary" onClick={onToggle} className="px-2 py-1 text-xs">
          {plan.is_active ? "Deactivate" : "Activate"}
        </Button>
        <Button variant="danger" onClick={onDelete} className="px-2 py-1 text-xs">
          Delete
        </Button>
      </div>
    </li>
  );
}

export default function AdminPlansPage() {
  const queryClient = useQueryClient();
  const { data: plans, isLoading, isError } = useQuery({ queryKey: PLANS_QUERY_KEY, queryFn: fetchPlans });

  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [durationDays, setDurationDays] = useState("");
  const [description, setDescription] = useState("");
  const submitOnce = useSubmitOnce();

  const invalidate = () => refreshPlanLists(queryClient);

  const create = useMutation({
    mutationFn: () =>
      createPlan({ name, price, duration_days: Number(durationDays), description, is_active: true }),
    onSuccess: () => {
      invalidate();
      setName("");
      setPrice("");
      setDurationDays("");
      setDescription("");
    },
  });

  const toggleActive = useMutation({
    mutationFn: (plan: Plan) => updatePlan(plan.id, { is_active: !plan.is_active }),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: number) => deletePlan(id),
    onSuccess: invalidate,
  });

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card accent={railColor(0)}>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Add plan
        </h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submitOnce((settled) => create.mutate(undefined, { onSettled: settled }));
          }}
          className="flex flex-col gap-3"
        >
          <Input
            placeholder="Plan name (e.g. Monthly)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <div className="flex gap-3">
            <Input
              type="number"
              step="0.01"
              min="0"
              placeholder="Price"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              required
            />
            <Input
              type="number"
              min="1"
              placeholder="Duration (days)"
              value={durationDays}
              onChange={(e) => setDurationDays(e.target.value)}
              required
            />
          </div>
          <Textarea
            placeholder={"Features, one per line (optional). Shown on your website's price list."}
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? "Saving..." : "Add plan"}
          </Button>
          {create.isError && (
            <ErrorState>
              {refusal(create.error, "Couldn't save that plan -- check the fields and try again.")}
            </ErrorState>
          )}
        </form>
      </Card>

      <Card accent={railColor(1)}>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Existing plans
        </h2>
        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState />
        ) : plans?.length === 0 ? (
          <EmptyState>No plans yet -- add one to start recording payments.</EmptyState>
        ) : (
          <ul className="flex flex-col gap-2">
            {plans?.map((plan) => (
              <PlanRow
                key={plan.id}
                plan={plan}
                onToggle={() => toggleActive.mutate(plan)}
                onDelete={() =>
                  askConfirm({
                    title: `Delete the "${plan.name}" plan?`,
                    consequence:
                      "Members already on it keep their paid period; the plan just cannot be sold again.",
                    run: () => remove.mutate(plan.id),
                  })
                }
              />
            ))}
          </ul>
        )}
        {remove.isError && (
          <ErrorState>Couldn't delete that plan -- it has payment history. Deactivate it instead.</ErrorState>
        )}
      </Card>
    </div>
  );
}
