"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import { api, type AuditLogEntry, ApiError } from "@/lib/api";
import { humanizeEventType } from "@/lib/format";

export default function ActivityLogPage() {
  const { token, user, loading } = useAuth();
  const router = useRouter();

  const [entries, setEntries] = useState<AuditLogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!token) return;
    api
      .getMyAuditLog(token)
      .then(setEntries)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Could not load your activity log.");
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
        <h1 className="mt-2 text-2xl font-semibold">Activity log</h1>
        <p className="mt-1 text-sm text-slate-500">
          Recent account activity — logins, registration, API key changes — the most recent 200 events.
        </p>

        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

        {entries === null ? (
          <p className="mt-6 text-sm text-slate-500">Loading…</p>
        ) : entries.length === 0 ? (
          <p className="mt-6 text-sm text-slate-500">No activity recorded yet.</p>
        ) : (
          <ul className="mt-6 divide-y divide-slate-200 dark:divide-slate-800">
            {entries.map((e) => (
              <li key={e.id} className="py-2 text-sm">
                <span className="text-slate-400">{new Date(e.created_at).toLocaleString()}</span>
                {" — "}
                <span className="capitalize">{humanizeEventType(e.event_type)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
