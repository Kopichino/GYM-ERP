import { useMutation } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import {
  commitImport,
  downloadTemplate,
  previewImport,
  type ImportKind,
  type ImportPreview,
  type ImportResult,
} from "../../api/dataimport";
import {
  Button,
  Card,
  EmptyState,
  ErrorText,
  Select,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "../../components/ui";
import { railColor } from "../../lib/theme";

const KINDS: { value: ImportKind; label: string; hint: string }[] = [
  { value: "members", label: "Members", hint: "Names, emails, phones, join dates, membership status." },
  { value: "billing", label: "Billing / Payments", hint: "Payments per member. Import members first so rows can be matched." },
  { value: "trainers", label: "Trainers", hint: "Trainer profiles. Rows with an email also get a trainer login." },
];

function fieldLabel(field: string) {
  return field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function AdminImportPage() {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<ImportKind>("members");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");

  function reset() {
    setPreview(null);
    setResult(null);
    setError("");
    setMapping({});
  }

  const runPreview = useMutation({
    mutationFn: (override?: Record<string, string>) => {
      if (!file) throw new Error("Choose a file first.");
      return previewImport(file, kind, override);
    },
    onSuccess: (data) => {
      setPreview(data);
      setMapping(data.mapping);
      setResult(null);
      setError("");
    },
    onError: (err: { response?: { data?: { detail?: string } } }) =>
      setError(err.response?.data?.detail ?? "Could not read that file."),
  });

  const runCommit = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("Choose a file first.");
      return commitImport(file, kind, mapping);
    },
    onSuccess: (data) => {
      setResult(data);
      setPreview(null);
      setError("");
      // Imported rows land in the member/billing/trainer lists.
      queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (err: { response?: { data?: { detail?: string } } }) =>
      setError(err.response?.data?.detail ?? "Import failed."),
  });

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    setFile(e.target.files?.[0] ?? null);
    reset();
  }

  function remap(field: string, header: string) {
    const next = { ...mapping };
    if (header) next[field] = header;
    else delete next[field];
    setMapping(next);
    runPreview.mutate(next);
  }

  const activeKind = KINDS.find((k) => k.value === kind)!;

  return (
    <div className="flex flex-col gap-6">
      <Card accent={railColor(0)}>
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Import from another system
        </h2>
        <p className="mb-4 text-sm text-[var(--color-text-muted)]">
          Upload a CSV or Excel export from FitnessForce, GymForce, Torzil, GymMaster or any
          other gym software. Columns are matched automatically -- check the preview and fix
          any that were guessed wrong before importing.
        </p>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex-1 text-xs text-[var(--color-text-muted)]">
            What are you importing?
            <Select
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as ImportKind);
                reset();
              }}
              className="mt-1"
            >
              {KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </Select>
          </label>
          <label className="flex-[2] text-xs text-[var(--color-text-muted)]">
            File (.csv or .xlsx)
            <input
              ref={fileInput}
              type="file"
              accept=".csv,.xlsx,.xlsm,.tsv,.txt"
              onChange={onFileChange}
              className="mt-1 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm text-[var(--color-text)] file:mr-3 file:rounded file:border-0 file:bg-[var(--color-accent)] file:px-3 file:py-1 file:text-sm file:font-semibold file:text-white"
            />
          </label>
        </div>
        <p className="mt-2 text-xs text-[var(--color-text-muted)]">{activeKind.hint}</p>

        <div className="mt-4 flex flex-wrap gap-2">
          <Button onClick={() => runPreview.mutate(undefined)} disabled={!file || runPreview.isPending}>
            {runPreview.isPending ? "Reading..." : "Preview import"}
          </Button>
          <Button variant="secondary" onClick={() => downloadTemplate(kind)}>
            Download blank template
          </Button>
        </div>
        <div className="mt-2">
          <ErrorText>{error}</ErrorText>
        </div>
      </Card>

      {result && (
        <Card accent={railColor(1)}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Import complete
          </h2>
          <div className="flex flex-wrap gap-6">
            <Stat label="Created" value={result.created} />
            <Stat label="Updated" value={result.updated} />
            <Stat label="Skipped" value={result.skipped} />
          </div>
          {result.problems.length > 0 && (
            <div className="mt-4 border-t border-[var(--color-border)] pt-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                Skipped rows
              </p>
              <ul className="flex flex-col gap-1">
                {result.problems.slice(0, 20).map((p) => (
                  <li key={p.row_number} className="text-sm text-red-400">
                    Row {p.row_number}: {p.errors.join(" ")}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}

      {preview && (
        <>
          <Card accent={railColor(2)}>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              Column mapping
            </h2>
            <p className="mb-4 text-sm text-[var(--color-text-muted)]">
              Each IRONCORE field below is matched to a column from your file. Change any that
              look wrong -- the preview updates as you go.
            </p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {preview.available_fields.map((field) => (
                <label key={field} className="text-xs text-[var(--color-text-muted)]">
                  {fieldLabel(field)}
                  {preview.required_fields.includes(field) && (
                    <span className="ml-1 text-[var(--color-accent)]">*</span>
                  )}
                  <Select
                    value={mapping[field] ?? ""}
                    onChange={(e) => remap(field, e.target.value)}
                    className="mt-1"
                  >
                    <option value="">-- not imported --</option>
                    {preview.headers.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </Select>
                </label>
              ))}
            </div>
          </Card>

          <Card accent={railColor(3)}>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap gap-6">
                <Stat label="Rows" value={preview.total_rows} />
                <Stat label="Will create" value={preview.create_count} />
                <Stat label="Will update" value={preview.update_count} />
                <Stat label="Have errors" value={preview.error_count} />
              </div>
              <Button
                onClick={() => runCommit.mutate()}
                disabled={runCommit.isPending || preview.total_rows === preview.error_count}
              >
                {runCommit.isPending
                  ? "Importing..."
                  : `Import ${preview.total_rows - preview.error_count} rows`}
              </Button>
            </div>

            {preview.rows.length === 0 ? (
              <EmptyState>Nothing to preview.</EmptyState>
            ) : (
              <div className="no-scrollbar overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-[var(--color-text-muted)]">
                    <tr className={tableHeadRowClass}>
                      <th className={tableHeadCellClass}>Row</th>
                      <th className={tableHeadCellClass}>Action</th>
                      {Object.keys(preview.rows[0].data)
                        .filter((k) => !k.endsWith("_id"))
                        .map((k) => (
                          <th key={k} className={tableHeadCellClass}>
                            {fieldLabel(k)}
                          </th>
                        ))}
                      <th className={tableHeadCellClass}>Issues</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row) => (
                      <tr key={row.row_number} className={tableRowClass}>
                        <td className={tableCellClass}>{row.row_number}</td>
                        <td className={`${tableCellClass} capitalize`}>
                          {row.errors.length ? "skip" : row.action}
                        </td>
                        {Object.keys(preview.rows[0].data)
                          .filter((k) => !k.endsWith("_id"))
                          .map((k) => (
                            <td key={k} className={tableCellClass}>
                              {String(row.data[k] ?? "") || "-"}
                            </td>
                          ))}
                        <td className={`${tableCellClass} text-red-400`}>
                          {row.errors.join(" ") || (row.warnings ?? []).join(" ") || "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {preview.truncated && (
                  <p className="mt-3 text-xs text-[var(--color-text-muted)]">
                    Showing the first {preview.rows.length} of {preview.total_rows} rows. All rows
                    will be imported.
                  </p>
                )}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="font-display text-2xl text-[var(--color-text)]">{value}</p>
      <p className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">{label}</p>
    </div>
  );
}
