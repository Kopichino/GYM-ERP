import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { fetchGalleryPosts, uploadGalleryPost } from "../api/gallery";
import { Button, Card, ErrorText, Input, PageHeader } from "../components/ui";

export default function GalleryPage() {
  const queryClient = useQueryClient();
  const { data: posts } = useQuery({ queryKey: ["gallery"], queryFn: fetchGalleryPosts });
  const fileRef = useRef<HTMLInputElement>(null);
  const [caption, setCaption] = useState("");
  const [error, setError] = useState("");

  const upload = useMutation({
    mutationFn: (formData: FormData) => uploadGalleryPost(formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["gallery"] });
      setCaption("");
      if (fileRef.current) fileRef.current.value = "";
    },
    onError: () => setError("Upload failed -- check file type/size (images or short video, max 20MB)."),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    const mediaType = file.type.startsWith("video") ? "video" : "image";
    const formData = new FormData();
    formData.append("media", file);
    formData.append("media_type", mediaType);
    formData.append("caption", caption);
    upload.mutate(formData);
  }

  return (
    <div>
      <PageHeader title="Community Gallery" subtitle="Share your gym moments." />
      <Card className="mb-6">
        <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Photo or video</label>
            <input
              ref={fileRef}
              type="file"
              accept="image/*,video/*"
              className="w-full text-sm text-[var(--color-text-muted)]"
              required
            />
          </div>
          <Input
            placeholder="Caption (optional)"
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
            className="sm:max-w-xs"
          />
          <Button type="submit" disabled={upload.isPending}>
            {upload.isPending ? "Uploading..." : "Upload"}
          </Button>
        </form>
        <ErrorText>{error}</ErrorText>
        <p className="mt-2 text-xs text-[var(--color-text-muted)]">
          Uploads are reviewed by an admin before appearing publicly.
        </p>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {posts?.map((post) => (
          <Card key={post.id} className="overflow-hidden p-0">
            <div className="relative aspect-square bg-[var(--color-surface-2)]">
              {post.media_type === "video" ? (
                <video src={post.media} controls className="h-full w-full object-cover" />
              ) : (
                <img src={post.media} alt={post.caption} className="h-full w-full object-cover" />
              )}
              {!post.approved && (
                <span className="absolute right-2 top-2 rounded bg-black/70 px-2 py-1 text-xs text-[var(--color-accent-2)]">
                  Pending review
                </span>
              )}
            </div>
            <div className="p-3">
              <p className="text-sm text-[var(--color-text)]">{post.caption}</p>
              <p className="text-xs text-[var(--color-text-muted)]">{post.uploader_name || "Gym"}</p>
            </div>
          </Card>
        ))}
        {posts?.length === 0 && <p className="text-sm text-[var(--color-text-muted)]">No posts yet -- be the first!</p>}
      </div>
    </div>
  );
}
