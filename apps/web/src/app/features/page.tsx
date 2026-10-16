import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

type Feature = { name: string; blurb: string };
type Group = { title: string; intro: string; features: Feature[] };

const GROUPS: Group[] = [
  {
    title: "Upload & clean",
    intro:
      "Bring a CSV or Excel file as it is — DataLume profiles it, flags what's wrong, and lets you fix it without leaving the browser.",
    features: [
      {
        name: "Secure upload",
        blurb:
          "Extension allow-listing, magic-byte verification (a renamed .exe doesn't get past the .csv check), a platform-wide size cap, and a zip-bomb guard on Excel files.",
      },
      {
        name: "Automatic data quality profiling",
        blurb:
          "Every column gets an inferred type, a missing-value percentage, an invalid-value count, and a duplicate-row check — summarised into a single quality score the moment you upload.",
      },
      {
        name: "11 cleaning operations",
        blurb:
          "Deduplicate, fill missing values, normalise text, filter rows, add a calculated field, merge or split columns, standardise values, pivot, unpivot, and group-by — each one a reviewable step, not a silent overwrite.",
      },
      {
        name: "Full version history",
        blurb:
          "Every cleaning step creates a new version; nothing is ever overwritten. Compare any two versions and see exactly what changed — row counts, added or removed columns, and per-column stat deltas.",
      },
    ],
  },
  {
    title: "Industry intelligence",
    intro:
      "Four built-in industry packs turn raw columns into the metrics that industry actually tracks — automatically mapped, with every figure traceable back to a documented formula.",
    features: [
      {
        name: "Automatic field mapping",
        blurb:
          "DataLume matches your column headers to the canonical fields an industry pack needs — \"Rent (PCM)\" maps to rent_amount, \"Lease Expiry\" to lease_end_date — and shows you the mapping to confirm or correct before anything is calculated.",
      },
      {
        name: "A deterministic KPI engine",
        blurb:
          "Every KPI — total rent roll, occupancy rate, void rate, net profit — is a documented formula over your data, not an AI guess. The same engine feeds your KPI view, your reports, and your dashboards, so none of them can ever disagree.",
      },
      {
        name: "Configurable lookback windows",
        blurb:
          "\"Leases expiring soon\" and \"overdue inspections\" use a 12-month window by default — set your own per workspace if that's not how your business thinks about the near term.",
      },
      {
        name: "Works for anything else too",
        blurb:
          "No matching industry pack? Every upload still gets full data-quality profiling and all seven analytics tools — you just won't get a fixed KPI set invented for a domain DataLume doesn't model yet.",
      },
    ],
  },
  {
    title: "Ask your data a question",
    intro:
      "A real AI analyst with real tool access — every answer is backed by an actual calculation over your actual data, shown to you, not a plausible-sounding guess.",
    features: [
      {
        name: "Plain-English questions, grounded answers",
        blurb:
          "Ask \"what's our total rent roll?\" or \"which expense category grew the most?\" — the model picks from seven real analytics tools (descriptive stats, group aggregation, time trends, correlation, outlier detection, frequency tables, simple forecasting) and shows you which one it used.",
      },
      {
        name: "Multi-turn conversations",
        blurb:
          "Ask a follow-up — \"and what percentage of that is from our top tenant?\" — without repeating yourself. Every conversation is saved and can be reopened later.",
      },
    ],
  },
  {
    title: "Reports & dashboards",
    intro: "Turn the same underlying numbers into a PDF, a live dashboard, or a scheduled email.",
    features: [
      {
        name: "Eight report templates",
        blurb:
          "A data-quality report plus a template for every industry pack — two packs get a second, more specific report — each one a PDF built from the exact same KPI engine behind everything else in the app.",
      },
      {
        name: "AI-generated executive summaries",
        blurb:
          "One report, Executive Intelligence, adds a genuinely AI-written narrative on top of the same deterministic KPI table every other report uses — clearly labelled, and built to never invent a figure that isn't in the data it was given.",
      },
      {
        name: "Persisted, shareable dashboards",
        blurb:
          "Build a dashboard from KPI stat cards and real bar-chart widgets, reorder them by drag-and-drop, and leave comments for teammates working from the same view.",
      },
      {
        name: "Scheduled delivery",
        blurb:
          "Set any report to generate daily, weekly, or monthly and land in your inbox as a PDF attachment automatically — no one has to remember to run it.",
      },
    ],
  },
  {
    title: "Scenario modelling",
    intro: "Test a change before it happens, against your real baseline numbers.",
    features: [
      {
        name: "\"What if\" adjustments",
        blurb:
          "Model a percentage change, a fixed amount, or a direct value override on any numeric column — rent up 10%, arrears cleared, expenses cut — and see every KPI recompute against that scenario.",
      },
      {
        name: "Saved, named scenarios",
        blurb: "Save a scenario to come back to later instead of re-entering the same adjustments.",
      },
      {
        name: "Side-by-side comparison",
        blurb:
          "Select two or more saved scenarios and compare their results in one table next to your real baseline — not one at a time.",
      },
    ],
  },
  {
    title: "Team & collaboration",
    intro: "Built for more than one person from the start, with access control enforced server-side.",
    features: [
      {
        name: "Organizations",
        blurb:
          "Share workspaces across a team with five roles from owner down to viewer. Invite by email, change roles, or remove a member — every action is audit-logged.",
      },
      {
        name: "Webhooks",
        blurb:
          "Get a signed (HMAC-SHA256) POST request to your own endpoint when a dataset is uploaded or a report is generated — verify authenticity the same way you'd verify a Stripe webhook.",
      },
      {
        name: "API keys",
        blurb: "Authenticate scripts and integrations as yourself, with keys you can name, list, and revoke individually.",
      },
      {
        name: "Activity & audit logs",
        blurb: "A personal activity log for your own account, and a full audit log per organization — exportable as CSV.",
      },
    ],
  },
];

export default function FeaturesPage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <section className="mx-auto max-w-4xl px-6 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Everything in one engine</h1>
        <p className="mt-4 text-lg text-slate-600 dark:text-slate-400">
          Upload, clean, understand, and share — the same underlying KPI engine and the same real data
          behind every answer, report, and dashboard.
        </p>
        <div className="mt-8 flex items-center justify-center gap-4">
          <Link
            href="/register"
            className="rounded-md bg-brand-500 px-6 py-3 font-medium text-white hover:bg-brand-600"
          >
            Start Analysing for Free
          </Link>
          <Link
            href="/how-it-works"
            className="rounded-md border border-slate-300 px-6 py-3 font-medium hover:border-brand-500 dark:border-slate-700"
          >
            See how it works
          </Link>
        </div>
      </section>

      <div className="mx-auto max-w-5xl space-y-16 px-6 pb-20">
        {GROUPS.map((group) => (
          <section key={group.title}>
            <h2 className="text-2xl font-semibold">{group.title}</h2>
            <p className="mt-2 max-w-3xl text-slate-600 dark:text-slate-400">{group.intro}</p>
            <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
              {group.features.map((f) => (
                <div key={f.name} className="rounded-lg border border-slate-200 p-5 dark:border-slate-800">
                  <h3 className="font-medium">{f.name}</h3>
                  <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{f.blurb}</p>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>

      <MarketingFooter />
    </main>
  );
}
