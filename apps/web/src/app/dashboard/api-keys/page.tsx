"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import { api, type ApiKeyInfo, ApiError } from "@/lib/api";

export default function ApiKeysPage() {
  const { token, user, loading } = useAuth();
  const router = useRouter();

  const [keys, setKeys] = useState<ApiKeyInfo[] | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [newRawKey, setNewRawKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setKeys(await api.listApiKeys(token));
    } catch {
      setKeys([]);
    }
  }, [token]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  useEffect(() => {
    load();
  }, [load]);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !name.trim()) return;
    setCreating(true);
    setError(null);
    setNewRawKey(null);
    try {
      const created = await api.createApiKey(token, name);
      setNewRawKey(created.raw_key);
      setName("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create API key.");
    } finally {
      setCreating(false);
    }
  };

  const onRevoke = async (keyId: string) => {
    if (!token) return;
    try {
      await api.revokeApiKey(token, keyId);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not revoke key.");
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
      <div className="mx-auto max-w-2xl px-6 py-12">
        <Link href="/dashboard" className="text-sm text-brand-500 hover:underline">
          ← Dashboard
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">API keys</h1>
        <p className="mt-1 text-sm text-slate-500">
          Authenticate requests to the DataLume API as yourself — pass a key as{" "}
          <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">Authorization: Bearer &lt;key&gt;</code>,
          same as a login token.
        </p>

        <form onSubmit={onCreate} className="mt-6 flex gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. CI pipeline"
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
          <button
            type="submit"
            disabled={creating}
            className="rounded-md bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {creating ? "Creating…" : "Create key"}
          </button>
        </form>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

        {newRawKey && (
          <div className="mt-4 rounded-md bg-amber-50 p-3 text-sm dark:bg-amber-950">
            <p className="font-medium text-amber-900 dark:text-amber-200">
              Copy this key now — it won&rsquo;t be shown again.
            </p>
            <code className="mt-2 block break-all rounded bg-white p-2 text-xs dark:bg-slate-900">
              {newRawKey}
            </code>
          </div>
        )}

        <div className="mt-8">
          {keys === null ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : keys.length === 0 ? (
            <p className="text-sm text-slate-500">No API keys yet.</p>
          ) : (
            <ul className="divide-y divide-slate-200 dark:divide-slate-800">
              {keys.map((k) => (
                <li key={k.id} className="flex items-center justify-between py-3 text-sm">
                  <div>
                    <span className="font-medium">{k.name}</span>{" "}
                    <code className="text-xs text-slate-500">{k.key_prefix}…</code>
                    <div className="text-xs text-slate-500">
                      {k.is_active ? "Active" : "Revoked"} ·{" "}
                      {k.last_used_at ? `last used ${new Date(k.last_used_at).toLocaleString()}` : "never used"}
                    </div>
                  </div>
                  {k.is_active && (
                    <button
                      onClick={() => onRevoke(k.id)}
                      className="text-xs text-red-600 hover:underline"
                    >
                      Revoke
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </main>
  );
}
