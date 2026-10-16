"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";

export function NavBar() {
  const { user, logout, loading } = useAuth();

  return (
    <header className="flex items-center justify-between border-b border-slate-200 px-6 py-4 dark:border-slate-800">
      <Link href="/" className="text-lg font-semibold tracking-tight">
        DataLume <span className="text-brand-500">Intelligence</span>
      </Link>
      <nav className="flex items-center gap-6 text-sm">
        <Link href="/pricing" className="hover:text-brand-500">
          Pricing
        </Link>
        {loading ? null : user ? (
          <>
            <Link href="/dashboard" className="hover:text-brand-500">
              Dashboard
            </Link>
            {user.is_platform_admin && (
              <Link href="/dashboard/admin" className="hover:text-brand-500">
                Admin
              </Link>
            )}
            <button onClick={logout} className="text-slate-500 hover:text-brand-500">
              Log out
            </button>
          </>
        ) : (
          <>
            <Link href="/login" className="hover:text-brand-500">
              Log in
            </Link>
            <Link
              href="/register"
              className="rounded-md bg-brand-500 px-4 py-2 font-medium text-white hover:bg-brand-600"
            >
              Start Analysing for Free
            </Link>
          </>
        )}
      </nav>
    </header>
  );
}
