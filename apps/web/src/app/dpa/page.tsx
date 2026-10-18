import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

export default function DpaPage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <div className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="text-3xl font-bold tracking-tight">Data Processing Agreement</h1>
        <p className="mt-2 text-sm text-slate-500">Last updated: 18 October 2026</p>

        <div className="mt-6 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <strong>Draft — pending legal review.</strong> This is a standard-shape UK GDPR Article 28
          processor agreement reflecting how the service actually processes data today. It has not
          been reviewed by a solicitor and is not yet in effect. If your organization needs a signed
          DPA in place, contact us — this page is a starting point, not a substitute for a
          negotiated, countersigned agreement.
        </div>

        <div className="mt-10 space-y-10 text-slate-600 dark:text-slate-400">
          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">1. Parties and relationship</h2>
            <p className="mt-3">
              This agreement is between the customer organization (&ldquo;Controller&rdquo;) and
              DataLume Intelligence Ltd (&ldquo;Processor&rdquo;). It applies whenever the
              Processor processes personal data on the Controller&rsquo;s behalf as part of the
              DataLume service, and supplements the Terms of Service.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">2. Subject matter and duration</h2>
            <p className="mt-3">
              Processing of personal data contained in files the Controller uploads to the service,
              for the duration of the Controller&rsquo;s subscription, or until the Controller
              deletes the relevant workspace or account.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">3. Nature and purpose of processing</h2>
            <p className="mt-3">
              Storage, profiling, cleaning, analysis, and report/dashboard generation of uploaded
              data, including sending the relevant portion of it to the AI sub-processor below when
              the Controller&rsquo;s users ask the AI analyst a question or request an AI-generated
              report summary.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">4. Categories of data subjects and personal data</h2>
            <p className="mt-3">
              Whatever the Controller includes in uploaded files — typically the Controller&rsquo;s
              own customers, tenants, employees, pupils, or similar individuals depending on the
              Controller&rsquo;s industry, and whatever columns of data about them the Controller
              chooses to upload. The Processor doesn&rsquo;t control or review what the Controller
              uploads.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">5. Processor obligations</h2>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>Process personal data only on the Controller&rsquo;s documented instructions (including via the Controller&rsquo;s own use of the service).</li>
              <li>Ensure anyone processing the data under the Processor&rsquo;s authority is subject to confidentiality.</li>
              <li>
                Implement appropriate technical and organisational security measures — see the{" "}
                <a href="/security" className="text-brand-500 hover:underline">
                  Security
                </a>{" "}
                page for the specifics.
              </li>
              <li>Assist the Controller in responding to data subject rights requests and in meeting its own UK GDPR obligations.</li>
              <li>Notify the Controller without undue delay on becoming aware of a personal data breach affecting the Controller&rsquo;s data.</li>
              <li>Delete or return all personal data at the end of the engagement, at the Controller&rsquo;s choice — in practice, by the Controller deleting the relevant workspace or account, which deletes the underlying data.</li>
              <li>Make available the information reasonably necessary to demonstrate compliance with this agreement.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">6. Sub-processors</h2>
            <p className="mt-3">
              The Controller authorises the Processor to use the following sub-processors, each
              engaged only for the purpose stated:
            </p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li><strong className="text-slate-900 dark:text-white">Anthropic</strong> — AI processing for the AI analyst and AI-generated report summaries.</li>
              <li><strong className="text-slate-900 dark:text-white">Cloudflare (R2)</strong> — object storage for uploaded files and generated reports.</li>
              <li><strong className="text-slate-900 dark:text-white">Stripe</strong> — payment processing and billing data.</li>
              <li><strong className="text-slate-900 dark:text-white">Our email provider</strong> — transactional email delivery.</li>
            </ul>
            <p className="mt-3">
              We&rsquo;ll give the Controller reasonable notice before adding a new sub-processor, so
              the Controller can object on reasonable grounds.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">7. International transfers</h2>
            <p className="mt-3">
              Where a sub-processor processes data outside the UK, the Processor relies on that
              sub-processor&rsquo;s own appropriate safeguards (such as the UK International Data
              Transfer Addendum or equivalent standard contractual clauses).
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">8. Audit</h2>
            <p className="mt-3">
              The Processor will provide information reasonably necessary to demonstrate compliance
              with this agreement, and permit and contribute to audits conducted by the Controller
              or an auditor mandated by the Controller, on reasonable notice.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">9. Contact</h2>
            <p className="mt-3">
              To discuss or request a countersigned version of this agreement: riaz@datalume.co.uk.
            </p>
          </section>
        </div>
      </div>

      <MarketingFooter />
    </main>
  );
}
