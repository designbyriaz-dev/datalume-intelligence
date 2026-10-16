"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import {
  api,
  type AIConversation,
  type ColumnProfile,
  type Dataset,
  type DatasetDetail,
  type FieldMapping,
  type IndustryKPIResponse,
  type ReportMeta,
  type SavedScenario,
  type ScenarioAdjustment,
  type ScenarioResponse,
  type ScheduledReport,
  type VersionComparison,
  type WebhookSubscription,
  type Workspace,
  ApiError,
  WEBHOOK_EVENT_TYPES,
} from "@/lib/api";

const INDUSTRY_PACK_IDS = new Set(["commercial_property", "residential_property", "social_housing", "business_finance"]);

// Industries whose KPIs/reports actually use the configurable date window
// (leases expiring, overdue inspection, tenancies ending) — business_finance
// has no such KPI, so the setting would be a no-op there.
const INDUSTRIES_WITH_KPI_WINDOW = new Set(["commercial_property", "residential_property", "social_housing"]);
const DEFAULT_KPI_WINDOW_MONTHS = 12;

function KpiWindowSetting({
  workspace,
  token,
  onChanged,
}: {
  workspace: Workspace;
  token: string;
  onChanged: (workspace: Workspace) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(String(workspace.kpi_window_months ?? DEFAULT_KPI_WINDOW_MONTHS));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!INDUSTRIES_WITH_KPI_WINDOW.has(workspace.industry)) return null;

  const effective = workspace.kpi_window_months ?? DEFAULT_KPI_WINDOW_MONTHS;

  const onSave = async () => {
    const months = parseInt(value, 10);
    if (!Number.isFinite(months) || months < 1 || months > 60) {
      setError("Enter a whole number of months between 1 and 60.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateWorkspaceSettings(
        token,
        workspace.id,
        months === DEFAULT_KPI_WINDOW_MONTHS ? null : months
      );
      onChanged(updated);
      setEditing(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save setting.");
    } finally {
      setSaving(false);
    }
  };

  if (!editing) {
    return (
      <p className="mt-1 text-xs text-slate-500">
        Lease/inspection date-window KPIs use {effective} month{effective === 1 ? "" : "s"}
        {workspace.kpi_window_months == null ? " (default)" : ""}.{" "}
        <button onClick={() => setEditing(true)} className="text-brand-500 hover:underline">
          Change
        </button>
      </p>
    );
  }

  return (
    <div className="mt-1 flex items-center gap-2 text-xs">
      <label htmlFor="kpi-window-months" className="text-slate-500">
        Months:
      </label>
      <input
        id="kpi-window-months"
        type="number"
        min={1}
        max={60}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="w-16 rounded-md border border-slate-300 px-2 py-0.5 dark:border-slate-700 dark:bg-slate-900"
      />
      <button
        onClick={onSave}
        disabled={saving}
        className="rounded-md border border-slate-300 px-2 py-0.5 font-medium hover:border-brand-500 disabled:opacity-50 dark:border-slate-700"
      >
        {saving ? "Saving…" : "Save"}
      </button>
      <button onClick={() => setEditing(false)} disabled={saving} className="text-slate-500 hover:underline">
        Cancel
      </button>
      {error && <span className="text-red-600">{error}</span>}
    </div>
  );
}

function QualityBadge({ score }: { score: number }) {
  const color =
    score >= 85
      ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
      : score >= 60
        ? "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200"
        : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${color}`}>{score}/100</span>;
}

function ReportButton({ tableId, token }: { tableId: string; token: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onGenerate = async () => {
    setError(null);
    setBusy(true);
    try {
      const report = await api.generateDataQualityReport(token, tableId);
      const blob = await api.downloadReport(token, report.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `data-quality-report-${report.id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate report.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="inline-block">
      <button
        onClick={onGenerate}
        disabled={busy}
        className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium hover:border-brand-500 disabled:opacity-50 dark:border-slate-700"
      >
        {busy ? "Generating…" : "Download PDF report"}
      </button>
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}

function DashboardGenerateButton({
  tableId,
  token,
  workspaceId,
}: {
  tableId: string;
  token: string;
  workspaceId: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onGenerate = async () => {
    setError(null);
    setBusy(true);
    try {
      const dashboard = await api.autoGenerateDashboard(token, workspaceId, tableId, "Auto-generated dashboard");
      router.push(`/dashboard/dashboards/${dashboard.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate dashboard.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="inline-block">
      <button
        onClick={onGenerate}
        disabled={busy}
        className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium hover:border-brand-500 disabled:opacity-50 dark:border-slate-700"
      >
        {busy ? "Generating…" : "Generate dashboard"}
      </button>
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}

function AskAnalystBox({ tableId, datasetId, token }: { tableId: string; datasetId: string; token: string }) {
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [notConfigured, setNotConfigured] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversation, setConversation] = useState<AIConversation | null>(null);

  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<AIConversation[] | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const loadConversation = async (id: string) => {
    try {
      setConversation(await api.getConversation(token, id));
    } catch {
      // leave the current transcript as-is on a transient fetch failure
    }
  };

  const onAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setAsking(true);
    setError(null);
    setNotConfigured(false);
    const askedQuestion = question;
    setQuestion("");
    try {
      const result = await api.askQuestion(token, tableId, askedQuestion, conversationId ?? undefined);
      setConversationId(result.conversation_id);
      await loadConversation(result.conversation_id);
      setHistory(null); // stale now — a new turn was added, or a new conversation started
    } catch (err) {
      setQuestion(askedQuestion); // restore so the user doesn't lose their question
      if (err instanceof ApiError && err.status === 503) {
        setNotConfigured(true);
      } else {
        setError(err instanceof ApiError ? err.message : "Could not reach the AI analyst.");
      }
    } finally {
      setAsking(false);
    }
  };

  const onNewConversation = () => {
    setConversationId(null);
    setConversation(null);
    setError(null);
    setNotConfigured(false);
  };

  const onToggleHistory = async () => {
    const next = !showHistory;
    setShowHistory(next);
    if (next && history === null) {
      try {
        setHistory(await api.listConversations(token, datasetId));
      } catch (err) {
        setHistoryError(err instanceof ApiError ? err.message : "Could not load conversation history.");
        setHistory([]);
      }
    }
  };

  const onSelectConversation = async (id: string) => {
    setConversationId(id);
    setShowHistory(false);
    setError(null);
    await loadConversation(id);
  };

  return (
    <div className="mt-3 rounded-md border border-dashed border-slate-300 p-3 dark:border-slate-700">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-slate-500">Ask the AI analyst</span>
        <div className="flex gap-3 text-xs">
          {conversation && (
            <button type="button" onClick={onNewConversation} className="text-brand-500 hover:underline">
              New conversation
            </button>
          )}
          <button type="button" onClick={onToggleHistory} className="text-brand-500 hover:underline">
            {showHistory ? "Hide history" : "History"}
          </button>
        </div>
      </div>

      {showHistory && (
        <div className="mt-2 rounded-md bg-slate-50 p-2 dark:bg-slate-900">
          {historyError ? (
            <p className="text-xs text-slate-500">{historyError}</p>
          ) : history === null ? (
            <p className="text-xs text-slate-500">Loading…</p>
          ) : history.length === 0 ? (
            <p className="text-xs text-slate-500">No past conversations yet.</p>
          ) : (
            <ul className="space-y-1">
              {history.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => onSelectConversation(c.id)}
                    className="text-left text-xs text-brand-500 hover:underline"
                  >
                    {c.title || "Untitled"} · {new Date(c.created_at).toLocaleString()}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {conversation && conversation.messages.length > 0 && (
        <div className="mt-2 max-h-80 space-y-2 overflow-y-auto">
          {conversation.messages.map((m) => (
            <div key={m.id} className="text-xs">
              <span className="font-medium text-slate-500">{m.role === "user" ? "You" : "Analyst"}:</span>{" "}
              <span>{m.content}</span>
              {m.tool_calls && m.tool_calls.length > 0 && (
                <div className="mt-0.5 text-slate-400">
                  Backed by: {m.tool_calls.map((tc) => tc.name).join(", ")}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <form onSubmit={onAsk} className="mt-2 flex gap-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask the AI analyst about this data…"
          className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
        />
        <button
          type="submit"
          disabled={asking}
          className="rounded-md bg-brand-500 px-3 py-1 text-xs font-medium text-white hover:bg-brand-600 disabled:opacity-50"
        >
          {asking ? "Asking…" : "Ask"}
        </button>
      </form>
      {notConfigured && (
        <p className="mt-2 text-xs text-slate-500">
          The AI analyst isn&rsquo;t connected to a model yet (no LLM API key configured) — the
          deterministic analysis tools above work without it.
        </p>
      )}
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </div>
  );
}

function FieldMappingReview({ tableId, token }: { tableId: string; token: string }) {
  const [open, setOpen] = useState(false);
  const [mapping, setMapping] = useState<FieldMapping | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const m = await api.getFieldMapping(token, tableId);
      setMapping(m);
      const initialEdits: Record<string, string> = {};
      m.fields.forEach((f) => {
        initialEdits[f.canonical_field] = f.matched_column ?? "";
      });
      setEdits(initialEdits);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load field mapping.");
    } finally {
      setLoading(false);
    }
  };

  const onOpen = () => {
    setOpen(true);
    if (!mapping) load();
  };

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const payload: Record<string, string | null> = {};
      Object.entries(edits).forEach(([field, col]) => {
        payload[field] = col === "" ? null : col;
      });
      const updated = await api.confirmFieldMapping(token, tableId, payload);
      setMapping(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save field mapping.");
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <button
        onClick={onOpen}
        className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium hover:border-brand-500 disabled:opacity-50 dark:border-slate-700"
      >
        Review field mapping
      </button>
    );
  }

  return (
    <div className="mt-3 rounded-md border border-dashed border-slate-300 p-3 dark:border-slate-700">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-medium uppercase text-slate-500">
          Field mapping {mapping && (mapping.is_confirmed ? "(confirmed)" : "(automatic guess — not yet confirmed)")}
        </h4>
        <button onClick={() => setOpen(false)} className="text-xs text-slate-500 hover:underline">
          Close
        </button>
      </div>
      {loading && <p className="mt-2 text-xs text-slate-500">Loading…</p>}
      {mapping && (
        <form onSubmit={onSave} className="mt-2 space-y-1">
          <p className="text-xs text-slate-500">
            Fields marked * are required for this industry&rsquo;s KPIs. Review the automatic column match
            below and correct anything that looks wrong before trusting the computed KPIs/reports.
          </p>
          {mapping.fields.map((f) => (
            <div key={f.canonical_field} className="flex items-center gap-2">
              <label className="w-40 flex-shrink-0 text-xs" title={f.description}>
                {f.canonical_field}
                {f.required_for_pack ? " *" : ""}
              </label>
              <select
                value={edits[f.canonical_field] ?? ""}
                onChange={(e) => setEdits((prev) => ({ ...prev, [f.canonical_field]: e.target.value }))}
                className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
              >
                <option value="">— not mapped —</option>
                {mapping.available_columns.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          ))}
          {error && <p className="text-xs text-red-600">{error}</p>}
          {saved && <p className="text-xs text-green-600">Mapping saved — KPIs/reports will use it from now on.</p>}
          <button
            type="submit"
            disabled={saving}
            className="mt-1 rounded-md bg-brand-500 px-3 py-1 text-xs font-medium text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save mapping"}
          </button>
        </form>
      )}
    </div>
  );
}

type ReportDescriptor = { label: string; generate: (token: string, tableId: string) => Promise<ReportMeta> };

// A list per industry, not a single generator, since social_housing and
// residential_property each now have two report templates (a portfolio
// overview plus a more specific second report — see
// generate_social_housing_compliance_exceptions_report_pdf and
// generate_residential_repairs_maintenance_report_pdf in
// app/services/reports.py for why each is a second report rather than a
// replacement). Commercial property and business finance still have
// just one; nothing here assumes that stays true.
const INDUSTRY_REPORTS: Record<string, ReportDescriptor[]> = {
  commercial_property: [{ label: "Portfolio report", generate: api.generateCommercialPropertyReport }],
  residential_property: [
    { label: "Portfolio report", generate: api.generateResidentialPropertyReport },
    { label: "Repairs & maintenance report", generate: api.generateResidentialRepairsMaintenanceReport },
  ],
  social_housing: [
    { label: "Asset report", generate: api.generateSocialHousingReport },
    { label: "Compliance exceptions report", generate: api.generateSocialHousingComplianceExceptionsReport },
  ],
  business_finance: [{ label: "Portfolio report", generate: api.generateBusinessFinanceReport }],
};

function IndustryKpiPanel({ tableId, token, industry }: { tableId: string; token: string; industry: string }) {
  const [result, setResult] = useState<IndustryKPIResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [reportBusyLabel, setReportBusyLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!INDUSTRY_PACK_IDS.has(industry)) return null;

  const onCompute = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.computeIndustryKpis(token, tableId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not compute industry KPIs.");
    } finally {
      setBusy(false);
    }
  };

  const onDownloadReport = async (report: ReportDescriptor) => {
    setReportBusyLabel(report.label);
    setError(null);
    try {
      const meta = await report.generate(token, tableId);
      const blob = await api.downloadReport(token, meta.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${industry}-${meta.report_type}-${meta.id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate report.");
    } finally {
      setReportBusyLabel(null);
    }
  };

  const reports = INDUSTRY_REPORTS[industry] ?? [];

  return (
    <div className="mt-3 rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={onCompute}
          disabled={busy}
          className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium hover:border-brand-500 disabled:opacity-50 dark:border-slate-700"
        >
          {busy ? "Computing…" : "Compute industry KPIs"}
        </button>
        <FieldMappingReview tableId={tableId} token={token} />
        {reports.map((report) => (
          <button
            key={report.label}
            onClick={() => onDownloadReport(report)}
            disabled={reportBusyLabel !== null}
            className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium hover:border-brand-500 disabled:opacity-50 dark:border-slate-700"
          >
            {reportBusyLabel === report.label ? "Generating…" : `Download ${report.label.toLowerCase()}`}
          </button>
        ))}
      </div>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      {result && (
        <div className="mt-3">
          {result.compliance_caveat && (
            <p className="mb-3 rounded-md bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-300">
              {result.compliance_caveat}
            </p>
          )}
          {result.missing_required_fields.length > 0 && (
            <p className="mb-3 text-xs text-slate-500">
              Some KPIs need columns this table doesn&rsquo;t have (or couldn&rsquo;t recognise):{" "}
              {result.missing_required_fields.join(", ")}.
            </p>
          )}
          {INDUSTRIES_WITH_KPI_WINDOW.has(industry) && (
            <p className="mb-3 text-xs text-slate-500">
              Date-window KPIs used a {result.window_months_used}-month window.
            </p>
          )}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {result.kpis.map((kpi) => (
              <div key={kpi.kpi_id} className="rounded-md bg-slate-50 p-2 dark:bg-slate-900">
                <div className="text-xs text-slate-500">
                  {kpi.kpi_id === "leases_expiring_12_months"
                    ? `Leases Expiring Within ${result.window_months_used} Month${result.window_months_used === 1 ? "" : "s"}`
                    : kpi.name}
                </div>
                <div className="text-sm font-medium">
                  {kpi.error ? <span className="text-slate-400">Not available</span> : kpi.formatted}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const ADJUSTMENT_TYPES: { value: ScenarioAdjustment["adjustment_type"]; label: string }[] = [
  { value: "percentage", label: "% change" },
  { value: "fixed_amount", label: "+/- fixed amount" },
  { value: "set_value", label: "set to value" },
];

interface AdjustmentRow {
  column: string;
  adjustment_type: ScenarioAdjustment["adjustment_type"];
  value: string;
}

function ScenarioPanel({
  tableId,
  workspaceId,
  token,
  industry,
  columns,
}: {
  tableId: string;
  workspaceId: string;
  token: string;
  industry: string;
  columns: ColumnProfile[];
}) {
  const numericColumns = columns.filter((c) => c.inferred_type === "integer" || c.inferred_type === "float");
  const [rows, setRows] = useState<AdjustmentRow[]>([
    { column: numericColumns[0]?.name ?? "", adjustment_type: "percentage", value: "" },
  ]);
  const [result, setResult] = useState<ScenarioResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scenarioName, setScenarioName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<SavedScenario[]>([]);

  const loadSaved = useCallback(async () => {
    try {
      setSaved(await api.listSavedScenarios(token, workspaceId, tableId));
    } catch {
      // leave the saved list as-is on a transient fetch failure
    }
  }, [token, workspaceId, tableId]);

  useEffect(() => {
    if (INDUSTRY_PACK_IDS.has(industry)) loadSaved();
  }, [industry, loadSaved]);

  if (!INDUSTRY_PACK_IDS.has(industry)) return null;

  const buildAdjustments = (): ScenarioAdjustment[] | null => {
    const parsed: ScenarioAdjustment[] = [];
    for (const row of rows) {
      if (!row.column || row.value.trim() === "") continue;
      const value = parseFloat(row.value);
      if (!Number.isFinite(value)) return null;
      parsed.push({ column: row.column, adjustment_type: row.adjustment_type, value });
    }
    return parsed.length > 0 ? parsed : null;
  };

  const onRun = async () => {
    const adjustments = buildAdjustments();
    if (!adjustments) {
      setError("Enter at least one adjustment with a numeric value.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setResult(await api.runScenario(token, tableId, adjustments));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not run scenario.");
    } finally {
      setBusy(false);
    }
  };

  const onSave = async () => {
    const adjustments = buildAdjustments();
    if (!adjustments || !scenarioName.trim()) {
      setError("Enter a name and at least one adjustment before saving.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.createSavedScenario(token, workspaceId, {
        dataset_table_id: tableId,
        name: scenarioName.trim(),
        adjustments,
      });
      setScenarioName("");
      await loadSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save scenario.");
    } finally {
      setSaving(false);
    }
  };

  const onRunSaved = async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.runSavedScenario(token, id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not run saved scenario.");
    } finally {
      setBusy(false);
    }
  };

  const onDeleteSaved = async (id: string) => {
    try {
      await api.deleteSavedScenario(token, id);
      await loadSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete saved scenario.");
    }
  };

  const updateRow = (index: number, patch: Partial<AdjustmentRow>) => {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  };

  const addRow = () => {
    setRows((prev) => [...prev, { column: numericColumns[0]?.name ?? "", adjustment_type: "percentage", value: "" }]);
  };

  const removeRow = (index: number) => {
    setRows((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="mt-3 rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <div className="text-xs font-medium text-slate-500">Scenario modelling (&ldquo;what if…&rdquo;)</div>
      {numericColumns.length === 0 ? (
        <p className="mt-2 text-xs text-slate-400">No numeric columns to adjust.</p>
      ) : (
        <>
          <div className="mt-2 space-y-2">
            {rows.map((row, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <select
                  value={row.column}
                  onChange={(e) => updateRow(i, { column: e.target.value })}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
                >
                  {numericColumns.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
                </select>
                <select
                  value={row.adjustment_type}
                  onChange={(e) => updateRow(i, { adjustment_type: e.target.value as ScenarioAdjustment["adjustment_type"] })}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
                >
                  {ADJUSTMENT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  value={row.value}
                  onChange={(e) => updateRow(i, { value: e.target.value })}
                  placeholder="value"
                  className="w-24 rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
                />
                {rows.length > 1 && (
                  <button
                    onClick={() => removeRow(i)}
                    aria-label="Remove adjustment"
                    className="text-xs text-slate-400 hover:text-red-500"
                  >
                    ×
                  </button>
                )}
              </div>
            ))}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button onClick={addRow} className="text-xs text-brand-500 hover:underline">
              + Add adjustment
            </button>
            <button
              onClick={onRun}
              disabled={busy}
              className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium hover:border-brand-500 disabled:opacity-50 dark:border-slate-700"
            >
              {busy ? "Running…" : "Run scenario"}
            </button>
            <input
              value={scenarioName}
              onChange={(e) => setScenarioName(e.target.value)}
              placeholder="Name to save as…"
              className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
            />
            <button
              onClick={onSave}
              disabled={saving}
              className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium hover:border-brand-500 disabled:opacity-50 dark:border-slate-700"
            >
              {saving ? "Saving…" : "Save scenario"}
            </button>
          </div>
        </>
      )}

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

      {saved.length > 0 && (
        <div className="mt-3">
          <div className="text-xs text-slate-400">Saved scenarios</div>
          <ul className="mt-1 space-y-1">
            {saved.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-2 text-xs">
                <span>{s.name}</span>
                <span className="flex gap-3">
                  <button
                    onClick={() => onRunSaved(s.id)}
                    disabled={busy}
                    className="text-brand-500 hover:underline disabled:opacity-50"
                  >
                    Run
                  </button>
                  <button onClick={() => onDeleteSaved(s.id)} className="text-slate-400 hover:text-red-500">
                    Delete
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {result && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-slate-500">
                <th className="pr-4 py-1">KPI</th>
                <th className="pr-4 py-1">Baseline</th>
                <th className="pr-4 py-1">Scenario</th>
                <th className="pr-4 py-1">Change</th>
              </tr>
            </thead>
            <tbody>
              {result.kpi_deltas.map((d) => (
                <tr key={d.kpi_id} className="border-t border-slate-200 dark:border-slate-800">
                  <td className="pr-4 py-1 font-medium">{d.name}</td>
                  <td className="pr-4 py-1">{d.baseline_value ?? "—"}</td>
                  <td className="pr-4 py-1">{d.scenario_value ?? "—"}</td>
                  <td className="pr-4 py-1">
                    {d.pct_change !== null ? (
                      <span
                        className={
                          d.pct_change > 0
                            ? "text-green-600"
                            : d.pct_change < 0
                              ? "text-red-600"
                              : "text-slate-500"
                        }
                      >
                        {d.pct_change > 0 ? "+" : ""}
                        {d.pct_change.toFixed(1)}%
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const INDUSTRY_REPORT_TYPES: Record<string, string[]> = {
  commercial_property: ["commercial_property_portfolio"],
  residential_property: ["residential_property_portfolio", "residential_repairs_maintenance"],
  social_housing: ["social_housing_asset", "social_housing_compliance_exceptions"],
  business_finance: ["business_performance"],
};

const REPORT_TYPE_LABELS: Record<string, string> = {
  data_quality: "Data Quality",
  commercial_property_portfolio: "Commercial Property Portfolio",
  residential_property_portfolio: "Residential Property Portfolio",
  residential_repairs_maintenance: "Residential Repairs & Maintenance",
  social_housing_asset: "Social Housing Asset",
  social_housing_compliance_exceptions: "Social Housing Compliance Exceptions",
  business_performance: "Business Performance",
};

const SCHEDULE_FREQUENCIES = ["daily", "weekly", "monthly"];

function ScheduledReportsPanel({
  tableId,
  workspaceId,
  token,
  industry,
}: {
  tableId: string;
  workspaceId: string;
  token: string;
  industry: string;
}) {
  const [open, setOpen] = useState(false);
  const [schedules, setSchedules] = useState<ScheduledReport[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reportType, setReportType] = useState("data_quality");
  const [frequency, setFrequency] = useState("daily");
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const reportTypeOptions = ["data_quality", ...(INDUSTRY_REPORT_TYPES[industry] ?? [])];

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const all = await api.listScheduledReports(token, workspaceId);
      setSchedules(all.filter((s) => s.dataset_table_id === tableId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load scheduled reports.");
    } finally {
      setLoading(false);
    }
  };

  const onOpen = () => {
    setOpen(true);
    if (!schedules) load();
  };

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await api.createScheduledReport(token, workspaceId, {
        dataset_table_id: tableId,
        report_type: reportType,
        frequency,
      });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create scheduled report.");
    } finally {
      setCreating(false);
    }
  };

  const onDelete = async (id: string) => {
    setDeletingId(id);
    setError(null);
    try {
      await api.deleteScheduledReport(token, id);
      setSchedules((prev) => (prev ? prev.filter((s) => s.id !== id) : prev));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete scheduled report.");
    } finally {
      setDeletingId(null);
    }
  };

  if (!open) {
    return (
      <button
        onClick={onOpen}
        className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium hover:border-brand-500 disabled:opacity-50 dark:border-slate-700"
      >
        Scheduled reports
      </button>
    );
  }

  return (
    <div className="mt-3 rounded-md border border-dashed border-slate-300 p-3 dark:border-slate-700">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-medium uppercase text-slate-500">Scheduled reports</h4>
        <button onClick={() => setOpen(false)} className="text-xs text-slate-500 hover:underline">
          Close
        </button>
      </div>

      {loading && <p className="mt-2 text-xs text-slate-500">Loading…</p>}

      {schedules && schedules.length > 0 && (
        <ul className="mt-2 space-y-1">
          {schedules.map((s) => (
            <li
              key={s.id}
              className="flex items-center justify-between gap-2 rounded-md bg-slate-50 px-2 py-1 text-xs dark:bg-slate-900"
            >
              <div>
                <div className="font-medium">
                  {REPORT_TYPE_LABELS[s.report_type] ?? s.report_type} &middot; {s.frequency}
                </div>
                <div className="text-slate-500">
                  Next run {new Date(s.next_run_at).toLocaleString()}
                  {s.last_run_at && <> &middot; last generated {new Date(s.last_run_at).toLocaleString()}</>}
                </div>
                {s.last_error && <div className="text-red-600">Generation failed: {s.last_error}</div>}
                {s.last_email_sent_at && !s.last_email_error && (
                  <div className="text-green-600">
                    Last emailed {new Date(s.last_email_sent_at).toLocaleString()}
                  </div>
                )}
                {s.last_email_error && <div className="text-red-600">Email failed: {s.last_email_error}</div>}
              </div>
              <button
                onClick={() => onDelete(s.id)}
                disabled={deletingId === s.id}
                className="flex-shrink-0 text-slate-500 hover:text-red-600 disabled:opacity-50"
              >
                {deletingId === s.id ? "Removing…" : "Remove"}
              </button>
            </li>
          ))}
        </ul>
      )}
      {schedules && schedules.length === 0 && (
        <p className="mt-2 text-xs text-slate-500">No scheduled reports for this table yet.</p>
      )}

      <form onSubmit={onCreate} className="mt-3 flex flex-wrap items-end gap-2">
        <div>
          <label className="block text-xs text-slate-500">Report</label>
          <select
            value={reportType}
            onChange={(e) => setReportType(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
          >
            {reportTypeOptions.map((rt) => (
              <option key={rt} value={rt}>
                {REPORT_TYPE_LABELS[rt] ?? rt}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500">Frequency</label>
          <select
            value={frequency}
            onChange={(e) => setFrequency(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
          >
            {SCHEDULE_FREQUENCIES.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          disabled={creating}
          className="rounded-md bg-brand-500 px-3 py-1 text-xs font-medium text-white hover:bg-brand-600 disabled:opacity-50"
        >
          {creating ? "Scheduling…" : "Schedule"}
        </button>
      </form>
      <p className="mt-1 text-xs text-slate-500">
        Emails the PDF to you each time it runs, if the server has email delivery configured.
      </p>

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </div>
  );
}

type CleaningOperation =
  | "fill_missing_values"
  | "normalize_text"
  | "filter_rows"
  | "calculated_field"
  | "merge_columns"
  | "split_column"
  | "standardize_column"
  | "pivot"
  | "unpivot"
  | "group_by";

const FILL_STRATEGIES = ["drop_rows", "constant", "mean", "median", "mode"];
const FILTER_OPERATORS = ["eq", "ne", "gt", "gte", "lt", "lte", "contains", "is_null", "not_null"];
const CALC_OPERATORS = ["add", "subtract", "multiply", "divide", "concat"];
const PIVOT_AGGREGATE_FUNCTIONS = ["sum", "mean", "min", "max", "first", "last", "median", "len"];
const GROUP_BY_FUNCTIONS = ["sum", "mean", "min", "max", "median", "count"];

function CleaningPanel({
  tableId,
  token,
  columns,
  onChanged,
}: {
  tableId: string;
  token: string;
  columns: ColumnProfile[];
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [operation, setOperation] = useState<CleaningOperation>("fill_missing_values");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // fill-missing-values fields
  const [fillColumn, setFillColumn] = useState("");
  const [fillStrategy, setFillStrategy] = useState("drop_rows");
  const [fillConstant, setFillConstant] = useState("");

  // normalize-text fields
  const [textColumn, setTextColumn] = useState("");
  const [textCase, setTextCase] = useState("lower");
  const [trim, setTrim] = useState(true);
  const [collapseWhitespace, setCollapseWhitespace] = useState(true);

  // filter-rows fields
  const [filterColumn, setFilterColumn] = useState("");
  const [filterOperator, setFilterOperator] = useState("eq");
  const [filterValue, setFilterValue] = useState("");

  // calculated-field fields
  const [newColumnName, setNewColumnName] = useState("");
  const [leftColumn, setLeftColumn] = useState("");
  const [calcOperator, setCalcOperator] = useState("add");
  const [rightMode, setRightMode] = useState<"column" | "value">("value");
  const [rightColumn, setRightColumn] = useState("");
  const [rightValue, setRightValue] = useState("");
  const [separator, setSeparator] = useState(" ");

  // merge-columns fields
  const [mergeColumns, setMergeColumns] = useState<string[]>([]);
  const [mergeNewColumnName, setMergeNewColumnName] = useState("");
  const [mergeSeparator, setMergeSeparator] = useState(" ");
  const [mergeDropSources, setMergeDropSources] = useState(true);

  // split-column fields
  const [splitColumn, setSplitColumn] = useState("");
  const [splitDelimiter, setSplitDelimiter] = useState("");
  const [splitNames, setSplitNames] = useState("");

  // standardize-column fields
  const [stdColumn, setStdColumn] = useState("");
  const [stdKind, setStdKind] = useState("date");
  const [stdDateFormat, setStdDateFormat] = useState("%Y-%m-%d");

  // pivot fields
  const [pivotIndexColumns, setPivotIndexColumns] = useState<string[]>([]);
  const [pivotColumn, setPivotColumn] = useState("");
  const [pivotValueColumn, setPivotValueColumn] = useState("");
  const [pivotAggregateFunction, setPivotAggregateFunction] = useState("sum");

  // unpivot fields
  const [unpivotIdColumns, setUnpivotIdColumns] = useState<string[]>([]);
  const [unpivotValueColumns, setUnpivotValueColumns] = useState<string[]>([]);
  const [unpivotVariableName, setUnpivotVariableName] = useState("variable");
  const [unpivotValueName, setUnpivotValueName] = useState("value");

  // group-by fields (one aggregation in the UI; the API supports more)
  const [groupByColumns, setGroupByColumns] = useState<string[]>([]);
  const [groupAggColumn, setGroupAggColumn] = useState("");
  const [groupAggFunction, setGroupAggFunction] = useState("sum");
  const [groupAggOutputName, setGroupAggOutputName] = useState("");

  const columnNames = columns.map((c) => c.name);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (operation === "fill_missing_values") {
        const constant =
          fillStrategy === "constant"
            ? isNaN(Number(fillConstant)) || fillConstant === ""
              ? fillConstant
              : Number(fillConstant)
            : undefined;
        await api.fillMissingValues(token, tableId, fillColumn, fillStrategy, constant);
      } else if (operation === "normalize_text") {
        await api.normalizeText(token, tableId, textColumn, {
          case: textCase || undefined,
          trim,
          collapse_whitespace: collapseWhitespace,
        });
      } else if (operation === "filter_rows") {
        const isUnary = filterOperator === "is_null" || filterOperator === "not_null";
        const value = isUnary
          ? undefined
          : isNaN(Number(filterValue)) || filterValue === ""
            ? filterValue
            : Number(filterValue);
        await api.filterRows(token, tableId, filterColumn, filterOperator, value);
      } else if (operation === "calculated_field") {
        await api.calculatedField(token, tableId, {
          new_column_name: newColumnName,
          left_column: leftColumn,
          operator: calcOperator,
          right_column: rightMode === "column" ? rightColumn : undefined,
          right_value:
            rightMode === "value"
              ? isNaN(Number(rightValue)) || rightValue === ""
                ? rightValue
                : Number(rightValue)
              : undefined,
          separator: calcOperator === "concat" ? separator : undefined,
        });
      } else if (operation === "merge_columns") {
        await api.mergeColumns(token, tableId, {
          columns: mergeColumns,
          new_column_name: mergeNewColumnName,
          separator: mergeSeparator,
          drop_source_columns: mergeDropSources,
        });
      } else if (operation === "split_column") {
        const names = splitNames
          .split(",")
          .map((n) => n.trim())
          .filter(Boolean);
        await api.splitColumn(token, tableId, {
          column: splitColumn,
          delimiter: splitDelimiter,
          new_column_names: names.length > 0 ? names : undefined,
        });
      } else if (operation === "standardize_column") {
        await api.standardizeColumn(token, tableId, stdColumn, stdKind, stdKind === "date" ? stdDateFormat : undefined);
      } else if (operation === "pivot") {
        await api.pivotTable(token, tableId, {
          index_columns: pivotIndexColumns,
          pivot_column: pivotColumn,
          value_column: pivotValueColumn,
          aggregate_function: pivotAggregateFunction,
        });
      } else if (operation === "unpivot") {
        await api.unpivotTable(token, tableId, {
          id_columns: unpivotIdColumns,
          value_columns: unpivotValueColumns,
          variable_name: unpivotVariableName,
          value_name: unpivotValueName,
        });
      } else {
        await api.groupByTable(token, tableId, {
          group_by_columns: groupByColumns,
          aggregations: [
            {
              column: groupAggFunction === "count" ? undefined : groupAggColumn,
              function: groupAggFunction,
              output_name: groupAggOutputName,
            },
          ],
        });
      }
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not apply that operation.");
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mt-3 rounded-md border border-slate-300 px-3 py-1 text-xs font-medium hover:border-brand-500 dark:border-slate-700"
      >
        Clean this data
      </button>
    );
  }

  const selectClass =
    "mt-1 rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900";
  const inputClass = selectClass + " w-full";

  return (
    <div className="mt-3 rounded-md border border-dashed border-slate-300 p-3 dark:border-slate-700">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-medium uppercase text-slate-500">Clean this data</h4>
        <button onClick={() => setOpen(false)} className="text-xs text-slate-500 hover:underline">
          Close
        </button>
      </div>

      <form onSubmit={onSubmit} className="mt-2 space-y-2">
        <div>
          <label className="block text-xs font-medium">Operation</label>
          <select
            value={operation}
            onChange={(e) => setOperation(e.target.value as CleaningOperation)}
            className={inputClass}
          >
            <option value="fill_missing_values">Fill missing values</option>
            <option value="normalize_text">Normalize text</option>
            <option value="filter_rows">Filter rows</option>
            <option value="calculated_field">Add calculated field</option>
            <option value="merge_columns">Merge columns</option>
            <option value="split_column">Split column</option>
            <option value="standardize_column">Standardize dates/currency</option>
            <option value="pivot">Pivot (long to wide)</option>
            <option value="unpivot">Unpivot (wide to long)</option>
            <option value="group_by">Group by</option>
          </select>
        </div>

        {operation === "fill_missing_values" && (
          <div className="flex flex-wrap gap-2">
            <select value={fillColumn} onChange={(e) => setFillColumn(e.target.value)} required className={selectClass}>
              <option value="">Column…</option>
              {columnNames.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <select value={fillStrategy} onChange={(e) => setFillStrategy(e.target.value)} className={selectClass}>
              {FILL_STRATEGIES.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, " ")}
                </option>
              ))}
            </select>
            {fillStrategy === "constant" && (
              <input
                value={fillConstant}
                onChange={(e) => setFillConstant(e.target.value)}
                placeholder="Fill value"
                required
                className={selectClass}
              />
            )}
          </div>
        )}

        {operation === "normalize_text" && (
          <div className="flex flex-wrap items-center gap-2">
            <select value={textColumn} onChange={(e) => setTextColumn(e.target.value)} required className={selectClass}>
              <option value="">Column…</option>
              {columnNames.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <select value={textCase} onChange={(e) => setTextCase(e.target.value)} className={selectClass}>
              <option value="">No case change</option>
              <option value="lower">lower case</option>
              <option value="upper">UPPER CASE</option>
              <option value="title">Title Case</option>
            </select>
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={trim} onChange={(e) => setTrim(e.target.checked)} />
              Trim
            </label>
            <label className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={collapseWhitespace}
                onChange={(e) => setCollapseWhitespace(e.target.checked)}
              />
              Collapse spaces
            </label>
          </div>
        )}

        {operation === "filter_rows" && (
          <div className="flex flex-wrap gap-2">
            <select
              value={filterColumn}
              onChange={(e) => setFilterColumn(e.target.value)}
              required
              className={selectClass}
            >
              <option value="">Column…</option>
              {columnNames.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <select value={filterOperator} onChange={(e) => setFilterOperator(e.target.value)} className={selectClass}>
              {FILTER_OPERATORS.map((op) => (
                <option key={op} value={op}>
                  {op.replace(/_/g, " ")}
                </option>
              ))}
            </select>
            {filterOperator !== "is_null" && filterOperator !== "not_null" && (
              <input
                value={filterValue}
                onChange={(e) => setFilterValue(e.target.value)}
                placeholder="Value"
                required
                className={selectClass}
              />
            )}
            <p className="w-full text-xs text-slate-500">Keeps only the rows matching this condition.</p>
          </div>
        )}

        {operation === "calculated_field" && (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-2">
              <input
                value={newColumnName}
                onChange={(e) => setNewColumnName(e.target.value)}
                placeholder="New column name"
                required
                className={selectClass}
              />
              <select
                value={leftColumn}
                onChange={(e) => setLeftColumn(e.target.value)}
                required
                className={selectClass}
              >
                <option value="">Column…</option>
                {columnNames.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <select value={calcOperator} onChange={(e) => setCalcOperator(e.target.value)} className={selectClass}>
                {CALC_OPERATORS.map((op) => (
                  <option key={op} value={op}>
                    {op}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={rightMode}
                onChange={(e) => setRightMode(e.target.value as "column" | "value")}
                className={selectClass}
              >
                <option value="value">constant…</option>
                <option value="column">another column…</option>
              </select>
              {rightMode === "column" ? (
                <select
                  value={rightColumn}
                  onChange={(e) => setRightColumn(e.target.value)}
                  required
                  className={selectClass}
                >
                  <option value="">Column…</option>
                  {columnNames.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  value={rightValue}
                  onChange={(e) => setRightValue(e.target.value)}
                  placeholder="Value"
                  required
                  className={selectClass}
                />
              )}
              {calcOperator === "concat" && (
                <input
                  value={separator}
                  onChange={(e) => setSeparator(e.target.value)}
                  placeholder="Separator"
                  className={selectClass}
                />
              )}
            </div>
          </div>
        )}

        {operation === "merge_columns" && (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-2">
              {columnNames.map((c) => (
                <label key={c} className="flex items-center gap-1 text-xs">
                  <input
                    type="checkbox"
                    checked={mergeColumns.includes(c)}
                    onChange={(e) =>
                      setMergeColumns((prev) => (e.target.checked ? [...prev, c] : prev.filter((x) => x !== c)))
                    }
                  />
                  {c}
                </label>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              <input
                value={mergeNewColumnName}
                onChange={(e) => setMergeNewColumnName(e.target.value)}
                placeholder="New column name"
                required
                className={selectClass}
              />
              <input
                value={mergeSeparator}
                onChange={(e) => setMergeSeparator(e.target.value)}
                placeholder="Separator"
                className={selectClass}
              />
              <label className="flex items-center gap-1 text-xs">
                <input
                  type="checkbox"
                  checked={mergeDropSources}
                  onChange={(e) => setMergeDropSources(e.target.checked)}
                />
                Drop source columns
              </label>
            </div>
            <p className="text-xs text-slate-500">Pick at least 2 columns above to combine.</p>
          </div>
        )}

        {operation === "split_column" && (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-2">
              <select
                value={splitColumn}
                onChange={(e) => setSplitColumn(e.target.value)}
                required
                className={selectClass}
              >
                <option value="">Column…</option>
                {columnNames.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <input
                value={splitDelimiter}
                onChange={(e) => setSplitDelimiter(e.target.value)}
                placeholder="Delimiter, e.g. space or ,"
                required
                className={selectClass}
              />
            </div>
            <input
              value={splitNames}
              onChange={(e) => setSplitNames(e.target.value)}
              placeholder="Optional: comma-separated new column names"
              className={inputClass}
            />
            <p className="text-xs text-slate-500">
              Leave names blank to auto-name columns — must match the number of parts the data actually
              splits into if provided.
            </p>
          </div>
        )}

        {operation === "standardize_column" && (
          <div className="flex flex-wrap items-center gap-2">
            <select value={stdColumn} onChange={(e) => setStdColumn(e.target.value)} required className={selectClass}>
              <option value="">Column…</option>
              {columnNames.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <select value={stdKind} onChange={(e) => setStdKind(e.target.value)} className={selectClass}>
              <option value="date">Date stored as text</option>
              <option value="currency">Currency/number stored as text</option>
            </select>
            {stdKind === "date" && (
              <select value={stdDateFormat} onChange={(e) => setStdDateFormat(e.target.value)} className={selectClass}>
                <option value="%Y-%m-%d">YYYY-MM-DD</option>
                <option value="%d/%m/%Y">DD/MM/YYYY</option>
                <option value="%m/%d/%Y">MM/DD/YYYY</option>
                <option value="%d-%m-%Y">DD-MM-YYYY</option>
              </select>
            )}
          </div>
        )}

        {operation === "pivot" && (
          <div className="space-y-2">
            <div>
              <p className="text-xs font-medium">Index column(s) (kept as rows)</p>
              <div className="flex flex-wrap gap-2">
                {columnNames.map((c) => (
                  <label key={c} className="flex items-center gap-1 text-xs">
                    <input
                      type="checkbox"
                      checked={pivotIndexColumns.includes(c)}
                      onChange={(e) =>
                        setPivotIndexColumns((prev) =>
                          e.target.checked ? [...prev, c] : prev.filter((x) => x !== c)
                        )
                      }
                    />
                    {c}
                  </label>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <select
                value={pivotColumn}
                onChange={(e) => setPivotColumn(e.target.value)}
                required
                className={selectClass}
              >
                <option value="">Pivot column (becomes new columns)…</option>
                {columnNames.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <select
                value={pivotValueColumn}
                onChange={(e) => setPivotValueColumn(e.target.value)}
                required
                className={selectClass}
              >
                <option value="">Value column…</option>
                {columnNames.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <select
                value={pivotAggregateFunction}
                onChange={(e) => setPivotAggregateFunction(e.target.value)}
                className={selectClass}
              >
                {PIVOT_AGGREGATE_FUNCTIONS.map((fn) => (
                  <option key={fn} value={fn}>
                    {fn}
                  </option>
                ))}
              </select>
            </div>
            <p className="text-xs text-slate-500">
              Replaces this table&rsquo;s columns entirely with index column(s) plus one new column per
              distinct pivot value.
            </p>
          </div>
        )}

        {operation === "unpivot" && (
          <div className="space-y-2">
            <div>
              <p className="text-xs font-medium">ID column(s) (kept on every row)</p>
              <div className="flex flex-wrap gap-2">
                {columnNames.map((c) => (
                  <label key={c} className="flex items-center gap-1 text-xs">
                    <input
                      type="checkbox"
                      checked={unpivotIdColumns.includes(c)}
                      onChange={(e) =>
                        setUnpivotIdColumns((prev) =>
                          e.target.checked ? [...prev, c] : prev.filter((x) => x !== c)
                        )
                      }
                    />
                    {c}
                  </label>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-medium">Value column(s) (unpivoted into rows)</p>
              <div className="flex flex-wrap gap-2">
                {columnNames.map((c) => (
                  <label key={c} className="flex items-center gap-1 text-xs">
                    <input
                      type="checkbox"
                      checked={unpivotValueColumns.includes(c)}
                      onChange={(e) =>
                        setUnpivotValueColumns((prev) =>
                          e.target.checked ? [...prev, c] : prev.filter((x) => x !== c)
                        )
                      }
                    />
                    {c}
                  </label>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <input
                value={unpivotVariableName}
                onChange={(e) => setUnpivotVariableName(e.target.value)}
                placeholder="Variable column name"
                className={selectClass}
              />
              <input
                value={unpivotValueName}
                onChange={(e) => setUnpivotValueName(e.target.value)}
                placeholder="Value column name"
                className={selectClass}
              />
            </div>
          </div>
        )}

        {operation === "group_by" && (
          <div className="space-y-2">
            <div>
              <p className="text-xs font-medium">Group by column(s)</p>
              <div className="flex flex-wrap gap-2">
                {columnNames.map((c) => (
                  <label key={c} className="flex items-center gap-1 text-xs">
                    <input
                      type="checkbox"
                      checked={groupByColumns.includes(c)}
                      onChange={(e) =>
                        setGroupByColumns((prev) =>
                          e.target.checked ? [...prev, c] : prev.filter((x) => x !== c)
                        )
                      }
                    />
                    {c}
                  </label>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <select
                value={groupAggFunction}
                onChange={(e) => setGroupAggFunction(e.target.value)}
                className={selectClass}
              >
                {GROUP_BY_FUNCTIONS.map((fn) => (
                  <option key={fn} value={fn}>
                    {fn}
                  </option>
                ))}
              </select>
              {groupAggFunction !== "count" && (
                <select
                  value={groupAggColumn}
                  onChange={(e) => setGroupAggColumn(e.target.value)}
                  required
                  className={selectClass}
                >
                  <option value="">Column…</option>
                  {columnNames.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              )}
              <input
                value={groupAggOutputName}
                onChange={(e) => setGroupAggOutputName(e.target.value)}
                placeholder="New column name"
                required
                className={selectClass}
              />
            </div>
            <p className="text-xs text-slate-500">
              Replaces this table&rsquo;s columns entirely with the group-by column(s) plus this one
              aggregate column.
            </p>
          </div>
        )}

        {error && <p className="text-xs text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-brand-500 px-3 py-1 text-xs font-medium text-white hover:bg-brand-600 disabled:opacity-50"
        >
          {busy ? "Applying…" : "Apply (creates a new version)"}
        </button>
      </form>
    </div>
  );
}

function formatNumber(value: number | null): string {
  if (value === null) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function CompareVersionsPanel({
  dataset,
  token,
}: {
  dataset: DatasetDetail;
  token: string;
}) {
  const [open, setOpen] = useState(false);
  const versionNumbers = dataset.versions.map((v) => v.version_number);
  const [versionA, setVersionA] = useState(versionNumbers[versionNumbers.length - 2] ?? versionNumbers[0]);
  const [versionB, setVersionB] = useState(versionNumbers[versionNumbers.length - 1]);
  const [result, setResult] = useState<VersionComparison | null>(null);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onCompare = async () => {
    setComparing(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.compareVersions(token, dataset.id, versionA, versionB));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not compare versions.");
    } finally {
      setComparing(false);
    }
  };

  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-xs text-brand-500 hover:underline"
      >
        {dataset.versions.length} versions · original data preserved at every step
        {open ? " · hide comparison" : " · compare versions"}
      </button>

      {open && (
        <div className="mt-2 rounded-md border border-slate-200 p-3 dark:border-slate-800">
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-xs text-slate-500">
              From version
              <select
                value={versionA}
                onChange={(e) => setVersionA(Number(e.target.value))}
                className="rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
              >
                {versionNumbers.map((n) => (
                  <option key={n} value={n}>
                    v{n}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-500">
              To version
              <select
                value={versionB}
                onChange={(e) => setVersionB(Number(e.target.value))}
                className="rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
              >
                {versionNumbers.map((n) => (
                  <option key={n} value={n}>
                    v{n}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={onCompare}
              disabled={comparing || versionA === versionB}
              className="rounded-md bg-brand-500 px-3 py-1 text-xs font-medium text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {comparing ? "Comparing…" : "Compare"}
            </button>
          </div>

          {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

          {result && (
            <div className="mt-3 text-xs">
              <p className="text-slate-700 dark:text-slate-300">
                <strong>{result.row_count_before.toLocaleString()}</strong> rows &rarr;{" "}
                <strong>{result.row_count_after.toLocaleString()}</strong> rows (
                {result.row_count_delta >= 0 ? "+" : ""}
                {result.row_count_delta.toLocaleString()}
                {result.row_count_pct_change !== null && `, ${result.row_count_pct_change.toFixed(1)}%`})
              </p>

              {result.columns_added.length > 0 && (
                <p className="mt-1 text-green-700 dark:text-green-400">
                  Columns added: {result.columns_added.join(", ")}
                </p>
              )}
              {result.columns_removed.length > 0 && (
                <p className="mt-1 text-red-700 dark:text-red-400">
                  Columns removed: {result.columns_removed.join(", ")}
                </p>
              )}

              {result.column_comparisons.length > 0 && (
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full border-collapse text-left">
                    <thead>
                      <tr className="border-b border-slate-200 text-slate-500 dark:border-slate-700">
                        <th className="py-1 pr-3">Column</th>
                        <th className="py-1 pr-3">Sum before &rarr; after</th>
                        <th className="py-1 pr-3">Mean before &rarr; after</th>
                        <th className="py-1 pr-3">Distinct before &rarr; after</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.column_comparisons.map((c) => (
                        <tr key={c.column} className="border-b border-slate-100 dark:border-slate-800">
                          <td className="py-1 pr-3 font-medium">{c.column}</td>
                          <td className="py-1 pr-3">
                            {c.sum_before !== null || c.sum_after !== null
                              ? `${formatNumber(c.sum_before)} → ${formatNumber(c.sum_after)}`
                              : "—"}
                          </td>
                          <td className="py-1 pr-3">
                            {c.mean_before !== null || c.mean_after !== null
                              ? `${formatNumber(c.mean_before)} → ${formatNumber(c.mean_after)}`
                              : "—"}
                          </td>
                          <td className="py-1 pr-3">
                            {c.distinct_before !== null || c.distinct_after !== null
                              ? `${c.distinct_before ?? "—"} → ${c.distinct_after ?? "—"}`
                              : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DatasetCard({
  dataset,
  token,
  industry,
  workspaceId,
  onChanged,
}: {
  dataset: DatasetDetail;
  token: string;
  industry: string;
  workspaceId: string;
  onChanged: () => void;
}) {
  const [busyTableId, setBusyTableId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latestVersion = dataset.versions[dataset.versions.length - 1];

  const onDeduplicate = async (tableId: string) => {
    setError(null);
    setBusyTableId(tableId);
    try {
      await api.deduplicateTable(token, tableId);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not deduplicate.");
    } finally {
      setBusyTableId(null);
    }
  };

  return (
    <div className="rounded-lg border border-slate-200 p-5 dark:border-slate-800">
      <div className="flex items-center justify-between">
        <h3 className="font-medium">{dataset.name}</h3>
        <span className="text-xs text-slate-500">
          version {latestVersion.version_number}
          {latestVersion.source_filename ? ` · ${latestVersion.source_filename}` : ""}
        </span>
      </div>

      {dataset.versions.length > 1 && <CompareVersionsPanel dataset={dataset} token={token} />}

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      <div className="mt-4 space-y-4">
        {latestVersion.tables.map((table) => (
          <div key={table.id} className="rounded-md bg-slate-50 p-4 dark:bg-slate-900">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="font-medium">{table.sheet_name}</span>
                <QualityBadge score={table.profile.quality_score} />
                <span className="text-xs text-slate-500">
                  {table.row_count} rows · {table.column_count} columns
                  {table.profile.duplicate_row_count > 0
                    ? ` · ${table.profile.duplicate_row_count} duplicate row(s)`
                    : ""}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {table.profile.duplicate_row_count > 0 && (
                  <button
                    onClick={() => onDeduplicate(table.id)}
                    disabled={busyTableId === table.id}
                    className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium hover:border-brand-500 disabled:opacity-50 dark:border-slate-700"
                  >
                    {busyTableId === table.id ? "Removing…" : "Remove duplicate rows"}
                  </button>
                )}
                <ReportButton tableId={table.id} token={token} />
                <DashboardGenerateButton tableId={table.id} token={token} workspaceId={workspaceId} />
              </div>
            </div>

            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="text-slate-500">
                    <th className="pr-4 py-1">Column</th>
                    <th className="pr-4 py-1">Type</th>
                    <th className="pr-4 py-1">Missing</th>
                    <th className="pr-4 py-1">Invalid</th>
                    <th className="pr-4 py-1">Distinct</th>
                    <th className="pr-4 py-1">Flags</th>
                  </tr>
                </thead>
                <tbody>
                  {table.profile.columns.map((col) => (
                    <tr key={col.name} className="border-t border-slate-200 dark:border-slate-800">
                      <td className="pr-4 py-1 font-medium">{col.name}</td>
                      <td className="pr-4 py-1">
                        {col.inferred_type}
                        {col.suggested_type !== col.inferred_type && (
                          <span className="text-slate-500"> (looks like {col.suggested_type})</span>
                        )}
                      </td>
                      <td className="pr-4 py-1">{(col.null_ratio * 100).toFixed(0)}%</td>
                      <td className="pr-4 py-1">
                        {col.invalid_count > 0 ? (
                          <span className="font-medium text-amber-700 dark:text-amber-400">
                            {col.invalid_count} ({(col.invalid_ratio * 100).toFixed(0)}%)
                          </span>
                        ) : (
                          <span className="text-slate-400">–</span>
                        )}
                      </td>
                      <td className="pr-4 py-1">{col.distinct_count}</td>
                      <td className="pr-4 py-1 text-slate-500">{col.flags.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {table.profile.issues.length > 0 && (
              <ul className="mt-3 space-y-1 text-xs">
                {table.profile.issues.map((issue, idx) => (
                  <li
                    key={idx}
                    className={issue.severity === "warning" ? "text-amber-700 dark:text-amber-400" : "text-slate-500"}
                  >
                    {issue.column ? `${issue.column}: ` : ""}
                    {issue.detail}
                  </li>
                ))}
              </ul>
            )}

            <CleaningPanel
              tableId={table.id}
              token={token}
              columns={table.profile.columns}
              onChanged={onChanged}
            />
            <IndustryKpiPanel tableId={table.id} token={token} industry={industry} />
            <ScenarioPanel
              tableId={table.id}
              workspaceId={workspaceId}
              token={token}
              industry={industry}
              columns={table.profile.columns}
            />
            <AskAnalystBox tableId={table.id} datasetId={dataset.id} token={token} />
            <ScheduledReportsPanel
              tableId={table.id}
              workspaceId={workspaceId}
              token={token}
              industry={industry}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function WebhooksPanel({ workspaceId, token }: { workspaceId: string; token: string }) {
  const [webhooks, setWebhooks] = useState<WebhookSubscription[] | null>(null);
  const [url, setUrl] = useState("");
  const [selectedEvents, setSelectedEvents] = useState<string[]>([...WEBHOOK_EVENT_TYPES]);
  const [creating, setCreating] = useState(false);
  const [newSecret, setNewSecret] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setWebhooks(await api.listWebhooks(token, workspaceId));
    } catch {
      setWebhooks([]);
    }
  }, [token, workspaceId]);

  useEffect(() => {
    load();
  }, [load]);

  const toggleEvent = (eventType: string) => {
    setSelectedEvents((prev) =>
      prev.includes(eventType) ? prev.filter((e) => e !== eventType) : [...prev, eventType]
    );
  };

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim() || selectedEvents.length === 0) return;
    setCreating(true);
    setError(null);
    setNewSecret(null);
    setTestResult(null);
    try {
      const created = await api.createWebhook(token, workspaceId, url, selectedEvents);
      setNewSecret(created.secret);
      setUrl("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create webhook.");
    } finally {
      setCreating(false);
    }
  };

  const onDelete = async (webhookId: string) => {
    setBusyId(webhookId);
    setError(null);
    try {
      await api.deleteWebhook(token, webhookId);
      setNewSecret(null);
      setTestResult(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete webhook.");
    } finally {
      setBusyId(null);
    }
  };

  const onTest = async (webhookId: string) => {
    setBusyId(webhookId);
    setError(null);
    setTestResult(null);
    try {
      const updated = await api.testWebhook(token, webhookId);
      setTestResult(
        updated.last_delivery_error
          ? `Test delivery failed: ${updated.last_delivery_error}`
          : `Test delivery sent — status ${updated.last_delivery_status}.`
      );
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send test delivery.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mt-10">
      <h2 className="font-medium">Webhooks</h2>
      <p className="mt-1 text-xs text-slate-500">
        Get a signed POST to a URL of your choice when something happens in this workspace — verify
        authenticity the same way you&rsquo;d verify a Stripe webhook (HMAC-SHA256, same header shape).
      </p>

      <form
        onSubmit={onCreate}
        className="mt-3 space-y-2 rounded-lg border border-slate-200 p-4 dark:border-slate-800"
      >
        <input
          type="url"
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/webhooks/datalume"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
        />
        <div className="flex flex-wrap gap-3">
          {WEBHOOK_EVENT_TYPES.map((eventType) => (
            <label key={eventType} className="flex items-center gap-1 text-xs text-slate-600 dark:text-slate-400">
              <input
                type="checkbox"
                checked={selectedEvents.includes(eventType)}
                onChange={() => toggleEvent(eventType)}
              />
              {eventType}
            </label>
          ))}
        </div>
        <button
          type="submit"
          disabled={creating || !url.trim() || selectedEvents.length === 0}
          className="rounded-md bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
        >
          {creating ? "Creating…" : "Add webhook"}
        </button>
      </form>

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      {testResult && <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{testResult}</p>}

      {newSecret && (
        <div className="mt-4 rounded-md bg-amber-50 p-3 text-sm dark:bg-amber-950">
          <p className="font-medium text-amber-900 dark:text-amber-200">
            Copy this signing secret now — it won&rsquo;t be shown again.
          </p>
          <code className="mt-2 block break-all rounded bg-white p-2 text-xs dark:bg-slate-900">{newSecret}</code>
        </div>
      )}

      <div className="mt-4">
        {webhooks === null ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : webhooks.length === 0 ? (
          <p className="text-sm text-slate-500">No webhooks configured for this workspace yet.</p>
        ) : (
          <ul className="divide-y divide-slate-200 dark:divide-slate-800">
            {webhooks.map((w) => (
              <li key={w.id} className="py-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <code className="break-all text-xs">{w.url}</code>
                    <div className="mt-0.5 text-xs text-slate-500">{w.event_types.join(", ")}</div>
                    <div className="mt-0.5 text-xs text-slate-500">
                      {w.last_delivery_at
                        ? `Last delivery ${new Date(w.last_delivery_at).toLocaleString()} · status ${
                            w.last_delivery_status ?? "—"
                          }${w.last_delivery_error ? ` · ${w.last_delivery_error}` : ""}`
                        : "No deliveries yet"}
                    </div>
                  </div>
                  <div className="flex gap-3">
                    <button
                      onClick={() => onTest(w.id)}
                      disabled={busyId === w.id}
                      className="text-xs text-brand-500 hover:underline disabled:opacity-50"
                    >
                      {busyId === w.id ? "…" : "Send test"}
                    </button>
                    <button
                      onClick={() => onDelete(w.id)}
                      disabled={busyId === w.id}
                      className="text-xs text-red-600 hover:underline disabled:opacity-50"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function WorkspaceDetailPage() {
  const { token, user, loading } = useAuth();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const workspaceId = params.id;

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [datasets, setDatasets] = useState<DatasetDetail[] | null>(null);
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDatasets = useCallback(async () => {
    if (!token) return;
    const summaries: Dataset[] = await api.listDatasets(token, workspaceId);
    const details = await Promise.all(summaries.map((d) => api.getDataset(token, d.id)));
    setDatasets(details);
  }, [token, workspaceId]);

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [loading, user, router]);

  useEffect(() => {
    if (!token) return;
    api.getWorkspace(token, workspaceId).then(setWorkspace).catch(() => setWorkspace(null));
    loadDatasets().catch(() => setDatasets([]));
  }, [token, workspaceId, loadDatasets]);

  const onUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !file || !name) return;
    setError(null);
    setUploading(true);
    try {
      await api.uploadDataset(token, workspaceId, file, name);
      setName("");
      setFile(null);
      await loadDatasets();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  if (loading || !user) {
    return (
      <main className="min-h-screen">
        <NavBar />
        <p className="px-6 py-16 text-center text-slate-500">Loading…</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen">
      <NavBar />
      <div className="mx-auto max-w-3xl px-6 py-12">
        <Link href="/dashboard" className="text-sm text-brand-500 hover:underline">
          ← All workspaces
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">{workspace?.name ?? "Workspace"}</h1>
        {workspace && (
          <>
            <p className="mt-1 text-sm text-slate-500">{workspace.industry.replace(/_/g, " ")}</p>
            {token && <KpiWindowSetting workspace={workspace} token={token} onChanged={setWorkspace} />}
          </>
        )}

        <form onSubmit={onUpload} className="mt-8 space-y-3 rounded-lg border border-slate-200 p-5 dark:border-slate-800">
          <h2 className="font-medium">Upload a dataset</h2>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1">
              <label className="block text-sm font-medium">Dataset name</label>
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Q1 Rent Roll"
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              />
            </div>
            <div>
              <label className="block text-sm font-medium">File (.csv or .xlsx)</label>
              <input
                required
                type="file"
                accept=".csv,.xlsx"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="mt-1 text-sm"
              />
            </div>
            <button
              type="submit"
              disabled={uploading}
              className="rounded-md bg-brand-500 px-4 py-2 font-medium text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {uploading ? "Uploading…" : "Upload"}
            </button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <p className="text-xs text-slate-500">
            Max 50MB. Files are validated by content, not just extension, and profiled immediately —
            no AI involved in this step, just deterministic parsing.
          </p>
        </form>

        <div className="mt-10 space-y-6">
          <h2 className="font-medium">Datasets</h2>
          {datasets === null ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : datasets.length === 0 ? (
            <p className="text-sm text-slate-500">No datasets yet — upload your first file above.</p>
          ) : (
            datasets.map((d) => (
              <DatasetCard
                key={d.id}
                dataset={d}
                token={token!}
                industry={workspace?.industry ?? "general"}
                workspaceId={workspaceId}
                onChanged={loadDatasets}
              />
            ))
          )}
        </div>

        <WebhooksPanel workspaceId={workspaceId} token={token!} />
      </div>
    </main>
  );
}
