import { isoDate } from "../../lib/dates";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";
import {
  createExpense,
  createExpenseCategory,
  deleteExpense,
  fetchExpenseCategories,
  fetchExpenses,
  fetchExpenseSummary,
} from "../../api/expenses";
import ExpenseBreakdownChart from "../../components/ExpenseBreakdownChart";
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

const monthStart = () => {
  const d = new Date();
  d.setDate(1);
  return isoDate(d);
};

export default function AdminExpensesPage() {
  const queryClient = useQueryClient();
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(isoDate(new Date()));
  const [form, setForm] = useState({
    category: "" as number | "",
    amount: "",
    spent_on: isoDate(new Date()),
    vendor: "",
    reference: "",
    notes: "",
  });
  const [newCategory, setNewCategory] = useState("");
  const [error, setError] = useState("");

  const filters = { from, to };
  const { data: categories } = useQuery({
    queryKey: ["expenses", "categories"],
    queryFn: fetchExpenseCategories,
  });
  const { data: expenses, isLoading, isError } = useQuery({
    queryKey: ["expenses", "list", from, to],
    queryFn: () => fetchExpenses(filters),
  });
  const { data: summary } = useQuery({
    queryKey: ["expenses", "summary", from, to],
    queryFn: () => fetchExpenseSummary(filters),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["expenses"] });

  const add = useMutation({
    mutationFn: () =>
      createExpense({
        category: Number(form.category),
        amount: form.amount,
        spent_on: form.spent_on,
        vendor: form.vendor,
        reference: form.reference,
        notes: form.notes,
      }),
    onSuccess: () => {
      setForm({ ...form, amount: "", vendor: "", reference: "", notes: "" });
      setError("");
      invalidate();
    },
    onError: (err: { response?: { data?: Record<string, string[]> } }) => {
      const first = err.response?.data && Object.entries(err.response.data)[0];
      setError(first ? `${first[0]}: ${first[1]}` : "Could not save that expense.");
    },
  });

  const addCategory = useMutation({
    mutationFn: () => createExpenseCategory({ name: newCategory }),
    onSuccess: () => {
      setNewCategory("");
      invalidate();
    },
  });

  const remove = useMutation({ mutationFn: deleteExpense, onSuccess: invalidate });
  const maxCategory = Math.max(1, ...(summary?.by_category.map((c) => Number(c.total)) ?? [1]));

  return (
    <div className="flex flex-col gap-6">
      <Card accent={railColor(0)}>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="font-display text-3xl leading-none text-[var(--color-text)]">
              {summary?.total ?? "0"}
            </p>
            <p className="mt-1 text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
              Spent in this period · {summary?.count ?? 0} entries
            </p>
          </div>
          <div className="flex gap-2">
            <label className="text-xs text-[var(--color-text-muted)]">
              From
              <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="mt-1" />
            </label>
            <label className="text-xs text-[var(--color-text-muted)]">
              To
              <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="mt-1" />
            </label>
          </div>
        </div>

        {summary && summary.by_category.length > 0 && (
          <div className="grid gap-6 border-t border-[var(--color-border)] pt-3 lg:grid-cols-2">
            <ExpenseBreakdownChart slices={summary.by_category} />
            {/* The bars stay alongside the donut: a pie is good for shares and
                bad for comparing two similar slices, which is exactly what an
                owner does when deciding what to cut. */}
            <ul className="flex flex-col justify-center">
              {summary.by_category.map((c, index) => (
                <li key={c.category} className="py-2">
                  <div className="mb-1 flex items-baseline justify-between text-sm">
                    <span className="flex items-center gap-2 text-[var(--color-text)]">
                      <span
                        className="h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ background: railColor(index) }}
                      />
                      {c.category}
                    </span>
                    <span className="text-[var(--color-text-muted)]">
                      {c.total}
                      {summary.total !== "0" && (
                        <span className="ml-2 text-xs">
                          {Math.round((Number(c.total) / Number(summary.total)) * 100)}%
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-2)]">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${(Number(c.total) / maxCategory) * 100}%`,
                        background: railColor(index),
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      <Card accent={railColor(1)}>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Record an expense
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Select
            value={form.category}
            onChange={(e) => setForm({ ...form, category: Number(e.target.value) || "" })}
          >
            <option value="">Select category</option>
            {categories?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
          <Input
            type="number"
            step="0.01"
            min="0"
            placeholder="Amount"
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
          />
          <label className="text-xs text-[var(--color-text-muted)]">
            Spent on
            <Input
              type="date"
              value={form.spent_on}
              onChange={(e) => setForm({ ...form, spent_on: e.target.value })}
              className="mt-1"
            />
          </label>
          <Input
            placeholder="Vendor (optional)"
            value={form.vendor}
            onChange={(e) => setForm({ ...form, vendor: e.target.value })}
          />
          <Input
            placeholder="Bill / reference no."
            value={form.reference}
            onChange={(e) => setForm({ ...form, reference: e.target.value })}
          />
          <Input
            placeholder="Notes"
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
          />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button
            onClick={() => add.mutate()}
            disabled={!form.category || !form.amount || add.isPending}
          >
            {add.isPending ? "Saving..." : "Record expense"}
          </Button>
          <span className="text-[var(--color-text-muted)]">|</span>
          <Input
            placeholder="New category"
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value)}
            className="max-w-[180px]"
          />
          <Button
            variant="secondary"
            onClick={() => addCategory.mutate()}
            disabled={!newCategory || addCategory.isPending}
          >
            Add category
          </Button>
          <ErrorText>{error}</ErrorText>
        </div>
      </Card>

      <Card accent={railColor(2)}>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {expenses?.length ?? 0} expenses
        </h2>
        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState />
        ) : !expenses?.length ? (
          <EmptyState>Nothing recorded in this period.</EmptyState>
        ) : (
          <div className="no-scrollbar overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Date</th>
                  <th className={tableHeadCellClass}>Category</th>
                  <th className={tableHeadCellClass}>Amount</th>
                  <th className={tableHeadCellClass}>Vendor</th>
                  <th className={tableHeadCellClass}>Reference</th>
                  <th className={tableHeadCellClass} />
                </tr>
              </thead>
              <motion.tbody initial="hidden" animate="visible" variants={staggerContainer(0.03)}>
                {expenses.map((e) => (
                  <motion.tr key={e.id} variants={fadeUp} className={tableRowClass}>
                    <td className={tableCellClass}>{new Date(e.spent_on).toLocaleDateString()}</td>
                    <td className={tableCellClass}>{e.category_name}</td>
                    <td className={tableCellClass}>{e.amount}</td>
                    <td className={tableCellClass}>{e.vendor || "-"}</td>
                    <td className={tableCellClass}>{e.reference || "-"}</td>
                    <td className={tableCellClass}>
                      <Button variant="danger" onClick={() =>
                        askConfirm({
                          title: "Delete this expense?",
                          consequence: "It will stop counting against your reported spend.",
                          run: () => remove.mutate(e.id),
                        })
                      }>
                        Delete
                      </Button>
                    </td>
                  </motion.tr>
                ))}
              </motion.tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
