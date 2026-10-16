"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import { api, type AdminUser, type PlatformStats, ApiError } from "@/lib/api";
import { formatBytes } from "@/lib/format";

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  );
}

export default function AdminPage() {
  const { token, user, loading } = useAuth();
  const router = useRouter();

  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!token) return;
    Promise.all([api.getPlatformStats(token), api.listPlatformUsers(token)])
      .then(([statsResult, usersResult]) => {
        setStats(statsResult);
        setUsers(usersResult);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 403) {
          setForbidden(true);
        } else {
          setError(err instanceof ApiError ? err.message : "Could not load admin data.");
        }
      });
  }, [token]);

  if (loading || !user) {
    return (
      <main className="min-h-screen">
        <NavBar />
        <p className="px-6 py-16 text-center text-slate-500">Loading…</p>
      </main>
    );
  }

  if (forbidden) {
    return (
      <main className="min-h-screen">
        <NavBar />
        <div className="mx-auto max-w-2xl px-6 py-16 text-center">
          <h1 className="text-xl font-semibold">Not authorized</h1>
          <p className="mt-2 text-sm text-slate-500">
            This page is restricted to platform administrators.
          </p>
          <Link href="/dashboard" className="mt-4 inline-block text-sm text-brand-500 hover:underline">
            ← Dashboard
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen">
      <NavBar />
      <div className="mx-auto max-w-4xl px-6 py-12">
        <Link href="/dashboard" className="text-sm text-brand-500 hover:underline">
          ← Dashboard
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">Platform admin</h1>
        <p className="mt-1 text-sm text-slate-500">
          Aggregate counts only — accessing the user list below is itself an audited event.
        </p>

        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

        {stats && (
          <>
            <p className="mt-6 text-xs text-slate-400">
              Generated {new Date(stats.generated_at).toLocaleString()}
            </p>
            <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3">
              <StatCard label="Total users" value={stats.total_users} />
              <StatCard label="Active users" value={stats.active_users} />
              <StatCard label="Signups (30d)" value={stats.signups_last_30_days} />
              <StatCard label="Organizations" value={stats.total_organizations} />
              <StatCard label="Workspaces" value={stats.total_workspaces} />
              <StatCard label="Datasets" value={stats.total_datasets} />
              <StatCard label="Dataset versions" value={stats.total_dataset_versions} />
              <StatCard label="Analysis runs" value={stats.total_analysis_runs} />
              <StatCard label="Reports generated" value={stats.total_reports_generated} />
              <StatCard label="Storage used" value={formatBytes(stats.total_storage_bytes)} />
              <StatCard label="Estimated MRR" value={`£${stats.estimated_mrr_gbp.toLocaleString()}`} />
              <StatCard label="Failed logins (24h)" value={stats.failed_logins_last_24h} />
            </div>

            <h2 className="mt-6 text-sm font-medium text-slate-500">Subscriptions by plan</h2>
            <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {Object.entries(stats.subscriptions_by_plan).map(([plan, count]) => (
                <StatCard key={plan} label={plan} value={count} />
              ))}
            </div>
          </>
        )}

        {users && (
          <>
            <h2 className="mt-8 text-sm font-medium text-slate-500">
              Users ({users.length})
            </h2>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="text-slate-500">
                    <th className="pr-4 py-1">Email</th>
                    <th className="pr-4 py-1">Name</th>
                    <th className="pr-4 py-1">Active</th>
                    <th className="pr-4 py-1">Verified</th>
                    <th className="pr-4 py-1">Admin</th>
                    <th className="pr-4 py-1">Joined</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} className="border-t border-slate-200 dark:border-slate-800">
                      <td className="pr-4 py-1">{u.email}</td>
                      <td className="pr-4 py-1">{u.full_name}</td>
                      <td className="pr-4 py-1">{u.is_active ? "Yes" : "No"}</td>
                      <td className="pr-4 py-1">{u.is_verified ? "Yes" : "No"}</td>
                      <td className="pr-4 py-1">{u.is_platform_admin ? "Yes" : "No"}</td>
                      <td className="pr-4 py-1">{new Date(u.created_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
