import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { approveGalleryPost, deleteGalleryPost, fetchGalleryPosts } from "../../api/gallery";
import { Button, Card, ErrorState, LoadingState } from "../../components/ui";
import { railColor } from "../../lib/theme";
import { askConfirm } from "../../store/confirmStore";

export default function AdminGalleryPage() {
  const queryClient = useQueryClient();
  const { data: posts, isLoading, isError } = useQuery({ queryKey: ["gallery"], queryFn: fetchGalleryPosts });

  const approve = useMutation({
    mutationFn: (id: number) => approveGalleryPost(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["gallery"] }),
  });
  const remove = useMutation({
    mutationFn: (id: number) => deleteGalleryPost(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["gallery"] }),
  });

  const pending = posts?.filter((p) => !p.approved) ?? [];
  const approved = posts?.filter((p) => p.approved) ?? [];

  if (isLoading) {
    return (
      <Card accent={railColor(0)}>
        <LoadingState />
      </Card>
    );
  }
  if (isError) {
    return (
      <Card accent={railColor(1)}>
        <ErrorState />
      </Card>
    );
  }

  return (
    <div>
      <Card accent={railColor(2)} className="mb-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Pending review ({pending.length})
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {pending.map((post) => (
            <div key={post.id} className="overflow-hidden rounded-lg border border-[var(--color-border)]">
              <div className="aspect-square bg-[var(--color-surface-2)]">
                {post.media_type === "video" ? (
                  <video src={post.media} controls className="h-full w-full object-cover" />
                ) : (
                  <img src={post.media} alt={post.caption} className="h-full w-full object-cover" />
                )}
              </div>
              <div className="flex gap-2 p-2">
                <Button
                  variant="success"
                  onClick={() => approve.mutate(post.id)}
                  className="flex-1 px-2 py-1 text-xs"
                >
                  Approve
                </Button>
                <Button
                  variant="danger"
                  onClick={() =>
                    askConfirm({
                      title: "Reject this photo?",
                      consequence: `${post.uploader_name || "The member"} will not be told why, and the upload is deleted.`,
                      confirmLabel: "Reject",
                      run: () => remove.mutate(post.id),
                    })
                  }
                  className="flex-1 px-2 py-1 text-xs"
                >
                  Reject
                </Button>
              </div>
            </div>
          ))}
          {pending.length === 0 && <p className="text-sm text-[var(--color-text-muted)]">Nothing pending.</p>}
        </div>
      </Card>

      <Card accent={railColor(3)}>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Approved ({approved.length})
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {approved.map((post) => (
            <div key={post.id} className="overflow-hidden rounded-lg border border-[var(--color-border)]">
              <div className="aspect-square bg-[var(--color-surface-2)]">
                {post.media_type === "video" ? (
                  <video src={post.media} controls className="h-full w-full object-cover" />
                ) : (
                  <img src={post.media} alt={post.caption} className="h-full w-full object-cover" />
                )}
              </div>
              <div className="p-2">
                <Button
                  variant="danger"
                  onClick={() =>
                    askConfirm({
                      title: "Remove this photo from the gallery?",
                      consequence: "It is already public; removing it deletes the upload.",
                      run: () => remove.mutate(post.id),
                    })
                  }
                  className="w-full px-2 py-1 text-xs"
                >
                  Remove
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
