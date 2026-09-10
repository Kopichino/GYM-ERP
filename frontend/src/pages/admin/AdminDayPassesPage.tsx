import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  checkInDayPass,
  createDayPass,
  deleteDayPass,
  fetchDayPasses,
  type DayPass,
} from "../../api/daypasses";
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
import { isoDate, todayIso } from "../../lib/dates";
import { railColor } from "../../lib/theme";
import { askConfirm } from "../../store/confirmStore";

const LABEL = "mb-1 block text-xs uppercase tracking-wide text-[var(--color-text-muted)]";

const METHODS = [
  { value: "cash", label: "Cash" },
  { value: "upi", label: "UPI" },
  { value: "card", label: "Card" },
  { value: "bank_transfer", label: "Bank transfer" },
  { value: "other", label: "Other" },
];

function PassRow({ pass }: { pass: DayPass }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["day-passes"] });

  const toggle = useMutation({
    mutationFn: () => checkInDayPass(pass.id),
    onSuccess: () => {
      setError("");
      invalidate();
    },
    onError: (err: { response?: { data?: { detail?: string } } }) =>
      setError(err.response?.data?.detail ?? "Could not do that."),
  });
  const remove = useMutation({ mutationFn: () => deleteDayPass(pass.id), onSuccess: invalidate });

  return (
    <tr className={tableRowClass}>
      <td className={tableCellClass}>
        {pass.name}
        {pass.phone && (
          <span className="block text-xs text-[var(--color-text-muted)]">{pass.phone}</span>
        )}
        <ErrorText>{error}</ErrorText>
      </td>
      <td className={tableCellClass}>{new Date(pass.valid_on).toLocaleDateString()}</td>
      <td className={`${tableCellClass} tabular-nums`}>{pass.amount}</td>
      <td className={tableCellClass}>{pass.method.replace("_", " ")}</td>
      <td className={tableCellClass}>
        {pass.checked_in ? (
          <span className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: "#22c55e" }}>
            In the gym
          </span>
        ) : (
          <span className="text-xs text-[var(--color-text-muted)]">
            {pass.visit_count > 0 ? "Been and gone" : "Not arrived"}
          </span>
        )}
      </td>
      <td className={`${tableCellClass} flex flex-wrap gap-2`}>
        {pass.is_valid_today && (
          <Button
            variant="secondary"
            onClick={() => toggle.mutate()}
            disabled={toggle.isPending}
            className="px-3 py-1 text-xs"
          >
            {pass.checked_in ? "Check out" : "Check in"}
          </Button>
        )}
        <Button
          variant="danger"
          onClick={() =>
            askConfirm({
              title: `Delete the pass for ${pass.name}?`,
              consequence: pass.checked_in
                ? "They are currently checked in; the visit goes with the pass."
                : "The sale and the visit it recorded are removed.",
              run: () => remove.mutate(),
            })
          }
          className="px-3 py-1 text-xs"
        >
          Delete
        </Button>
      </td>
    </tr>
  );
}

export default function AdminDayPassesPage() {
  const queryClient = useQueryClient();
  const [on, setOn] = useState(todayIso());
  const [form, setForm] = useState({
    name: "",
    phone: "",
    email: "",
    amount: "",
    method: "cash",
    notes: "",
  });
  const [error, setError] = useState("");

  const { data: passes, isLoading, isError } = useQuery({
    queryKey: ["day-passes", on],
    queryFn: () => fetchDayPasses({ on }),
  });

  const add = useMutation({
    mutationFn: () => createDayPass({ ...form, valid_on: on, amount: form.amount || "0" }),
    onSuccess: () => {
      setForm({ ...form, name: "", phone: "", email: "", amount: "", notes: "" });
      setError("");
      queryClient.invalidateQueries({ queryKey: ["day-passes"] });
    },
    onError: (err: { response?: { data?: Record<string, string[]> } }) => {
      const first = err.response?.data && Object.entries(err.response.data)[0];
      setError(first ? `${first[0]}: ${first[1]}` : "Could not issue that pass.");
    },
  });

  const inside = passes?.filter((p) => p.checked_in).length ?? 0;
  const takings = (passes ?? []).reduce((sum, p) => sum + Number(p.amount), 0);

  return (
    <div className="flex flex-col gap-6">
      <Card accent={railColor(0)}>
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Sell a day pass
        </h2>
        <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
          A walk-in gets a pass, not an account — no login, no plan, no membership status, and
          they never appear in member lists or reminder emails. Their visit is still recorded
          alongside everyone else's, so the occupancy figures count the whole gym.
        </p>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <label htmlFor="pass-name" className={LABEL}>
              Name
            </label>
            <Input
              id="pass-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="pass-phone" className={LABEL}>
              Phone
            </label>
            <Input
              id="pass-phone"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="pass-amount" className={LABEL}>
              Charged
            </label>
            <Input
              id="pass-amount"
              type="number"
              min={0}
              step="0.01"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="pass-method" className={LABEL}>
              Paid by
            </label>
            <Select
              id="pass-method"
              value={form.method}
              onChange={(e) => setForm({ ...form, method: e.target.value })}
            >
              {METHODS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor="pass-email" className={LABEL}>
              Email (optional)
            </label>
            <Input
              id="pass-email"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="pass-notes" className={LABEL}>
              Notes
            </label>
            <Input
              id="pass-notes"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button onClick={() => add.mutate()} disabled={!form.name || add.isPending}>
            {add.isPending ? "Issuing..." : "Issue pass"}
          </Button>
          <span className="text-xs text-[var(--color-text-muted)]">
            Valid for {new Date(on).toLocaleDateString()} only.
          </span>
          <ErrorText>{error}</ErrorText>
        </div>
      </Card>

      <Card accent={railColor(1)}>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              {passes?.length ?? 0} passes ·{" "}
              <span style={{ color: "#22c55e" }}>{inside} in the gym</span>
            </h2>
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">
              {takings.toLocaleString()} taken on walk-ins that day
            </p>
          </div>
          <label className="text-xs text-[var(--color-text-muted)]">
            Day
            <Input
              type="date"
              value={on}
              onChange={(e) => setOn(e.target.value || isoDate(new Date()))}
              className="mt-1"
            />
          </label>
        </div>

        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState />
        ) : !passes?.length ? (
          <EmptyState>No day passes sold on that date.</EmptyState>
        ) : (
          <div className="no-scrollbar overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Guest</th>
                  <th className={tableHeadCellClass}>Valid on</th>
                  <th className={tableHeadCellClass}>Charged</th>
                  <th className={tableHeadCellClass}>Paid by</th>
                  <th className={tableHeadCellClass}>Status</th>
                  <th className={tableHeadCellClass} />
                </tr>
              </thead>
              <tbody>
                {passes.map((pass) => (
                  <PassRow key={pass.id} pass={pass} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
