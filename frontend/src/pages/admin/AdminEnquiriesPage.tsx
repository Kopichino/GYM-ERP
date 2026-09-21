import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Fragment, useState } from "react";
import {
  addEnquiryNote,
  convertEnquiry,
  createEnquiry,
  deleteEnquiry,
  ENQUIRY_SOURCES,
  fetchEnquiries,
  fetchPipeline,
  markCalled,
  updateEnquiry,
  type Enquiry,
  type EnquirySource,
  type EnquiryStatus,
} from "../../api/crm";
import { fetchSellablePlans } from "../../api/billing";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  Input,
  LoadingState,
  Select,
  Textarea,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "../../components/ui";
import { useEnquiryReminder } from "../../hooks/useEnquiryReminder";
import { fadeUp, staggerContainer } from "../../lib/motion";
import { isoDate, todayIso } from "../../lib/dates";
import { askConfirm } from "../../store/confirmStore";

const STATUS_COLOR: Record<EnquiryStatus, string> = {
  open: "#ffb020",
  contacted: "#4f8dfd",
  trial: "#a855f7",
  joined: "#22c55e",
  lost: "#9494a8",
};

const STATUS_LABEL: Record<EnquiryStatus, string> = {
  open: "To call",
  contacted: "Contacted",
  trial: "Trial booked",
  joined: "Joined",
  lost: "Not interested",
};

const emptyForm = {
  name: "",
  phone: "",
  email: "",
  follow_up_on: todayIso(),
  source: "walk_in" as EnquirySource,
  interested_in: "" as number | "",
  notes: "",
};

function StatusPill({ status }: { status: EnquiryStatus }) {
  return (
    <span
      // inline-block + nowrap: as a plain inline span a two-word label like
      // "Not interested" wrapped inside a narrow column, and the rounded
      // padding did not follow the second line -- so the text spilled outside
      // the pill shape. A status is one token and should never break.
      className="inline-block whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-semibold leading-none"
      style={{ background: `${STATUS_COLOR[status]}22`, color: STATUS_COLOR[status] }}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}

function WhenLabel({ enquiry }: { enquiry: Enquiry }) {
  const when = new Date(enquiry.follow_up_on).toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
  if (enquiry.status !== "open") return <span>{when}</span>;
  if (enquiry.days_overdue > 0) {
    return (
      <span style={{ color: "var(--color-accent)" }}>
        {when} · {enquiry.days_overdue}d overdue
      </span>
    );
  }
  if (enquiry.is_due) return <span style={{ color: "var(--color-accent-2)" }}>{when} · today</span>;
  return <span>{when}</span>;
}

/** The call trail and the one-click conversion, opened per row. */
function LeadDetail({ enquiry }: { enquiry: Enquiry }) {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [username, setUsername] = useState("");
  const [error, setError] = useState("");

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["enquiries"] });

  const note = useMutation({
    mutationFn: () => addEnquiryNote(enquiry.id, body),
    onSuccess: () => {
      setBody("");
      setError("");
      invalidate();
    },
    onError: () => setError("Could not save that note."),
  });

  const convert = useMutation({
    mutationFn: () => convertEnquiry(enquiry.id, username ? { username } : undefined),
    onSuccess: () => {
      setError("");
      invalidate();
    },
    onError: (err: { response?: { data?: { detail?: string } } }) =>
      setError(err.response?.data?.detail ?? "Could not convert that lead."),
  });

  return (
    <div className="flex flex-col gap-3 rounded-md bg-[var(--color-surface-2)] p-3">
      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="What happened on the call?"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          className="min-w-[220px] flex-1"
        />
        <Button variant="secondary" onClick={() => note.mutate()} disabled={!body || note.isPending}>
          Add to trail
        </Button>
      </div>

      {enquiry.trail.length > 0 && (
        <ul className="flex flex-col">
          {enquiry.trail.map((entry) => (
            <li
              key={entry.id}
              className="border-b border-[var(--color-border)] py-1.5 text-xs last:border-none"
            >
              <span className="text-[var(--color-text)]">{entry.body}</span>
              <span className="text-[var(--color-text-muted)]">
                {" "}
                — {entry.author_name ?? "someone"},{" "}
                {new Date(entry.created_at).toLocaleDateString()}
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-[var(--color-border)] pt-3">
        {enquiry.is_converted ? (
          <span className="text-xs text-[var(--color-text-muted)]">
            Became member <b>{enquiry.converted_username}</b>.
          </span>
        ) : (
          <>
            <Input
              placeholder="Username (auto if blank)"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="max-w-[220px]"
            />
            <Button
              variant="success"
              onClick={() => convert.mutate()}
              disabled={convert.isPending}
            >
              {convert.isPending ? "Creating..." : "Convert to member"}
            </Button>
            <span className="text-[11px] text-[var(--color-text-muted)]">
              Creates the account with no password — they set their own.
            </span>
          </>
        )}
      </div>
      <ErrorText>{error}</ErrorText>
    </div>
  );
}

/** Counts by stage and by channel, read live off the leads. */
function PipelineCard() {
  const { data } = useQuery({ queryKey: ["enquiries", "pipeline"], queryFn: fetchPipeline });
  if (!data || !data.total) return null;

  return (
    <Card accent="#22c55e">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Pipeline
        </h2>
        <div className="text-right">
          <p className="font-display text-3xl leading-none text-[var(--color-accent)]">
            {data.conversion_rate}%
          </p>
          <p className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
            {data.converted} of {data.total} leads joined
          </p>
        </div>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
        {data.by_status.map((row) => (
          <div key={row.status}>
            <p className="font-display text-2xl leading-none text-[var(--color-text)]">
              {row.count}
            </p>
            <p className="mt-1 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
              {row.status_name}
            </p>
          </div>
        ))}
      </div>

      <ul className="flex flex-col border-t border-[var(--color-border)] pt-2">
        {data.by_source.map((row) => (
          <li
            key={row.source}
            className="flex items-baseline justify-between gap-2 border-b border-[var(--color-border)] py-1.5 text-sm last:border-none"
          >
            <span className="text-[var(--color-text)]">{row.source_name}</span>
            <span className="text-xs text-[var(--color-text-muted)]">
              {row.joined}/{row.total} joined · <b>{row.conversion_rate}%</b>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function AdminEnquiriesPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(emptyForm);
  const [filter, setFilter] = useState<EnquiryStatus | "">("");
  const [sourceFilter, setSourceFilter] = useState<EnquirySource | "">("");
  const [openRow, setOpenRow] = useState<number | null>(null);
  const [error, setError] = useState("");

  const { due, canAsk, requestPermission, permission } = useEnquiryReminder(true);
  const { data: enquiries, isLoading, isError } = useQuery({
    queryKey: ["enquiries", filter, sourceFilter],
    queryFn: () =>
      fetchEnquiries({ status: filter || undefined, source: sourceFilter || undefined }),
  });
  // Only plans on sale: a new lead is not recorded against a retired plan.
  const { data: plans } = useQuery({ queryKey: ["plans", "sellable"], queryFn: fetchSellablePlans });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["enquiries"] });

  const add = useMutation({
    mutationFn: () =>
      createEnquiry({
        ...form,
        interested_in: form.interested_in === "" ? null : Number(form.interested_in),
      }),
    onSuccess: () => {
      setForm({ ...emptyForm, follow_up_on: todayIso() });
      setError("");
      invalidate();
    },
    onError: (err: { response?: { data?: Record<string, string[]> } }) => {
      const first = err.response?.data && Object.entries(err.response.data)[0];
      setError(first ? `${first[0]}: ${first[1]}` : "Could not save that enquiry.");
    },
  });

  const called = useMutation({
    mutationFn: ({ id, next }: { id: number; next?: string }) => markCalled(id, next),
    onSuccess: invalidate,
  });
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: EnquiryStatus }) =>
      updateEnquiry(id, { status }),
    onSuccess: invalidate,
  });
  const remove = useMutation({ mutationFn: deleteEnquiry, onSuccess: invalidate });

  function snooze(enquiry: Enquiry, days: number) {
    const next = new Date();
    next.setDate(next.getDate() + days);
    called.mutate({ id: enquiry.id, next: isoDate(next) });
  }

  return (
    <div className="flex flex-col gap-6">
      <PipelineCard />
      {/* The reminder itself: whoever opens the admin portal sees this first. */}
      {due && due.count > 0 && (
        <Card accent="var(--color-accent)">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-display text-2xl text-[var(--color-text)]">
              {due.count === 1 ? "1 call to make" : `${due.count} calls to make`}
            </h2>
            <span className="text-sm text-[var(--color-text-muted)]">
              {due.overdue_count > 0 && (
                <span style={{ color: "var(--color-accent)" }}>
                  {due.overdue_count} overdue ·{" "}
                </span>
              )}
              {new Date(due.date).toLocaleDateString(undefined, {
                weekday: "long",
                day: "numeric",
                month: "long",
              })}
            </span>
          </div>

          <ul className="flex flex-col">
            {due.results.map((e) => (
              <li
                key={e.id}
                className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] py-2.5 last:border-none"
              >
                <div className="min-w-0">
                  <p className="font-semibold text-[var(--color-text)]">{e.name}</p>
                  <a
                    href={`tel:${e.phone.replace(/\s/g, "")}`}
                    className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-accent)]"
                  >
                    {e.phone}
                  </a>
                  {e.days_overdue > 0 && (
                    <span className="ml-2 text-xs" style={{ color: "var(--color-accent)" }}>
                      {e.days_overdue}d overdue
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="success"
                    onClick={() => called.mutate({ id: e.id })}
                    disabled={called.isPending}
                  >
                    Mark called
                  </Button>
                  <Button variant="secondary" onClick={() => snooze(e, 1)}>
                    Tomorrow
                  </Button>
                  <Button variant="secondary" onClick={() => snooze(e, 7)}>
                    Next week
                  </Button>
                </div>
              </li>
            ))}
          </ul>

          {canAsk && (
            <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-[var(--color-border)] pt-3">
              <p className="text-sm text-[var(--color-text-muted)]">
                Want a desktop notification when a call is due?
              </p>
              <Button variant="secondary" onClick={requestPermission}>
                Turn on notifications
              </Button>
            </div>
          )}
          {permission === "denied" && (
            <p className="mt-3 border-t border-[var(--color-border)] pt-3 text-xs text-[var(--color-text-muted)]">
              Desktop notifications are blocked for this site, so this panel is the reminder.
            </p>
          )}
        </Card>
      )}

      <Card accent="#4f8dfd">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          New enquiry
        </h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <Input
            placeholder="Customer name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <Input
            placeholder="Phone number"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
          />
          <label className="text-xs text-[var(--color-text-muted)]">
            Call them on
            <Input
              type="date"
              value={form.follow_up_on}
              onChange={(e) => setForm({ ...form, follow_up_on: e.target.value })}
              className="mt-1"
            />
          </label>
          <label className="text-xs text-[var(--color-text-muted)]">
            How did they find us?
            <Select
              value={form.source}
              onChange={(e) => setForm({ ...form, source: e.target.value as EnquirySource })}
              className="mt-1"
            >
              {ENQUIRY_SOURCES.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </label>
          <label className="text-xs text-[var(--color-text-muted)]">
            Interested in
            <Select
              value={form.interested_in}
              onChange={(e) =>
                setForm({ ...form, interested_in: Number(e.target.value) || "" })
              }
              className="mt-1"
            >
              <option value="">Not sure yet</option>
              {plans?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </label>
          <Input
            placeholder="Email (optional)"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </div>
        <Textarea
          rows={2}
          placeholder="What did they ask about? (optional)"
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
          className="mt-3"
        />
        <div className="mt-3 flex items-center gap-3">
          <Button
            onClick={() => add.mutate()}
            disabled={!form.name || !form.phone || !form.follow_up_on || add.isPending}
          >
            {add.isPending ? "Saving..." : "Add enquiry"}
          </Button>
          <ErrorText>{error}</ErrorText>
        </div>
      </Card>

      <Card accent="#a855f7">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {enquiries?.length ?? 0} enquiries
          </h2>
          <Select
            value={filter}
            onChange={(e) => setFilter(e.target.value as EnquiryStatus | "")}
            className="max-w-[190px]"
          >
            <option value="">All stages</option>
            <option value="open">To call</option>
            <option value="contacted">Contacted</option>
            <option value="trial">Trial booked</option>
            <option value="joined">Joined</option>
            <option value="lost">Not interested</option>
          </Select>
          <Select
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value as EnquirySource | "")}
            className="max-w-[190px]"
          >
            <option value="">All channels</option>
            {ENQUIRY_SOURCES.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </div>

        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState />
        ) : !enquiries?.length ? (
          <EmptyState>No enquiries yet. Add the first one above.</EmptyState>
        ) : (
          <div className="no-scrollbar overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Name</th>
                  <th className={tableHeadCellClass}>Phone</th>
                  <th className={tableHeadCellClass}>Call on</th>
                  <th className={tableHeadCellClass}>Channel</th>
                  <th className={tableHeadCellClass}>Status</th>
                  <th className={tableHeadCellClass}>Last called</th>
                  <th className={tableHeadCellClass} />
                </tr>
              </thead>
              <motion.tbody initial="hidden" animate="visible" variants={staggerContainer(0.03)}>
                {enquiries.map((e) => (
                  <Fragment key={e.id}>
                  <motion.tr variants={fadeUp} className={tableRowClass}>
                    <td className={tableCellClass}>
                      <span className="text-[var(--color-text)]">{e.name}</span>
                      {e.notes && (
                        <span className="block text-xs text-[var(--color-text-muted)]">
                          {e.notes}
                        </span>
                      )}
                    </td>
                    <td className={tableCellClass}>
                      <a
                        href={`tel:${e.phone.replace(/\s/g, "")}`}
                        className="hover:text-[var(--color-accent)]"
                      >
                        {e.phone}
                      </a>
                    </td>
                    <td className={tableCellClass}>
                      <WhenLabel enquiry={e} />
                    </td>
                    <td className={tableCellClass}>
                      {e.source_name}
                      {e.interested_in_name && (
                        <span className="block text-xs text-[var(--color-text-muted)]">
                          wants {e.interested_in_name}
                        </span>
                      )}
                    </td>
                    <td className={tableCellClass}>
                      <StatusPill status={e.status} />
                    </td>
                    <td className={tableCellClass}>
                      {e.last_contacted_on
                        ? new Date(e.last_contacted_on).toLocaleDateString()
                        : "-"}
                    </td>
                    <td className={`${tableCellClass} flex flex-wrap gap-2`}>
                      {e.status === "open" && (
                        <Button
                          variant="secondary"
                          onClick={() => called.mutate({ id: e.id })}
                          disabled={called.isPending}
                        >
                          Called
                        </Button>
                      )}
                      {e.status === "open" && (
                        <Button
                          variant="secondary"
                          onClick={() => setStatus.mutate({ id: e.id, status: "trial" })}
                        >
                          Trial booked
                        </Button>
                      )}
                      <Button
                        variant="secondary"
                        onClick={() => setOpenRow(openRow === e.id ? null : e.id)}
                      >
                        {openRow === e.id ? "Close" : "Open"}
                      </Button>
                      <Button variant="danger" onClick={() =>
                        askConfirm({
                          title: `Delete the enquiry from ${e.name}?`,
                          consequence: "Their call history and notes go with it.",
                          run: () => remove.mutate(e.id),
                        })
                      }>
                        Delete
                      </Button>
                    </td>
                  </motion.tr>
                  {openRow === e.id && (
                    <tr>
                      <td colSpan={7} className="px-3 pb-3">
                        <LeadDetail enquiry={e} />
                      </td>
                    </tr>
                  )}
                  </Fragment>
                ))}
              </motion.tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
