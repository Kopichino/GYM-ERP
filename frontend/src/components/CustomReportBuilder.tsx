import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  deleteSavedReport,
  exportReport,
  fetchReportSchema,
  fetchSavedReports,
  runCustomReport,
  saveReport,
  type CustomResult,
  type ReportDefinition,
} from "../api/reports";
import {
  Button,
  Card,
  EmptyState,
  ErrorText,
  Input,
  LoadingState,
  Select,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "./ui";
import { railColor } from "../lib/theme";
import { askConfirm } from "../store/confirmStore";

const AGGREGATES = [
  { value: "count", label: "Count" },
  { value: "sum", label: "Sum" },
  { value: "avg", label: "Average" },
  { value: "min", label: "Minimum" },
  { value: "max", label: "Maximum" },
];

const OPERATORS = [
  { value: "eq", label: "is" },
  { value: "ne", label: "is not" },
  { value: "contains", label: "contains" },
  { value: "gt", label: "greater than" },
  { value: "lt", label: "less than" },
];

/**
 * Builds a report definition from dropdowns rather than free text.
 *
 * Every option here comes from the server's own whitelist, so the form can only
 * offer combinations the runner will accept -- there is no way to type a field
 * name and have it reach the ORM.
 */
export default function CustomReportBuilder() {
  const queryClient = useQueryClient();
  const { data: sources, isLoading } = useQuery({
    queryKey: ["reports", "schema"],
    queryFn: fetchReportSchema,
  });
  const { data: saved } = useQuery({ queryKey: ["reports", "saved"], queryFn: fetchSavedReports });

  const [source, setSource] = useState("payments");
  const [groupBy, setGroupBy] = useState("");
  const [aggFn, setAggFn] = useState("count");
  const [aggField, setAggField] = useState("");
  const [filterField, setFilterField] = useState("");
  const [filterOp, setFilterOp] = useState("eq");
  const [filterValue, setFilterValue] = useState("");
  const [name, setName] = useState("");
  const [result, setResult] = useState<CustomResult | null>(null);
  const [error, setError] = useState("");

  const fields = useMemo(
    () => sources?.find((s) => s.source === source)?.fields ?? [],
    [sources, source]
  );

  const definition: ReportDefinition = useMemo(() => {
    const d: ReportDefinition = { source };
    if (groupBy) {
      d.group_by = groupBy;
      d.aggregates = [
        { fn: aggFn, ...(aggField ? { field: aggField } : {}), alias: aggField ? `${aggFn}_${aggField}` : "rows" },
      ];
    }
    if (filterField && filterValue) {
      d.filters = [{ field: filterField, op: filterOp, value: filterValue }];
    }
    return d;
  }, [source, groupBy, aggFn, aggField, filterField, filterOp, filterValue]);

  const runIt = useMutation({
    mutationFn: () => runCustomReport(definition),
    onSuccess: (data) => {
      setResult(data);
      setError("");
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      setResult(null);
      setError(err.response?.data?.detail ?? "Could not run that report.");
    },
  });

  const persist = useMutation({
    mutationFn: () => saveReport({ name, definition }),
    onSuccess: () => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["reports", "saved"] });
    },
  });

  const remove = useMutation({
    mutationFn: deleteSavedReport,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["reports", "saved"] }),
  });

  function load(definition: ReportDefinition) {
    setSource(definition.source);
    setGroupBy(definition.group_by ?? "");
    const agg = definition.aggregates?.[0];
    setAggFn(agg?.fn ?? "count");
    setAggField(agg?.field ?? "");
    const filter = definition.filters?.[0];
    setFilterField(filter?.field ?? "");
    setFilterOp(filter?.op ?? "eq");
    setFilterValue(filter ? String(filter.value) : "");
  }

  if (isLoading) {
    return (
      <Card accent={railColor(1)}>
        <LoadingState />
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <Card accent={railColor(1)}>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Build a report
        </h3>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="text-xs text-[var(--color-text-muted)]">
            Data
            <Select
              value={source}
              onChange={(e) => {
                setSource(e.target.value);
                setGroupBy("");
                setAggField("");
                setFilterField("");
                setResult(null);
              }}
              className="mt-1"
            >
              {sources?.map((s) => (
                <option key={s.source} value={s.source}>
                  {s.label}
                </option>
              ))}
            </Select>
          </label>

          <label className="text-xs text-[var(--color-text-muted)]">
            Group by (optional)
            <Select value={groupBy} onChange={(e) => setGroupBy(e.target.value)} className="mt-1">
              <option value="">No grouping — list rows</option>
              {fields.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </Select>
          </label>

          {groupBy && (
            <div className="flex gap-2">
              <label className="flex-1 text-xs text-[var(--color-text-muted)]">
                Measure
                <Select value={aggFn} onChange={(e) => setAggFn(e.target.value)} className="mt-1">
                  {AGGREGATES.map((a) => (
                    <option key={a.value} value={a.value}>
                      {a.label}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="flex-1 text-xs text-[var(--color-text-muted)]">
                Of
                <Select value={aggField} onChange={(e) => setAggField(e.target.value)} className="mt-1">
                  <option value="">rows</option>
                  {fields.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </Select>
              </label>
            </div>
          )}
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <label className="text-xs text-[var(--color-text-muted)]">
            Filter (optional)
            <Select value={filterField} onChange={(e) => setFilterField(e.target.value)} className="mt-1">
              <option value="">No filter</option>
              {fields.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </Select>
          </label>
          {filterField && (
            <>
              <label className="text-xs text-[var(--color-text-muted)]">
                Comparison
                <Select value={filterOp} onChange={(e) => setFilterOp(e.target.value)} className="mt-1">
                  {OPERATORS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="text-xs text-[var(--color-text-muted)]">
                Value
                <Input value={filterValue} onChange={(e) => setFilterValue(e.target.value)} className="mt-1" />
              </label>
            </>
          )}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button onClick={() => runIt.mutate()} disabled={runIt.isPending}>
            {runIt.isPending ? "Running..." : "Run report"}
          </Button>
          <Button variant="secondary" onClick={() => exportReport(definition)} disabled={!result}>
            Export to Excel
          </Button>
          <Input
            placeholder="Save as..."
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="max-w-[200px]"
          />
          <Button variant="secondary" onClick={() => persist.mutate()} disabled={!name || persist.isPending}>
            Save
          </Button>
        </div>
        <ErrorText>{error}</ErrorText>
      </Card>

      {result && (
        <Card accent={railColor(2)}>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {result.row_count} rows
          </h3>
          {!result.rows.length ? (
            <EmptyState>Nothing matched.</EmptyState>
          ) : (
            <div className="no-scrollbar max-h-96 overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-[var(--color-text-muted)]">
                  <tr className={tableHeadRowClass}>
                    {result.columns.map((c) => (
                      <th key={c} className={tableHeadCellClass}>
                        {c.replace(/_/g, " ")}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, i) => (
                    <tr key={i} className={tableRowClass}>
                      {result.columns.map((c) => (
                        <td key={c} className={tableCellClass}>
                          {String(row[c] ?? "-")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {saved && saved.length > 0 && (
        <Card accent={railColor(3)}>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Saved reports
          </h3>
          <ul className="flex flex-col">
            {saved.map((r) => (
              <li
                key={r.id}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] py-2 text-sm last:border-none"
              >
                <span className="text-[var(--color-text)]">{r.name}</span>
                <span className="flex gap-2">
                  <Button variant="secondary" onClick={() => load(r.definition)}>
                    Load
                  </Button>
                  <Button variant="danger" onClick={() =>
                        askConfirm({
                          title: `Delete "${r.name}"?`,
                          consequence: "The saved report will be removed for everyone.",
                          run: () => remove.mutate(r.id),
                        })
                      }>
                    Delete
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
