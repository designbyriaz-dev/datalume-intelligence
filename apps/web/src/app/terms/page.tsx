import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

export default function TermsPage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <div className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="text-3xl font-bold tracking-tight">Terms of Service</h1>
        <p className="mt-2 text-sm text-slate-500">Last updated: 18 October 2026</p>

        <div className="mt-6 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <strong>Draft — pending legal review.</strong> This page describes how DataLume
          Intelligence actually works today, in plain English, but has not yet been reviewed by a
          solicitor and is not yet in effect as a binding agreement.
        </div>

        <div className="mt-10 space-y-10 text-slate-600 dark:text-slate-400">
          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">1. Who these terms are with</h2>
            <p className="mt-3">
              These terms are between you (or the organization you represent) and DataLume
              Intelligence Ltd (&ldquo;DataLume&rdquo;, &ldquo;we&rdquo;, &ldquo;us&rdquo;), a company
              registered in England and Wales. By creating an account or using the service, you
              agree to these terms.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">2. What the service is</h2>
            <p className="mt-3">
              DataLume lets you upload spreadsheet and CSV data, clean and profile it, ask questions
              of it using an AI analyst, and generate dashboards and reports from it. See{" "}
              <Link href="/features" className="text-brand-500 hover:underline">
                Features
              </Link>{" "}
              for the full current list — the service changes and grows, and what&rsquo;s actually
              built is documented there, not promised in advance here.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">3. Your account</h2>
            <p className="mt-3">
              You&rsquo;re responsible for keeping your login credentials secure and for activity
              that happens under your account. Tell us promptly if you believe your account has
              been compromised. You must be old enough to form a binding contract in your
              jurisdiction to use the service.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">4. Your data and content</h2>
            <p className="mt-3">
              You own the data you upload. You give us permission to store it, process it, and send
              the relevant parts of it to our AI provider, solely to provide the service to you —
              see the{" "}
              <Link href="/privacy" className="text-brand-500 hover:underline">
                Privacy Policy
              </Link>{" "}
              for exactly what that involves. We don&rsquo;t use your uploaded data to train our own
              or anyone else&rsquo;s general-purpose AI models, and we don&rsquo;t sell it.
            </p>
            <p className="mt-3">
              You&rsquo;re responsible for having the right to upload whatever data you upload,
              including any personal data about other people it may contain.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">5. AI features</h2>
            <p className="mt-3">
              The AI analyst and AI-generated report summaries are built to ground their answers in
              real calculations over your actual data, not invent figures — but AI output can still
              be wrong, and prose summaries in particular may misinterpret context. Treat AI output
              as a starting point for your own judgement, not professional advice, and verify
              anything you rely on for a material decision.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">6. Subscriptions and billing</h2>
            <p className="mt-3">
              Paid plans are billed through Stripe on the cadence you choose (monthly or annual).
              You can upgrade, downgrade, or cancel at any time from your account&rsquo;s billing
              settings; cancellation takes effect at the end of your current billing period unless
              stated otherwise at checkout. Fees already paid are non-refundable except where
              required by law.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">7. Acceptable use</h2>
            <p className="mt-3">
              Don&rsquo;t use the service to upload unlawful content, attempt to access another
              account or workspace you&rsquo;re not authorised to see, probe or disrupt the
              service&rsquo;s security, or resell access without our agreement.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">8. Ending your account</h2>
            <p className="mt-3">
              You can delete a workspace, or your whole account, at any time from Settings — see the{" "}
              <Link href="/security" className="text-brand-500 hover:underline">
                Security
              </Link>{" "}
              page for exactly what that deletes. We may suspend or terminate an account that
              breaches these terms, with notice where practical.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">9. Service availability</h2>
            <p className="mt-3">
              We aim to keep the service available and reliable but don&rsquo;t currently guarantee
              a specific uptime commitment. We&rsquo;ll give notice of planned maintenance where
              practical.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">10. Liability</h2>
            <p className="mt-3">
              Nothing in these terms limits liability where the law doesn&rsquo;t allow it (for
              example, death or personal injury caused by negligence, or fraud). Subject to that, our
              liability to you for any claim arising from the service is limited to the amount you
              paid us in the 12 months before the claim arose.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">11. Changes to these terms</h2>
            <p className="mt-3">
              We may update these terms as the service changes. We&rsquo;ll update the date at the
              top of this page when we do; continuing to use the service after a change means you
              accept the updated terms.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">12. Governing law</h2>
            <p className="mt-3">These terms are governed by the law of England and Wales.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">13. Contact</h2>
            <p className="mt-3">
              Questions about these terms: designbyriaz@gmail.com.
            </p>
          </section>
        </div>
      </div>

      <MarketingFooter />
    </main>
  );
}
