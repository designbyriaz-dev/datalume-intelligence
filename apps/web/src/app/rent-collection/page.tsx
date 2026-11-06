import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

export default function RentCollectionPage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <section className="mx-auto max-w-4xl px-6 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Rent Collection</h1>
        <p className="mt-4 text-lg text-slate-600 dark:text-slate-400">
          A clear rent ledger today. Pay-by-link collection via Stripe is built, and stays switched
          off until our own Stripe Connect approval is in place.
        </p>
      </section>

      <div className="mx-auto max-w-3xl px-6 pb-16">
        <div className="rounded-lg border border-slate-200 p-6 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900 dark:text-green-200">
              Live today
            </span>
            <h2 className="text-lg font-semibold">A rent ledger you can trust</h2>
          </div>
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">
            Record charges, payments, adjustments and refunds against a tenancy as they happen. Every
            entry is append-only — nothing is ever edited or deleted in place — so a tenancy&rsquo;s
            balance is always reconstructed fresh from the full history and can never quietly drift
            from what actually happened. See{" "}
            <Link href="/property-intelligence" className="text-brand-500 hover:underline">
              Property Intelligence
            </Link>{" "}
            for the rest of what&rsquo;s built around it.
          </p>
        </div>

        <div className="mt-6 rounded-lg border border-amber-300 bg-amber-50 p-6 dark:border-amber-800 dark:bg-amber-950">
          <div className="flex items-center gap-2">
            <span className="rounded bg-amber-200 px-2 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-800 dark:text-amber-100">
              Built — switched off until Stripe approval
            </span>
            <h2 className="text-lg font-semibold text-amber-900 dark:text-amber-100">
              Pay-by-link rent collection (Stripe Connect)
            </h2>
          </div>
          <p className="mt-3 text-sm text-amber-900 dark:text-amber-200">
            A landlord or agent can request payment for a specific rent charge; the tenant pays via a
            Stripe-hosted page from a link emailed to them, with no DataLume account needed. Moving
            real tenant money is a regulated activity, so this stays switched off platform-wide until
            our own Stripe Connect platform application is approved and a real payment has been
            tested end-to-end — we won&rsquo;t market it as live before it genuinely is. Recurring
            auto-debit, a tenant portal, and refunds through Stripe are not part of this first version.
          </p>
        </div>
      </div>

      <section className="mx-auto max-w-3xl px-6 pb-20 text-center">
        <Link
          href="/register"
          className="rounded-md bg-brand-500 px-6 py-3 font-medium text-white hover:bg-brand-600"
        >
          Start Analysing for Free
        </Link>
      </section>

      <MarketingFooter />
    </main>
  );
}
