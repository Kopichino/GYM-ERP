import { useQuery } from "@tanstack/react-query";
import { fetchAnnouncements } from "../api/announcements";
import { Card, PageHeader } from "../components/ui";

export default function AnnouncementsPage() {
  const { data: announcements, isLoading } = useQuery({
    queryKey: ["announcements"],
    queryFn: fetchAnnouncements,
  });

  return (
    <div>
      <PageHeader title="Announcements" subtitle="Gym-wide notices from staff." />
      <div className="flex flex-col gap-4">
        {isLoading && <p className="text-sm text-[var(--color-text-muted)]">Loading...</p>}
        {announcements?.map((a) => (
          <Card key={a.id} className={a.pinned ? "border-[var(--color-accent)]" : ""}>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="font-semibold text-[var(--color-text)]">
                {a.pinned && <span className="mr-2 text-[var(--color-accent)]">PINNED</span>}
                {a.title}
              </h2>
              <span className="text-xs text-[var(--color-text-muted)]">
                {new Date(a.created_at).toLocaleDateString()}
              </span>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">{a.body}</p>
          </Card>
        ))}
        {announcements?.length === 0 && (
          <p className="text-sm text-[var(--color-text-muted)]">No announcements yet.</p>
        )}
      </div>
    </div>
  );
}
