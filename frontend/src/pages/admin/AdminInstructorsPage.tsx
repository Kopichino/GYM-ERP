import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { createInstructor, deleteInstructor, fetchInstructors } from "../../api/instructors";
import { Button, Card, Input, Textarea } from "../../components/ui";

export default function AdminInstructorsPage() {
  const queryClient = useQueryClient();
  const { data: instructors } = useQuery({ queryKey: ["instructors"], queryFn: fetchInstructors });
  const [name, setName] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [bio, setBio] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const create = useMutation({
    mutationFn: () => {
      const formData = new FormData();
      formData.append("name", name);
      formData.append("specialty", specialty);
      formData.append("bio", bio);
      formData.append("active", "true");
      const file = fileRef.current?.files?.[0];
      if (file) formData.append("photo", file);
      return createInstructor(formData);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["instructors"] });
      setName("");
      setSpecialty("");
      setBio("");
      if (fileRef.current) fileRef.current.value = "";
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => deleteInstructor(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["instructors"] }),
  });

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Add instructor
        </h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
          className="flex flex-col gap-3"
        >
          <Input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
          <Input placeholder="Specialty" value={specialty} onChange={(e) => setSpecialty(e.target.value)} />
          <Textarea placeholder="Bio" rows={3} value={bio} onChange={(e) => setBio(e.target.value)} />
          <input ref={fileRef} type="file" accept="image/*" className="text-sm text-[var(--color-text-muted)]" />
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? "Saving..." : "Add instructor"}
          </Button>
        </form>
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Current instructors
        </h2>
        <ul className="flex flex-col gap-2">
          {instructors?.map((i) => (
            <li key={i.id} className="flex items-center justify-between border-b border-[var(--color-border)] py-2">
              <span className="text-sm text-[var(--color-text)]">{i.name}</span>
              <Button variant="danger" onClick={() => remove.mutate(i.id)} className="px-2 py-1 text-xs">
                Delete
              </Button>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
