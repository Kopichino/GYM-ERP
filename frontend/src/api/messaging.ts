import { api } from "../lib/api";

export interface WhatsAppMessage {
  id: number;
  user: number | null;
  username: string | null;
  /** Digits only, as stored. */
  phone: string;
  direction: "in" | "out";
  direction_name: string;
  body: string;
  status: "queued" | "sent" | "failed" | "received";
  external_id: string;
  error: string;
  /** True when the assistant wrote it rather than a person. */
  is_automated: boolean;
  created_at: string;
}

export async function fetchWhatsAppStatus() {
  const res = await api.get<{ enabled: boolean }>("/whatsapp/status/");
  return res.data;
}

export async function fetchMessages(phone?: string) {
  const res = await api.get<{ results: WhatsAppMessage[] }>("/whatsapp/messages/", {
    params: phone ? { phone } : undefined,
  });
  return res.data.results;
}

export async function sendMessage(phone: string, body: string) {
  const res = await api.post<WhatsAppMessage>("/whatsapp/messages/send/", { phone, body });
  return res.data;
}
