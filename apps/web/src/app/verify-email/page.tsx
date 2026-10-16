"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { api, ApiError } from "@/lib/api";

function VerifyEmailStatus() {
  const token = useSearchParams().get("token") ?? "";
  const [status, setStatus] = useState<"verifying" | "done" | "error">("verifying");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setError("This link is missing its verification token.");
      return;
    }
    api
      .verifyEmail(token)
      .then(() => setStatus("done"))
      .catch((err) => {
        setStatus("error");
        setError(err instanceof ApiError ? err.message : "Something went wrong.");
      });
  }, [token]);

  if (status === "verifying") {
    return <p className="mt-8 text-sm text-slate-500">Verifying your email…</p>;
  }
  if (status === "error") {
    return <p className="mt-8 text-sm text-red-600">{error}</p>;
  }
  return <p className="mt-8 text-sm text-slate-600 dark:text-slate-300">Your email is verified.</p>;
}

export default function VerifyEmailPage() {
  return (
    <main className="min-h-screen">
      <NavBar />
      <div className="mx-auto max-w-sm px-6 py-16">
        <h1 className="text-2xl font-semibold">Email verification</h1>
        <Suspense fallback={<p className="mt-8 text-sm text-slate-500">Loading…</p>}>
          <VerifyEmailStatus />
        </Suspense>
        <p className="mt-6 text-sm text-slate-500">
          <Link href="/dashboard" className="text-brand-500 hover:underline">
            Go to dashboard
          </Link>
        </p>
      </div>
    </main>
  );
}
