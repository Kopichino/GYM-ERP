import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { downloadMembersExcel, fetchMembers } from "../../api/admin";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "../../components/ui";
import { fadeUp, staggerContainer } from "../../lib/motion";

export default function AdminMembersPage() {
  const { data: members, isLoading, isError } = useQuery({ queryKey: ["admin", "members"], queryFn: fetchMembers });

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {members?.length ?? 0} members
        </h2>
        <Button onClick={() => downloadMembersExcel()}>Download as Excel</Button>
      </div>
      {isLoading ? (
        <LoadingState />
      ) : isError ? (
        <ErrorState />
      ) : members?.length === 0 ? (
        <EmptyState>No members yet.</EmptyState>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-[var(--color-text-muted)]">
              <tr className={tableHeadRowClass}>
                <th className={tableHeadCellClass}>Username</th>
                <th className={tableHeadCellClass}>Email</th>
                <th className={tableHeadCellClass}>Phone</th>
                <th className={tableHeadCellClass}>Status</th>
                <th className={tableHeadCellClass}>Joined</th>
                <th className={tableHeadCellClass}>Last check-in</th>
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
                </motion.tr>
              ))}
            </motion.tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
