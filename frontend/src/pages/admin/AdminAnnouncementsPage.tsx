import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createAnnouncement, deleteAnnouncement, fetchAnnouncements } from "../../api/announcements";
import { Button, Card, EmptyState, ErrorState, Input, LoadingState, Textarea } from "../../components/ui";

export default function AdminAnnouncementsPage() {
  const queryClient = useQueryClient();
  const { data: announcements, isLoading, isError } = useQuery({
    queryKey: ["announcements"],
    queryFn: fetchAnnouncements,
  });
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [pinned, setPinned] = useState(false);

  const create = useMutation({
    mutationFn: () => createAnnouncement({ title, body, pinned }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["announcements"] });
      setTitle("");
      setBody("");
      setPinned(false);
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => deleteAnnouncement(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["announcements"] }),
  });

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          New announcement
        </h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
          className="flex flex-col gap-3"
        >
          <Input placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} required />
          <Textarea placeholder="Body" rows={4} value={body} onChange={(e) => setBody(e.target.value)} required />
          <label className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
            <input type="checkbox" checked={pinned} onChange={(e) => setPinned(e.target.checked)} />
            Pin to top
          </label>
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? "Posting..." : "Post announcement"}
          </Button>
        </form>
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Existing announcements
        </h2>
        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState />
        ) : announcements?.length === 0 ? (
          <EmptyState>No announcements yet.</EmptyState>
        ) : (
          <ul className="flex flex-col gap-2">
            {announcements?.map((a) => (
              <li key={a.id} className="flex items-center justify-between border-b border-[var(--color-border)] py-2">
                <span className="text-sm text-[var(--color-text)]">
                  {a.pinned && <span className="mr-1 text-[var(--color-accent)]">*</span>}
                  {a.title}
                </span>
                <Button variant="danger" onClick={() => remove.mutate(a.id)} className="px-2 py-1 text-xs">
                  Delete
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
