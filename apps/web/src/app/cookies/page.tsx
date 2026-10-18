import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

export default function CookiesPage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <div className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="text-3xl font-bold tracking-tight">Cookie Policy</h1>
        <p className="mt-2 text-sm text-slate-500">Last updated: 18 October 2026</p>

        <div className="mt-6 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <strong>Draft — pending legal review.</strong> This page describes the cookies the
          application actually sets today, in plain English, but has not yet been reviewed by a
          solicitor.
        </div>

        <div className="mt-10 space-y-6 text-slate-600 dark:text-slate-400">
          <p>
            DataLume uses a short list of cookies — all strictly necessary to keep you signed in
            securely. There are no advertising cookies, no third-party tracking or analytics
            cookies, and no cookie consent banner, because nothing here needs your consent under UK
            law: strictly-necessary cookies are exempt.
          </p>

          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left dark:border-slate-800">
                  <th className="py-2 pr-4 font-medium text-slate-900 dark:text-white">Cookie</th>
                  <th className="py-2 pr-4 font-medium text-slate-900 dark:text-white">Purpose</th>
                  <th className="py-2 font-medium text-slate-900 dark:text-white">Duration</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                <tr>
                  <td className="py-3 pr-4 font-mono text-xs">refresh_token</td>
                  <td className="py-3 pr-4">
                    Keeps you signed in between visits. httpOnly — never readable by any page
                    script, including DataLume&rsquo;s own, which is deliberate: it&rsquo;s what
                    makes session hijacking via a script injection attack much harder.
                  </td>
                  <td className="py-3">14 days, or until you sign out</td>
                </tr>
                <tr>
                  <td className="py-3 pr-4 font-mono text-xs">csrf_token</td>
                  <td className="py-3 pr-4">
                    Pairs with refresh_token to confirm a session-refresh request genuinely came
                    from the DataLume application, not a malicious site riding on your cookie.
                  </td>
                  <td className="py-3">14 days, or until you sign out</td>
                </tr>
              </tbody>
            </table>
          </div>

          <p>
            If this changes — for example, if we ever add product analytics — this page will be
            updated first, and a consent banner added if the cookies we introduce actually require
            one.
          </p>

          <p>
            Questions: see the{" "}
            <Link href="/privacy" className="text-brand-500 hover:underline">
              Privacy Policy
            </Link>{" "}
            or email designbyriaz@gmail.com.
          </p>
        </div>
      </div>

      <MarketingFooter />
    </main>
  );
}
