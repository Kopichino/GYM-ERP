import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fetchInstructors } from "../../api/instructors";
import { createClassSession, deleteClassSession, fetchClassSessions } from "../../api/schedule";
import { Button, Card, Input, Select } from "../../components/ui";

export default function AdminSchedulePage() {
  const queryClient = useQueryClient();
  const { data: sessions } = useQuery({ queryKey: ["schedule"], queryFn: fetchClassSessions });
  const { data: instructors } = useQuery({ queryKey: ["instructors"], queryFn: fetchInstructors });

  const [form, setForm] = useState({
    title: "",
    instructor: "",
    date: "",
    start_time: "",
    end_time: "",
    capacity: "",
    description: "",
  });

  const create = useMutation({
    mutationFn: () =>
      createClassSession({
        title: form.title,
        instructor: form.instructor ? Number(form.instructor) : null,
        date: form.date,
        start_time: form.start_time,
        end_time: form.end_time,
        capacity: form.capacity ? Number(form.capacity) : null,
        description: form.description,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedule"] });
      setForm({ title: "", instructor: "", date: "", start_time: "", end_time: "", capacity: "", description: "" });
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => deleteClassSession(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["schedule"] }),
  });

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Schedule a class
        </h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
          className="flex flex-col gap-3"
        >
          <Input
            placeholder="Title"
            value={form.title}
            onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            required
          />
          <Select
            value={form.instructor}
            onChange={(e) => setForm((f) => ({ ...f, instructor: e.target.value }))}
          >
            <option value="">No instructor</option>
            {instructors?.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </Select>
          <Input
            type="date"
            value={form.date}
            onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))}
            required
          />
          <div className="flex gap-3">
            <Input
              type="time"
              value={form.start_time}
              onChange={(e) => setForm((f) => ({ ...f, start_time: e.target.value }))}
              required
            />
            <Input
              type="time"
              value={form.end_time}
              onChange={(e) => setForm((f) => ({ ...f, end_time: e.target.value }))}
              required
            />
          </div>
          <Input
            type="number"
            placeholder="Capacity (optional)"
            value={form.capacity}
            onChange={(e) => setForm((f) => ({ ...f, capacity: e.target.value }))}
          />
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? "Saving..." : "Add to schedule"}
          </Button>
        </form>
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Upcoming
        </h2>
        <ul className="flex flex-col gap-2">
          {sessions?.map((s) => (
            <li key={s.id} className="flex items-center justify-between border-b border-[var(--color-border)] py-2">
              <span className="text-sm text-[var(--color-text)]">
                {s.title} - {s.date} {s.start_time.slice(0, 5)}
              </span>
              <Button variant="danger" onClick={() => remove.mutate(s.id)} className="px-2 py-1 text-xs">
                Delete
              </Button>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
