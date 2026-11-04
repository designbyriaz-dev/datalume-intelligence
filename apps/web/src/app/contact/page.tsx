import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

export default function ContactPage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <section className="mx-auto max-w-2xl px-6 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Contact</h1>
        <p className="mt-4 text-lg text-slate-600 dark:text-slate-400">
          Questions, feedback, a security concern, or something that looks broken — email us
          directly. Every message is read by a real person, not a ticket queue.
        </p>

        <div className="mt-10 rounded-lg border border-slate-200 p-8 dark:border-slate-800">
          <p className="text-sm font-medium uppercase text-slate-500">Email</p>
          <a
            href="mailto:support@datalume.co.uk"
            className="mt-2 block text-2xl font-semibold text-brand-500 hover:underline"
          >
            support@datalume.co.uk
          </a>
          <p className="mt-4 text-sm text-slate-500">
            For a security vulnerability specifically, see{" "}
            <Link href="/security" className="text-brand-500 hover:underline">
              Security
            </Link>
            . For data protection or a GDPR request, see our{" "}
            <Link href="/privacy" className="text-brand-500 hover:underline">
              Privacy Policy
            </Link>
            .
          </p>
        </div>

        <p className="mt-8 text-sm text-slate-500">
          DataLume Intelligence Ltd, a company registered in England and Wales.
        </p>
      </section>

      <MarketingFooter />
    </main>
  );
}
