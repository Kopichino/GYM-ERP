import { todayIso } from "../../lib/dates";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";
import {
  createDiscount,
  deleteDiscount,
  fetchDiscounts,
  fetchSellablePlans,
  updateDiscount,
  type Discount,
  type DiscountType,
} from "../../api/billing";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  Input,
  LoadingState,
  Select,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "../../components/ui";
import { fadeUp, staggerContainer } from "../../lib/motion";
import { railColor } from "../../lib/theme";
import { askConfirm } from "../../store/confirmStore";


const emptyForm = {
  code: "",
  description: "",
  discount_type: "percent" as DiscountType,
  value: "",
  plan: "" as number | "",
  valid_from: todayIso(),
  valid_until: "",
  max_uses: "",
  max_uses_per_member: "1",
};

function offerValue(d: Discount) {
  return d.discount_type === "percent" ? `${Number(d.value)}% off` : `${Number(d.value)} off`;
}

/** An offer can be live, not started, finished, fully redeemed or switched off
 *  -- the table says which rather than just "active/inactive". */
function statusOf(d: Discount): { label: string; colour: string } {
  const now = todayIso();
  if (!d.is_active) return { label: "Paused", colour: "#9494a8" };
  if (d.valid_from > now) return { label: "Scheduled", colour: "#4f8dfd" };
  if (d.valid_until && d.valid_until < now) return { label: "Expired", colour: "#ff3d5a" };
  if (d.max_uses !== null && d.times_used >= d.max_uses)
    return { label: "Used up", colour: "#ff3d5a" };
  return { label: "Live", colour: "#22c55e" };
}

export default function AdminOffersPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");

  const { data: offers, isLoading, isError } = useQuery({
    queryKey: ["admin", "discounts"],
    queryFn: fetchDiscounts,
  });
  // Only plans on sale: an offer limited to a retired plan could never be used.
  const { data: plans } = useQuery({ queryKey: ["plans", "sellable"], queryFn: fetchSellablePlans });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin", "discounts"] });

  const add = useMutation({
    mutationFn: () =>
      createDiscount({
        code: form.code,
        description: form.description,
        discount_type: form.discount_type,
        value: form.value,
        // No plan chosen means the offer is good on everything.
        plans: form.plan === "" ? [] : [Number(form.plan)],
        valid_from: form.valid_from,
        valid_until: form.valid_until || null,
        max_uses: form.max_uses ? Number(form.max_uses) : null,
        max_uses_per_member: Number(form.max_uses_per_member || 0),
      }),
    onSuccess: () => {
      setForm({ ...emptyForm, valid_from: todayIso() });
      setError("");
      invalidate();
    },
    onError: (err: { response?: { data?: Record<string, string[]> } }) => {
      const first = err.response?.data && Object.entries(err.response.data)[0];
      setError(first ? `${first[0]}: ${first[1]}` : "Could not create that offer.");
    },
  });

  const toggle = useMutation({
    mutationFn: (d: Discount) => updateDiscount(d.id, { is_active: !d.is_active }),
    onSuccess: invalidate,
  });
  const remove = useMutation({ mutationFn: deleteDiscount, onSuccess: invalidate });

  return (
    <div className="flex flex-col gap-6">
      <Card accent={railColor(0)}>
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Create an offer
        </h2>
        <p className="mb-4 text-sm text-[var(--color-text-muted)]">
          Codes are matched without regard to case, and can never take a sale below zero.
        </p>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Input
            placeholder="Code (e.g. NEWYEAR)"
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
          />
          <Select
            value={form.discount_type}
            onChange={(e) => setForm({ ...form, discount_type: e.target.value as DiscountType })}
          >
            <option value="percent">Percentage off</option>
            <option value="flat">Flat amount off</option>
          </Select>
          <Input
            type="number"
            step="0.01"
            min="0.01"
            placeholder={form.discount_type === "percent" ? "e.g. 20 (%)" : "e.g. 250"}
            value={form.value}
            onChange={(e) => setForm({ ...form, value: e.target.value })}
          />
          <Select
            value={form.plan}
            onChange={(e) => setForm({ ...form, plan: Number(e.target.value) || "" })}
          >
            <option value="">Any plan</option>
            {plans?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} only
              </option>
            ))}
          </Select>
          <label className="text-xs text-[var(--color-text-muted)]">
            Valid from
            <Input
              type="date"
              value={form.valid_from}
              onChange={(e) => setForm({ ...form, valid_from: e.target.value })}
              className="mt-1"
            />
          </label>
          <label className="text-xs text-[var(--color-text-muted)]">
            Until (optional)
            <Input
              type="date"
              value={form.valid_until}
              onChange={(e) => setForm({ ...form, valid_until: e.target.value })}
              className="mt-1"
            />
          </label>
          <label className="text-xs text-[var(--color-text-muted)]">
            Total uses (blank = unlimited)
            <Input
              type="number"
              min="1"
              value={form.max_uses}
              onChange={(e) => setForm({ ...form, max_uses: e.target.value })}
              className="mt-1"
            />
          </label>
          <label className="text-xs text-[var(--color-text-muted)]">
            Per member (0 = unlimited)
            <Input
              type="number"
              min="0"
              value={form.max_uses_per_member}
              onChange={(e) => setForm({ ...form, max_uses_per_member: e.target.value })}
              className="mt-1"
            />
          </label>
          <Input
            placeholder="Description (optional)"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>

        <div className="mt-3 flex items-center gap-3">
          <Button onClick={() => add.mutate()} disabled={!form.code || !form.value || add.isPending}>
            {add.isPending ? "Creating..." : "Create offer"}
          </Button>
          <ErrorText>{error}</ErrorText>
        </div>
      </Card>

      <Card accent={railColor(1)}>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {offers?.length ?? 0} offers
        </h2>
        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState />
        ) : !offers?.length ? (
          <EmptyState>No offers yet. Create one above.</EmptyState>
        ) : (
          <div className="no-scrollbar overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Code</th>
                  <th className={tableHeadCellClass}>Offer</th>
                  <th className={tableHeadCellClass}>Applies to</th>
                  <th className={tableHeadCellClass}>Runs</th>
                  <th className={tableHeadCellClass}>Used</th>
                  <th className={tableHeadCellClass}>Status</th>
                  <th className={tableHeadCellClass} />
                </tr>
              </thead>
              <motion.tbody initial="hidden" animate="visible" variants={staggerContainer(0.03)}>
                {offers.map((d) => {
                  const status = statusOf(d);
                  return (
                    <motion.tr key={d.id} variants={fadeUp} className={tableRowClass}>
                      <td className={`${tableCellClass} font-mono text-xs`}>{d.code}</td>
                      <td className={tableCellClass}>
                        {offerValue(d)}
                        {d.description && (
                          <span className="block text-xs text-[var(--color-text-muted)]">
                            {d.description}
                          </span>
                        )}
                      </td>
                      <td className={tableCellClass}>{d.plan_names.join(", ")}</td>
                      <td className={tableCellClass}>
                        {new Date(d.valid_from).toLocaleDateString()}
                        {d.valid_until ? ` - ${new Date(d.valid_until).toLocaleDateString()}` : " onwards"}
                      </td>
                      <td className={tableCellClass}>
                        {d.times_used}
                        {d.max_uses !== null && ` / ${d.max_uses}`}
                      </td>
                      <td className={tableCellClass}>
                        <span
                          className="rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
                          style={{ background: `${status.colour}22`, color: status.colour }}
                        >
                          {status.label}
                        </span>
                      </td>
                      <td className={`${tableCellClass} flex gap-2`}>
                        <Button variant="secondary" onClick={() => toggle.mutate(d)}>
                          {d.is_active ? "Pause" : "Resume"}
                        </Button>
                        <Button variant="danger" onClick={() =>
                        askConfirm({
                          title: `Delete offer "${d.code}"?`,
                          consequence: "Anyone holding the code will no longer be able to use it.",
                          run: () => remove.mutate(d.id),
                        })
                      }>
                          Delete
                        </Button>
                      </td>
                    </motion.tr>
                  );
                })}
              </motion.tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
