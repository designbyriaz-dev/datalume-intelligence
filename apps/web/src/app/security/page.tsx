import { NavBar } from "@/components/NavBar";
import { MarketingFooter } from "@/components/MarketingFooter";

type Item = { title: string; body: string };
type Section = { title: string; items: Item[] };

const SECTIONS: Section[] = [
  {
    title: "Authentication",
    items: [
      {
        title: "Password hashing",
        body: "Passwords are hashed with bcrypt — never stored or logged in plain text.",
      },
      {
        title: "Short-lived access tokens, httpOnly refresh cookie",
        body:
          "Your browser session runs on a short-lived access token held only in memory, refreshed via a token stored in an httpOnly cookie your own page's JavaScript can never read — paired with CSRF protection on the one request that relies on that cookie.",
      },
      {
        title: "Optional two-factor authentication",
        body:
          "Turn on TOTP-based 2FA (compatible with Google Authenticator, 1Password, and any standard authenticator app) from your account's Security settings. Disabling it requires re-entering your password.",
      },
      {
        title: "Single sign-on",
        body:
          "Sign in with Google, or any OIDC-compliant identity provider your organization already uses — DataLume's SSO is provider-agnostic by design.",
      },
      {
        title: "Rate limiting",
        body:
          "Every authentication endpoint — login, registration, password reset, email verification — is rate-limited per IP address server-side, independent of anything the browser does.",
      },
    ],
  },
  {
    title: "Access control",
    items: [
      {
        title: "Tenant isolation",
        body:
          "Every workspace, dataset, and report belongs to an account or an organization, and every single API endpoint checks that before returning anything — not just the pages the UI happens to show you.",
      },
      {
        title: "Role-based organization access",
        body:
          "Five roles — owner, administrator, analyst, viewer, auditor — govern what a team member can see and do inside a shared organization. Only owners and administrators can invite, remove, or re-role members.",
      },
      {
        title: "Revocable API keys",
        body:
          "Generate a named API key for a script or integration and revoke it individually at any time, without touching your password or any other key.",
      },
      {
        title: "Server-side plan enforcement",
        body:
          "Every plan limit — upload size, saved datasets, analyses per month, team size — is checked and enforced on the server, not just hidden in the UI.",
      },
    ],
  },
  {
    title: "Data handling",
    items: [
      {
        title: "Upload validation",
        body:
          "Uploads are checked against a file-extension allow-list and verified by their actual file signature, not just their name — a renamed executable or archive is rejected before it's processed. Excel files are also checked for decompression bombs before being fully inflated.",
      },
      {
        title: "Full version history",
        body:
          "Your original upload is never overwritten. Every cleaning operation creates a new version, so you can always see — and return to — exactly what you started with.",
      },
      {
        title: "Pluggable object storage",
        body:
          "Uploaded files and generated reports are stored through a standard object-storage interface — your deployment can point it at local disk or any S3-compatible provider.",
      },
    ],
  },
  {
    title: "Visibility",
    items: [
      {
        title: "Audit logging",
        body:
          "Security-relevant events — logins, failed logins, MFA changes, password resets, organization membership and role changes — are recorded with who did what and when, exportable per organization as CSV.",
      },
      {
        title: "Signed webhooks",
        body:
          "Outbound webhook payloads are signed with HMAC-SHA256, the same shape you'd verify a Stripe webhook with, so your endpoint can confirm a request genuinely came from DataLume.",
      },
      {
        title: "Your own activity log",
        body: "Every account has a personal activity log of its own actions, visible to you at any time.",
      },
    ],
  },
  {
    title: "Your data",
    items: [
      {
        title: "What we collect, and why",
        body:
          "Your account details (email, name, hashed password), the files you upload, and the questions you ask the AI analyst. We use this to run the product you signed up for — profiling and cleaning your data, computing the KPIs and reports you ask for, and answering your questions — not for anything beyond that.",
      },
      {
        title: "Data isolation",
        body:
          "Every workspace, dataset, and report belongs to one account or one organization, and every API endpoint checks that ownership before returning anything — see \"Tenant isolation\" above. Your data is never visible to another customer's account.",
      },
      {
        title: "AI processing",
        body:
          "Questions you ask the AI analyst, and the data needed to answer them, are sent to Anthropic's API (Claude) to generate a response. Per Anthropic's own commercial API terms, data submitted through the API is not used to train their models by default. DataLume doesn't send your data to any other third-party AI provider.",
      },
      {
        title: "Encryption",
        body:
          "Uploaded files and generated reports are stored on Cloudflare R2, which encrypts everything at rest automatically (AES-256). All traffic to the application is required to run over HTTPS/TLS — enforced at the infrastructure layer a production deployment sits behind, the same as any web application. Database-level encryption at rest depends on whichever managed Postgres provider a deployment uses, and isn't a blanket guarantee from this codebase alone.",
      },
      {
        title: "Hosting and infrastructure",
        body:
          "Object storage runs on Cloudflare R2, in its Western Europe location. Where the application itself is hosted isn't finalised yet — this section will be updated with the specific provider and region once that's decided and live, rather than naming one in advance.",
      },
      {
        title: "Data retention and deletion",
        body:
          "Delete a workspace at any time — everything in it (datasets, reports, dashboards) is deleted, including the underlying stored files, not just hidden. Delete your whole account from Settings (re-enter your password to confirm) and every workspace you personally own is deleted the same way; anything you contributed to a shared team workspace stays in place for your team, no longer attributed to you. There's no separate backup system beyond what your database/storage provider keeps — version history (see \"Full version history\" above) protects you against your own mistakes, not infrastructure failure.",
      },
    ],
  },
  {
    title: "Compliance",
    items: [
      {
        title: "UK GDPR",
        body:
          "DataLume Intelligence Ltd is the data controller for your account details, and typically a data processor for the content of files you upload on your organization's behalf. See the Privacy Policy for the full detail, and the Data Processing Agreement if your organization needs one in place.",
      },
      {
        title: "Incident response",
        body:
          "If a security incident affecting customer data occurs, we investigate it, take steps to contain it, and notify affected customers directly and without undue delay — not buried in a changelog. We don't currently hold any formal incident-response certification; this describes our actual commitment, not a certified process.",
      },
      {
        title: "No unverified claims",
        body:
          "We don't claim certifications we don't hold (ISO 27001, Cyber Essentials, SOC 2) or say \"fully GDPR compliant\" as a blanket marketing phrase. Everything on this page is true of the product today; anything that changes gets updated here, not left stale.",
      },
      {
        title: "Report a security issue",
        body: "Email designbyriaz@gmail.com directly — every report is read by a real person, not a ticket queue.",
      },
    ],
  },
];

export default function SecurityPage() {
  return (
    <main className="min-h-screen">
      <NavBar />

      <section className="mx-auto max-w-4xl px-6 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Security</h1>
        <p className="mt-4 text-lg text-slate-600 dark:text-slate-400">
          What's actually built, described plainly — not a compliance checklist, just how your
          account and your data are protected today.
        </p>
      </section>

      <div className="mx-auto max-w-4xl space-y-14 px-6 pb-20">
        {SECTIONS.map((section) => (
          <section key={section.title}>
            <h2 className="text-2xl font-semibold">{section.title}</h2>
            <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
              {section.items.map((item) => (
                <div key={item.title} className="rounded-lg border border-slate-200 p-5 dark:border-slate-800">
                  <h3 className="font-medium">{item.title}</h3>
                  <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{item.body}</p>
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
