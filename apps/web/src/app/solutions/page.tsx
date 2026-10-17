import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

type Pack = {
  name: string;
  summary: string;
  kpis: string[];
  questions: string[];
  reports: string[];
};

const PACKS: Pack[] = [
  {
    name: "Commercial Property",
    summary: "Rent roll, occupancy, arrears, and lease-expiry risk for a commercial portfolio.",
    kpis: [
      "Total rent roll & average rent",
      "Occupancy & vacancy rate",
      "Total arrears & arrears as % of rent roll",
      "Leases expiring within 12 months",
      "Top 5 tenant concentration",
    ],
    questions: [
      "What's our total rent roll and how is it split by category?",
      "Which leases are expiring in the next 12 months?",
      "How concentrated is our income among our top tenants?",
    ],
    reports: ["Commercial Property Portfolio Report"],
  },
  {
    name: "Residential Property & Lettings",
    summary: "Occupancy, arrears, and maintenance spend across a residential or lettings portfolio.",
    kpis: [
      "Total rent roll & average rent",
      "Occupancy & vacancy rate",
      "Total arrears & arrears as % of rent roll",
      "Total maintenance cost",
    ],
    questions: [
      "What's our current occupancy rate?",
      "Which properties have the highest arrears?",
      "Which tenancies are ending soon?",
    ],
    reports: ["Residential Property Portfolio Report", "Residential Repairs & Maintenance Report"],
  },
  {
    name: "Social Housing & Asset Management",
    summary: "Stock condition, inspection compliance, and investment planning across your properties.",
    kpis: [
      "Total properties & void rate",
      "Properties overdue an inspection",
      "Total repair cost & average repair cost per property",
      "Total planned investment",
    ],
    questions: [
      "How many properties are overdue an inspection?",
      "What's our total planned investment this year?",
      "Which properties have the highest repair costs?",
    ],
    reports: ["Social Housing Asset Report", "Social Housing Compliance Exceptions Report"],
  },
  {
    name: "Business & Financial Intelligence",
    summary: "Revenue, expenses, and profitability trends for any business, explained plainly.",
    kpis: [
      "Total revenue & total expenses",
      "Net profit & profit margin",
      "Average monthly revenue",
    ],
    questions: [
      "What's our net profit this period?",
      "How has revenue trended month to month?",
      "Which expense categories are largest?",
    ],
    reports: ["Business Performance Report"],
  },
  {
    name: "Public Sector Budget",
    summary: "UK local authority revenue budget monitoring — budget vs. actual spend vs. forecast outturn by service area.",
    kpis: [
      "Total budget, actual spend & forecast outturn",
      "Overall variance (£ and %)",
      "Budget utilisation rate",
      "Over-budget line count & top 5 overspend concentration",
    ],
    questions: [
      "Which service areas are forecast to overspend this year?",
      "What's our total budget variance and is it improving or worsening?",
      "What's our current budget utilisation rate?",
    ],
    reports: [],
  },
];

export default function SolutionsPage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <section className="mx-auto max-w-4xl px-6 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Built for how your industry works</h1>
        <p className="mt-4 text-lg text-slate-600 dark:text-slate-400">
          Five industries get a dedicated KPI engine, automatic field mapping, and purpose-built
          reports out of the box. Every other industry still gets full data profiling and all seven
          analytics tools — just not a fixed KPI set invented for a domain DataLume doesn't model yet.
        </p>
      </section>

      <div className="mx-auto max-w-5xl space-y-10 px-6 pb-16">
        {PACKS.map((pack) => (
          <div key={pack.name} className="rounded-lg border border-slate-200 p-6 dark:border-slate-800">
            <h2 className="text-xl font-semibold">{pack.name}</h2>
            <p className="mt-1 text-slate-600 dark:text-slate-400">{pack.summary}</p>

            <div className="mt-5 grid grid-cols-1 gap-6 sm:grid-cols-3">
              <div>
                <h3 className="text-xs font-medium uppercase text-slate-500">Key metrics</h3>
                <ul className="mt-2 space-y-1 text-sm text-slate-600 dark:text-slate-400">
                  {pack.kpis.map((k) => (
                    <li key={k}>{k}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="text-xs font-medium uppercase text-slate-500">You can ask things like</h3>
                <ul className="mt-2 space-y-1 text-sm text-slate-600 dark:text-slate-400">
                  {pack.questions.map((q) => (
                    <li key={q}>&ldquo;{q}&rdquo;</li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="text-xs font-medium uppercase text-slate-500">Report templates</h3>
                <ul className="mt-2 space-y-1 text-sm text-slate-600 dark:text-slate-400">
                  {pack.reports.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                  <li>Executive Intelligence Report (AI-generated summary)</li>
                </ul>
              </div>
            </div>
          </div>
        ))}
      </div>

      <section className="mx-auto max-w-3xl px-6 pb-20 text-center">
        <h2 className="text-xl font-semibold">Not one of these?</h2>
        <p className="mt-2 text-slate-600 dark:text-slate-400">
          General data analysis, education, operations &amp; logistics, or anything else — pick
          &ldquo;Something else&rdquo; when you create a workspace. You'll get the same upload,
          cleaning, AI analyst, and dashboard tools, without a dedicated KPI pack.
        </p>
        <div className="mt-8 flex items-center justify-center gap-4">
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
