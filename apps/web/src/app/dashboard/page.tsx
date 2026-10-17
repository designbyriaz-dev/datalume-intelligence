"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import { api, type IndustryPack, type Organization, type Subscription, type Workspace, ApiError } from "@/lib/api";
import { daysUntil, resetCountdownLabel } from "@/lib/format";

// Industries with no dedicated pack (app/core/industry_packs.py has no
// entry for these) — kept as a plain dropdown behind "Something else",
// same free-form choice the old single-step form always offered,
// rather than inventing KPI packs for domains the backend doesn't
// actually support yet. public_sector and education moved out of this
// list once they got real packs — each now shows as its own card
// above, populated dynamically from the real backend registry, like
// every other dedicated pack.
const OTHER_INDUSTRIES = [
  { value: "general", label: "General Data Analysis" },
  { value: "operations_logistics", label: "Operations & Logistics" },
  { value: "other", label: "Other" },
];

type WorkspaceTypeChoice = { industryId: string; packName: string | null };

function CreateWorkspace({
  token,
  organizations,
  onCreated,
}: {
  token: string;
  organizations: Organization[];
  onCreated: (ws: Workspace) => void;
}) {
  const [packs, setPacks] = useState<IndustryPack[] | null>(null);
  const [choice, setChoice] = useState<WorkspaceTypeChoice | null>(null);
  const [otherIndustry, setOtherIndustry] = useState("general");
  const [name, setName] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listIndustryPacks(token).then(setPacks).catch(() => setPacks([]));
  }, [token]);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!choice) return;
    const industry = choice.industryId === "__other__" ? otherIndustry : choice.industryId;
    setError(null);
    setCreating(true);
    try {
      const ws = await api.createWorkspace(token, name, industry, organizationId || undefined);
      onCreated(ws);
      setName("");
      setChoice(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create workspace.");
    } finally {
      setCreating(false);
    }
  };

  if (!choice) {
    return (
      <div className="mt-8">
        <h2 className="font-medium">What do you want to analyse?</h2>
        <p className="mt-1 text-sm text-slate-500">
          Pick what&rsquo;s closest to your data — it tunes the KPIs, reports, and questions you&rsquo;ll
          see for this workspace. You can still upload any CSV or Excel file either way.
        </p>
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {packs === null ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : (
            <>
              {packs.map((pack) => (
                <button
                  key={pack.industry_id}
                  type="button"
                  onClick={() => setChoice({ industryId: pack.industry_id, packName: pack.name })}
                  className="rounded-lg border border-slate-200 p-4 text-left hover:border-brand-500 dark:border-slate-800"
                >
                  <div className="font-medium">{pack.name}</div>
                  {pack.suggested_questions.slice(0, 2).map((q) => (
                    <div key={q} className="mt-1 text-xs text-slate-500">
                      &ldquo;{q}&rdquo;
                    </div>
                  ))}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setChoice({ industryId: "__other__", packName: null })}
                className="rounded-lg border border-dashed border-slate-300 p-4 text-left hover:border-brand-500 dark:border-slate-700"
              >
                <div className="font-medium">Something else</div>
                <div className="mt-1 text-xs text-slate-500">
                  General data analysis, operations &amp; logistics, or anything else.
                </div>
              </button>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="mt-8">
      <button
        type="button"
        onClick={() => setChoice(null)}
        className="text-sm text-brand-500 hover:underline"
      >
        ← Choose a different type
      </button>
      <h2 className="mt-2 font-medium">{choice.packName ?? "Something else"}</h2>

      <form onSubmit={onCreate} className="mt-3 flex flex-wrap items-end gap-3">
        <div className="flex-1">
          <label htmlFor="workspace-name" className="block text-sm font-medium">
            Workspace name
          </label>
          <input
            id="workspace-name"
            required
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. My Rental Portfolio"
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        {choice.industryId === "__other__" && (
          <div>
            <label htmlFor="other-industry" className="block text-sm font-medium">
              Industry
            </label>
            <select
              id="other-industry"
              value={otherIndustry}
              onChange={(e) => setOtherIndustry(e.target.value)}
              className="mt-1 rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
            >
              {OTHER_INDUSTRIES.map((i) => (
                <option key={i.value} value={i.value}>
                  {i.label}
                </option>
              ))}
            </select>
          </div>
        )}
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
    </div>
  );
}

export default function DashboardPage() {
  const { user, token, loading } = useAuth();
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [portalBusy, setPortalBusy] = useState(false);
  const [portalError, setPortalError] = useState<string | null>(null);

  const openBillingPortal = async () => {
    if (!token) return;
    setPortalBusy(true);
    setPortalError(null);
    try {
      const { portal_url } = await api.createPortalSession(token);
      window.location.href = portal_url;
    } catch (err) {
      setPortalError(err instanceof ApiError ? err.message : "Could not open billing portal.");
      setPortalBusy(false);
    }
  };

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
              <Link href="/dashboard/activity" className="text-sm text-brand-500 hover:underline">
                Activity log
              </Link>
              <Link href="/dashboard/security" className="text-sm text-brand-500 hover:underline">
                Security
              </Link>
              <Link href="/pricing" className="text-sm text-brand-500 hover:underline">
                {subscription.plan_id === "free" ? "Upgrade plan" : "Manage plan"}
              </Link>
            </div>
          </div>
        )}

        {subscription?.status === "past_due" && subscription.downgrade_scheduled_for && (
          <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-5 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
            <span className="font-medium">We couldn&apos;t process your last payment.</span> Your{" "}
            {subscription.plan_id} plan will be downgraded to Free in{" "}
            {daysUntil(subscription.downgrade_scheduled_for)} day
            {daysUntil(subscription.downgrade_scheduled_for) === 1 ? "" : "s"} unless it&apos;s resolved.{" "}
            <button
              type="button"
              onClick={openBillingPortal}
              disabled={portalBusy}
              className="font-medium underline disabled:opacity-60"
            >
              {portalBusy ? "Opening…" : "Update payment method"}
            </button>
            {portalError && <span className="mt-1 block text-red-700 dark:text-red-400">{portalError}</span>}
          </div>
        )}

        {token && (
          <CreateWorkspace
            token={token}
            organizations={organizations}
            onCreated={(ws) => setWorkspaces((prev) => [...(prev ?? []), ws])}
          />
        )}

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
