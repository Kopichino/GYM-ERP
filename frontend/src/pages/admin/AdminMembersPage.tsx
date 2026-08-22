import { useQuery } from "@tanstack/react-query";
import { downloadMembersExcel, fetchMembers } from "../../api/admin";
import { Button, Card } from "../../components/ui";

export default function AdminMembersPage() {
  const { data: members, isLoading } = useQuery({ queryKey: ["admin", "members"], queryFn: fetchMembers });

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {members?.length ?? 0} members
        </h2>
        <Button onClick={() => downloadMembersExcel()}>Download as Excel</Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-[var(--color-text-muted)]">
            <tr className="border-b border-[var(--color-border)]">
              <th className="py-2 pr-4">Username</th>
              <th className="py-2 pr-4">Email</th>
              <th className="py-2 pr-4">Phone</th>
              <th className="py-2 pr-4">Status</th>
              <th className="py-2 pr-4">Joined</th>
              <th className="py-2 pr-4">Last check-in</th>
            </tr>
          </thead>
          <tbody>
            {members?.map((m) => (
              <tr key={m.id} className="border-b border-[var(--color-border)] text-[var(--color-text)] last:border-none">
                <td className="py-2 pr-4">{m.username}</td>
                <td className="py-2 pr-4">{m.email}</td>
                <td className="py-2 pr-4">{m.phone || "-"}</td>
                <td className="py-2 pr-4 capitalize">{m.membership_status || "-"}</td>
                <td className="py-2 pr-4">{m.join_date}</td>
                <td className="py-2 pr-4">
                  {m.last_check_in ? new Date(m.last_check_in).toLocaleString() : "Never"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {isLoading && <p className="py-4 text-sm text-[var(--color-text-muted)]">Loading...</p>}
        {members?.length === 0 && <p className="py-4 text-sm text-[var(--color-text-muted)]">No members yet.</p>}
      </div>
    </Card>
  );
}
