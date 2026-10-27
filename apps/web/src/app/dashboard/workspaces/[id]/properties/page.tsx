"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import { api, ApiError, type Property, type PropertyKPIs } from "@/lib/api";

function PropertyKpiRow({ kpis }: { kpis: PropertyKPIs }) {
  const tiles: { label: string; value: string }[] = [
    { label: "Properties", value: String(kpis.total_properties) },
    { label: "Active tenancies", value: String(kpis.active_tenancies) },
    { label: "Expected monthly rent", value: `£${kpis.expected_monthly_rent_gbp.toFixed(2)}` },
    { label: "Collected (this period)", value: `£${kpis.collected_this_period_gbp.toFixed(2)}` },
    { label: "Outstanding balance", value: `£${kpis.outstanding_balance_gbp.toFixed(2)}` },
    { label: "Tenancies in arrears", value: String(kpis.arrears_count) },
  ];
  return (
    <div className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-3">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-md bg-slate-50 p-3 dark:bg-slate-900">
          <div className="text-xs text-slate-500">{t.label}</div>
          <div className="text-lg font-medium">{t.value}</div>
        </div>
      ))}
    </div>
  );
}

export default function PropertiesPage() {
  const { token, user, loading } = useAuth();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const workspaceId = params.id;

  const [properties, setProperties] = useState<Property[] | null>(null);
  const [kpis, setKpis] = useState<PropertyKPIs | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [addressLine1, setAddressLine1] = useState("");
  const [city, setCity] = useState("");
  const [postcode, setPostcode] = useState("");
  const [propertyType, setPropertyType] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const [props, kpiResult] = await Promise.all([
        api.listProperties(token, workspaceId),
        api.getPropertyKpis(token, workspaceId),
      ]);
      setProperties(props);
      setKpis(kpiResult);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load properties.");
      setProperties([]);
    }
  }, [token, workspaceId]);

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [loading, user, router]);

  useEffect(() => {
    load();
  }, [load]);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setCreating(true);
    setError(null);
    try {
      await api.createProperty(token, workspaceId, {
        address_line1: addressLine1,
        city,
        postcode,
        property_type: propertyType || undefined,
      });
      setAddressLine1("");
      setCity("");
      setPostcode("");
      setPropertyType("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create property.");
    } finally {
      setCreating(false);
    }
  };

  if (loading || !user) {
    return (
      <main className="min-h-screen">
        <NavBar />
        <p className="px-6 py-16 text-center text-slate-500">Loading…</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen">
      <NavBar />
      <div className="mx-auto max-w-3xl px-6 py-12">
        <Link href={`/dashboard/workspaces/${workspaceId}`} className="text-sm text-brand-500 hover:underline">
          ← Back to workspace
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">Properties & rent ledger</h1>
        <p className="mt-1 text-sm text-slate-500">
          Manual rent-ledger records — no payment collection happens here. See a tenancy&rsquo;s page to
          record a charge, payment, refund, or adjustment by hand.
        </p>

        {kpis && <PropertyKpiRow kpis={kpis} />}

        <form onSubmit={onCreate} className="mt-8 space-y-3 rounded-lg border border-slate-200 p-5 dark:border-slate-800">
          <h2 className="font-medium">Add a property</h2>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1">
              <label className="block text-sm font-medium">Address line 1</label>
              <input
                required
                value={addressLine1}
                onChange={(e) => setAddressLine1(e.target.value)}
                placeholder="e.g. 12 Example Street"
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              />
            </div>
            <div>
              <label className="block text-sm font-medium">City</label>
              <input
                required
                value={city}
                onChange={(e) => setCity(e.target.value)}
                className="mt-1 rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              />
            </div>
            <div>
              <label className="block text-sm font-medium">Postcode</label>
              <input
                required
                value={postcode}
                onChange={(e) => setPostcode(e.target.value)}
                className="mt-1 rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              />
            </div>
            <div>
              <label className="block text-sm font-medium">Type (optional)</label>
              <input
                value={propertyType}
                onChange={(e) => setPropertyType(e.target.value)}
                placeholder="e.g. flat, house"
                className="mt-1 rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              />
            </div>
            <button
              type="submit"
              disabled={creating}
              className="rounded-md bg-brand-500 px-4 py-2 font-medium text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {creating ? "Adding…" : "Add property"}
            </button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </form>

        <div className="mt-10 space-y-3">
          <h2 className="font-medium">Properties</h2>
          {properties === null ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : properties.length === 0 ? (
            <p className="text-sm text-slate-500">No properties yet — add your first one above.</p>
          ) : (
            properties.map((p) => (
              <Link
                key={p.id}
                href={`/dashboard/workspaces/${workspaceId}/properties/${p.id}`}
                className="block rounded-lg border border-slate-200 p-4 hover:border-brand-500 dark:border-slate-800"
              >
                <div className="font-medium">{p.address_line1}</div>
                <div className="text-sm text-slate-500">
                  {[p.address_line2, p.city, p.postcode].filter(Boolean).join(", ")}
                  {p.property_type && ` · ${p.property_type}`}
                </div>
              </Link>
            ))
          )}
        </div>
      </div>
    </main>
  );
}
