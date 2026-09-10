import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";
import {
  deleteDevice,
  fetchDeviceEvents,
  fetchDevices,
  registerDevice,
  reprocessEvent,
  rotateDeviceKey,
  DEVICE_KINDS,
  type DeviceKind,
  type EventOutcome,
} from "../../api/devices";
import { fetchMembers } from "../../api/admin";
import { updateUser } from "../../api/users";
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

const OUTCOME_COLOR: Record<EventOutcome, string> = {
  checked_in: "#22c55e",
  checked_out: "#4f8dfd",
  unmatched: "#ff3d5a",
  // A refusal is amber rather than red: the system working as intended, not a
  // fault -- but still the row the front desk should look at.
  denied: "#ffb020",
  duplicate: "#9494a8",
  failed: "#ff3d5a",
  pending: "#ffb020",
};

const emptyForm = {
  name: "",
  serial: "",
  location: "",
  kind: "terminal" as DeviceKind,
  grace_days: "0",
};

/** The key is shown once and never again, so it gets its own visible callout
 *  rather than a toast that can be missed. */
function KeyCallout({ apiKey, onDismiss }: { apiKey: string; onDismiss: () => void }) {
  return (
    <div className="mt-4 rounded-lg border border-[var(--color-accent-2)] bg-[var(--color-surface-2)] p-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-accent-2)]">
        Device key — copy it now
      </p>
      <p className="mb-3 break-all font-mono text-sm text-[var(--color-text)]">{apiKey}</p>
      <p className="mb-3 text-xs text-[var(--color-text-muted)]">
        This is the only time it is shown. Set it on the terminal as the
        <code className="mx-1 rounded bg-[var(--color-bg)] px-1">X-Device-Key</code>
        header. If it's lost, rotate the key rather than looking it up.
      </p>
      <Button variant="secondary" onClick={onDismiss}>
        Done
      </Button>
    </div>
  );
}

export default function AdminDevicesPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(emptyForm);
  const [newKey, setNewKey] = useState("");
  const [error, setError] = useState("");
  const [outcome, setOutcome] = useState<EventOutcome | "">("");
  const [enrolling, setEnrolling] = useState<Record<number, string>>({});

  const { data: devices, isLoading, isError } = useQuery({
    queryKey: ["admin", "devices"],
    queryFn: fetchDevices,
  });
  const { data: events } = useQuery({
    queryKey: ["admin", "device-events", outcome],
    queryFn: () => fetchDeviceEvents(outcome ? { outcome } : undefined),
  });
  const { data: members } = useQuery({ queryKey: ["admin", "members"], queryFn: fetchMembers });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin"] });

  const add = useMutation({
    mutationFn: () =>
      registerDevice({
        ...form,
        grace_days: Number(form.grace_days) || 0,
      }),
    onSuccess: (device) => {
      setNewKey(device.api_key);
      setForm(emptyForm);
      setError("");
      invalidate();
    },
    onError: (err: { response?: { data?: Record<string, string[]> } }) => {
      const first = err.response?.data && Object.entries(err.response.data)[0];
      setError(first ? `${first[0]}: ${first[1]}` : "Could not register that device.");
    },
  });

  const rotate = useMutation({
    mutationFn: rotateDeviceKey,
    onSuccess: (data) => {
      setNewKey(data.api_key);
      invalidate();
    },
  });
  const remove = useMutation({ mutationFn: deleteDevice, onSuccess: invalidate });
  const replay = useMutation({ mutationFn: reprocessEvent, onSuccess: invalidate });
  const enrol = useMutation({
    mutationFn: ({ id, biometric_id }: { id: number; biometric_id: string }) =>
      updateUser(id, { biometric_id }),
    onSuccess: invalidate,
  });

  const unmatchedCount = events?.filter((e) => e.outcome === "unmatched").length ?? 0;
  const deniedCount = events?.filter((e) => e.outcome === "denied").length ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <Card accent={railColor(0)}>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Register a terminal
        </h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <Input
            placeholder="Name (e.g. Front door)"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <Input
            placeholder="Serial number"
            value={form.serial}
            onChange={(e) => setForm({ ...form, serial: e.target.value })}
          />
          <Input
            placeholder="Location (optional)"
            value={form.location}
            onChange={(e) => setForm({ ...form, location: e.target.value })}
          />
          <label className="text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
            What it does
            <Select
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value as DeviceKind })}
              className="mt-1"
            >
              {DEVICE_KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </Select>
          </label>
          {/* Only a gate can turn anyone away, so the grace period only means
              anything for one. */}
          {form.kind !== "terminal" && (
            <label className="text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
              Grace days after expiry
              <Input
                type="number"
                min={0}
                value={form.grace_days}
                onChange={(e) => setForm({ ...form, grace_days: e.target.value })}
                className="mt-1"
              />
            </label>
          )}
        </div>
        <p className="mt-3 max-w-prose text-sm text-[var(--color-text-muted)]">
          An attendance terminal only records visits and never refuses anyone. A turnstile or
          door lock asks before it opens, and the answer comes from the same membership status
          the rest of the system uses — so paying at the desk opens the gate on the very next
          swipe, with nothing to synchronise.
        </p>
        <div className="mt-3 flex items-center gap-3">
          <Button onClick={() => add.mutate()} disabled={!form.name || !form.serial || add.isPending}>
            {add.isPending ? "Registering..." : "Register device"}
          </Button>
          <ErrorText>{error}</ErrorText>
        </div>
        {newKey && <KeyCallout apiKey={newKey} onDismiss={() => setNewKey("")} />}
      </Card>

      <Card accent={railColor(1)}>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {devices?.length ?? 0} devices
        </h2>
        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState />
        ) : !devices?.length ? (
          <EmptyState>No terminals registered yet.</EmptyState>
        ) : (
          <div className="no-scrollbar overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Name</th>
                  <th className={tableHeadCellClass}>Does</th>
                  <th className={tableHeadCellClass}>Serial</th>
                  <th className={tableHeadCellClass}>Location</th>
                  <th className={tableHeadCellClass}>Last seen</th>
                  <th className={tableHeadCellClass}>Punches</th>
                  <th className={tableHeadCellClass} />
                </tr>
              </thead>
              <motion.tbody initial="hidden" animate="visible" variants={staggerContainer(0.03)}>
                {devices.map((d) => (
                  <motion.tr key={d.id} variants={fadeUp} className={tableRowClass}>
                    <td className={tableCellClass}>{d.name}</td>
                    <td className={tableCellClass}>
                      {d.kind_name}
                      {/* Only a gate can turn anyone away, so the grace period
                          is only worth showing on one. */}
                      {d.kind !== "terminal" && (
                        <span className="block text-[11px] text-[var(--color-text-muted)]">
                          {d.grace_days > 0
                            ? `${d.grace_days}d grace after expiry`
                            : "no grace after expiry"}
                        </span>
                      )}
                    </td>
                    <td className={`${tableCellClass} font-mono text-xs`}>{d.serial}</td>
                    <td className={tableCellClass}>{d.location || "-"}</td>
                    <td className={tableCellClass}>
                      {d.last_seen_at ? (
                        new Date(d.last_seen_at).toLocaleString()
                      ) : (
                        <span style={{ color: "var(--color-accent-2)" }}>Never</span>
                      )}
                    </td>
                    <td className={tableCellClass}>{d.event_count}</td>
                    <td className={`${tableCellClass} flex gap-2`}>
                      <Button variant="secondary" onClick={() => rotate.mutate(d.id)}>
                        Rotate key
                      </Button>
                      <Button variant="danger" onClick={() =>
                        askConfirm({
                          title: `Remove "${d.name}"?`,
                          consequence: "The terminal will stop being able to record visits until it is registered again.",
                          run: () => remove.mutate(d.id),
                        })
                      }>
                        Remove
                      </Button>
                    </td>
                  </motion.tr>
                ))}
              </motion.tbody>
            </table>
          </div>
        )}
      </Card>

      <Card accent={railColor(2)}>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Biometric enrolment
        </h2>
        <p className="mb-4 text-sm text-[var(--color-text-muted)]">
          The id a member is enrolled under on the terminal. A punch with no matching id is
          kept and can be replayed once the id is set here.
        </p>
        {!members?.length ? (
          <EmptyState>No members yet.</EmptyState>
        ) : (
          <div className="no-scrollbar overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Member</th>
                  <th className={tableHeadCellClass}>Biometric id</th>
                  <th className={tableHeadCellClass} />
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.id} className={tableRowClass}>
                    <td className={tableCellClass}>{m.username}</td>
                    <td className={tableCellClass}>
                      <Input
                        placeholder="Not enrolled"
                        // Falls back to the saved id so the column shows who is
                        // already enrolled, not just what's been typed.
                        value={enrolling[m.id] ?? m.biometric_id ?? ""}
                        onChange={(e) => setEnrolling({ ...enrolling, [m.id]: e.target.value })}
                        className="max-w-[180px]"
                      />
                    </td>
                    <td className={tableCellClass}>
                      <Button
                        variant="secondary"
                        disabled={
                          enrolling[m.id] === undefined ||
                          enrolling[m.id] === (m.biometric_id ?? "") ||
                          enrol.isPending
                        }
                        onClick={() =>
                          enrol.mutate({ id: m.id, biometric_id: enrolling[m.id] })
                        }
                      >
                        Save
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card accent={railColor(3)}>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Punch log
            {unmatchedCount > 0 && (
              <span className="ml-2" style={{ color: "var(--color-accent)" }}>
                {unmatchedCount} unmatched
              </span>
            )}
            {deniedCount > 0 && (
              <span className="ml-2" style={{ color: OUTCOME_COLOR.denied }}>
                {deniedCount} refused
              </span>
            )}
          </h2>
          <Select
            value={outcome}
            onChange={(e) => setOutcome(e.target.value as EventOutcome | "")}
            className="max-w-[200px]"
          >
            <option value="">All outcomes</option>
            <option value="checked_in">Checked in</option>
            <option value="checked_out">Checked out</option>
            <option value="unmatched">Unmatched</option>
            <option value="denied">Refused entry</option>
            <option value="duplicate">Duplicate</option>
            <option value="failed">Failed</option>
          </Select>
        </div>

        {!events?.length ? (
          <EmptyState>No punches recorded yet.</EmptyState>
        ) : (
          <div className="no-scrollbar overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Time</th>
                  <th className={tableHeadCellClass}>Device</th>
                  <th className={tableHeadCellClass}>Biometric id</th>
                  <th className={tableHeadCellClass}>Member</th>
                  <th className={tableHeadCellClass}>Outcome</th>
                  <th className={tableHeadCellClass} />
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id} className={tableRowClass}>
                    <td className={tableCellClass}>{new Date(e.event_time).toLocaleString()}</td>
                    <td className={tableCellClass}>{e.device_name}</td>
                    <td className={`${tableCellClass} font-mono text-xs`}>{e.biometric_id}</td>
                    <td className={tableCellClass}>{e.member_name ?? "-"}</td>
                    <td className={tableCellClass}>
                      <span style={{ color: OUTCOME_COLOR[e.outcome] }}>
                        {e.outcome.replace("_", " ")}
                      </span>
                      {e.detail && (
                        <span className="block text-xs text-[var(--color-text-muted)]">
                          {e.detail}
                        </span>
                      )}
                    </td>
                    <td className={tableCellClass}>
                      {e.outcome === "unmatched" && (
                        <Button
                          variant="secondary"
                          onClick={() => replay.mutate(e.id)}
                          disabled={replay.isPending}
                        >
                          Replay
                        </Button>
                      )}
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
