import { api } from "../lib/api";

export interface GalleryPost {
  id: number;
  uploader: number | null;
  uploader_name: string;
  media: string;
  media_type: "image" | "video";
  caption: string;
  approved: boolean;
  created_at: string;
}

export async function fetchGalleryPosts() {
  const res = await api.get<{ results: GalleryPost[] }>("/gallery/");
  return res.data.results;
}

export async function uploadGalleryPost(payload: FormData) {
  const res = await api.post<GalleryPost>("/gallery/", payload, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

export async function approveGalleryPost(id: number) {
  const res = await api.post<GalleryPost>(`/gallery/${id}/approve/`);
  return res.data;
}

export async function deleteGalleryPost(id: number) {
  await api.delete(`/gallery/${id}/`);
}
