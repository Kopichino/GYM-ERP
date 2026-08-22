import { useQuery } from "@tanstack/react-query";
import { fetchInstructors } from "../api/instructors";
import { Card, PageHeader } from "../components/ui";

export default function InstructorsPage() {
  const { data: instructors } = useQuery({ queryKey: ["instructors"], queryFn: fetchInstructors });

  return (
    <div>
      <PageHeader title="Instructors" subtitle="Meet the team." />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {instructors
          ?.filter((i) => i.active)
          .map((instructor) => (
            <Card key={instructor.id} className="text-center">
              <div className="mx-auto mb-3 h-20 w-20 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
                {instructor.photo && (
                  <img src={instructor.photo} alt={instructor.name} className="h-full w-full object-cover" />
                )}
              </div>
              <h2 className="font-semibold text-[var(--color-text)]">{instructor.name}</h2>
              <p className="mb-2 text-xs uppercase tracking-wide text-[var(--color-accent)]">
                {instructor.specialty}
              </p>
              <p className="text-sm text-[var(--color-text-muted)]">{instructor.bio}</p>
            </Card>
          ))}
        {instructors?.length === 0 && (
          <p className="text-sm text-[var(--color-text-muted)]">No instructors listed yet.</p>
        )}
      </div>
    </div>
  );
}
