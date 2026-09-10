import { api } from "../lib/api";

export interface Announcement {
  id: number;
  title: string;
  body: string;
  created_by: number | null;
  created_by_name: string;
  pinned: boolean;
  created_at: string;
  updated_at: string;
}

export async function fetchAnnouncements() {
  const res = await api.get<{ results: Announcement[] }>("/announcements/");
  return res.data.results;
}

export async function createAnnouncement(payload: { title: string; body: string; pinned?: boolean }) {
  const res = await api.post<Announcement>("/announcements/", payload);
  return res.data;
}

export async function deleteAnnouncement(id: number) {
  await api.delete(`/announcements/${id}/`);
}
