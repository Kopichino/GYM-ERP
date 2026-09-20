import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";
import { fetchMembers } from "../../api/admin";
import { createUser, deleteUser, fetchUsers, updateUser } from "../../api/users";
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
import MfaResetCell from "../../components/MfaResetCell";
import { fadeUp, staggerContainer } from "../../lib/motion";
import { railColor } from "../../lib/theme";
import { askConfirm } from "../../store/confirmStore";

const emptyForm = { username: "", email: "", first_name: "", last_name: "", password: "" };

export default function AdminTrainersPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");

  const { data: trainers, isLoading, isError } = useQuery({
    queryKey: ["admin", "trainers"],
    queryFn: () => fetchUsers("trainer"),
  });
  const { data: members } = useQuery({ queryKey: ["admin", "members"], queryFn: fetchMembers });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["admin"] });
  }

  const addTrainer = useMutation({
    mutationFn: () => createUser({ ...form, role: "trainer" }),
    onSuccess: () => {
      setForm(emptyForm);
      setError("");
      invalidate();
    },
    onError: (err: { response?: { data?: Record<string, string[]> } }) => {
      const data = err.response?.data;
      const first = data && Object.entries(data)[0];
      setError(first ? `${first[0]}: ${first[1]}` : "Could not create that trainer.");
    },
  });

  const assign = useMutation({
    mutationFn: ({ memberId, trainerId }: { memberId: number; trainerId: number | null }) =>
      updateUser(memberId, { trainer: trainerId }),
    onSuccess: invalidate,
  });

  const removeTrainer = useMutation({
    mutationFn: (id: number) => deleteUser(id),
    onSuccess: invalidate,
  });

  return (
    <div className="flex flex-col gap-6">
      <Card accent={railColor(0)}>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Add a trainer
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Input
            placeholder="Username"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
          />
          <Input
            type="email"
            placeholder="Email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <Input
            placeholder="First name"
            value={form.first_name}
            onChange={(e) => setForm({ ...form, first_name: e.target.value })}
          />
          <Input
            placeholder="Last name"
            value={form.last_name}
            onChange={(e) => setForm({ ...form, last_name: e.target.value })}
          />
          <Input
            type="password"
            placeholder="Password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </div>
        <div className="mt-3 flex items-center gap-3">
          <Button
            onClick={() => addTrainer.mutate()}
            disabled={!form.username || !form.email || addTrainer.isPending}
          >
            {addTrainer.isPending ? "Adding..." : "Add trainer"}
          </Button>
          <ErrorText>{error}</ErrorText>
        </div>
      </Card>

      <Card accent={railColor(1)}>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {trainers?.length ?? 0} trainers
        </h2>
        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState />
        ) : trainers?.length === 0 ? (
          <EmptyState>No trainers yet.</EmptyState>
        ) : (
          <div className="no-scrollbar overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Username</th>
                  <th className={tableHeadCellClass}>Name</th>
                  <th className={tableHeadCellClass}>Email</th>
                  <th className={tableHeadCellClass}>Members</th>
                  <th className={tableHeadCellClass}>Two-step sign-in</th>
                  <th className={tableHeadCellClass} />
                </tr>
              </thead>
              <motion.tbody initial="hidden" animate="visible" variants={staggerContainer(0.03)}>
                {trainers?.map((t) => (
                  <motion.tr key={t.id} variants={fadeUp} className={tableRowClass}>
                    <td className={tableCellClass}>{t.username}</td>
                    <td className={tableCellClass}>
                      {`${t.first_name} ${t.last_name}`.trim() || "-"}
                    </td>
                    <td className={tableCellClass}>{t.email}</td>
                    <td className={tableCellClass}>
                      {members?.filter((m) => m.trainer === t.id).length ?? 0}
                    </td>
                    <td className={tableCellClass}>
                      <MfaResetCell
                        userId={t.id}
                        name={`${t.first_name} ${t.last_name}`.trim() || t.username}
                        hasMfa={t.has_mfa}
                      />
                    </td>
                    <td className={tableCellClass}>
                      <Button
                        variant="danger"
                        onClick={() =>
                        askConfirm({
                          title: `Remove ${[t.first_name, t.last_name].filter(Boolean).join(" ") || t.username}?`,
                          consequence: "Their assigned members become unassigned.",
                          run: () => removeTrainer.mutate(t.id),
                        })
                      }
                        disabled={removeTrainer.isPending}
                      >
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
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Assign members to trainers
        </h2>
        {!members?.length ? (
          <EmptyState>No members yet.</EmptyState>
        ) : (
          <div className="no-scrollbar overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Member</th>
                  <th className={tableHeadCellClass}>Email</th>
                  <th className={tableHeadCellClass}>Assigned trainer</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.id} className={tableRowClass}>
                    <td className={tableCellClass}>{m.username}</td>
                    <td className={tableCellClass}>{m.email}</td>
                    <td className={tableCellClass}>
                      <Select
                        value={m.trainer ?? ""}
                        onChange={(e) =>
                          assign.mutate({
                            memberId: m.id,
                            trainerId: e.target.value ? Number(e.target.value) : null,
                          })
                        }
                        className="max-w-xs"
                      >
                        <option value="">-- none --</option>
                        {trainers?.map((t) => (
                          <option key={t.id} value={t.id}>
                            {`${t.first_name} ${t.last_name}`.trim() || t.username}
                          </option>
                        ))}
                      </Select>
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
