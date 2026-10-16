import Link from "next/link";
import { NavBar } from "@/components/NavBar";

const SOLUTIONS = [
  { name: "Commercial Property", blurb: "Lease expiry, rent rolls, vacancy and NOI in one view." },
  { name: "Residential & Lettings", blurb: "Arrears, void periods and portfolio profitability." },
  { name: "Social Housing", blurb: "Stock condition, compliance exceptions and investment planning." },
  { name: "Business & Finance", blurb: "Revenue, cash flow and customer trends, explained plainly." },
  { name: "Public Sector", blurb: "Service demand, spend and outcomes across your area." },
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
      </section>

      <footer className="border-t border-slate-200 px-6 py-8 text-center text-sm text-slate-500 dark:border-slate-800">
        DataLume Intelligence — built incrementally. See{" "}
        <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">docs/CHECKLIST.md</code> for what
        is live today.
      </footer>
    </main>
  );
}
