import { useState } from "react";
import { statusColor } from "../lib/theme";
import { ghostButtonClass } from "./ui";

/**
 * One DNS record, split into the boxes a registrar actually asks for.
 *
 * Deliberately not one line of "add a TXT record with name X and value Y". The
 * people doing this are gym owners, and Type / Name / Value land in three
 * separate fields on every registrar's form. Splitting them, each with its own
 * copy button, is the difference between a five-minute job and a support call.
 */
export function RecordField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Blocked in some contexts. The value is on screen and selectable, so
      // this is not worth an error message.
    }
  }

  return (
    <div className="min-w-0">
      <p className="mb-1 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
        {label}
      </p>
      <div className="flex items-center gap-2">
        {/* Truncated to fit; the whole value is on hover and is what gets copied. */}
        <code
          title={value}
          className="min-w-0 flex-1 truncate rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1.5 text-xs text-[var(--color-text)]"
        >
          {value}
        </code>
        {/* Named for its field. Three buttons that all read "Copy" leave a
            screen reader -- or anything else reading the page -- to guess which
            one copies the host; the audit's own check took the first for it. */}
        <button
          onClick={copy}
          aria-label={`${copied ? "Copied" : "Copy"} ${label}`}
          className={ghostButtonClass}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

export interface GuidedRecord {
  purpose?: string;
  explain?: string;
  type: string;
  name: string;
  value: string;
  note?: string;
  /** Already published and confirmed. Undefined where there is nothing to check. */
  satisfied?: boolean;
}

/**
 * A record to publish, showing whether it is already done.
 *
 * The per-record tick matters when there is more than one: told only "not
 * verified", an owner goes back and re-checks the record that was already
 * right. Showing which half is outstanding is the whole point of the screen.
 */
export default function DnsRecordCard({ record }: { record: GuidedRecord }) {
  const done = record.satisfied === true;

  return (
    <div
      className="rounded-lg border p-4"
      style={{
        borderColor: done ? statusColor("positive") : "var(--color-border)",
        background: "var(--color-surface-2)",
      }}
    >
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm text-[var(--color-text)]">
          {record.purpose && <b>{record.purpose}</b>}
          {record.explain && (
            <span className="ml-2 text-[var(--color-text-muted)]">{record.explain}</span>
          )}
        </p>
        {record.satisfied !== undefined && (
          <span
            className="text-xs font-semibold"
            style={{ color: done ? statusColor("positive") : statusColor("caution") }}
          >
            {done ? "Done" : "Not found yet"}
          </span>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <RecordField label="Type" value={record.type} />
        <RecordField label="Name / Host" value={record.name} />
        <RecordField label="Value" value={record.value} />
      </div>

      {record.note && (
        <p className="mt-3 text-xs text-[var(--color-text-muted)]">{record.note}</p>
      )}
    </div>
  );
}
