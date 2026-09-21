import { api } from "../lib/api";

export interface Branding {
  name: string;
  tagline: string;
  logo: string | null;
  accent: string;
  accent_2: string;
  /** Headline face. Body copy is always Inter. */
  display_font: string;
  phone: string;
  email: string;
  address: string;
  website: string;
  instagram: string;
  /** One line per row, e.g. "Monday to Friday: 5:30 - 23:00". Shown on the website. */
  opening_hours: string;
  /** False when no gym has filled the branding page in yet. */
  configured: boolean;
}

/** Admin-only fields the public endpoint deliberately withholds. */
export interface BrandingAdmin extends Omit<Branding, "configured"> {
  id: number;
  gstin: string;
  state: string;
  is_active: boolean;
  updated_at: string;
}

/** Readable signed out — the login screen has to be branded too. */
export async function fetchBranding() {
  const res = await api.get<Branding>("/branding/");
  return res.data;
}

export async function fetchBrandingAdmin() {
  const res = await api.get<{ results: BrandingAdmin[] }>("/branding/admin/");
  return res.data.results;
}

export async function saveBranding(payload: FormData) {
  const res = await api.post<BrandingAdmin>("/branding/admin/", payload);
  return res.data;
}
