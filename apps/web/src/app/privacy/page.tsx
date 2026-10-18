import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

export default function PrivacyPage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <div className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="text-3xl font-bold tracking-tight">Privacy Policy</h1>
        <p className="mt-2 text-sm text-slate-500">Last updated: 18 October 2026</p>

        <div className="mt-6 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <strong>Draft — pending legal review.</strong> This page describes how DataLume
          Intelligence actually handles data today, in plain English, but has not yet been reviewed
          by a solicitor and is not yet in effect as a finalised policy.
        </div>

        <div className="mt-10 space-y-10 text-slate-600 dark:text-slate-400">
          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Who we are</h2>
            <p className="mt-3">
              DataLume Intelligence Ltd, a company registered in England and Wales, is the data
              controller for your account details and the data processor for the content of files
              your organization uploads. If your organization needs a formal processor agreement in
              place, see the{" "}
              <Link href="/dpa" className="text-brand-500 hover:underline">
                Data Processing Agreement
              </Link>
              .
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">What we collect</h2>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>
                <strong className="text-slate-900 dark:text-white">Account data:</strong> email
                address, full name, hashed password (we never store or can see your actual
                password), and MFA status if you turn it on.
              </li>
              <li>
                <strong className="text-slate-900 dark:text-white">Content you upload:</strong> the
                CSV/Excel files you upload, every version produced by cleaning operations, and any
                reports or dashboards you generate from them.
              </li>
              <li>
                <strong className="text-slate-900 dark:text-white">AI analyst conversations:</strong>{" "}
                the questions you ask and the answers given, saved so you can return to a
                conversation later.
              </li>
              <li>
                <strong className="text-slate-900 dark:text-white">Usage and security data:</strong>{" "}
                sign-ins, API key activity, organization membership changes, and similar
                security-relevant events — see the{" "}
                <Link href="/security" className="text-brand-500 hover:underline">
                  Security
                </Link>{" "}
                page for exactly what&rsquo;s logged.
              </li>
              <li>
                <strong className="text-slate-900 dark:text-white">Billing data:</strong> handled by
                Stripe, our payment processor — we don&rsquo;t store your card details ourselves.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Why we process it, and our lawful basis</h2>
            <p className="mt-3">
              Mainly to perform the contract we have with you — running the service you signed up
              for (profiling your data, computing KPIs, answering your questions, generating
              reports, billing your subscription). Some processing (security logging, abuse
              prevention) is on the basis of our legitimate interest in keeping the service secure
              and reliable.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Who we share it with</h2>
            <p className="mt-3">We use a small number of sub-processors to run the service:</p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>
                <strong className="text-slate-900 dark:text-white">Anthropic</strong> — processes the
                portion of your data needed to answer an AI analyst question or generate an
                AI-written report summary. Per Anthropic&rsquo;s own commercial API terms, data sent
                this way isn&rsquo;t used to train their models by default.
              </li>
              <li>
                <strong className="text-slate-900 dark:text-white">Cloudflare (R2)</strong> — stores
                your uploaded files and generated reports.
              </li>
              <li>
                <strong className="text-slate-900 dark:text-white">Stripe</strong> — processes
                payments and stores your billing/card details on our behalf.
              </li>
              <li>
                <strong className="text-slate-900 dark:text-white">Our email provider</strong> —
                sends transactional email (verification, password reset, scheduled report
                delivery).
              </li>
            </ul>
            <p className="mt-3">
              We don&rsquo;t sell your data, and we don&rsquo;t share it with anyone else for their
              own marketing purposes.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">International transfers</h2>
            <p className="mt-3">
              Some of the sub-processors above may process data outside the UK. Where that happens,
              we rely on the safeguards those providers offer for international transfers (such as
              the UK&rsquo;s International Data Transfer Addendum or equivalent standard
              contractual clauses).
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">How long we keep it</h2>
            <p className="mt-3">
              For as long as your account exists. Delete a workspace, or your whole account, at any
              time from Settings, and the underlying data — including stored files — is deleted,
              not just hidden; see the{" "}
              <Link href="/security" className="text-brand-500 hover:underline">
                Security
              </Link>{" "}
              page for exactly what that covers.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Your rights</h2>
            <p className="mt-3">Under UK GDPR, you can ask us to:</p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>give you a copy of the personal data we hold about you (access);</li>
              <li>correct it if it&rsquo;s wrong (rectification) — or just update it yourself in Settings;</li>
              <li>
                delete it (erasure) — self-serve, from Settings, at any time, rather than needing to
                ask us;
              </li>
              <li>restrict or object to certain processing; and</li>
              <li>receive your data in a portable format.</li>
            </ul>
            <p className="mt-3">
              To exercise any of these, email designbyriaz@gmail.com. You can also complain to the
              UK&rsquo;s Information Commissioner&rsquo;s Office (ico.org.uk) if you think
              we&rsquo;ve handled your data wrongly.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Cookies</h2>
            <p className="mt-3">
              See the{" "}
              <Link href="/cookies" className="text-brand-500 hover:underline">
                Cookie Policy
              </Link>{" "}
              for the specific cookies we use.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Children&rsquo;s privacy</h2>
            <p className="mt-3">
              The service is intended for business use and isn&rsquo;t directed at children. We
              don&rsquo;t knowingly collect personal data from children.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Changes to this policy</h2>
            <p className="mt-3">
              We&rsquo;ll update the date at the top of this page whenever this policy changes.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Contact</h2>
            <p className="mt-3">
              Questions about this policy, or to exercise any of your rights above: designbyriaz@gmail.com.
            </p>
          </section>
        </div>
      </div>

      <MarketingFooter />
    </main>
  );
}
