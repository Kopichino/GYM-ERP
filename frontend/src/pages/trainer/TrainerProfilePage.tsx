import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fetchMyInstructorProfile, updateMyInstructorProfile } from "../../api/instructors";
import {
  Button,
  Card,
  EmptyState,
  ErrorText,
  Input,
  LoadingState,
  PageHeader,
  Textarea,
} from "../../components/ui";

export default function TrainerProfilePage() {
  const queryClient = useQueryClient();
  const [photo, setPhoto] = useState<File | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const { data: profile, isLoading, isError } = useQuery({
    queryKey: ["trainer", "profile"],
    queryFn: fetchMyInstructorProfile,
    retry: false,
  });

  // Only the fields the trainer has actually typed into are held in state; the
  // rest derive from the server copy on each render. Copying the whole profile
  // into state from an effect meant every load rendered twice -- once empty,
  // once populated -- and a refetch could clobber unsaved edits.
  type Field = "name" | "specialty" | "bio";
  const [edits, setEdits] = useState<Partial<Record<Field, string>>>({});

  const name = edits.name ?? profile?.name ?? "";
  const specialty = edits.specialty ?? profile?.specialty ?? "";
  const bio = edits.bio ?? profile?.bio ?? "";

  const edit = (field: Field) => (e: { target: { value: string } }) =>
    setEdits((prev) => ({ ...prev, [field]: e.target.value }));

  const save = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("name", name);
      form.append("specialty", specialty);
      form.append("bio", bio);
      if (photo) form.append("photo", photo);
      return updateMyInstructorProfile(form);
    },
    onSuccess: () => {
      setSaved(true);
      setError("");
      setPhoto(null);
      setEdits({});
      queryClient.invalidateQueries({ queryKey: ["trainer", "profile"] });
      queryClient.invalidateQueries({ queryKey: ["instructors"] });
    },
    onError: () => setError("Could not save your profile."),
  });

  return (
    <div>
      <PageHeader title="My Profile" subtitle="How members see you on the instructors page." />
      <Card>
        {isLoading ? (
          <LoadingState />
        ) : isError || !profile ? (
          <EmptyState>
            No instructor profile is linked to your account yet. Ask an admin to create one.
          </EmptyState>
        ) : (
          <div className="flex flex-col gap-3">
            {profile.photo && (
              <img
                src={profile.photo}
                alt={profile.name}
                className="h-24 w-24 rounded-full object-cover"
              />
            )}
            <label className="text-xs text-[var(--color-text-muted)]">
              Display name
              <Input value={name} onChange={edit("name")} className="mt-1" />
            </label>
            <label className="text-xs text-[var(--color-text-muted)]">
              Specialty
              <Input
                value={specialty}
                onChange={edit("specialty")}
                className="mt-1"
              />
            </label>
            <label className="text-xs text-[var(--color-text-muted)]">
              Bio
              <Textarea rows={4} value={bio} onChange={edit("bio")} className="mt-1" />
            </label>
            <label className="text-xs text-[var(--color-text-muted)]">
              Photo
              <input
                type="file"
                accept="image/*"
                onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
                className="mt-1 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm text-[var(--color-text)] file:mr-3 file:rounded file:border-0 file:bg-[var(--color-accent)] file:px-3 file:py-1 file:text-sm file:font-semibold file:text-white"
              />
            </label>
            <div className="flex items-center gap-3">
              <Button
                onClick={() => {
                  setSaved(false);
                  save.mutate();
                }}
                disabled={save.isPending}
              >
                {save.isPending ? "Saving..." : "Save profile"}
              </Button>
              {saved && <span className="text-sm text-[var(--color-text-muted)]">Saved.</span>}
              <ErrorText>{error}</ErrorText>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
