"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import { api, type UsageHistoryEntry, ApiError } from "@/lib/api";
import { formatPeriodKey } from "@/lib/format";

export default function UsageHistoryPage() {
  const { token, user, loading } = useAuth();
  const router = useRouter();

  const [entries, setEntries] = useState<UsageHistoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!token) return;
    api
      .getUsageHistory(token)
      .then(setEntries)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Could not load your usage history.");
        setEntries([]);
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

  return (
    <main className="min-h-screen">
      <NavBar />
      <div className="mx-auto max-w-2xl px-6 py-12">
        <Link href="/dashboard" className="text-sm text-brand-500 hover:underline">
          ← Dashboard
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">Usage history</h1>
        <p className="mt-1 text-sm text-slate-500">
          Analyses run per calendar month, most recent first — the last 12 months.
        </p>

        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

        {entries === null ? (
          <p className="mt-6 text-sm text-slate-500">Loading…</p>
        ) : entries.length === 0 ? (
          <p className="mt-6 text-sm text-slate-500">No usage recorded yet.</p>
        ) : (
          <table className="mt-6 w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500 dark:border-slate-800">
                <th className="py-2 font-medium">Month</th>
                <th className="py-2 font-medium">Analyses run</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {entries.map((e) => (
                <tr key={e.period_key}>
                  <td className="py-2">
                    {formatPeriodKey(e.period_key)}
                  </td>
                  <td className="py-2">{e.analyses_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
