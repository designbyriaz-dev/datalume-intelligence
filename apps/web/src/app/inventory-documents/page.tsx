import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

const DOCUMENT_TYPES = [
  "Tenancy agreement",
  "Gas safety certificate",
  "EICR (electrical safety)",
  "EPC (energy performance certificate)",
  "Deposit protection certificate",
  "Right to rent check",
  "Insurance certificate",
  "Inventory report",
];

const CONDITIONS = ["Excellent", "Good", "Fair", "Poor", "Damaged", "Missing"];

export default function InventoryDocumentsPage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <section className="mx-auto max-w-4xl px-6 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Inventory &amp; Documents</h1>
        <p className="mt-4 text-lg text-slate-600 dark:text-slate-400">
          Every certificate and agreement in one place, and a room-by-room record of condition at
          check-in and check-out — with an automatic comparison between the two.
        </p>
      </section>

      <div className="mx-auto max-w-5xl grid grid-cols-1 gap-8 px-6 pb-16 sm:grid-cols-2">
        <div className="rounded-lg border border-slate-200 p-6 dark:border-slate-800">
          <h2 className="text-lg font-semibold">Documents</h2>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
            Upload a PDF, JPEG, PNG or Word document against a property, or a specific tenancy
            within it — scanned for malicious content before it&rsquo;s stored, with an expiry date
            where one applies so DataLume&rsquo;s compliance checks can use it.
          </p>
          <h3 className="mt-4 text-xs font-medium uppercase text-slate-500">Recognised document types</h3>
          <ul className="mt-2 grid grid-cols-1 gap-1 text-sm text-slate-600 dark:text-slate-400 sm:grid-cols-2">
            {DOCUMENT_TYPES.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </div>

        <div className="rounded-lg border border-slate-200 p-6 dark:border-slate-800">
          <h2 className="text-lg font-semibold">Inventories</h2>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
            Record a check-in inventory room by room — item, condition, and notes — then do the same
            at check-out. DataLume compares the two automatically and tells you exactly what changed.
          </p>
          <h3 className="mt-4 text-xs font-medium uppercase text-slate-500">Condition scale</h3>
          <ul className="mt-2 flex flex-wrap gap-2 text-sm text-slate-600 dark:text-slate-400">
            {CONDITIONS.map((c) => (
              <li key={c} className="rounded bg-slate-100 px-2 py-0.5 dark:bg-slate-800">
                {c}
              </li>
            ))}
          </ul>
          <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
            A comparison between two inventories reports each item as unchanged, changed (condition
            and/or notes), added, or removed — so a dispute over a damage deposit has a real record
            to point to, not just memory.
          </p>
        </div>
      </div>

      <section className="mx-auto max-w-3xl px-6 pb-20 text-center">
        <div className="flex items-center justify-center gap-4">
          <Link
            href="/register"
            className="rounded-md bg-brand-500 px-6 py-3 font-medium text-white hover:bg-brand-600"
          >
            Start Analysing for Free
          </Link>
          <Link
            href="/property-intelligence"
            className="rounded-md border border-slate-300 px-6 py-3 font-medium hover:border-brand-500 dark:border-slate-700"
          >
            See Property Intelligence
          </Link>
        </div>
      </section>

      <MarketingFooter />
    </main>
  );
}
