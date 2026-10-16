"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";

export default function SsoCallbackPage() {
  const { completeSso } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const providerError = searchParams.get("error");

    if (providerError) {
      setError(`Google declined the request: ${providerError}`);
      return;
    }
    if (!code || !state) {
      setError("Missing authorization code or state in the callback URL.");
      return;
    }

    completeSso(code, state)
      .then(() => router.push("/dashboard"))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Something went wrong completing sign-in.");
      });
  }, [searchParams, completeSso, router]);

  return (
    <main className="min-h-screen">
      <NavBar />
      <div className="mx-auto max-w-sm px-6 py-16 text-center">
        {error ? (
          <>
            <h1 className="text-xl font-semibold text-red-600">Sign-in failed</h1>
            <p className="mt-2 text-sm text-slate-500">{error}</p>
          </>
        ) : (
          <p className="text-sm text-slate-500">Completing sign-in…</p>
        )}
      </div>
    </main>
  );
}
