import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

export default function AboutPage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <section className="mx-auto max-w-3xl px-6 py-20">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl text-center">About DataLume</h1>

        <div className="mt-10 space-y-8 text-slate-600 dark:text-slate-400">
          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">What we&rsquo;re building</h2>
            <p className="mt-3">
              DataLume Intelligence is an AI-powered data analyst for people who work with
              spreadsheets, rent rolls, and asset registers instead of a data team. Upload a file,
              get a real data-quality profile, clean it, ask it questions in plain English, and get
              answers grounded in your actual numbers — not a model guessing at them. Six industries
              (commercial property, residential lettings, social housing, business finance, public
              sector budgets, and pupil attendance) get a dedicated KPI engine and report templates
              built for that data shape; everything else still gets full analytics without a
              fixed KPI set invented for a domain we don&rsquo;t model yet.
            </p>
            <p className="mt-3">
              We&rsquo;ve since extended that into structured property and tenancy management —
              rent ledgers, documents, inventories, maintenance tracking, and configurable
              compliance checks — built the same way as everything else here: real, tested, and
              verified against a running system before it&rsquo;s called done.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">How we work</h2>
            <p className="mt-3">
              We&rsquo;d rather ship something real and incomplete than something that looks
              finished and isn&rsquo;t. We don&rsquo;t claim certifications we don&rsquo;t hold, we
              don&rsquo;t invent testimonials, and we don&rsquo;t market a feature as live before it
              genuinely is — see{" "}
              <Link href="/rent-collection" className="text-brand-500 hover:underline">
                Rent Collection
              </Link>{" "}
              for an example of us saying plainly what isn&rsquo;t built yet. If you want the
              unvarnished list of what&rsquo;s actually implemented versus still planned, the
              project tracks that openly in{" "}
              <code className="rounded bg-slate-100 px-1 text-sm dark:bg-slate-800">
                docs/CHECKLIST.md
              </code>
              .
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Who we are</h2>
            <p className="mt-3">
              DataLume Intelligence Ltd is a company registered in England and Wales. We&rsquo;re
              early — if you want to talk to a real person about the product, see{" "}
              <Link href="/contact" className="text-brand-500 hover:underline">
                Contact
              </Link>
              .
            </p>
          </section>
        </div>

        <div className="mt-12 flex items-center justify-center gap-4">
          <Link
            href="/register"
            className="rounded-md bg-brand-500 px-6 py-3 font-medium text-white hover:bg-brand-600"
          >
            Start Analysing for Free
          </Link>
          <Link
            href="/features"
            className="rounded-md border border-slate-300 px-6 py-3 font-medium hover:border-brand-500 dark:border-slate-700"
          >
            See every feature
          </Link>
        </div>
      </section>

      <MarketingFooter />
    </main>
  );
}
