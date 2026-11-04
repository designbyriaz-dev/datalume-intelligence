import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

type Feature = { title: string; body: string };

const KPI_FEATURES: Feature[] = [
  {
    title: "Stock condition & investment planning",
    body: "Upload your rent roll or asset register and get total properties, void rate, total repair cost, average repair cost per property, and total planned investment — computed from your real data, not estimated.",
  },
  {
    title: "Inspection compliance",
    body: "See how many properties are overdue an inspection, straight from the KPI engine, plus a dedicated Compliance Exceptions Report for anything that needs attention.",
  },
];

const PORTFOLIO_FEATURES: Feature[] = [
  {
    title: "Property & tenancy records",
    body: "Structured records for every property and tenancy in your stock, not a static spreadsheet — see Property Intelligence for the full detail.",
  },
  {
    title: "Configurable compliance checks",
    body: "Define the documents a property needs on file — gas safety, EICR, EPC, and more — and DataLume checks every property automatically, with the exact status language (passes, potential issue, missing information, action may be overdue, requires human review) rather than a blunt pass/fail. This checks what you've told DataLume you require — it is not a legal compliance determination.",
  },
  {
    title: "Maintenance register & inventories",
    body: "Track reported repairs through to resolution, and record condition at check-in and check-out with an automatic before/after comparison.",
  },
];

export default function HousingIntelligencePage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <section className="mx-auto max-w-4xl px-6 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Housing Intelligence</h1>
        <p className="mt-4 text-lg text-slate-600 dark:text-slate-400">
          For social housing providers and larger residential portfolios: a dedicated KPI engine
          over your asset data, plus the same property records, documents, inventories, and
          compliance checks every DataLume portfolio gets.
        </p>
      </section>

      <div className="mx-auto max-w-5xl px-6 pb-10">
        <h2 className="text-xl font-semibold">Social Housing & Asset Management KPI pack</h2>
        <p className="mt-2 text-slate-600 dark:text-slate-400">
          Upload a stock condition spreadsheet or asset register and get a dedicated KPI engine and
          report templates built for this data shape — see{" "}
          <Link href="/solutions" className="text-brand-500 hover:underline">
            Solutions
          </Link>{" "}
          for the full industry-pack list.
        </p>
        <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-2">
          {KPI_FEATURES.map((f) => (
            <div key={f.title} className="rounded-lg border border-slate-200 p-6 dark:border-slate-800">
              <h3 className="text-lg font-semibold">{f.title}</h3>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{f.body}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="mx-auto max-w-5xl px-6 pb-16">
        <h2 className="text-xl font-semibold">Property management foundation</h2>
        <p className="mt-2 text-slate-600 dark:text-slate-400">
          The same structured property/tenancy records, documents and compliance engine every
          DataLume portfolio runs on — see{" "}
          <Link href="/property-intelligence" className="text-brand-500 hover:underline">
            Property Intelligence
          </Link>{" "}
          for the detail.
        </p>
        <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-3">
          {PORTFOLIO_FEATURES.map((f) => (
            <div key={f.title} className="rounded-lg border border-slate-200 p-6 dark:border-slate-800">
              <h3 className="text-lg font-semibold">{f.title}</h3>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{f.body}</p>
            </div>
          ))}
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
            href="/compliance-intelligence"
            className="rounded-md border border-slate-300 px-6 py-3 font-medium hover:border-brand-500 dark:border-slate-700"
          >
            See Compliance Intelligence
          </Link>
        </div>
      </section>

      <MarketingFooter />
    </main>
  );
}
