"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import {
  api,
  ApiError,
  type DocumentType,
  type Inventory,
  type InventoryType,
  type ItemCondition,
  type Property,
  type PropertyDocument,
  type RentLedgerEntry,
  type Tenancy,
  type TenancyBalance,
} from "@/lib/api";

const LEDGER_ENTRY_TYPES: RentLedgerEntry["entry_type"][] = ["charge", "payment", "adjustment", "refund"];

const INVENTORY_TYPES: InventoryType[] = ["check_in", "check_out", "mid_term"];
const ITEM_CONDITIONS: ItemCondition[] = ["excellent", "good", "fair", "poor", "damaged", "missing"];

function formatLabel(value: string): string {
  return value.replace(/_/g, " ");
}

interface InventoryItemRow {
  room: string;
  item_name: string;
  condition: ItemCondition;
  notes: string;
}

function InventoriesPanel({ tenancyId, token }: { tenancyId: string; token: string }) {
  const [inventories, setInventories] = useState<Inventory[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [open, setOpen] = useState(false);
  const [inventoryType, setInventoryType] = useState<InventoryType>("check_in");
  const [inspectionDate, setInspectionDate] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState("");
  const [rows, setRows] = useState<InventoryItemRow[]>([
    { room: "", item_name: "", condition: "good", notes: "" },
  ]);
  const [creating, setCreating] = useState(false);

  const [beforeId, setBeforeId] = useState("");
  const [afterId, setAfterId] = useState("");
  const [comparing, setComparing] = useState(false);
  const [comparison, setComparison] = useState<Awaited<ReturnType<typeof api.compareInventories>> | null>(null);

  const load = useCallback(async () => {
    try {
      setInventories(await api.listInventories(token, tenancyId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load inventories.");
      setInventories([]);
    }
  }, [token, tenancyId]);

  useEffect(() => {
    load();
  }, [load]);

  const updateRow = (index: number, patch: Partial<InventoryItemRow>) => {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  };

  const addRow = () => setRows((prev) => [...prev, { room: "", item_name: "", condition: "good", notes: "" }]);
  const removeRow = (index: number) => setRows((prev) => prev.filter((_, i) => i !== index));

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const items = rows
      .filter((r) => r.room.trim() && r.item_name.trim())
      .map((r) => ({ room: r.room, item_name: r.item_name, condition: r.condition, notes: r.notes || undefined }));
    setCreating(true);
    setError(null);
    try {
      await api.createInventory(token, tenancyId, {
        inventory_type: inventoryType,
        inspection_date: inspectionDate,
        notes: notes || undefined,
        items,
      });
      setNotes("");
      setRows([{ room: "", item_name: "", condition: "good", notes: "" }]);
      setOpen(false);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create inventory.");
    } finally {
      setCreating(false);
    }
  };

  const onDelete = async (inventoryId: string) => {
    setError(null);
    try {
      await api.deleteInventory(token, inventoryId);
      setComparison(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete inventory.");
    }
  };

  const onCompare = async () => {
    if (!beforeId || !afterId) return;
    setComparing(true);
    setError(null);
    try {
      setComparison(await api.compareInventories(token, beforeId, afterId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not compare inventories.");
    } finally {
      setComparing(false);
    }
  };

  return (
    <div className="mt-3 rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-medium uppercase text-slate-500">Inventories</h4>
        <button onClick={() => setOpen((v) => !v)} className="text-xs text-brand-500 hover:underline">
          {open ? "Close" : "+ Add inventory"}
        </button>
      </div>

      {open && (
        <form onSubmit={onCreate} className="mt-2 space-y-2 rounded-md border border-dashed border-slate-300 p-3 dark:border-slate-700">
          <div className="flex flex-wrap items-end gap-2">
            <select
              value={inventoryType}
              onChange={(e) => setInventoryType(e.target.value as InventoryType)}
              className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
            >
              {INVENTORY_TYPES.map((t) => (
                <option key={t} value={t}>
                  {formatLabel(t)}
                </option>
              ))}
            </select>
            <input
              type="date"
              required
              value={inspectionDate}
              onChange={(e) => setInspectionDate(e.target.value)}
              className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
            />
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Overall notes (optional)"
              className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
            />
          </div>

          <div className="space-y-1">
            {rows.map((row, i) => (
              <div key={i} className="flex flex-wrap items-center gap-1">
                <input
                  value={row.room}
                  onChange={(e) => updateRow(i, { room: e.target.value })}
                  placeholder="Room"
                  className="w-28 rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
                />
                <input
                  value={row.item_name}
                  onChange={(e) => updateRow(i, { item_name: e.target.value })}
                  placeholder="Item"
                  className="w-28 rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
                />
                <select
                  value={row.condition}
                  onChange={(e) => updateRow(i, { condition: e.target.value as ItemCondition })}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
                >
                  {ITEM_CONDITIONS.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
                <input
                  value={row.notes}
                  onChange={(e) => updateRow(i, { notes: e.target.value })}
                  placeholder="Notes (optional)"
                  className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
                />
                {rows.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeRow(i)}
                    aria-label="Remove item"
                    className="text-xs text-slate-400 hover:text-red-500"
                  >
                    ×
                  </button>
                )}
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <button type="button" onClick={addRow} className="text-xs text-brand-500 hover:underline">
              + Add item
            </button>
            <button
              type="submit"
              disabled={creating}
              className="rounded-md bg-brand-500 px-3 py-1 text-xs font-medium text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {creating ? "Saving…" : "Save inventory"}
            </button>
          </div>
        </form>
      )}

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

      <div className="mt-2">
        {inventories === null ? (
          <p className="text-xs text-slate-500">Loading…</p>
        ) : inventories.length === 0 ? (
          <p className="text-xs text-slate-500">No inventories yet.</p>
        ) : (
          <ul className="space-y-1">
            {inventories.map((inv) => (
              <li key={inv.id} className="rounded-md bg-slate-50 px-2 py-1 text-xs dark:bg-slate-900">
                <div className="flex items-center justify-between">
                  <span className="font-medium">
                    {formatLabel(inv.inventory_type)} · {new Date(inv.inspection_date).toLocaleDateString()} ·{" "}
                    {inv.items.length} item{inv.items.length === 1 ? "" : "s"}
                  </span>
                  <button onClick={() => onDelete(inv.id)} className="text-slate-400 hover:text-red-500">
                    Delete
                  </button>
                </div>
                {inv.notes && <div className="text-slate-500">{inv.notes}</div>}
              </li>
            ))}
          </ul>
        )}
      </div>

      {inventories && inventories.length >= 2 && (
        <div className="mt-3 border-t border-slate-200 pt-2 dark:border-slate-800">
          <div className="text-xs font-medium text-slate-500">Compare two inventories</div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <select
              value={beforeId}
              onChange={(e) => setBeforeId(e.target.value)}
              className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="">Before…</option>
              {inventories.map((inv) => (
                <option key={inv.id} value={inv.id}>
                  {formatLabel(inv.inventory_type)} · {new Date(inv.inspection_date).toLocaleDateString()}
                </option>
              ))}
            </select>
            <select
              value={afterId}
              onChange={(e) => setAfterId(e.target.value)}
              className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="">After…</option>
              {inventories.map((inv) => (
                <option key={inv.id} value={inv.id}>
                  {formatLabel(inv.inventory_type)} · {new Date(inv.inspection_date).toLocaleDateString()}
                </option>
              ))}
            </select>
            <button
              onClick={onCompare}
              disabled={!beforeId || !afterId || comparing}
              className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium hover:border-brand-500 disabled:opacity-50 dark:border-slate-700"
            >
              {comparing ? "Comparing…" : "Compare"}
            </button>
          </div>

          {comparison && (
            <div className="mt-2 overflow-x-auto">
              <div className="text-xs text-slate-500">
                {comparison.added_count} added · {comparison.removed_count} removed ·{" "}
                {comparison.changed_count} changed · {comparison.unchanged_count} unchanged
              </div>
              <table className="mt-1 w-full text-left text-xs">
                <thead>
                  <tr className="text-slate-500">
                    <th className="pr-3 py-1">Room</th>
                    <th className="pr-3 py-1">Item</th>
                    <th className="pr-3 py-1">Status</th>
                    <th className="pr-3 py-1">Before</th>
                    <th className="pr-3 py-1">After</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.items.map((d, i) => (
                    <tr key={i} className="border-t border-slate-200 dark:border-slate-800">
                      <td className="pr-3 py-1">{d.room}</td>
                      <td className="pr-3 py-1">{d.item_name}</td>
                      <td
                        className={
                          "pr-3 py-1 " +
                          (d.status === "changed"
                            ? "text-amber-600"
                            : d.status === "removed"
                              ? "text-red-600"
                              : d.status === "added"
                                ? "text-green-600"
                                : "text-slate-500")
                        }
                      >
                        {d.status}
                      </td>
                      <td className="pr-3 py-1">{d.condition_before ?? "—"}</td>
                      <td className="pr-3 py-1">{d.condition_after ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const DOCUMENT_TYPES: DocumentType[] = [
  "tenancy_agreement",
  "gas_safety_certificate",
  "eicr",
  "epc",
  "deposit_protection_certificate",
  "right_to_rent_check",
  "insurance_certificate",
  "inventory_report",
  "other",
];

function formatDocumentType(type: DocumentType): string {
  return type.replace(/_/g, " ");
}

function DocumentsPanel({ propertyId, tenancies, token }: { propertyId: string; tenancies: Tenancy[]; token: string }) {
  const [documents, setDocuments] = useState<PropertyDocument[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [documentType, setDocumentType] = useState<DocumentType>("other");
  const [tenancyId, setTenancyId] = useState("");
  const [expiryDate, setExpiryDate] = useState("");
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDocuments(await api.listDocuments(token, propertyId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load documents.");
      setDocuments([]);
    }
  }, [token, propertyId]);

  useEffect(() => {
    load();
  }, [load]);

  const onUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !title) return;
    setUploading(true);
    setError(null);
    try {
      await api.uploadDocument(token, propertyId, file, {
        title,
        document_type: documentType,
        tenancy_id: tenancyId || undefined,
        expiry_date: expiryDate || undefined,
      });
      setFile(null);
      setTitle("");
      setExpiryDate("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not upload document.");
    } finally {
      setUploading(false);
    }
  };

  const onDownload = async (doc: PropertyDocument) => {
    try {
      const blob = await api.downloadDocument(token, doc.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = doc.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not download document.");
    }
  };

  const onDelete = async (documentId: string) => {
    setDeletingId(documentId);
    setError(null);
    try {
      await api.deleteDocument(token, documentId);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete document.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="mt-10">
      <h2 className="font-medium">Documents</h2>
      <p className="mt-1 text-xs text-slate-500">
        Certificates, agreements and photos for this property. PDF, JPG/PNG or DOCX, no payment/compliance
        checking happens here yet.
      </p>

      <form onSubmit={onUpload} className="mt-3 space-y-2 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1">
            <label className="block text-xs font-medium">Title</label>
            <input
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Gas safety certificate 2026"
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
            />
          </div>
          <div>
            <label className="block text-xs font-medium">Type</label>
            <select
              value={documentType}
              onChange={(e) => setDocumentType(e.target.value as DocumentType)}
              className="mt-1 rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              {DOCUMENT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {formatDocumentType(t)}
                </option>
              ))}
            </select>
          </div>
          {tenancies.length > 0 && (
            <div>
              <label className="block text-xs font-medium">Tenancy</label>
              <select
                value={tenancyId}
                onChange={(e) => setTenancyId(e.target.value)}
                className="mt-1 rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
              >
                <option value="">Property-level</option>
                {tenancies.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.tenant_name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label className="block text-xs font-medium">Expiry (optional)</label>
            <input
              type="date"
              value={expiryDate}
              onChange={(e) => setExpiryDate(e.target.value)}
              className="mt-1 rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
            />
          </div>
          <div>
            <label className="block text-xs font-medium">File</label>
            <input
              required
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.docx"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="mt-1 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={uploading}
            className="rounded-md bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
      </form>

      <div className="mt-3">
        {documents === null ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : documents.length === 0 ? (
          <p className="text-sm text-slate-500">No documents yet.</p>
        ) : (
          <ul className="space-y-1">
            {documents.map((doc) => (
              <li
                key={doc.id}
                className="flex items-center justify-between gap-2 rounded-md bg-slate-50 px-3 py-2 text-sm dark:bg-slate-900"
              >
                <div>
                  <div className="font-medium">{doc.title}</div>
                  <div className="text-xs text-slate-500">
                    {formatDocumentType(doc.document_type)}
                    {doc.tenancy_id && " · tenancy-specific"}
                    {doc.expiry_date && ` · expires ${new Date(doc.expiry_date).toLocaleDateString()}`}
                  </div>
                </div>
                <div className="flex flex-shrink-0 gap-3 text-xs">
                  <button onClick={() => onDownload(doc)} className="text-brand-500 hover:underline">
                    Download
                  </button>
                  <button
                    onClick={() => onDelete(doc.id)}
                    disabled={deletingId === doc.id}
                    className="text-slate-400 hover:text-red-500 disabled:opacity-50"
                  >
                    {deletingId === doc.id ? "Removing…" : "Delete"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

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

      <InventoriesPanel tenancyId={tenancy.id} token={token} />
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

        <DocumentsPanel propertyId={propertyId} tenancies={tenancies ?? []} token={token!} />
      </div>
    </main>
  );
}
