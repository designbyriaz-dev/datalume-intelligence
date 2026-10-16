"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import { api, ApiError, type MfaSetup } from "@/lib/api";

function EnableMfa({ onEnabled }: { onEnabled: () => void }) {
  const { token } = useAuth();
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onStart = async () => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      setSetup(await api.mfaSetup(token));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start MFA setup.");
    } finally {
      setBusy(false);
    }
  };

  const onConfirm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await api.mfaEnable(token, code);
      onEnabled();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Incorrect code. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  if (!setup) {
    return (
      <div>
        <p className="text-sm text-slate-500">
          Two-factor authentication is off. Turning it on requires a 6-digit code from an
          authenticator app (like Google Authenticator or 1Password) every time you log in.
        </p>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        <button
          onClick={onStart}
          disabled={busy}
          className="mt-4 rounded-md bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
        >
          {busy ? "Starting…" : "Enable two-factor authentication"}
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={onConfirm} className="space-y-4">
      <div>
        <p className="text-sm text-slate-500">
          Scan this with your authenticator app, or enter the code manually, then confirm with the
          6-digit code it generates.
        </p>
        <a
          href={setup.otpauth_url}
          className="mt-2 block break-all rounded-md bg-slate-100 p-3 text-xs text-brand-500 hover:underline dark:bg-slate-900"
        >
          {setup.otpauth_url}
        </a>
        <p className="mt-2 text-xs text-slate-500">
          Manual entry code:{" "}
          <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">{setup.secret}</code>
        </p>
      </div>
      <div>
        <label className="block text-sm font-medium">6-digit code</label>
        <input
          required
          autoFocus
          inputMode="numeric"
          pattern="[0-9]{6}"
          maxLength={6}
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
          className="mt-1 w-full max-w-[12rem] rounded-md border border-slate-300 px-3 py-2 tracking-[0.3em] dark:border-slate-700 dark:bg-slate-900"
          placeholder="000000"
        />
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button
        type="submit"
        disabled={busy || code.length !== 6}
        className="rounded-md bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
      >
        {busy ? "Confirming…" : "Confirm and enable"}
      </button>
    </form>
  );
}

function DisableMfa({ onDisabled }: { onDisabled: () => void }) {
  const { token } = useAuth();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await api.mfaDisable(token, password);
      onDisabled();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Incorrect password.");
    } finally {
      setBusy(false);
    }
  };

  if (!confirming) {
    return (
      <div>
        <p className="text-sm text-slate-500">
          Two-factor authentication is <span className="font-medium text-green-600">on</span>.
        </p>
        <button
          onClick={() => setConfirming(true)}
          className="mt-4 text-sm text-red-600 hover:underline"
        >
          Disable two-factor authentication
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <p className="text-sm text-slate-500">
        Enter your password to confirm you want to disable two-factor authentication.
      </p>
      <input
        required
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full max-w-sm rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
        placeholder="Password"
      />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex gap-3">
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
        >
          {busy ? "Disabling…" : "Confirm disable"}
        </button>
        <button
          type="button"
          onClick={() => {
            setConfirming(false);
            setPassword("");
            setError(null);
          }}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium hover:border-brand-500 dark:border-slate-700"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

export default function SecurityPage() {
  const { user, loading, refreshUser } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

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
        <h1 className="mt-2 text-2xl font-semibold">Security</h1>
        <p className="mt-1 text-sm text-slate-500">
          Add a second factor to your login, on top of your password.
        </p>

        <div className="mt-6 rounded-lg border border-slate-200 p-5 dark:border-slate-800">
          <h2 className="text-sm font-medium uppercase text-slate-500">Two-factor authentication</h2>
          <div className="mt-3">
            {user.mfa_enabled ? (
              <DisableMfa onDisabled={refreshUser} />
            ) : (
              <EnableMfa onEnabled={refreshUser} />
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
