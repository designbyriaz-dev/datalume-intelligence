import Link from "next/link";

const LINKS = [
  { href: "/features", label: "Features" },
  { href: "/solutions", label: "Solutions" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/security", label: "Security" },
  { href: "/pricing", label: "Pricing" },
  { href: "/faq", label: "FAQ" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
];

const PROPERTY_LINKS = [
  { href: "/property-intelligence", label: "Property Intelligence" },
  { href: "/housing-intelligence", label: "Housing Intelligence" },
  { href: "/compliance-intelligence", label: "Compliance Intelligence" },
  { href: "/rent-collection", label: "Rent Collection" },
  { href: "/inventory-documents", label: "Inventory & Documents" },
];

const LEGAL_LINKS = [
  { href: "/terms", label: "Terms" },
  { href: "/privacy", label: "Privacy" },
  { href: "/cookies", label: "Cookies" },
  { href: "/dpa", label: "DPA" },
  { href: "/acceptable-use", label: "Acceptable Use" },
];

export function MarketingFooter() {
  return (
    <footer className="border-t border-slate-200 px-6 py-10 dark:border-slate-800">
      <div className="mx-auto flex max-w-5xl flex-col items-center gap-4 text-center">
        <nav className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-slate-500">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-brand-500">
              {l.label}
            </Link>
          ))}
        </nav>
        <nav className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-slate-400">
          {PROPERTY_LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-brand-500">
              {l.label}
            </Link>
          ))}
        </nav>
        <nav className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-slate-400">
          {LEGAL_LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-brand-500">
              {l.label}
            </Link>
          ))}
        </nav>
        <p className="text-sm text-slate-500">
          DataLume Intelligence — built incrementally. See{" "}
          <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">docs/CHECKLIST.md</code> for
          what is live today.
        </p>
      </div>
    </footer>
  );
}
