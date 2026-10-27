"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import { api, ApiError, type Property, type RentLedgerEntry, type Tenancy, type TenancyBalance } from "@/lib/api";

const LEDGER_ENTRY_TYPES: RentLedgerEntry["entry_type"][] = ["charge", "payment", "adjustment", "refund"];

function TenancyCard({ tenancy, token }: { tenancy: Tenancy; token: string }) {
  const [entries, setEntries] = useState<RentLedgerEntry[] | null>(null);
  const [balance, setBalance] = useState<TenancyBalance | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [entryType, setEntryType] = useState<RentLedgerEntry["entry_type"]>("charge");
  const [amount, setAmount] = useState("");
  const [entryDate, setEntryDate] = useState(new Date().toISOString().slice(0, 10));
  const [description, setDescription] = useState("");
  const [adding, setAdding] = useState(false);

  const [status, setStatus] = useState<Tenancy["status"]>(tenancy.status);
  const [updatingStatus, setUpdatingStatus] = useState(false);

  const load = useCallback(async () => {
    try {
      const [entryList, balanceResult] = await Promise.all([
        api.listLedgerEntries(token, tenancy.id),
        api.getTenancyBalance(token, tenancy.id),
      ]);
      setEntries(entryList);
      setBalance(balanceResult);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the ledger.");
    }
  }, [token, tenancy.id]);

  useEffect(() => {
    load();
  }, [load]);

  const onAddEntry = async (e: React.FormEvent) => {
    e.preventDefault();
    const value = parseFloat(amount);
    if (!Number.isFinite(value) || value <= 0) {
      setError("Enter an amount greater than zero.");
      return;
    }
    setAdding(true);
    setError(null);
    try {
      await api.createLedgerEntry(token, tenancy.id, {
        entry_type: entryType,
        amount_gbp: value,
        entry_date: entryDate,
        description: description || undefined,
      });
      setAmount("");
      setDescription("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add ledger entry.");
    } finally {
      setAdding(false);
    }
  };

  const onUpdateStatus = async (next: Tenancy["status"]) => {
    setStatus(next);
    setUpdatingStatus(true);
    setError(null);
    try {
      await api.updateTenancy(token, tenancy.id, next, tenancy.end_date ?? undefined);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update tenancy status.");
      setStatus(tenancy.status);
    } finally {
      setUpdatingStatus(false);
    }
  };

  return (
    <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-medium">{tenancy.tenant_name}</div>
          <div className="text-sm text-slate-500">
            £{tenancy.rent_amount_gbp.toFixed(2)} / {tenancy.rent_frequency} · from{" "}
            {new Date(tenancy.start_date).toLocaleDateString()}
            {tenancy.end_date && ` to ${new Date(tenancy.end_date).toLocaleDateString()}`}
          </div>
        </div>
        <select
          value={status}
          onChange={(e) => onUpdateStatus(e.target.value as Tenancy["status"])}
          disabled={updatingStatus}
          className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
        >
          <option value="upcoming">Upcoming</option>
          <option value="active">Active</option>
          <option value="ended">Ended</option>
        </select>
      </div>

      {balance && (
        <p className="mt-2 text-sm">
          Balance:{" "}
          <span className={balance.balance_gbp > 0 ? "font-medium text-red-600" : "font-medium text-green-600"}>
            £{balance.balance_gbp.toFixed(2)}
          </span>{" "}
          <span className="text-slate-500">
            {balance.balance_gbp > 0 ? "(in arrears)" : balance.balance_gbp < 0 ? "(credit)" : "(settled)"}
          </span>
        </p>
      )}

      <form onSubmit={onAddEntry} className="mt-3 flex flex-wrap items-end gap-2">
        <select
          value={entryType}
          onChange={(e) => setEntryType(e.target.value as RentLedgerEntry["entry_type"])}
          className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
        >
          {LEDGER_ENTRY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input
          type="number"
          step="0.01"
          min="0.01"
          required
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="Amount £"
          className="w-24 rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
        />
        <input
          type="date"
          required
          value={entryDate}
          onChange={(e) => setEntryDate(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
        />
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description (optional)"
          className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
        />
        <button
          type="submit"
          disabled={adding}
          className="rounded-md bg-brand-500 px-3 py-1 text-xs font-medium text-white hover:bg-brand-600 disabled:opacity-50"
        >
          {adding ? "Adding…" : "Add entry"}
        </button>
      </form>

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

      <div className="mt-3">
        {entries === null ? (
          <p className="text-xs text-slate-500">Loading ledger…</p>
        ) : entries.length === 0 ? (
          <p className="text-xs text-slate-500">No ledger entries yet.</p>
        ) : (
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-slate-500">
                <th className="pr-4 py-1">Date</th>
                <th className="pr-4 py-1">Type</th>
                <th className="pr-4 py-1">Amount</th>
                <th className="pr-4 py-1">Description</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id} className="border-t border-slate-200 dark:border-slate-800">
                  <td className="pr-4 py-1">{new Date(entry.entry_date).toLocaleDateString()}</td>
                  <td className="pr-4 py-1 capitalize">{entry.entry_type}</td>
                  <td className="pr-4 py-1">£{entry.amount_gbp.toFixed(2)}</td>
                  <td className="pr-4 py-1 text-slate-500">{entry.description ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default function PropertyDetailPage() {
  const { token, user, loading } = useAuth();
  const router = useRouter();
  const params = useParams<{ id: string; propertyId: string }>();
  const workspaceId = params.id;
  const propertyId = params.propertyId;

  const [property, setProperty] = useState<Property | null>(null);
  const [tenancies, setTenancies] = useState<Tenancy[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [tenantName, setTenantName] = useState("");
  const [rentAmount, setRentAmount] = useState("");
  const [rentFrequency, setRentFrequency] = useState<Tenancy["rent_frequency"]>("monthly");
  const [startDate, setStartDate] = useState(new Date().toISOString().slice(0, 10));
  const [creating, setCreating] = useState(false);

  const loadTenancies = useCallback(async () => {
    if (!token) return;
    try {
      setTenancies(await api.listTenancies(token, propertyId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load tenancies.");
      setTenancies([]);
    }
  }, [token, propertyId]);

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [loading, user, router]);

  useEffect(() => {
    if (!token) return;
    api.getProperty(token, propertyId).then(setProperty).catch(() => setProperty(null));
    loadTenancies();
  }, [token, propertyId, loadTenancies]);

  const onCreateTenancy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    const value = parseFloat(rentAmount);
    if (!Number.isFinite(value) || value <= 0) {
      setError("Enter a rent amount greater than zero.");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      await api.createTenancy(token, propertyId, {
        tenant_name: tenantName,
        rent_amount_gbp: value,
        rent_frequency: rentFrequency,
        start_date: startDate,
      });
      setTenantName("");
      setRentAmount("");
      await loadTenancies();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create tenancy.");
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
        <Link href={`/dashboard/workspaces/${workspaceId}/properties`} className="text-sm text-brand-500 hover:underline">
          ← All properties
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">{property?.address_line1 ?? "Property"}</h1>
        {property && (
          <p className="mt-1 text-sm text-slate-500">
            {[property.address_line2, property.city, property.postcode].filter(Boolean).join(", ")}
            {property.property_type && ` · ${property.property_type}`}
          </p>
        )}

        <form
          onSubmit={onCreateTenancy}
          className="mt-8 space-y-3 rounded-lg border border-slate-200 p-5 dark:border-slate-800"
        >
          <h2 className="font-medium">Add a tenancy</h2>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1">
              <label className="block text-sm font-medium">Tenant name</label>
              <input
                required
                value={tenantName}
                onChange={(e) => setTenantName(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              />
            </div>
            <div>
              <label className="block text-sm font-medium">Rent (£)</label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                required
                value={rentAmount}
                onChange={(e) => setRentAmount(e.target.value)}
                className="mt-1 w-28 rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              />
            </div>
            <div>
              <label className="block text-sm font-medium">Frequency</label>
              <select
                value={rentFrequency}
                onChange={(e) => setRentFrequency(e.target.value as Tenancy["rent_frequency"])}
                className="mt-1 rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              >
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
                <option value="quarterly">Quarterly</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium">Start date</label>
              <input
                type="date"
                required
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="mt-1 rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              />
            </div>
            <button
              type="submit"
              disabled={creating}
              className="rounded-md bg-brand-500 px-4 py-2 font-medium text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {creating ? "Adding…" : "Add tenancy"}
            </button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </form>

        <div className="mt-10 space-y-4">
          <h2 className="font-medium">Tenancies</h2>
          {tenancies === null ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : tenancies.length === 0 ? (
            <p className="text-sm text-slate-500">No tenancies yet — add one above.</p>
          ) : (
            tenancies.map((t) => <TenancyCard key={t.id} tenancy={t} token={token!} />)
          )}
        </div>
      </div>
    </main>
  );
}
