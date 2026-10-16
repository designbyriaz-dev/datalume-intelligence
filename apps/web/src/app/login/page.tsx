"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";

export default function LoginPage() {
  const { login, completeMfaLogin } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [ssoRedirecting, setSsoRedirecting] = useState(false);
  const [challengeToken, setChallengeToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await login(email, password);
      if (result.mfaRequired) {
        setChallengeToken(result.challengeToken);
      } else {
        router.push("/dashboard");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const onSubmitMfaCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!challengeToken) return;
    setError(null);
    setSubmitting(true);
    try {
      await completeMfaLogin(challengeToken, mfaCode);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Incorrect code. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const onGoogleSignIn = async () => {
    setError(null);
    setSsoRedirecting(true);
    try {
      const { authorization_url } = await api.ssoLogin();
      window.location.href = authorization_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Google sign-in isn't available right now.");
      setSsoRedirecting(false);
    }
  };

  if (challengeToken) {
    return (
      <main className="min-h-screen">
        <NavBar />
        <div className="mx-auto max-w-sm px-6 py-16">
          <h1 className="text-2xl font-semibold">Enter your code</h1>
          <p className="mt-2 text-sm text-slate-500">
            Open your authenticator app and enter the 6-digit code for DataLume Intelligence.
          </p>

          <form onSubmit={onSubmitMfaCode} className="mt-8 space-y-4">
            <div>
              <label className="block text-sm font-medium">Authentication code</label>
              <input
                required
                autoFocus
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ""))}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 tracking-[0.3em] dark:border-slate-700 dark:bg-slate-900"
                placeholder="000000"
              />
            </div>

            {error && <p className="text-sm text-red-600">{error}</p>}

            <button
              type="submit"
              disabled={submitting || mfaCode.length !== 6}
              className="w-full rounded-md bg-brand-500 px-4 py-2 font-medium text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {submitting ? "Verifying…" : "Verify"}
            </button>
            <button
              type="button"
              onClick={() => {
                setChallengeToken(null);
                setMfaCode("");
                setError(null);
              }}
              className="w-full text-center text-sm text-slate-500 hover:underline"
            >
              Back to log in
            </button>
          </form>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen">
      <NavBar />
      <div className="mx-auto max-w-sm px-6 py-16">
        <h1 className="text-2xl font-semibold">Log in</h1>

        <form onSubmit={onSubmit} className="mt-8 space-y-4">
          <div>
            <label className="block text-sm font-medium">Email</label>
            <input
              required
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
            />
          </div>
          <div>
            <div className="flex items-center justify-between">
              <label className="block text-sm font-medium">Password</label>
              <Link href="/forgot-password" className="text-xs text-brand-500 hover:underline">
                Forgot password?
              </Link>
            </div>
            <input
              required
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
            />
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-brand-500 px-4 py-2 font-medium text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {submitting ? "Logging in…" : "Log in"}
          </button>
        </form>

        <div className="mt-4 flex items-center gap-3 text-xs text-slate-400">
          <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
          or
          <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
        </div>

        <button
          type="button"
          onClick={onGoogleSignIn}
          disabled={ssoRedirecting}
          className="mt-4 w-full rounded-md border border-slate-300 px-4 py-2 font-medium hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-900"
        >
          {ssoRedirecting ? "Redirecting to Google…" : "Continue with Google"}
        </button>

        <p className="mt-6 text-sm text-slate-500">
          Need an account?{" "}
          <Link href="/register" className="text-brand-500 hover:underline">
            Register
          </Link>
        </p>
      </div>
    </main>
  );
}
