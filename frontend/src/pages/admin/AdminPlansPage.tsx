import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createPlan, deletePlan, fetchPlans, updatePlan, type Plan } from "../../api/billing";
import { Button, Card, EmptyState, ErrorState, Input, LoadingState, Textarea } from "../../components/ui";

const PLANS_QUERY_KEY = ["billing", "plans", "admin"];

export default function AdminPlansPage() {
  const queryClient = useQueryClient();
  const { data: plans, isLoading, isError } = useQuery({ queryKey: PLANS_QUERY_KEY, queryFn: fetchPlans });

  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [durationDays, setDurationDays] = useState("");
  const [description, setDescription] = useState("");

  const invalidate = () => queryClient.invalidateQueries({ queryKey: PLANS_QUERY_KEY });

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
      <Card>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Add plan
        </h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
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
            placeholder="Description (optional)"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? "Saving..." : "Add plan"}
          </Button>
          {create.isError && (
            <ErrorState>Couldn't save that plan -- check the fields and try again.</ErrorState>
          )}
        </form>
      </Card>

      <Card>
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
              <li
                key={plan.id}
                className="flex items-center justify-between border-b border-[var(--color-border)] py-2 last:border-none"
              >
                <div>
                  <span
                    className={`text-sm ${
                      plan.is_active ? "text-[var(--color-text)]" : "text-[var(--color-text-muted)] line-through"
                    }`}
                  >
                    {plan.name}
                  </span>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    {plan.price} - {plan.duration_days} days
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => toggleActive.mutate(plan)}
                    className="px-2 py-1 text-xs"
                  >
                    {plan.is_active ? "Deactivate" : "Activate"}
                  </Button>
                  <Button variant="danger" onClick={() => remove.mutate(plan.id)} className="px-2 py-1 text-xs">
                    Delete
                  </Button>
                </div>
              </li>
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
