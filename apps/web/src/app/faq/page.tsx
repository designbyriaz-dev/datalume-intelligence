import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

type QA = { q: string; a: React.ReactNode };

export default function FaqPage() {
  const QA_LIST: QA[] = [
    {
      q: "What file formats can I upload?",
      a: "CSV and Excel (.xlsx) today. Each upload is profiled automatically as soon as it finishes.",
    },
    {
      q: "Do I need to know SQL or write any code?",
      a: "No. Cleaning, KPIs, and reports are all point-and-click, and the AI analyst answers questions typed in plain English.",
    },
    {
      q: "What if my industry isn't Commercial Property, Residential, Social Housing, Business Finance, Public Sector, or Education?",
      a: (
        <>
          Pick &ldquo;Something else&rdquo; when you create a workspace. You still get full data
          profiling, all the cleaning tools, and the AI analyst — you just won&rsquo;t get a
          dedicated KPI set built for an industry DataLume doesn&rsquo;t model yet. See{" "}
          <Link href="/solutions" className="text-brand-500 hover:underline">
            Solutions
          </Link>{" "}
          for what&rsquo;s covered today.
        </>
      ),
    },
    {
      q: "How does the AI analyst avoid making numbers up?",
      a: "It doesn't generate figures freeform — it picks from a fixed set of real analytics tools (descriptive stats, group aggregation, time trends, and more), runs them against your actual data, and shows you which tool produced the answer.",
    },
    {
      q: "Does my data get sent to a third party when I use the AI analyst?",
      a: "Yes — answering a question, or generating the Executive Intelligence report's narrative summary, sends the relevant portion of your data to our AI provider so it can produce a grounded response.",
    },
    {
      q: "Can my team share a workspace?",
      a: (
        <>
          Yes — create an organization, invite people by email, and give each one a role from owner
          down to viewer. See{" "}
          <Link href="/security" className="text-brand-500 hover:underline">
            Security
          </Link>{" "}
          for how access is controlled.
        </>
      ),
    },
    {
      q: "What happens if I go over my plan's limits?",
      a: "You'll get a clear message telling you which limit you hit — uploads, saved datasets, or analyses for the month — before anything is blocked silently. Upgrade anytime from the Pricing page.",
    },
    {
      q: "Is two-factor authentication required?",
      a: "No, it's optional — turn it on from your account's Security settings whenever you want an extra layer on login.",
    },
    {
      q: "Can I cancel or change my plan?",
      a: "Yes, anytime, from the billing portal linked on your dashboard — there's no minimum term.",
    },
  ];

  return (
    <main className="min-h-screen">
      <NavBar />

      <section className="mx-auto max-w-3xl px-6 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Frequently asked questions</h1>
      </section>

      <div className="mx-auto max-w-3xl space-y-8 px-6 pb-20">
        {QA_LIST.map((item) => (
          <div key={item.q} className="border-b border-slate-200 pb-8 last:border-b-0 dark:border-slate-800">
            <h2 className="font-medium">{item.q}</h2>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{item.a}</p>
          </div>
        ))}
      </div>

      <MarketingFooter />
    </main>
  );
}
