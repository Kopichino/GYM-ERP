import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { fetchInstructors } from "../api/instructors";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader } from "../components/ui";
import { fadeUp, staggerContainer } from "../lib/motion";

export default function InstructorsPage() {
  const { data: instructors, isLoading, isError } = useQuery({
    queryKey: ["instructors"],
    queryFn: fetchInstructors,
  });
  const active = instructors?.filter((i) => i.active) ?? [];

  return (
    <div>
      <PageHeader title="Instructors" subtitle="Meet the team." />
      {isLoading ? (
        <LoadingState />
      ) : isError ? (
        <ErrorState />
      ) : active.length === 0 ? (
        <EmptyState>No instructors listed yet.</EmptyState>
      ) : (
        <motion.div
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
          initial="hidden"
          animate="visible"
          variants={staggerContainer()}
        >
          {active.map((instructor) => (
            <motion.div key={instructor.id} variants={fadeUp} whileHover={{ y: -4 }}>
              <Card className="h-full text-center">
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
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  );
}
