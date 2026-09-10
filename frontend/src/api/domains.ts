import { api } from "../lib/api";

export type CertificateStatus = "pending" | "issuing" | "active" | "failed";

/** The exact row to create at the registrar, as data rather than prose. */
export interface DnsRecord {
  type: string;
  name: string;
  value: string;
}

export interface Domain {
  id: number;
  hostname: string;
  is_verified: boolean;
  verified_at: string | null;
  is_primary: boolean;
  certificate: CertificateStatus;
  /** Present only while unverified — afterwards it is noise. */
  dns_record: DnsRecord | null;
  last_checked_at: string | null;
  last_error: string;
  created_at: string;
}

export async function fetchDomains() {
  const res = await api.get<{ results: Domain[] }>("/tenancy/domains/");
  return res.data.results;
}

export async function addDomain(hostname: string) {
  const res = await api.post<Domain>("/tenancy/domains/", { hostname });
  return res.data;
}

export async function verifyDomain(id: number) {
  const res = await api.post<Domain>(`/tenancy/domains/${id}/verify/`);
  return res.data;
}

export async function makePrimary(id: number) {
  const res = await api.post<Domain>(`/tenancy/domains/${id}/make-primary/`);
  return res.data;
}

export async function deleteDomain(id: number) {
  await api.delete(`/tenancy/domains/${id}/`);
}
