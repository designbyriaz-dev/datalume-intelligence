import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

type Status = { label: string; body: string; color: string };

const STATUSES: Status[] = [
  { label: "Passes", body: "A qualifying document is on file and, if required, not expiring soon.", color: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200" },
  { label: "Potential issue", body: "A document is on file but its expiry falls within your warning window.", color: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200" },
  { label: "Missing information", body: "No qualifying document is on file — DataLume doesn't know, it isn't asserting the property lacks one.", color: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300" },
  { label: "Action may be overdue", body: "A document is on file but its expiry date has already passed.", color: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200" },
  { label: "Requires human review", body: "A document is on file but is missing the expiry information the rule needs — a person needs to look at it.", color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200" },
  { label: "Unable to determine", body: "The rule type isn't one the engine can evaluate yet — never silently reported as passing.", color: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400" },
];

export default function ComplianceIntelligencePage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <section className="mx-auto max-w-4xl px-6 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Compliance Intelligence</h1>
        <p className="mt-4 text-lg text-slate-600 dark:text-slate-400">
          Define the documents you require on file for a property — a valid gas safety certificate,
          for example — and DataLume checks every property against your own rules automatically.
        </p>
      </section>

      <section className="mx-auto max-w-3xl px-6 pb-10">
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <strong>This is a configurable checklist, not legal advice.</strong> Compliance Intelligence
          checks your properties against rules you define yourself. It does not determine, certify,
          or guarantee that a property meets UK lettings law, and DataLume holds no accreditation or
          certification of its own. Treat it as a way to keep track of the documents you&rsquo;ve told
          it to require — not a substitute for your own legal or regulatory judgement.
        </div>
      </section>

      <div className="mx-auto max-w-4xl px-6 pb-16">
        <h2 className="text-xl font-semibold text-center">Six honest outcomes, not a blunt pass/fail</h2>
        <p className="mt-2 text-center text-slate-600 dark:text-slate-400">
          Every check reports one of six statuses — chosen specifically so DataLume never overstates
          what it actually knows.
        </p>
        <div className="mt-6 space-y-3">
          {STATUSES.map((s) => (
            <div key={s.label} className="flex items-start gap-4 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
              <span className={`flex-shrink-0 rounded px-2 py-1 text-xs font-medium ${s.color}`}>{s.label}</span>
              <p className="text-sm text-slate-600 dark:text-slate-400">{s.body}</p>
            </div>
          ))}
        </div>
      </div>

      <section className="mx-auto max-w-3xl px-6 pb-16 text-center">
        <h2 className="text-xl font-semibold">Built on real documents, not guesswork</h2>
        <p className="mt-2 text-slate-600 dark:text-slate-400">
          Rules check against the documents you&rsquo;ve actually uploaded — gas safety
          certificates, EICRs, EPCs, deposit protection certificates and more — with their real
          expiry dates. See{" "}
          <Link href="/inventory-documents" className="text-brand-500 hover:underline">
            Inventory &amp; Documents
          </Link>{" "}
          for how documents are stored.
        </p>
      </section>

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
