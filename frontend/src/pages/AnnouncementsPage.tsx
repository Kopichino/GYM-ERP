import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { fetchAnnouncements } from "../api/announcements";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader } from "../components/ui";
import { fadeUp, staggerContainer } from "../lib/motion";

export default function AnnouncementsPage() {
  const { data: announcements, isLoading, isError } = useQuery({
    queryKey: ["announcements"],
    queryFn: fetchAnnouncements,
  });

  return (
    <div>
      <PageHeader title="Announcements" subtitle="Gym-wide notices from staff." />
      {isLoading ? (
        <LoadingState />
      ) : isError ? (
        <ErrorState />
      ) : announcements?.length === 0 ? (
        <EmptyState>No announcements yet.</EmptyState>
      ) : (
        <motion.div
          className="flex flex-col gap-4"
          initial="hidden"
          animate="visible"
          variants={staggerContainer()}
        >
          {announcements?.map((a) => (
            <motion.div key={a.id} variants={fadeUp}>
              <Card className={a.pinned ? "border-[var(--color-accent)]" : ""}>
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
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  );
}
