import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

type Feature = { title: string; body: string };

const FEATURES: Feature[] = [
  {
    title: "Property & tenancy records",
    body: "Add properties to a portfolio and track each one's tenancies — tenant name, rent, frequency, and status (upcoming, active, ended) — as structured records, not just a spreadsheet row.",
  },
  {
    title: "A rent ledger that can't drift",
    body: "Charges, payments, adjustments and refunds are append-only entries. A tenancy's balance is always recalculated fresh from the full entry history, so it can never silently go out of sync with reality.",
  },
  {
    title: "Documents & certificates",
    body: "Upload gas safety certificates, EICRs, EPCs, deposit protection certificates, tenancy agreements and more against a property or a specific tenancy, with an expiry date where one applies.",
  },
  {
    title: "Check-in / check-out inventories",
    body: "Record room-by-room condition at check-in and check-out, then compare the two automatically — DataLume highlights exactly which items changed condition, were added, or went missing.",
  },
  {
    title: "A maintenance register",
    body: "Log reported issues with a priority and status, and track them through to resolution. A register for keeping on top of what's outstanding — not a contractor-dispatch system.",
  },
  {
    title: "Configurable compliance checks",
    body: "Define the documents you require on file (a valid gas safety certificate, for example) and DataLume checks your properties against them automatically, with an early-warning window before anything expires.",
  },
];

export default function PropertyIntelligencePage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <section className="mx-auto max-w-4xl px-6 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Property Intelligence</h1>
        <p className="mt-4 text-lg text-slate-600 dark:text-slate-400">
          Structured property and tenancy records, a rent ledger, documents, inventories, a
          maintenance register, and configurable compliance checks — the real, working foundation
          for managing a portfolio, not a spreadsheet upload pretending to be one.
        </p>
      </section>

      <div className="mx-auto max-w-5xl px-6 pb-16">
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-lg border border-slate-200 p-6 dark:border-slate-800">
              <h2 className="text-lg font-semibold">{f.title}</h2>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{f.body}</p>
            </div>
          ))}
        </div>
      </div>

      <section className="mx-auto max-w-3xl px-6 pb-16 text-center">
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          Rent is recorded by hand today — a charge, a payment, an adjustment — rather than
          collected automatically. See{" "}
          <Link href="/rent-collection" className="underline">
            Rent Collection
          </Link>{" "}
          for where automated collection stands.
        </div>
      </section>

      <section className="mx-auto max-w-3xl px-6 pb-20 text-center">
        <div className="flex items-center justify-center gap-4">
          <Link
            href="/register"
            className="rounded-md bg-brand-500 px-6 py-3 font-medium text-white hover:bg-brand-600"
          >
            Start Analysing for Free
          </Link>
          <Link
            href="/inventory-documents"
            className="rounded-md border border-slate-300 px-6 py-3 font-medium hover:border-brand-500 dark:border-slate-700"
          >
            See Inventory & Documents
          </Link>
        </div>
      </section>

      <MarketingFooter />
    </main>
  );
}
