"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import { api, type Organization, type Subscription, type Workspace, ApiError } from "@/lib/api";
import { resetCountdownLabel } from "@/lib/format";

const INDUSTRIES = [
  { value: "general", label: "General Data Analysis" },
  { value: "commercial_property", label: "Commercial Property" },
  { value: "residential_property", label: "Residential Property" },
  { value: "social_housing", label: "Social Housing" },
  { value: "business_finance", label: "Business & Finance" },
  { value: "public_sector", label: "Government & Public Services" },
  { value: "education", label: "Education" },
  { value: "operations_logistics", label: "Operations & Logistics" },
  { value: "other", label: "Other" },
];

export default function DashboardPage() {
  const { user, token, loading } = useAuth();
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("general");
  const [organizationId, setOrganizationId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [loading, user, router]);

  useEffect(() => {
    if (token) {
      api.listWorkspaces(token).then(setWorkspaces).catch(() => setWorkspaces([]));
      api.getSubscription(token).then(setSubscription).catch(() => setSubscription(null));
      api.listOrganizations(token).then(setOrganizations).catch(() => setOrganizations([]));
    }
  }, [token]);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setError(null);
    setCreating(true);
    try {
      const ws = await api.createWorkspace(token, name, industry, organizationId || undefined);
      setWorkspaces((prev) => [...(prev ?? []), ws]);
      setName("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create workspace.");
    } finally {
      setCreating(false);
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
        <h1 className="text-2xl font-semibold">Welcome, {user.full_name}</h1>
        <p className="mt-1 text-sm text-slate-500">
          Create a workspace, then open it to upload a CSV or Excel file and see its data quality
          profile.
        </p>

        {subscription && (
          <div className="mt-6 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 px-5 py-3 dark:border-slate-800">
            <div className="text-sm">
              <span className="font-medium capitalize">{subscription.plan_id}</span> plan ·{" "}
              {subscription.usage.analyses_limit === null
                ? `${subscription.usage.analyses_used} analyses this month`
                : `${subscription.usage.analyses_used} / ${subscription.usage.analyses_limit} analyses used this month`}
              {" · "}
              <span className="text-slate-500">{resetCountdownLabel(subscription.usage.resets_at)}</span>
            </div>
            <div className="flex items-center gap-4">
              <Link href="/dashboard/organizations" className="text-sm text-brand-500 hover:underline">
                Organizations
              </Link>
              <Link href="/dashboard/api-keys" className="text-sm text-brand-500 hover:underline">
                API keys
              </Link>
              <Link href="/pricing" className="text-sm text-brand-500 hover:underline">
                {subscription.plan_id === "free" ? "Upgrade plan" : "Manage plan"}
              </Link>
            </div>
          </div>
        )}

        <form onSubmit={onCreate} className="mt-8 flex flex-wrap items-end gap-3">
          <div className="flex-1">
            <label className="block text-sm font-medium">Workspace name</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. My Rental Portfolio"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
            />
          </div>
          <div>
            <label className="block text-sm font-medium">Industry</label>
            <select
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className="mt-1 rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
            >
              {INDUSTRIES.map((i) => (
                <option key={i.value} value={i.value}>
                  {i.label}
                </option>
              ))}
            </select>
          </div>
          {organizations.length > 0 && (
            <div>
              <label className="block text-sm font-medium">Owner</label>
              <select
                value={organizationId}
                onChange={(e) => setOrganizationId(e.target.value)}
                className="mt-1 rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              >
                <option value="">Personal</option>
                {organizations.map((org) => (
                  <option key={org.id} value={org.id}>
                    {org.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <button
            type="submit"
            disabled={creating}
            className="rounded-md bg-brand-500 px-4 py-2 font-medium text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {creating ? "Creating…" : "Create workspace"}
          </button>
        </form>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

        <div className="mt-10">
          <h2 className="font-medium">Your workspaces</h2>
          {workspaces === null ? (
            <p className="mt-2 text-sm text-slate-500">Loading…</p>
          ) : workspaces.length === 0 ? (
            <p className="mt-2 text-sm text-slate-500">No workspaces yet — create your first one above.</p>
          ) : (
            <ul className="mt-3 divide-y divide-slate-200 dark:divide-slate-800">
              {workspaces.map((ws) => (
                <li key={ws.id}>
                  <Link
                    href={`/dashboard/workspaces/${ws.id}`}
                    className="flex items-center justify-between py-3 hover:text-brand-500"
                  >
                    <span>
                      {ws.name}
                      {ws.organization_id && (
                        <span className="ml-2 text-xs text-slate-400">
                          · {organizations.find((o) => o.id === ws.organization_id)?.name ?? "shared"}
                        </span>
                      )}
                    </span>
                    <span className="text-xs uppercase text-slate-500">{ws.industry.replace(/_/g, " ")}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </main>
  );
}
