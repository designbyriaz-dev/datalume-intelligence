"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { api, ApiError } from "@/lib/api";

function ResetPasswordForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.resetPassword(token, newPassword);
      setDone(true);
      setTimeout(() => router.push("/login"), 2000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (!token) {
    return <p className="mt-8 text-sm text-red-600">This link is missing its reset token.</p>;
  }

  if (done) {
    return <p className="mt-8 text-sm text-slate-600 dark:text-slate-300">Password reset. Taking you to log in…</p>;
  }

  return (
    <form onSubmit={onSubmit} className="mt-8 space-y-4">
      <div>
        <label className="block text-sm font-medium">New password</label>
        <input
          required
          minLength={10}
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
        />
        <p className="mt-1 text-xs text-slate-500">At least 10 characters.</p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-md bg-brand-500 px-4 py-2 font-medium text-white hover:bg-brand-600 disabled:opacity-50"
      >
        {submitting ? "Resetting…" : "Reset password"}
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <main className="min-h-screen">
      <NavBar />
      <div className="mx-auto max-w-sm px-6 py-16">
        <h1 className="text-2xl font-semibold">Choose a new password</h1>
        <Suspense fallback={<p className="mt-8 text-sm text-slate-500">Loading…</p>}>
          <ResetPasswordForm />
        </Suspense>
        <p className="mt-6 text-sm text-slate-500">
          <Link href="/login" className="text-brand-500 hover:underline">
            Back to log in
          </Link>
        </p>
      </div>
    </main>
  );
}
