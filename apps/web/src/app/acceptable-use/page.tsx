import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

export default function AcceptableUsePage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <div className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="text-3xl font-bold tracking-tight">Acceptable Use Policy</h1>
        <p className="mt-2 text-sm text-slate-500">Last updated: 4 November 2026</p>

        <div className="mt-6 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <strong>Draft — pending legal review.</strong> This page describes how we expect DataLume
          Intelligence to be used, in plain English, but has not yet been reviewed by a solicitor
          and is not yet in effect as a binding policy.
        </div>

        <div className="mt-10 space-y-10 text-slate-600 dark:text-slate-400">
          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">1. Scope</h2>
            <p className="mt-3">
              This policy applies to everyone who accesses DataLume Intelligence — the dashboard,
              the API, and any data uploaded to either — and sits alongside our{" "}
              <Link href="/terms" className="text-brand-500 hover:underline">
                Terms of Service
              </Link>
              . Where the two conflict, the Terms of Service govern.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">2. Don&rsquo;t misuse the service</h2>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>
                Don&rsquo;t attempt to probe, scan, or test the vulnerability of the service, or
                breach its authentication or tenant-isolation controls, except through our
                responsible-disclosure process — see{" "}
                <Link href="/security" className="text-brand-500 hover:underline">
                  Security
                </Link>
                .
              </li>
              <li>Don&rsquo;t attempt to access another account, workspace, or organization&rsquo;s data without authorization.</li>
              <li>Don&rsquo;t reverse-engineer, decompile, or attempt to extract the underlying models or source code, beyond what&rsquo;s already open about this project.</li>
              <li>Don&rsquo;t use the service to send spam, conduct phishing, or distribute malware.</li>
              <li>Don&rsquo;t attempt to circumvent plan limits, rate limits, or billing.</li>
              <li>Don&rsquo;t use automated means to scrape or bulk-extract data from the service outside the documented API.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">3. Don&rsquo;t upload unlawful content</h2>
            <p className="mt-3">
              Don&rsquo;t upload data you don&rsquo;t have the right to upload, or content that is
              illegal, infringes someone else&rsquo;s intellectual property, or violates someone
              else&rsquo;s privacy rights. You&rsquo;re responsible for having a lawful basis to
              process any personal data you upload — see our{" "}
              <Link href="/privacy" className="text-brand-500 hover:underline">
                Privacy Policy
              </Link>{" "}
              for how we handle it on your behalf.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">4. The AI analyst</h2>
            <p className="mt-3">
              The AI analyst answers questions grounded in the data you&rsquo;ve uploaded. Don&rsquo;t
              use it to try to extract its system prompt or underlying instructions, to generate
              content unrelated to analysing your data, or to attempt prompt injection against the
              tools it has access to.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">5. Compliance features aren&rsquo;t legal advice</h2>
            <p className="mt-3">
              If you use the compliance-rules engine, remember it checks your properties against
              rules you define yourself — it does not determine or certify that a property meets any
              particular law or regulation. Don&rsquo;t represent a DataLume compliance check to a
              third party (a tenant, a regulator, an insurer) as an independent legal or regulatory
              determination.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">6. Enforcement</h2>
            <p className="mt-3">
              We may suspend or terminate access for a violation of this policy. If you believe
              we&rsquo;ve made a mistake, email{" "}
              <a href="mailto:support@datalume.co.uk" className="text-brand-500 hover:underline">
                support@datalume.co.uk
              </a>{" "}
              and we&rsquo;ll look into it.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">7. Changes</h2>
            <p className="mt-3">
              We may update this policy as the product changes. Material changes will be reflected
              here with an updated date.
            </p>
          </section>
        </div>
      </div>

      <MarketingFooter />
    </main>
  );
}
