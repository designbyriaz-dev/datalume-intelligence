import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

const SOLUTIONS = [
  { name: "Commercial Property", blurb: "Lease expiry, rent rolls, vacancy and arrears in one view." },
  { name: "Residential & Lettings", blurb: "Arrears, void periods and portfolio profitability." },
  { name: "Social Housing", blurb: "Stock condition, compliance exceptions and investment planning." },
  { name: "Business & Finance", blurb: "Revenue, expenses and profitability trends, explained plainly." },
  { name: "Public Sector Budgets", blurb: "Budget vs. actual spend, forecast outturn and variance by service area." },
  { name: "Pupil Attendance", blurb: "Attendance rate, persistent absence, and the Pupil Premium attendance gap." },
];

export default function HomePage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <section className="mx-auto max-w-4xl px-6 py-24 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          Turn Your Data Into Decisions.
        </h1>
        <p className="mt-4 text-lg text-slate-600 dark:text-slate-400">
          Your AI-powered data analyst, available anytime. Upload a spreadsheet, ask a question in
          plain English, and get grounded, evidence-based answers — no SQL required.
        </p>
        <div className="mt-8 flex items-center justify-center gap-4">
          <Link
            href="/register"
            className="rounded-md bg-brand-500 px-6 py-3 font-medium text-white hover:bg-brand-600"
          >
            Start Analysing for Free
          </Link>
          <Link
            href="/dashboard"
            className="rounded-md border border-slate-300 px-6 py-3 font-medium hover:border-brand-500 dark:border-slate-700"
          >
            Explore a Live Demo
          </Link>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-6 py-16">
        <h2 className="text-center text-2xl font-semibold">One engine. Every industry.</h2>
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SOLUTIONS.map((s) => (
            <div
              key={s.name}
              className="rounded-lg border border-slate-200 p-5 dark:border-slate-800"
            >
              <h3 className="font-medium">{s.name}</h3>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{s.blurb}</p>
            </div>
          ))}
        </div>
        <p className="mt-6 text-center text-sm text-slate-500">
          <Link href="/solutions" className="text-brand-500 hover:underline">
            See the detail for each industry
          </Link>{" "}
          · four get a dedicated KPI engine today; everything else still gets full analytics.
        </p>
      </section>

      <MarketingFooter />
    </main>
  );
}
