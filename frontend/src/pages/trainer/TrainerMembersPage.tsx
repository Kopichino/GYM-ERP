import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { fetchMyMembers } from "../../api/users";
import {
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "../../components/ui";
import { fadeUp, staggerContainer } from "../../lib/motion";

export default function TrainerMembersPage() {
  const { data: members, isLoading, isError } = useQuery({
    queryKey: ["trainer", "members"],
    queryFn: fetchMyMembers,
  });

  return (
    <div>
      <PageHeader title="My Members" subtitle="The members assigned to you." />
      <Card>
        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState />
        ) : !members?.length ? (
          <EmptyState>No members assigned to you yet.</EmptyState>
        ) : (
          <div className="no-scrollbar overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Name</th>
                  <th className={tableHeadCellClass}>Username</th>
                  <th className={tableHeadCellClass}>Phone</th>
                  <th className={tableHeadCellClass}>Status</th>
                  <th className={tableHeadCellClass}>Last check-in</th>
                </tr>
              </thead>
              <motion.tbody initial="hidden" animate="visible" variants={staggerContainer(0.03)}>
                {members.map((m) => (
                  <motion.tr key={m.id} variants={fadeUp} className={tableRowClass}>
                    <td className={tableCellClass}>
                      <Link
                        to={`/trainer/members/${m.id}`}
                        className="text-[var(--color-text)] hover:text-[var(--color-accent)]"
                      >
                        {`${m.first_name} ${m.last_name}`.trim() || m.username}
                      </Link>
                    </td>
                    <td className={tableCellClass}>{m.username}</td>
                    <td className={tableCellClass}>{m.phone || "-"}</td>
                    <td className={`${tableCellClass} capitalize`}>{m.membership_status || "-"}</td>
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
    </div>
  );
}
