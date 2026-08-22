import { useQuery } from "@tanstack/react-query";
import { fetchClassSessions } from "../api/schedule";
import { Card, PageHeader } from "../components/ui";

export default function SchedulePage() {
  const { data: sessions } = useQuery({ queryKey: ["schedule"], queryFn: fetchClassSessions });

  return (
    <div>
      <PageHeader title="Upcoming Sessions" subtitle="Classes scheduled at the gym." />
      <div className="flex flex-col gap-3">
        {sessions?.map((s) => (
          <Card key={s.id} className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold text-[var(--color-text)]">{s.title}</h2>
              <p className="text-sm text-[var(--color-text-muted)]">
                {s.instructor_name ? `with ${s.instructor_name}` : ""}
              </p>
              {s.description && <p className="mt-1 text-sm text-[var(--color-text-muted)]">{s.description}</p>}
            </div>
            <div className="text-right text-sm text-[var(--color-text)]">
              <p>{new Date(s.date).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}</p>
              <p className="text-[var(--color-text-muted)]">
                {s.start_time.slice(0, 5)} - {s.end_time.slice(0, 5)}
              </p>
              {s.capacity != null && <p className="text-xs text-[var(--color-text-muted)]">Capacity: {s.capacity}</p>}
            </div>
          </Card>
        ))}
        {sessions?.length === 0 && <p className="text-sm text-[var(--color-text-muted)]">Nothing scheduled yet.</p>}
      </div>
    </div>
  );
}
