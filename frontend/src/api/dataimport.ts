import { api } from "../lib/api";

export type ImportKind = "members" | "billing" | "trainers";

export interface ImportRow {
  row_number: number;
  action: "create" | "update";
  errors: string[];
  warnings?: string[];
  data: Record<string, unknown>;
}

export interface ImportPreview {
  kind: ImportKind;
  headers: string[];
  mapping: Record<string, string>;
  available_fields: string[];
  required_fields: string[];
  total_rows: number;
  create_count: number;
  update_count: number;
  error_count: number;
  rows: ImportRow[];
  truncated: boolean;
}

export interface ImportResult {
  created: number;
  updated: number;
  skipped: number;
  problems: { row_number: number; errors: string[] }[];
}

function body(file: File, kind: ImportKind, mapping?: Record<string, string>) {
  const form = new FormData();
  form.append("file", file);
  form.append("kind", kind);
  if (mapping) form.append("mapping", JSON.stringify(mapping));
  return form;
}

export async function previewImport(file: File, kind: ImportKind, mapping?: Record<string, string>) {
  const res = await api.post<ImportPreview>("/import/preview/", body(file, kind, mapping));
  return res.data;
}

export async function commitImport(file: File, kind: ImportKind, mapping: Record<string, string>) {
  const res = await api.post<ImportResult>("/import/commit/", body(file, kind, mapping));
  return res.data;
}

export async function downloadTemplate(kind: ImportKind) {
  const res = await api.get(`/import/template/${kind}/`, { responseType: "blob" });
  const url = window.URL.createObjectURL(new Blob([res.data]));
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", `ironcore_${kind}_template.xlsx`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
