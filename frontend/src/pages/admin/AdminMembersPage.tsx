import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";
import {
  downloadMembersExcel,
  fetchMembers,
  setMemberPassword,
  type Member,
} from "../../api/admin";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  ghostButtonClass,
  Input,
  LoadingState,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "../../components/ui";
import MfaResetCell from "../../components/MfaResetCell";
import { fadeUp, staggerContainer } from "../../lib/motion";
import { statusColor, tint } from "../../lib/theme";

/**
 * Setting a member's password from the admin screen.
 *
 * Imported members are created without one, and a phone-only import has no
 * real email to receive a reset link at -- so for them this is the only way in.
 * The badge says who cannot log in yet, so an admin is not left guessing why a
 * member says the app will not let them.
 */
function PasswordCell({ member }: { member: Member }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  function close() {
    setOpen(false);
    setPassword("");
    setError("");
  }

  const save = useMutation({
    mutationFn: () => setMemberPassword(member.id, password),
    onSuccess: () => {
      close();
      setSaved(true);
      queryClient.invalidateQueries({ queryKey: ["admin", "members"] });
    },
    onError: (err: { response?: { data?: { password?: string[]; detail?: string } } }) => {
      const data = err.response?.data;
      setError(data?.password?.join(" ") || data?.detail || "Could not set that password.");
    },
  });

  if (open) {
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
        className="flex min-w-[260px] flex-col gap-1.5"
      >
        <div className="flex items-center gap-2">
          <Input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="New password"
            aria-label={`New password for ${member.username}`}
            className="h-8"
          />
          <Button
            type="submit"
            disabled={!password || save.isPending}
            className="px-3 py-1 text-xs"
          >
            {save.isPending ? "Saving..." : "Save"}
          </Button>
          <button type="button" onClick={close} className={ghostButtonClass}>
            Cancel
          </button>
        </div>
        <ErrorText>{error}</ErrorText>
      </form>
    );
  }

  return (
    <span className="flex items-center gap-2 whitespace-nowrap">
      {!member.has_password && (
        <span
          className="inline-block rounded-full px-2 py-1 text-[11px] font-semibold leading-none"
          style={{ color: statusColor("caution"), background: tint(statusColor("caution")) }}
        >
          No password
        </span>
      )}
      {saved && (
        <span className="text-xs" style={{ color: statusColor("positive") }}>
          Saved
        </span>
      )}
      <button
        type="button"
        onClick={() => {
          setOpen(true);
          setSaved(false);
        }}
        className={ghostButtonClass}
      >
        {member.has_password ? "Reset password" : "Set password"}
      </button>
    </span>
  );
}

export default function AdminMembersPage() {
  const { data: members, isLoading, isError } = useQuery({ queryKey: ["admin", "members"], queryFn: fetchMembers });
  const withoutPassword = (members ?? []).filter((m) => !m.has_password).length;

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {members?.length ?? 0} members
        </h2>
        <Button onClick={() => downloadMembersExcel()}>Download as Excel</Button>
      </div>
      {withoutPassword > 0 && (
        <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
          <b style={{ color: statusColor("caution") }}>{withoutPassword}</b>{" "}
          {withoutPassword === 1 ? "account has" : "accounts have"} no password yet, usually because
          {withoutPassword === 1 ? " it was" : " they were"} imported, so{" "}
          {withoutPassword === 1 ? "it cannot" : "they cannot"} log in. Set one here, or the member can
          use <b className="text-[var(--color-text)]">Forgot password</b> on the login page if their
          email is real.
        </p>
      )}
      {isLoading ? (
        <LoadingState />
      ) : isError ? (
        <ErrorState />
      ) : members?.length === 0 ? (
        <EmptyState>No members yet.</EmptyState>
      ) : (
        <div className="no-scrollbar overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-[var(--color-text-muted)]">
              <tr className={tableHeadRowClass}>
                <th className={tableHeadCellClass}>Username</th>
                <th className={tableHeadCellClass}>Email</th>
                <th className={tableHeadCellClass}>Phone</th>
                <th className={tableHeadCellClass}>Status</th>
                <th className={tableHeadCellClass}>Joined</th>
                <th className={tableHeadCellClass}>Last check-in</th>
                <th className={tableHeadCellClass}>Password</th>
                <th className={tableHeadCellClass}>Two-step sign-in</th>
              </tr>
            </thead>
            <motion.tbody initial="hidden" animate="visible" variants={staggerContainer(0.03)}>
              {members?.map((m) => (
                <motion.tr key={m.id} variants={fadeUp} className={tableRowClass}>
                  <td className={tableCellClass}>{m.username}</td>
                  <td className={tableCellClass}>{m.email}</td>
                  <td className={tableCellClass}>{m.phone || "-"}</td>
                  <td className={`${tableCellClass} capitalize`}>{m.membership_status || "-"}</td>
                  <td className={tableCellClass}>{m.join_date}</td>
                  <td className={tableCellClass}>
                    {m.last_check_in ? new Date(m.last_check_in).toLocaleString() : "Never"}
                  </td>
                  <td className={tableCellClass}>
                    <PasswordCell member={m} />
                  </td>
                  <td className={tableCellClass}>
                    <MfaResetCell
                      userId={m.id}
                      name={`${m.first_name} ${m.last_name}`.trim() || m.username}
                      hasMfa={m.has_mfa}
                    />
                  </td>
                </motion.tr>
              ))}
            </motion.tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
