import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

type Step = { title: string; body: string };

const STEPS: Step[] = [
  {
    title: "1. Create a workspace",
    body:
      "Tell DataLume what you want to analyse — commercial property, residential lettings, social housing, business finance, or something else entirely. Picking a match tunes the KPIs, reports, and questions you'll see; picking \"something else\" keeps everything general-purpose.",
  },
  {
    title: "2. Upload a CSV or Excel file",
    body:
      "Drop in your data as it actually looks — messy headers and all. DataLume checks it's genuinely what it claims to be (not a disguised executable), caps size and inflation on Excel files, and immediately profiles every column: type, missing values, invalid values, duplicates, and an overall quality score.",
  },
  {
    title: "3. Review and clean",
    body:
      "See exactly what's wrong before you trust any number. Fix it with one of eleven cleaning operations — deduplicate, fill gaps, normalise text, filter rows, merge or split columns, pivot or unpivot, and more. Every step creates a new version; your original upload is never touched.",
  },
  {
    title: "4. Confirm the field mapping",
    body:
      "If your workspace matches an industry pack, DataLume automatically matches your columns to the fields that pack's KPIs need — review the match, correct anything it got wrong, and confirm it once. Every KPI from here on uses exactly that mapping.",
  },
  {
    title: "5. Get your numbers",
    body:
      "See your KPIs computed instantly, ask the AI analyst a question in plain English and watch it pick a real analytics tool to answer with, or generate a PDF report — deterministic or, for one report type, with an AI-written executive summary on top. All three read from the same engine, so they can never disagree.",
  },
  {
    title: "6. Build a dashboard, model a scenario, or share it",
    body:
      "Turn your KPIs and charts into a persisted dashboard your team can comment on. Test \"what if rent goes up 10%?\" against your real baseline and compare it with other saved scenarios. Schedule a report to land in your inbox automatically, or invite a colleague into the workspace with a role that fits what they need to do.",
  },
];

export default function HowItWorksPage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <section className="mx-auto max-w-4xl px-6 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">From spreadsheet to answer</h1>
        <p className="mt-4 text-lg text-slate-600 dark:text-slate-400">
          No SQL, no pivot-table archaeology. Here's the whole path, start to finish.
        </p>
      </section>

      <div className="mx-auto max-w-3xl space-y-10 px-6 pb-20">
        {STEPS.map((step) => (
          <div key={step.title}>
            <h2 className="text-xl font-semibold">{step.title}</h2>
            <p className="mt-2 text-slate-600 dark:text-slate-400">{step.body}</p>
          </div>
        ))}
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
