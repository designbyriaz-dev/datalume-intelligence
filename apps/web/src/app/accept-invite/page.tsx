"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import { api, type InvitePreview, ApiError } from "@/lib/api";

function AcceptInviteForm() {
  const { register } = useAuth();
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";

  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) {
      setPreviewError("This invite link is missing its token.");
      return;
    }
    api
      .previewInvite(token)
      .then(setPreview)
      .catch((err) =>
        setPreviewError(err instanceof ApiError ? err.message : "This invite link is invalid or has expired.")
      );
  }, [token]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!preview) return;
    setSubmitError(null);
    setSubmitting(true);
    try {
      await register(preview.email, password, fullName, token);
      router.push("/dashboard");
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (previewError) {
    return <p className="mt-8 text-sm text-red-600">{previewError}</p>;
  }

  if (!preview) {
    return <p className="mt-8 text-sm text-slate-500">Loading invite…</p>;
  }

  return (
    <>
      <p className="mt-1 text-sm text-slate-500">
        You&rsquo;ve been invited to join <span className="font-medium">{preview.organization_name}</span> as{" "}
        <span className="font-medium">{preview.role}</span>.
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <div>
          <label className="block text-sm font-medium">Email</label>
          <input
            disabled
            value={preview.email}
            className="mt-1 w-full rounded-md border border-slate-300 bg-slate-100 px-3 py-2 text-slate-500 dark:border-slate-700 dark:bg-slate-800"
          />
        </div>
        <div>
          <label className="block text-sm font-medium">Full name</label>
          <input
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <div>
          <label className="block text-sm font-medium">Password</label>
          <input
            required
            minLength={10}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
          />
          <p className="mt-1 text-xs text-slate-500">At least 10 characters.</p>
        </div>

        {submitError && <p className="text-sm text-red-600">{submitError}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-brand-500 px-4 py-2 font-medium text-white hover:bg-brand-600 disabled:opacity-50"
        >
          {submitting ? "Creating account…" : `Join ${preview.organization_name}`}
        </button>
      </form>
    </>
  );
}

export default function AcceptInvitePage() {
  return (
    <main className="min-h-screen">
      <NavBar />
      <div className="mx-auto max-w-sm px-6 py-16">
        <h1 className="text-2xl font-semibold">You&rsquo;re invited</h1>
        <Suspense fallback={<p className="mt-8 text-sm text-slate-500">Loading…</p>}>
          <AcceptInviteForm />
        </Suspense>
        <p className="mt-6 text-sm text-slate-500">
          <Link href="/login" className="text-brand-500 hover:underline">
            Already have an account? Log in
          </Link>
        </p>
      </div>
    </main>
  );
}
