import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  addDomain,
  deleteDomain,
  fetchDomains,
  makePrimary,
  verifyDomain,
  type Domain,
  type DnsRecord,
} from "../../api/domains";
import { RecordField } from "../../components/DnsRecordCard";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  ghostButtonClass,
  Input,
  LoadingState,
} from "../../components/ui";
import { askConfirm } from "../../store/confirmStore";
import { statusColor } from "../../lib/theme";

const CERT_LABEL: Record<Domain["certificate"], string> = {
  pending: "Certificate not requested yet",
  issuing: "Certificate being issued",
  active: "Secure",
  failed: "Certificate failed",
};

/**
 * What to do at the registrar, in the order you do it.
 *
 * Deliberately not "add a TXT record with name X and value Y" in one line: the
 * people doing this are gym owners, and the three fields land in three separate
 * boxes on a registrar's form. Splitting them, each with its own copy button,
 * is the difference between a five-minute job and a support call.
 */
function SetupSteps({ record, hostname }: { record: DnsRecord; hostname: string }) {
  return (
    <div className="mt-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
      <p className="mb-3 text-sm text-[var(--color-text)]">
        To prove <b>{hostname}</b> is yours, add one record where your domain is
        registered — GoDaddy, Namecheap, Cloudflare or whoever you bought it from.
        Look for <b>DNS</b> or <b>DNS records</b>, then add a new record:
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <RecordField label="Type" value={record.type} />
        <RecordField label="Name / Host" value={record.name} />
        <RecordField label="Value" value={record.value} />
      </div>
      <p className="mt-3 text-xs text-[var(--color-text-muted)]">
        Some registrars want the name without your domain on the end — if{" "}
        <code>{record.name}</code> is rejected, try just{" "}
        <code>{record.name.replace(`.${hostname}`, "")}</code>. Changes usually
        appear within a few minutes, occasionally up to an hour.
      </p>
    </div>
  );
}

function DomainRow({ domain }: { domain: Domain }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["domains"] });

  const check = useMutation({
    mutationFn: () => verifyDomain(domain.id),
    onSuccess: () => {
      setError("");
      invalidate();
    },
    onError: (err: { response?: { data?: { detail?: string } } }) =>
      setError(err.response?.data?.detail ?? "Could not check that domain."),
  });
  const promote = useMutation({ mutationFn: () => makePrimary(domain.id), onSuccess: invalidate });
  const remove = useMutation({ mutationFn: () => deleteDomain(domain.id), onSuccess: invalidate });

  const live = domain.is_verified;
  const accent = live ? statusColor("positive") : statusColor("caution");

  return (
    <li className="border-b border-[var(--color-border)] py-4 last:border-none">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-[var(--color-text)]">
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ background: accent }}
              aria-hidden="true"
            />
            <b className="truncate">{domain.hostname}</b>
            {domain.is_primary && (
              <span className="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
                Primary
              </span>
            )}
          </p>
          <p className="mt-1 text-xs" style={{ color: live ? accent : undefined }}>
            {live ? CERT_LABEL[domain.certificate] : "Waiting for the DNS record"}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {!live && (
            <Button
              variant="success"
              onClick={() => check.mutate()}
              disabled={check.isPending}
              className="px-3 py-1 text-xs"
            >
              {check.isPending ? "Checking..." : "Check now"}
            </Button>
          )}
          {live && !domain.is_primary && (
            <button onClick={() => promote.mutate()} className={ghostButtonClass}>
              Make primary
            </button>
          )}
          <Button
            variant="danger"
            className="px-3 py-1 text-xs"
            onClick={() =>
              askConfirm({
                title: `Remove ${domain.hostname}?`,
                consequence: live
                  ? "Members using this address will stop being able to reach your gym."
                  : "You can add it again later; a new DNS record will be issued.",
                confirmLabel: "Remove",
                run: () => remove.mutate(),
              })
            }
          >
            Remove
          </Button>
        </div>
      </div>

      {!live && domain.dns_record && (
        <SetupSteps record={domain.dns_record} hostname={domain.hostname} />
      )}
      <ErrorText>{error}</ErrorText>
    </li>
  );
}

export default function AdminDomainsPage() {
  const queryClient = useQueryClient();
  const [hostname, setHostname] = useState("");
  const [error, setError] = useState("");

  const { data: domains, isLoading, isError } = useQuery({
    queryKey: ["domains"],
    queryFn: fetchDomains,
  });

  const add = useMutation({
    mutationFn: () => addDomain(hostname),
    onSuccess: () => {
      setHostname("");
      setError("");
      queryClient.invalidateQueries({ queryKey: ["domains"] });
    },
    onError: (err: { response?: { data?: Record<string, string[]> } }) => {
      const first = err.response?.data && Object.values(err.response.data)[0];
      setError(String(Array.isArray(first) ? first[0] : (first ?? "Could not add that domain.")));
    },
  });

  return (
    <div>
      <Card accent={statusColor("neutral")} className="mb-6">
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Add a domain
        </h2>
        <p className="mb-2 text-sm text-[var(--color-text)]">
          Put your gym on your own address instead of a shared link.
        </p>
        <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
          Use a subdomain of a domain you already own — <code>app.yourgym.com</code>{" "}
          is the usual choice. You will add one record to prove it is yours, and
          nothing changes for your members until it is verified.
        </p>
        <div className="flex flex-wrap gap-2">
          <Input
            value={hostname}
            onChange={(e) => setHostname(e.target.value)}
            placeholder="app.yourgym.com"
            className="min-w-[220px] flex-1"
            aria-label="Domain"
          />
          <Button onClick={() => add.mutate()} disabled={!hostname.trim() || add.isPending}>
            {add.isPending ? "Adding..." : "Add domain"}
          </Button>
        </div>
        <ErrorText>{error}</ErrorText>
      </Card>

      <Card accent={statusColor("neutral")}>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Your domains
        </h2>
        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState />
        ) : !domains?.length ? (
          <EmptyState>
            No domains yet — your gym is reachable on the shared address.
          </EmptyState>
        ) : (
          <ul className="flex flex-col">
            {domains.map((domain) => (
              <DomainRow key={domain.id} domain={domain} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
