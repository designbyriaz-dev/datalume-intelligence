"use client";

import { useEffect, useState } from "react";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import { api, type Plan, ApiError } from "@/lib/api";

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024 * 1024) return `${Math.round(bytes / (1024 * 1024 * 1024))}GB`;
  return `${Math.round(bytes / (1024 * 1024))}MB`;
}

function PlanCard({ plan }: { plan: Plan }) {
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const onSubscribe = async () => {
    if (!token) {
      window.location.href = "/register";
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const { checkout_url } = await api.createCheckoutSession(token, plan.plan_id);
      window.location.href = checkout_url;
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setMessage("Billing isn't connected to Stripe yet — this plan can't be purchased yet.");
      } else {
        setMessage(err instanceof ApiError ? err.message : "Could not start checkout.");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border border-slate-200 p-5 dark:border-slate-800">
      <h2 className="font-medium">{plan.name}</h2>
      <p className="mt-1 text-2xl font-semibold">
        {plan.monthly_price_gbp === null ? "Custom" : plan.monthly_price_gbp === 0 ? "£0" : `£${plan.monthly_price_gbp}`}
        {plan.monthly_price_gbp !== null && plan.monthly_price_gbp > 0 && (
          <span className="text-sm font-normal text-slate-500">/mo</span>
        )}
      </p>
      <p className="mt-2 text-sm text-slate-500">
        {plan.max_analyses_per_month ? `${plan.max_analyses_per_month} analyses/mo` : "Unlimited analyses"} ·{" "}
        {formatSize(plan.max_upload_size_bytes)} uploads
        {plan.max_saved_datasets ? ` · ${plan.max_saved_datasets} saved datasets` : ""}
        {plan.max_team_members ? ` · ${plan.max_team_members} seats` : ""}
      </p>

      {plan.plan_id === "free" ? (
        <p className="mt-4 text-xs text-slate-500">Default plan — no payment needed.</p>
      ) : plan.plan_id === "enterprise" ? (
        <a
          href="mailto:sales@datalume.example"
          className="mt-4 inline-block rounded-md border border-slate-300 px-4 py-2 text-sm font-medium hover:border-brand-500 dark:border-slate-700"
        >
          Contact sales
        </a>
      ) : (
        <button
          onClick={onSubscribe}
          disabled={busy}
          className="mt-4 rounded-md bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
        >
          {busy ? "Starting checkout…" : "Subscribe"}
        </button>
      )}
      {message && <p className="mt-2 text-xs text-slate-500">{message}</p>}
      {!plan.self_serve && plan.plan_id !== "free" && plan.plan_id !== "enterprise" && (
        <p className="mt-2 text-xs text-slate-400">Not yet purchasable — Stripe pricing not configured.</p>
      )}
    </div>
  );
}

export default function PricingPage() {
  const [plans, setPlans] = useState<Plan[] | null>(null);

  useEffect(() => {
    api.listPlans().then(setPlans).catch(() => setPlans([]));
  }, []);

  return (
    <main className="min-h-screen">
      <NavBar />
      <div className="mx-auto max-w-5xl px-6 py-16">
        <h1 className="text-center text-3xl font-semibold">Pricing</h1>
        <p className="mt-2 text-center text-slate-500">
          Every limit below is enforced server-side, not just shown here — see the plan registry at{" "}
          <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">apps/api/app/core/plans.py</code>.
        </p>
        {plans === null ? (
          <p className="mt-10 text-center text-sm text-slate-500">Loading…</p>
        ) : (
          <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {plans.map((p) => (
              <PlanCard key={p.plan_id} plan={p} />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
