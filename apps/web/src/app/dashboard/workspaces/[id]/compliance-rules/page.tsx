"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import { api, ApiError, type ComplianceRule, type DocumentType } from "@/lib/api";

const DOCUMENT_TYPES: DocumentType[] = [
  "tenancy_agreement",
  "gas_safety_certificate",
  "eicr",
  "epc",
  "deposit_protection_certificate",
  "right_to_rent_check",
  "insurance_certificate",
  "inventory_report",
  "other",
];

function formatLabel(value: string): string {
  return value.replace(/_/g, " ");
}

export default function ComplianceRulesPage() {
  const { token, user, loading } = useAuth();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const workspaceId = params.id;

  const [rules, setRules] = useState<ComplianceRule[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [documentType, setDocumentType] = useState<DocumentType>("gas_safety_certificate");
  const [requiresNonExpired, setRequiresNonExpired] = useState(true);
  const [warningWindowDays, setWarningWindowDays] = useState("30");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setRules(await api.listComplianceRules(token, workspaceId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load compliance rules.");
      setRules([]);
    }
  }, [token, workspaceId]);

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [loading, user, router]);

  useEffect(() => {
    load();
  }, [load]);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !name.trim()) return;
    const days = parseInt(warningWindowDays, 10);
    setCreating(true);
    setError(null);
    try {
      await api.createComplianceRule(token, workspaceId, {
        name,
        document_type: documentType,
        requires_non_expired: requiresNonExpired,
        warning_window_days: Number.isFinite(days) ? days : 30,
      });
      setName("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create compliance rule.");
    } finally {
      setCreating(false);
    }
  };

  const onToggleActive = async (rule: ComplianceRule) => {
    if (!token) return;
    setError(null);
    try {
      await api.updateComplianceRule(token, rule.id, {
        name: rule.name,
        document_type: rule.document_type ?? "other",
        requires_non_expired: rule.requires_non_expired,
        warning_window_days: rule.warning_window_days,
        is_active: !rule.is_active,
      });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update compliance rule.");
    }
  };

  const onDelete = async (ruleId: string) => {
    if (!token) return;
    setError(null);
    try {
      await api.deleteComplianceRule(token, ruleId);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete compliance rule.");
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
        <Link href={`/dashboard/workspaces/${workspaceId}`} className="text-sm text-brand-500 hover:underline">
          ← Back to workspace
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">Compliance rules</h1>
        <p className="mt-1 text-sm text-slate-500">
          Rules you define for this portfolio — e.g. &ldquo;every property needs a valid gas safety
          certificate&rdquo;. This checks against the documents on file; it is not a legal determination
          and does not certify that a property actually meets UK lettings law. See each property&rsquo;s
          page for the resulting checks.
        </p>

        <form onSubmit={onCreate} className="mt-6 space-y-3 rounded-lg border border-slate-200 p-5 dark:border-slate-800">
          <h2 className="font-medium">Add a rule</h2>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1">
              <label className="block text-sm font-medium">Name</label>
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Gas Safety Certificate"
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              />
            </div>
            <div>
              <label className="block text-sm font-medium">Required document type</label>
              <select
                value={documentType}
                onChange={(e) => setDocumentType(e.target.value as DocumentType)}
                className="mt-1 rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              >
                {DOCUMENT_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {formatLabel(t)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="flex items-center gap-2 text-sm font-medium">
                <input
                  type="checkbox"
                  checked={requiresNonExpired}
                  onChange={(e) => setRequiresNonExpired(e.target.checked)}
                />
                Must not be expired
              </label>
            </div>
            {requiresNonExpired && (
              <div>
                <label className="block text-sm font-medium">Warning window (days)</label>
                <input
                  type="number"
                  min={0}
                  max={365}
                  value={warningWindowDays}
                  onChange={(e) => setWarningWindowDays(e.target.value)}
                  className="mt-1 w-24 rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
                />
              </div>
            )}
            <button
              type="submit"
              disabled={creating}
              className="rounded-md bg-brand-500 px-4 py-2 font-medium text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {creating ? "Adding…" : "Add rule"}
            </button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </form>

        <div className="mt-8 space-y-2">
          <h2 className="font-medium">Rules</h2>
          {rules === null ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : rules.length === 0 ? (
            <p className="text-sm text-slate-500">No compliance rules yet — add one above.</p>
          ) : (
            rules.map((rule) => (
              <div
                key={rule.id}
                className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800"
              >
                <div>
                  <div className="font-medium">
                    {rule.name} {!rule.is_active && <span className="text-xs text-slate-400">(inactive)</span>}
                  </div>
                  <div className="text-xs text-slate-500">
                    Requires {rule.document_type ? formatLabel(rule.document_type) : "—"}
                    {rule.requires_non_expired && `, not expired (warns ${rule.warning_window_days} days before)`}
                  </div>
                </div>
                <div className="flex flex-shrink-0 gap-3 text-xs">
                  <button onClick={() => onToggleActive(rule)} className="text-brand-500 hover:underline">
                    {rule.is_active ? "Deactivate" : "Activate"}
                  </button>
                  <button onClick={() => onDelete(rule.id)} className="text-slate-400 hover:text-red-500">
                    Delete
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </main>
  );
}
