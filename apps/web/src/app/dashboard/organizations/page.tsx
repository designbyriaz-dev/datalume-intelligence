"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import {
  api,
  type AuditLogEntry,
  type Membership,
  type MembershipCreated,
  type Organization,
  type PendingInvite,
  ApiError,
  MEMBERSHIP_ROLES,
} from "@/lib/api";

function isPendingInvite(result: MembershipCreated | PendingInvite): result is PendingInvite {
  return "status" in result;
}

function OrganizationPanel({ org, token }: { org: Organization; token: string }) {
  const [open, setOpen] = useState(false);
  const [members, setMembers] = useState<Membership[] | null>(null);
  const [auditLog, setAuditLog] = useState<AuditLogEntry[] | null>(null);
  const [auditLogError, setAuditLogError] = useState<string | null>(null);
  const [showAuditLog, setShowAuditLog] = useState(false);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<string>("analyst");
  const [inviting, setInviting] = useState(false);
  const [inviteResult, setInviteResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [memberBusyId, setMemberBusyId] = useState<string | null>(null);

  const loadMembers = useCallback(async () => {
    try {
      setMembers(await api.listOrganizationMembers(token, org.id));
    } catch {
      setMembers([]);
    }
  }, [token, org.id]);

  useEffect(() => {
    if (open) loadMembers();
  }, [open, loadMembers]);

  const onInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setInviting(true);
    setError(null);
    setInviteResult(null);
    try {
      const result = await api.inviteOrganizationMember(token, org.id, inviteEmail, inviteRole);
      setInviteResult(
        isPendingInvite(result)
          ? `Invite emailed to ${result.email} — they'll join as ${result.role} once they accept.`
          : `${inviteEmail} added as ${result.role}.`
      );
      setInviteEmail("");
      await loadMembers();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send invite.");
    } finally {
      setInviting(false);
    }
  };

  const onChangeRole = async (membershipId: string, role: string) => {
    setMemberBusyId(membershipId);
    setError(null);
    try {
      await api.updateMembershipRole(token, org.id, membershipId, role);
      await loadMembers();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change that member's role.");
    } finally {
      setMemberBusyId(null);
    }
  };

  const onRemoveMember = async (membershipId: string) => {
    setMemberBusyId(membershipId);
    setError(null);
    try {
      await api.removeOrganizationMember(token, org.id, membershipId);
      await loadMembers();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove that member.");
    } finally {
      setMemberBusyId(null);
    }
  };

  const onShowAuditLog = async () => {
    setShowAuditLog((v) => !v);
    if (auditLog !== null) return;
    try {
      setAuditLog(await api.getOrganizationAuditLog(token, org.id));
    } catch (err) {
      setAuditLogError(
        err instanceof ApiError ? err.message : "Could not load the audit log."
      );
      setAuditLog([]);
    }
  };

  return (
    <div className="rounded-lg border border-slate-200 p-5 dark:border-slate-800">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="font-medium">{org.name}</span>
        <span className="text-xs text-slate-500">{open ? "hide" : "manage"}</span>
      </button>

      {open && (
        <div className="mt-4 space-y-4">
          <div>
            <h3 className="text-xs font-medium uppercase text-slate-500">Members</h3>
            {members === null ? (
              <p className="mt-1 text-sm text-slate-500">Loading…</p>
            ) : members.length === 0 ? (
              <p className="mt-1 text-sm text-slate-500">No members found.</p>
            ) : (
              <ul className="mt-1 divide-y divide-slate-200 dark:divide-slate-800">
                {members.map((m) => (
                  <li key={m.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                    <div>
                      <span className="font-medium">{m.user_full_name}</span>{" "}
                      <span className="text-xs text-slate-500">{m.user_email}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <select
                        value={m.role}
                        disabled={memberBusyId === m.id}
                        onChange={(e) => onChangeRole(m.id, e.target.value)}
                        className="rounded-md border border-slate-300 bg-transparent px-2 py-1 text-xs uppercase disabled:opacity-50 dark:border-slate-700"
                      >
                        {MEMBERSHIP_ROLES.map((role) => (
                          <option key={role} value={role}>
                            {role}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() => onRemoveMember(m.id)}
                        disabled={memberBusyId === m.id}
                        className="text-xs text-slate-400 hover:text-red-500 disabled:opacity-50"
                      >
                        Remove
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <form onSubmit={onInvite} className="flex flex-wrap items-end gap-2">
            <div className="flex-1">
              <label className="block text-xs font-medium text-slate-500">Invite by email</label>
              <input
                type="email"
                required
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="colleague@example.com"
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500">Role</label>
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="mt-1 rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
              >
                {MEMBERSHIP_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="submit"
              disabled={inviting}
              className="rounded-md bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {inviting ? "Inviting…" : "Invite"}
            </button>
          </form>
          {inviteResult && <p className="text-sm text-slate-600 dark:text-slate-400">{inviteResult}</p>}
          {error && <p className="text-sm text-red-600">{error}</p>}

          <div>
            <button type="button" onClick={onShowAuditLog} className="text-xs text-brand-500 hover:underline">
              {showAuditLog ? "Hide audit log" : "Show audit log"}
            </button>
            {showAuditLog &&
              (auditLogError ? (
                <p className="mt-2 text-xs text-slate-500">{auditLogError}</p>
              ) : auditLog === null ? (
                <p className="mt-2 text-xs text-slate-500">Loading…</p>
              ) : auditLog.length === 0 ? (
                <p className="mt-2 text-xs text-slate-500">No audit events yet.</p>
              ) : (
                <ul className="mt-2 space-y-1 text-xs text-slate-500">
                  {auditLog.map((e) => (
                    <li key={e.id}>
                      {new Date(e.created_at).toLocaleString()} — {e.event_type}
                    </li>
                  ))}
                </ul>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function OrganizationsPage() {
  const { token, user, loading } = useAuth();
  const router = useRouter();

  const [organizations, setOrganizations] = useState<Organization[] | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setOrganizations(await api.listOrganizations(token));
    } catch {
      setOrganizations([]);
    }
  }, [token]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  useEffect(() => {
    load();
  }, [load]);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api.createOrganization(token, name);
      setName("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create organization.");
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
      <div className="mx-auto max-w-2xl px-6 py-12">
        <Link href="/dashboard" className="text-sm text-brand-500 hover:underline">
          ← Dashboard
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">Organizations</h1>
        <p className="mt-1 text-sm text-slate-500">
          Share workspaces with a team. Creating an organization makes you its owner; invite colleagues
          by email and give each one a role. A plan/subscription is billed per organization, separate
          from your personal plan.
        </p>

        <form onSubmit={onCreate} className="mt-6 flex gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Acme Property Group"
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
          <button
            type="submit"
            disabled={creating}
            className="rounded-md bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {creating ? "Creating…" : "Create organization"}
          </button>
        </form>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

        <div className="mt-8 space-y-4">
          {organizations === null ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : organizations.length === 0 ? (
            <p className="text-sm text-slate-500">You're not a member of any organization yet.</p>
          ) : (
            organizations.map((org) => <OrganizationPanel key={org.id} org={org} token={token!} />)
          )}
        </div>
      </div>
    </main>
  );
}
