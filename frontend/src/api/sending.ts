import { api } from "../lib/api";
import type { GuidedRecord } from "../components/DnsRecordCard";

export interface SendingDomain {
  id: number;
  domain: string;
  from_local_part: string;
  from_name: string;
  from_email: string;
  spf_verified: boolean;
  dkim_verified: boolean;
  /** Both halves. SPF alone still fails DMARC alignment at most receivers. */
  is_verified: boolean;
  verified_at: string | null;
  dns_records: GuidedRecord[];
  last_checked_at: string | null;
  last_error: string;
  created_at: string;
}

/** One per gym, so the list is empty or a single row. */
export async function fetchSendingDomain() {
  const res = await api.get<{ results: SendingDomain[] }>("/tenancy/sending-domain/");
  return res.data.results[0] ?? null;
}

export async function createSendingDomain(payload: {
  domain: string;
  from_local_part: string;
  from_name: string;
}) {
  const res = await api.post<SendingDomain>("/tenancy/sending-domain/", payload);
  return res.data;
}

export async function verifySendingDomain(id: number) {
  const res = await api.post<SendingDomain>(`/tenancy/sending-domain/${id}/verify/`);
  return res.data;
}

export async function requestRecords(id: number) {
  const res = await api.post<SendingDomain>(
    `/tenancy/sending-domain/${id}/request-records/`,
  );
  return res.data;
}

export async function deleteSendingDomain(id: number) {
  await api.delete(`/tenancy/sending-domain/${id}/`);
}
